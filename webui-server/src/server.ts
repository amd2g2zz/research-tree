/** WebUI server (issue #632 spike, WebUI wave architecture baseline).

Node backend **embedding rt-core directly** (the engine is a library, not a
remote service). Wiring baseline pinned by #632:

- LLM judgments go through the **pi host only** — the server never calls a
  model; the research walk drives the engine exactly like #579 headless
  (the pi session driver plugs in at the #552 dispatch port, proven in the
  #606 pi-host e2e; CI uses the mock boundary per the #607 precedent).
- Config single source of truth: pi's config dir, read-only here
  (pi-config.ts) — no parallel model/API config exists.
- MCP (#553) stays the external programmatic exit, not this server's bus.

Surface:
- REST reads: /api/projects, /api/projects/:id/vitals, /api/config/pi
- WebSocket RPC: project.create / project.registerTask / chat.ingest /
  research.launch — engine events stream to the browser as JSON lines
  (same discipline as the headless emit stream).
*/

import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { join } from "node:path";

import { WebSocketServer, type WebSocket } from "ws";

import { LedgerStore } from "../../rt-core/src/store/ledger.js";
import { EngineCore } from "../../rt-core/src/store/engine.js";
import { VersionStore } from "../../rt-core/src/versions/store.js";
import { ProductStateMachine } from "../../rt-core/src/state/machine.js";
import { ProjectHomeModel, ProjectHomeError } from "../../rt-core/src/ux/project_home.js";
import { DialogueController } from "../../rt-core/src/dialogue/controller.js";
import { runHeadless, type HeadlessScript } from "../../rt-core/src/headless/runner.js";
import {
  parseDecomposition,
  saveDraftDecomposition,
  confirmDecomposition,
  checklistFor,
  type DecompositionElements,
} from "../../rt-core/src/decomposition/engine.js";
import { readPiConfig } from "./pi-config.js";

export interface WebUIOptions {
  /** server workspace — the ledger lives here */
  workspace: string;
  /** pi config dir override (tests); default ~/.pi/agent */
  piConfigDir?: string;
}

interface RpcMessage {
  id: number;
  method: string;
  params?: Record<string, unknown>;
}

const CHAT_KINDS = ["preference", "claim", "guess", "constraint", "branch"] as const;

export class WebUIServer {
  private readonly ledger: LedgerStore;
  private readonly versions: VersionStore;
  private readonly machine: ProductStateMachine;
  private readonly home: ProjectHomeModel;
  private readonly http = createServer((req, res) => this.rest(req, res));
  private readonly wss = new WebSocketServer({ noServer: true });
  private msgId = 0;

  constructor(private readonly options: WebUIOptions) {
    this.ledger = new LedgerStore(join(options.workspace, "ledger.sqlite"));
    this.ledger.initialize();
    this.versions = new VersionStore(this.ledger);
    this.machine = new ProductStateMachine(new EngineCore(this.ledger), this.versions);
    this.home = new ProjectHomeModel(this.ledger, this.versions);
    this.http.on("upgrade", (req, socket, head) => {
      if (req.url === "/ws") {
        this.wss.handleUpgrade(req, socket, head, (ws) => this.wss.emit("connection", ws, req));
      } else {
        socket.destroy();
      }
    });
    this.wss.on("connection", (ws) => {
      ws.on("message", (data) => this.rpc(ws, data));
    });
  }

  /** P1 sidebar tree: project → research lines (main/fork) → version nodes
   * (vN·hash·verdict, fork markers) + the draft row (未冻结·不可跟踪).
   * Assembled read-only from #571 ProjectHomeModel + #548 version store. */
  private tree(): Array<Record<string, unknown>> {
    return this.home.listProjects().map((project) => ({
      ...project,
      vitals: this.home.vitals(project.project_id),
      lines: this.home.listLines(project.project_id).map((line) => {
        const versions = this.versions
          .listVersions(line.task_id)
          .slice()
          .sort((a, b) => b.v - a.v)
          .map((v) => ({
          v: v.v,
          verdict: v.verdict,
          commit_hash: v.commit_hash,
          summary: v.summary,
          forked: this.versions.forkChildren(line.task_id, v.v).length > 0,
        }));
        const draft = this.versions.draftOf(line.task_id);
        return {
          task_id: line.task_id,
          role: line.role,
          latest: line.latest,
          versions,
          draft: draft !== null ? { base_v: draft.base_v, updated_at: draft.updated_at } : null,
        };
      }),
    }));
  }

  listen(port = 0): Promise<number> {
    return new Promise((resolve) => {
      this.http.listen(port, "127.0.0.1", () => resolve((this.http.address() as { port: number }).port));
    });
  }

  close(): Promise<void> {
    return new Promise((resolve) => {
      for (const client of this.wss.clients) {
        client.close();
      }
      this.http.close(() => resolve());
    });
  }

  private rest(req: IncomingMessage, res: ServerResponse): void {
    const reply = (code: number, body: unknown): void => {
      res.writeHead(code, { "content-type": "application/json" });
      res.end(JSON.stringify(body));
    };
    if (req.url === "/api/config/pi") {
      reply(200, readPiConfig(this.options.piConfigDir));
      return;
    }
    if (req.url === "/api/projects") {
      reply(200, { projects: this.home.listProjects() });
      return;
    }
    if (req.url === "/api/tree") {
      reply(200, { projects: this.tree() });
      return;
    }
    const vitals = /^\/api\/projects\/([^/]+)\/vitals$/.exec(req.url ?? "");
    if (vitals !== null) {
      try {
        reply(200, this.home.vitals(decodeURIComponent(vitals[1]!)));
      } catch (error) {
        reply(404, { error: String(error instanceof Error ? error.message : error) });
      }
      return;
    }
    reply(404, { error: "not found" });
  }

  private rpc(ws: WebSocket, data: unknown): void {
    let msg: RpcMessage;
    try {
      msg = JSON.parse(String(data)) as RpcMessage;
    } catch {
      return;
    }
    Promise.resolve()
      .then(() => this.dispatch(msg.method, msg.params ?? {}))
      .then(
        (result) => ws.send(JSON.stringify({ id: msg.id, ok: true, result })),
        (error) =>
          ws.send(JSON.stringify({ id: msg.id, ok: false, error: String(error instanceof Error ? error.message : error) })),
      );
  }

  private async dispatch(method: string, params: Record<string, unknown>): Promise<unknown> {
    switch (method) {
      case "project.create":
        return this.home.createProject(String(params.project_id), {
          name: String(params.name ?? ""),
          description: String(params.description ?? ""),
          attachments: Array.isArray(params.attachments) ? (params.attachments as never) : [],
        });
      case "project.registerTask":
        this.home.registerTask(String(params.project_id), String(params.task_id), params.role === "fork" ? "fork" : "main");
        return { registered: true };
      case "project.archive":
        this.home.archiveProject(String(params.project_id));
        return { archived: true };
      case "project.delete":
        this.home.deleteProject(String(params.project_id));
        return { deleted: true };
      case "chat.ingest": {
        const kind = String(params.kind);
        if (!(CHAT_KINDS as readonly string[]).includes(kind)) {
          throw new ProjectHomeError(`utterance kind must be one of ${CHAT_KINDS.join("|")}`);
        }
        const text = String(params.text ?? "");
        const taskId = String(params.task_id);
        const controller = new DialogueController(this.ledger, taskId);
        const receipt = controller.ingest({
          kind: kind as never,
          text,
          source: { kind: "chat-message", ref: `msg:${++this.msgId}`, quote: text },
          hardness: params.hardness === "guessed" ? "guessed" : undefined,
        });
        // P2 hub transcript: user message + rt routing receipt persisted (migration v8)
        this.appendChat(taskId, "user", kind, text, null);
        this.appendChat(taskId, "rt", "receipt", routingLabel(receipt as never), receipt as never);
        return { receipt, routed_count: this.routedCount(taskId) };
      }
      case "chat.history":
        return {
          messages: this.ledger.connection
            .prepare("SELECT seq, role, kind, text, receipt_json, created_at FROM chat_messages WHERE task_id = ? ORDER BY seq")
            .all(String(params.task_id)) as Array<Record<string, unknown>>,
        };
      case "task.status": {
        // 任务状态卡 data: phase → 下一步动作唯一化 (运行中→查看研究 / 收敛→报告+冻结 / 提交后消失)
        const taskId = String(params.task_id);
        const latest = this.versions.listVersions(taskId).slice().sort((a, b) => b.v - a.v)[0] ?? null;
        return {
          phase: this.machine.phaseOf(taskId) ?? "chat",
          latest: latest !== null ? { v: latest.v, verdict: latest.verdict, commit_hash: latest.commit_hash } : null,
          routed_count: this.routedCount(taskId),
        };
      }
      case "decompose.prepare": {
        // P3: the extraction arrives from the LLM side (pi session); parse +
        // save as a DRAFT — confirmation is a separate explicit user action.
        const taskId = String(params.task_id);
        const decompositionId = String(params.decomposition_id);
        const parsed = parseDecomposition(params.extraction as DecompositionElements);
        const notes = { refusals: typeof params.refusals_note === "string" ? params.refusals_note : undefined };
        const row = saveDraftDecomposition(this.ledger, taskId, parsed, notes, { decomposition_id: decompositionId });
        return { checklist: row.checklist_state, elements: row.elements, dropped: parsed.dropped };
      }
      case "decompose.get": {
        const row = this.ledger.getDecomposition(String(params.task_id), String(params.decomposition_id));
        if (row === null) {
          throw new ProjectHomeError(`unknown decomposition: ${String(params.decomposition_id)}`);
        }
        return row;
      }
      case "decompose.removeElement": {
        // 编辑权在确认前: removing an element re-drafts; a confirmed set is
        // frozen — post-confirmation change is a major pivot (re-sign).
        const taskId = String(params.task_id);
        const decompositionId = String(params.decomposition_id);
        const row = this.ledger.getDecomposition(taskId, decompositionId);
        if (row === null) {
          throw new ProjectHomeError(`unknown decomposition: ${decompositionId}`);
        }
        if (row.status === "confirmed") {
          throw new ProjectHomeError("decomposition is confirmed; post-confirmation change is a major pivot (re-sign)");
        }
        const elementClass = String(params.element_class);
        const index = Number(params.index);
        const elements = row.elements as DecompositionElements;
        const list = (elements as Record<string, unknown>)[elementClass];
        if (!Array.isArray(list) || index < 0 || index >= list.length) {
          throw new ProjectHomeError(`no removable element at ${elementClass}[${index}]`);
        }
        list.splice(index, 1);
        const parsed = parseDecomposition(elements);
        const saved = saveDraftDecomposition(this.ledger, taskId, parsed, (row.checklist_state as { notes?: { refusals?: string } }).notes ?? {}, {
          decomposition_id: decompositionId,
        });
        return { checklist: saved.checklist_state, elements: saved.elements };
      }
      case "decompose.confirm": {
        // 确认 → the element set freezes as the research constitution (v0)
        const taskId = String(params.task_id);
        const decompositionId = String(params.decomposition_id);
        const row = this.ledger.getDecomposition(taskId, decompositionId);
        if (row === null) {
          throw new ProjectHomeError(`unknown decomposition: ${decompositionId}`);
        }
        const parsed = parseDecomposition(row.elements as DecompositionElements);
        const notes = (row.checklist_state as { notes?: { refusals?: string } }).notes ?? {};
        const confirmed = confirmDecomposition(this.ledger, taskId, parsed, notes, { decomposition_id: decompositionId });
        this.machine.attachDecomposition(taskId, decompositionId);
        return { confirmed: true, checklist: confirmed.checklist_state };
      }
      case "decompose.checklist": {
        const taskId = String(params.task_id);
        const decompositionId = String(params.decomposition_id);
        const row = this.ledger.getDecomposition(taskId, decompositionId);
        if (row === null) {
          throw new ProjectHomeError(`unknown decomposition: ${decompositionId}`);
        }
        const parsed = parseDecomposition(row.elements as DecompositionElements);
        return checklistFor(parsed, (row.checklist_state as { notes?: { refusals?: string } }).notes ?? {});
      }
      case "research.launch": {
        const script: HeadlessScript = {
          task_id: String(params.task_id),
          pre_signed: (params.pre_signed ?? {}) as HeadlessScript["pre_signed"],
          steps: Array.isArray(params.steps) ? (params.steps as HeadlessScript["steps"]) : [],
        };
        const lines: Array<Record<string, unknown>> = [];
        const result = await runHeadless({
          ledger: this.ledger,
          machine: this.machine,
          versions: this.versions,
          script,
          emit: (line) => {
            lines.push(line);
            for (const client of this.wss.clients) {
              client.send(JSON.stringify({ event: "engine", line }));
            }
          },
        });
        return { ...result, events: lines.length };
      }
      default:
        throw new ProjectHomeError(`unknown rpc method: ${method}`);
    }
  }

  private appendChat(taskId: string, role: "user" | "rt" | "system", kind: string, text: string, receipt: unknown): void {
    const seq = (
      this.ledger.connection.prepare("SELECT COALESCE(MAX(seq), 0) + 1 AS next FROM chat_messages WHERE task_id = ?").get(taskId) as {
        next: number;
      }
    ).next;
    this.ledger.connection
      .prepare("INSERT INTO chat_messages (task_id, seq, role, kind, text, receipt_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)")
      .run(taskId, seq, role, kind, text, receipt !== null ? JSON.stringify(receipt) : null, new Date().toISOString());
  }

  private routedCount(taskId: string): number {
    return (
      this.ledger.connection.prepare("SELECT COUNT(*) AS n FROM chat_messages WHERE task_id = ? AND role = 'rt'").get(taskId) as { n: number }
    ).n;
  }
}

const ROUTE_LABELS: Record<string, string> = {
  slot: "→ 偏好槽位（权威域，遵循到底）",
  "claim-ledger": "→ 主张账本（检验：不信不驳）",
  "hypothesis-ledger": "→ 假设账本（受理受审：与替代方案同台评审）",
  "parking-lot": "→ 停车场（收纳不惩罚，不进关键路径）",
  constraint: "→ 约束槽位（溯源问询）",
};

function routingLabel(receipt: { routed: string }): string {
  return ROUTE_LABELS[receipt.routed] ?? `→ ${receipt.routed}`;
}
