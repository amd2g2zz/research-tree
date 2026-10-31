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
      case "chat.ingest": {
        const kind = String(params.kind);
        if (!(CHAT_KINDS as readonly string[]).includes(kind)) {
          throw new ProjectHomeError(`utterance kind must be one of ${CHAT_KINDS.join("|")}`);
        }
        const text = String(params.text ?? "");
        const taskId = String(params.task_id);
        const controller = new DialogueController(this.ledger, taskId);
        return controller.ingest({
          kind: kind as never,
          text,
          source: { kind: "chat-message", ref: `msg:${++this.msgId}`, quote: text },
          hardness: params.hardness === "guessed" ? "guessed" : undefined,
        });
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
}
