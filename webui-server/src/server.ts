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
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

import { WebSocketServer, type WebSocket } from "ws";

import { LedgerStore } from "../../rt-core/src/store/ledger.js";
import { EngineCore } from "../../rt-core/src/store/engine.js";
import { VersionStore } from "../../rt-core/src/versions/store.js";
import { ProductStateMachine } from "../../rt-core/src/state/machine.js";
import { ProjectHomeModel, ProjectHomeError } from "../../rt-core/src/ux/project_home.js";
import { BackgroundResearchRunner } from "./research_worker.js";
import { DialogueController } from "../../rt-core/src/dialogue/controller.js";
import { runHeadless, type HeadlessScript } from "../../rt-core/src/headless/runner.js";
import { CanvasProjection } from "../../rt-core/src/canvas/projection.js";
import { TimelineScrubber } from "../../rt-core/src/canvas/scrubber.js";
import { LineageDrillDown } from "../../rt-core/src/canvas/lineage.js";
import { VersionTimeline, VersionTimelineError } from "../../rt-core/src/versions/timeline.js";
import { FourStateArchive } from "../../rt-core/src/versions/archive.js";
import { ParallelDagScheduler, type ParallelStage } from "../../rt-core/src/scheduler/parallel_dag.js";
import {
  parseDecomposition,
  saveDraftDecomposition,
  confirmDecomposition,
  checklistFor,
  type DecompositionElements,
} from "../../rt-core/src/decomposition/engine.js";
import type { MindNode } from "./mindmap.js";
import { runPi } from "./pi-run.js";
import { readPiConfig, writeProviderKey, writeDefaultModel, ConfigWriteError } from "./pi-config.js";
import { mindmapPrompt, parseMindmap, mechanicalPlan as planFromTree, editNode, type MindTree } from "./mindmap.js";
import { extensionStatuses, ensurePiExtensions, DEFAULT_PI_EXTENSIONS } from "./pi-extensions.js";
import { pickClassifier } from "./classify.js";
import { extractionPrompt, parseExtraction, mechanicalPlan, type TranscriptMessage } from "./real-flow.js";
import { buildTurnPrompt, parseTurnOutput, runRecon, reconToText, type TurnOutput } from "./chat-turn.js";
import { AnysearchProvider } from "../../rt-core/src/providers/anysearch.js";
import { SkillSearchProvider } from "./skill_search.js";
import type { DataSourceProvider } from "../../rt-core/src/providers/types.js";

export interface WebUIOptions {
  /** server workspace — the ledger lives here */
  workspace: string;
  /** pi config dir override (tests); default ~/.pi/agent */
  piConfigDir?: string;
  /** injectable pi headless runner (contract tests; CI never spawns pi);
   * may be async — the server awaits it (issue #670) */
  piRunner?: (command: string, prompt: string) => string | Promise<string>;
  /** injectable data-source provider (recon; tests) — default anysearch */
  provider?: DataSourceProvider;
  /** pi headless call timeout (chat.turn/extraction/classification); default 300s/120s */
  piTimeoutMs?: number;
}

interface RpcMessage {
  id: number;
  method: string;
  params?: Record<string, unknown>;
}

const CHAT_KINDS = ["preference", "claim", "guess", "constraint", "branch"] as const;
const VERDICTS = ["GO", "NO-GO", "PARK", "REFRAMED"] as const;

/** Locate the pi binary: RT_PI_CMD env → PATH → the known local scratch
 * install. Honest failure: nothing is faked when pi is unavailable. */
function resolvePiCommand(): string | null {
  const fromEnv = process.env.RT_PI_CMD;
  if (fromEnv !== undefined && fromEnv !== "" && existsSync(fromEnv)) {
    return fromEnv;
  }
  const pathProbe = spawnSync("which", ["pi"], { encoding: "utf8" });
  if (pathProbe.status === 0 && pathProbe.stdout.trim() !== "" && existsSync(pathProbe.stdout.trim())) {
    return pathProbe.stdout.trim();
  }
  // persistent local install (~/.pi/agent/npm — same prefix as the default
  // extensions, #664); the /private/tmp scratch install evaporates on cleanup
  const local = join(homedir(), ".pi", "agent", "npm", "node_modules", ".bin", "pi");
  if (existsSync(local)) {
    return local;
  }
  const scratch = "/private/tmp/pi-host/node_modules/.bin/pi";
  if (existsSync(scratch)) {
    return scratch;
  }
  return null;
}

export class WebUIServer {
  private readonly ledger: LedgerStore;
  private readonly versions: VersionStore;
  private readonly machine: ProductStateMachine;
  private readonly home: ProjectHomeModel;
  private readonly researchRunner: BackgroundResearchRunner;
  private readonly canvas: Promise<CanvasProjection>;
  private readonly timeline: VersionTimeline;
  private readonly archive: FourStateArchive;
  private _scrubber: TimelineScrubber | null = null;
  private readonly http = createServer((req, res) => void this.rest(req, res));
  private readonly wss = new WebSocketServer({ noServer: true });
  private msgId = 0;

  constructor(private readonly options: WebUIOptions) {
    this.ledger = new LedgerStore(join(options.workspace, "ledger.sqlite"));
    this.ledger.initialize();
    this.versions = new VersionStore(this.ledger);
    this.machine = new ProductStateMachine(new EngineCore(this.ledger), this.versions);
    // 重启适配（issue #690 e2e）：phase 图在进程内存里，重启后必须从事件日志
    // 认领既有任务的阶段，否则 task.status / research.freeze 全部回落 unknown
    this.machine.hydrate(this.ledger.graphEvents() as Array<Record<string, unknown>>);
    this.home = new ProjectHomeModel(this.ledger, this.versions);
    this.canvas = CanvasProjection.fromLedger(this.ledger);
    this.timeline = new VersionTimeline(this.ledger, this.versions, this.machine);
    this.archive = new FourStateArchive(this.ledger, this.versions, this.machine);
    // 后台调研执行器（#709）：多任务并发、真实检索→综合→阶段流转；
    // 进度落账——前端离开不影响，重开即见最新状态
    this.researchRunner = new BackgroundResearchRunner({
      ledger: this.ledger,
      versions: this.versions,
      provider: () => this.options.provider ?? this.defaultProvider(),
      piCommand: () => this.resolvePiCommand(),
      piRunner: this.options.piRunner,
      piTimeoutMs: this.options.piTimeoutMs,
      broadcast: (line) => {
        for (const client of this.wss.clients) {
          client.send(JSON.stringify({ event: "engine", line }));
        }
      },
    });
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
          title: line.title ?? null,
          latest: line.latest,
          versions,
          draft: draft !== null ? { base_v: draft.base_v, updated_at: draft.updated_at } : null,
        };
      }),
    }));
  }

  listen(port = 0): Promise<number> {
    this.researchRunner.start(5000);
    return new Promise((resolve) => {
      this.http.listen(port, "127.0.0.1", () => resolve((this.http.address() as { port: number }).port));
    });
  }

  close(): Promise<void> {
    this.researchRunner.stop();
    return new Promise((resolve) => {
      for (const client of this.wss.clients) {
        client.close();
      }
      this.http.close(() => resolve());
    });
  }

  private async rest(req: IncomingMessage, res: ServerResponse): Promise<void> {
    const reply = (code: number, body: unknown): void => {
      res.writeHead(code, { "content-type": "application/json" });
      res.end(JSON.stringify(body));
    };
    if (req.url === "/api/config/pi") {
      const summary = readPiConfig(this.options.piConfigDir) as unknown as Record<string, unknown>;
      summary.default_extensions = extensionStatuses(this.extensionsDir());
      reply(200, summary);
      return;
    }
    if (req.url === "/api/projects") {
      reply(200, { projects: this.home.listProjects() });
      return;
    }
    if (req.url === "/api/archive") {
      reply(200, { entries: this.archive.list(), graveyard: this.archive.graveyard().map((e) => e.task_id) });
      return;
    }
    const versionsRoute = /^\/api\/versions\/([^/]+)(\/snapshot\/(\d+))?$/.exec(req.url ?? "");
    if (versionsRoute !== null) {
      const taskId = decodeURIComponent(versionsRoute[1]!);
      try {
        if (versionsRoute[3] !== undefined) {
          // 只读快照视图: frozen banner + full report projection
          reply(200, this.timeline.snapshotView(taskId, Number(versionsRoute[3])));
        } else {
          reply(200, this.timeline.timeline(taskId));
        }
      } catch (error) {
        reply(error instanceof VersionTimelineError ? 404 : 500, { error: String(error instanceof Error ? error.message : error) });
      }
      return;
    }
    if (req.url === "/api/tree") {
      reply(200, { projects: this.tree() });
      return;
    }
    // 全文搜索（#704）：项目名/描述/任务 id 跨全库匹配（不受侧栏惰性加载
    // 限制——搜索时必须能看到还没滚到的项目）
    const search = /^\/api\/projects\/search\?q=(.+)$/.exec(req.url ?? "");
    if (search !== null) {
      const q = decodeURIComponent(search[1]!).toLowerCase();
      const hits = this.tree().filter((p) => {
        const name = String(p.name ?? "").toLowerCase();
        const desc = String(p.description ?? "").toLowerCase();
        const lines = (p.lines as Array<{ task_id: string; title: string | null }>).map(
          (l) => `${l.task_id} ${l.title ?? ""}`.toLowerCase(),
        );
        return name.includes(q) || desc.includes(q) || lines.some((l) => l.includes(q));
      });
      reply(200, { projects: hits, query: q });
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
    const research = /^\/api\/research\/([^/]+)(\/beats|\/at\/(\d+)|\/lineage\/(\d+)\/([^/]+))?$/.exec(req.url ?? "");
    if (research !== null) {
      const taskId = decodeURIComponent(research[1]!);
      try {
        if (research[2] === "/beats") {
          reply(200, { beats: this.scrubber().beats() });
        } else if (research[3] !== undefined) {
          reply(200, await this.atBeat(taskId, Number(research[3])));
        } else if (research[4] !== undefined && research[5] !== undefined) {
          const lineage = this.lineage().resolve(taskId, Number(research[4]), decodeURIComponent(research[5]));
          reply(200, lineage ?? { error: "no lineage (no fake lineage)" });
        } else {
          reply(200, await this.researchView(taskId));
        }
      } catch (error) {
        reply(500, { error: String(error instanceof Error ? error.message : error) });
      }
      return;
    }
    reply(404, { error: "not found" });
  }

  /** P4 three-layer view: ❓研究问题 → 🧵主线任务 → 调研 DAG (stage containers
   * × claim rows). Assembled from the #559 canvas projection + the stage table. */
  private async researchView(taskId: string): Promise<Record<string, unknown>> {
    const canvas = await (await this.canvas).render(taskId);
    // the claims surface is the live posterior authority (dual-write: the
    // engine updates surfaces + events; surface wins for display state)
    const claims: Record<string, unknown> = { ...canvas.claims };
    for (const claim of this.ledger.listClaims(taskId)) {
      claims[String(claim.claim_id)] = {
        text: String(claim.text ?? ""),
        posterior: Number(claim.posterior ?? 0),
        verify_tier: String(claim.verify_tier ?? ""),
        weight: String(claim.weight ?? "important"),
        state: Number(claim.posterior ?? 0) >= 0.9 ? "decided" : "undecided",
      };
    }
    // stage_id = `${taskId}/${stage.id}`（research.start / mindmap.confirm）—
    // 只取本任务的 stage，别的任务的不得泄漏进本任务画布（issue #690 e2e）
    const stages = (this.ledger.connection
      .prepare("SELECT stage_id, title, status, claim_ids, depends_on, assigned_worker_class, outputs FROM parallel_stages")
      .all() as Array<Record<string, unknown>>).filter((s) => String(s.stage_id).startsWith(`${taskId}/`));
    return {
      question: canvas.question,
      claims,
      transitions: canvas.transitions,
      providers: canvas.providers,
      stages: stages.map((s) => {
        // 产出解析（#709）：outputs[0] = {findings, sources, completed_at}
        let findings: string | null = null;
        let sources: Array<{ title: string; url?: string; snippet?: string }> = [];
        try {
          const raw = JSON.parse(String(s.outputs ?? "[]")) as string[];
          if (raw.length > 0) {
            const artifact = JSON.parse(raw[0] ?? "{}") as {
              findings?: string;
              sources?: Array<{ title: string; url?: string; snippet?: string }>;
            };
            findings = artifact.findings ?? null;
            sources = artifact.sources ?? [];
          }
        } catch {
          /* outputs 未就绪或格式异常——画布仍显示状态 */
        }
        return {
          ...s,
          claim_ids: JSON.parse(String(s.claim_ids)) as string[],
          depends_on: JSON.parse(String(s.depends_on)) as string[],
          findings,
          sources,
        };
      }),
    };
  }

  /** Latest persisted phase for a task from the hash-chained event log.
   * The state machine's phase map is per-process — after a server restart
   * the ledger's task.transition trail is the only source of truth
   * (issue #690 e2e: restart regressed every task to "chat"). */
  private persistedPhase(taskId: string): string {
    const row = this.ledger.connection
      .prepare(
        "SELECT json_extract(CAST(payload_json AS TEXT), '$.to') AS to_phase FROM graph_events "
        + "WHERE event_type = 'task.transition' AND json_extract(CAST(payload_json AS TEXT), '$.task_id') = ? "
        + "ORDER BY seq DESC LIMIT 1",
      )
      .get(taskId) as { to_phase: string | null } | undefined;
    return row?.to_phase ?? "chat";
  }

  /** #572 scrubber: the canvas at any t is a pure projection of events ≤ t. */
  private atBeat(taskId: string, t: number): Promise<Record<string, unknown>> {
    void taskId;
    return this.scrubber().projectionAt(t).then((view) => ({
      console: view.console,
      claims: view.snapshot.Claim ?? {},
      stages: view.snapshot.Stage ?? {},
      beats: this.scrubber().beatCount(),
    }));
  }

  private piConfigDir(): string | undefined {
    return this.options.piConfigDir;
  }

  private extensionsDir(): string {
    return this.options.piConfigDir ?? join(homedir(), ".pi", "agent");
  }

  /** Default recon provider: the vendored anysearch skill CLI when present
   * (positional query, markdown), else the generic anysearch-on-PATH form. */
  private defaultProvider(): DataSourceProvider {
    if (this.options.provider !== undefined) {
      return this.options.provider;
    }
    const skill = new SkillSearchProvider();
    return skill.available() ? skill : new AnysearchProvider();
  }

  /** per-task DAG scheduler over the persisted stage table */
  private schedulers = new Map<string, ParallelDagScheduler>();
  private schedulerFor(taskId: string): ParallelDagScheduler {
    let scheduler = this.schedulers.get(taskId);
    if (scheduler === undefined) {
      scheduler = new ParallelDagScheduler(this.ledger, { maxConcurrency: 4 });
      this.schedulers.set(taskId, scheduler);
    }
    return scheduler;
  }

  /** pi binary resolution for keyed server-side calls (env → PATH → known
   * scratch install); null when unavailable — callers fail closed. */
  private resolvePiCommand(): string | null {
    return resolvePiCommand();
  }


  /** test access to the engine log (H7 telemetry assertions) */
  ledgerForTests(): LedgerStore {
    return this.ledger;
  }

  private scrubber(): TimelineScrubber {
    if (this._scrubber === null) {
      this._scrubber = new TimelineScrubber(this.ledger, join(this.options.workspace, "scrub-replay.db"));
    }
    return this._scrubber;
  }

  private lineage(): LineageDrillDown {
    return new LineageDrillDown(this.versions);
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
      case "project.rename":
        this.home.renameProject(String(params.project_id), String(params.name ?? ""));
        return { renamed: true };
      case "project.delete":
        this.home.deleteProject(String(params.project_id));
        return { deleted: true };
      case "task.rename":
        this.home.renameTask(String(params.task_id), String(params.title ?? ""));
        return { renamed: true };
      case "task.archive":
        this.home.archiveTask(String(params.task_id));
        return { archived: true };
      case "task.delete":
        this.home.deleteTask(String(params.task_id));
        return { deleted: true };
      case "version.continue":
        // 继续研究 (version+1): live draft resumes, never clobbers; H7 telemetry lands
        this.timeline.continueResearch(String(params.task_id));
        return { opened: true };
      case "version.fork": {
        // 从此分叉: new task inherits the snapshot (分叉即继承), lands in chat —
        // and is REGISTERED into the from-task's project as a fork line so the
        // sidebar tree actually shows the支线 (#655 e2e finding)
        const newTask = this.timeline.fork(String(params.task_id), Number(params.v), String(params.new_task_id));
        const projectId = this.home.projectIdForTask(String(params.task_id));
        if (projectId !== null) {
          this.home.registerTask(projectId, String(params.new_task_id), "fork");
        }
        return newTask;
      }
      case "chat.turn": {
        // #660: the conversational loop — the agent RESPONDS (never a wall):
        // transcript+state → pi session → {reply, questions[], recon?} →
        // recon executes for real through the DataSourceProvider port →
        // everything lands in chat_messages as data. Fail-closed when the
        // keyed session is not ready; the classification receipt (#651)
        // stays parallel and untouched.
        const text = String(params.text ?? "");
        const taskId = String(params.task_id);
        // 用户消息**最先**落账（#706 P0-3）：key 未配置/二进制缺失时也不能
        // 静默吞掉用户的第一个想法——落账 + 中文引导错误行，然后 fail-closed
        this.appendChat(taskId, "user", "pending", text, { classified_by: "pi-session" });
        const summary = readPiConfig(this.options.piConfigDir);
        if (!summary.keyed_session_ready) {
          const guide = "pi 密钥未配置：请点左侧「pi 已就绪」打开设置页，配置 provider key 后重新发送（这条消息已保留在对话里）。";
          this.appendChat(taskId, "system", "error", guide, { failed: true, reason: "keyed_session_not_ready" });
          throw new ProjectHomeError(guide);
        }
        const command = this.resolvePiCommand();
        if (command === null) {
          const guide = "pi 程序未找到（RT_PI_CMD）：请安装 pi 或设置环境变量后重试。";
          this.appendChat(taskId, "system", "error", guide, { failed: true, reason: "pi_binary_missing" });
          throw new ProjectHomeError(guide);
        }
        const userSeq = (
          this.ledger.connection
            .prepare("SELECT MAX(seq) AS seq FROM chat_messages WHERE task_id = ?")
            .get(taskId) as { seq: number }
        ).seq;

        const transcript = this.ledger.connection
          // seq <= userSeq：**包含本轮用户消息**——先落账是为了持久化，不是
          // 为了把输入藏起来（#711：模型看不到当前输入就会答"对话是空的"）
          .prepare("SELECT seq, role, kind, text, receipt_json, created_at FROM chat_messages WHERE task_id = ? AND seq <= ? ORDER BY seq")
          .all(taskId, userSeq) as TranscriptMessage[];
        const prompt = buildTurnPrompt(transcript);
        // async pi (issue #670) + streaming deltas (#679): 思维链先行
        for (const client of this.wss.clients) {
          client.send(JSON.stringify({ event: "turn-start", task_id: taskId }));
        }
        const runTurn = (): Promise<string> =>
          this.options.piRunner !== undefined
            ? Promise.resolve(this.options.piRunner(command, prompt))
            : runPi(command, prompt, this.options.piTimeoutMs ?? 300_000, ["-nt", "-ne", "--no-session", "--no-skills"], (delta) => {
                for (const client of this.wss.clients) {
                  client.send(JSON.stringify({ event: "turn-delta", delta }));
                }
              });
        // 一次重试：模型偶发非 JSON 输出时补一句硬约束再试；仍失败 → 诚实
        // 错误行落账（用户消息已先落账，不会只剩 think）并抛出（#704）
        let stdout: string;
        let turn: TurnOutput;
        try {
          stdout = await runTurn();
          turn = parseTurnOutput(stdout);
        } catch (firstError) {
          const retryPrompt = `${prompt}\n\n（注意：上一次输出不可用：${String(firstError instanceof Error ? firstError.message : firstError).slice(0, 120)}。只输出一个 JSON 对象，不要输出任何其它文字。）`;
          stdout =
            this.options.piRunner !== undefined
              ? await this.options.piRunner(command, retryPrompt)
              : await runPi(command, retryPrompt, this.options.piTimeoutMs ?? 300_000, ["-nt", "-ne", "--no-session", "--no-skills"]);
          try {
            turn = parseTurnOutput(stdout);
          } catch (secondError) {
            const reason = String(secondError instanceof Error ? secondError.message : secondError);
            this.appendChat(taskId, "system", "error", `本轮模型输出异常（${reason}）——你的消息已保留，请重新发送或稍后重试。`, { failed: true });
            throw secondError;
          }
        }

        let reconResults: Array<{ title: string; url?: string; snippet?: string }> | undefined;
        let reconError: string | undefined;
        if (turn.recon !== null && turn.recon !== undefined) {
          const query = turn.recon.query;
          const provider: DataSourceProvider = this.options.provider ?? this.defaultProvider();
          try {
            reconResults = await runRecon(provider, query);
          } catch (error) {
            // #666: recon is an ENHANCEMENT — its failure must not kill the
            // reply. Degrade honestly into the transcript, keep the turn.
            const reason = String(error instanceof Error ? error.message : error);
            this.appendChat(taskId, "rt", "recon", `前期侦查失败：${reason}（回应不受影响）`, { query, failed: true });
            this.ledger.appendGraphEvent("provider.action", {
              id: `recon-${Date.now()}`,
              provider: "anysearch",
              action: "search",
              target: query,
              outcome: "error",
            });
            reconResults = undefined;
            reconError = reason;
          }
        }
        if (reconResults !== undefined) {
          const query = turn.recon?.query ?? "";
          this.appendChat(taskId, "rt", "recon", reconToText(reconResults), { query });
          this.ledger.appendGraphEvent("provider.action", {
            id: `recon-${Date.now()}`,
            provider: "anysearch",
            action: "search",
            target: query,
            outcome: "ok",
            result_count: reconResults.length,
          });
        }
        // user message（先落账的 pending 行升格为判定 kind）+ reply + plan +
        // questions 依次落账（one pi call per turn, issue #674）
        this.ledger.connection
          .prepare("UPDATE chat_messages SET kind = ? WHERE task_id = ? AND seq = ?")
          .run(turn.kind, taskId, userSeq);
        this.appendChat(taskId, "rt", "reply", turn.reply, {
          questions: turn.questions,
          converged: turn.converged,
          flow: turn.flow,
          userConfirmed: turn.userConfirmed,
          blockers: turn.blockers,
          classified_by: "pi-session",
        });
        for (const q of turn.questions) {
          this.appendChat(taskId, "rt", "question", q, null);
        }
        return {
          kind: turn.kind,
          converged: turn.converged,
          flow: turn.flow,
          userConfirmed: turn.userConfirmed,
          blockers: turn.blockers,
          reply: turn.reply,
          questions: turn.questions,
          recon_results: reconResults ?? [],
          recon_error: reconError,
          classified_by: "pi-session",
        };
      }
      case "chat.ingest": {
        const text = String(params.text ?? "");
        const taskId = String(params.task_id);
        // #651: kind is now optional — an explicit user kind is always
        // respected; otherwise the ClassificationPort judges (LLM when the
        // keyed session is ready, disclosed heuristic fallback otherwise)
        let kind: string;
        let classifiedBy: string;
        if (typeof params.kind === "string" && (CHAT_KINDS as readonly string[]).includes(params.kind)) {
          kind = params.kind;
          classifiedBy = "user";
        } else {
          const summary = readPiConfig(this.options.piConfigDir);
          if (summary.keyed_session_ready) {
            const command = this.resolvePiCommand();
            if (command === null) {
              throw new ProjectHomeError(
                "keyed session is ready but the pi binary was not found (set RT_PI_CMD) — auto-classification fails closed",
              );
            }
            const classification = await pickClassifier({ ready: true }, { runner: this.options.piRunner, command, timeoutMs: 300_000 }).classify(text);
            kind = classification.kind;
            classifiedBy = classification.classified_by;
          } else {
            const fallback = await pickClassifier({ ready: false }).classify(text);
            kind = fallback.kind;
            classifiedBy = fallback.classified_by;
          }
        }
        const controller = new DialogueController(this.ledger, taskId);
        const receipt = controller.ingest({
          kind: kind as never,
          text,
          source: { kind: "chat-message", ref: `msg:${++this.msgId}`, quote: text },
          hardness: params.hardness === "guessed" ? "guessed" : undefined,
        });
        // P2 hub transcript: user message + rt routing receipt persisted (migration v8)
        this.appendChat(taskId, "user", kind, text, { classified_by: classifiedBy });
        this.appendChat(taskId, "rt", "receipt", routingLabel(receipt as never), { ...receipt, classified_by: classifiedBy });
        return { receipt: { ...receipt, classified_by: classifiedBy }, routed_count: this.routedCount(taskId) };
      }
      case "chat.history":
        return {
          messages: this.ledger.connection
            .prepare("SELECT seq, role, kind, text, receipt_json, created_at FROM chat_messages WHERE task_id = ? ORDER BY seq")
            .all(String(params.task_id)) as Array<Record<string, unknown>>,
        };
      case "config.setProviderKey": {
        // #638/#655: upsert INTO pi's own models.json provider registry —
        // the audit records the provider NAME only, never the key; the key
        // never echoes back over the wire
        const result = writeProviderKey(this.piConfigDir(), {
          provider: String(params.provider ?? ""),
          api_key: String(params.api_key ?? ""),
          name: typeof params.name === "string" ? params.name : undefined,
          baseUrl: typeof params.baseUrl === "string" ? params.baseUrl : undefined,
          api: typeof params.api === "string" ? params.api : undefined,
          model_id: typeof params.model_id === "string" ? params.model_id : undefined,
          model_name: typeof params.model_name === "string" ? params.model_name : undefined,
        });
        this.ledger.appendGraphEvent("provider.action", {
          id: `settings-auth-${Date.now()}`,
          provider: "settings",
          action: "report",
          target: `settings:auth:${result.provider}`,
          outcome: "ok",
        });
        return result;
      }
      case "config.installExtensions": {
        // #664: explicit settings-page action (never silent) — provisions the
        // default pi extensions and audits the outcome by name
        const result = ensurePiExtensions({ settingsDir: this.piConfigDir() ?? undefined, piCommand: this.resolvePiCommand() });
        this.ledger.appendGraphEvent("provider.action", {
          id: `settings-ext-${Date.now()}`,
          provider: "settings",
          action: "report",
          target: `settings:extensions:installed=[${result.installed.join(",")}] failed=${result.failed.length}`,
          outcome: result.failed.length === 0 ? "ok" : "error",
        });
        return { ...result, default: DEFAULT_PI_EXTENSIONS };
      }
      case "config.setDefaultModel": {
        const result = writeDefaultModel(this.piConfigDir(), String(params.model ?? ""));
        this.ledger.appendGraphEvent("provider.action", {
          id: `settings-model-${Date.now()}`,
          provider: "settings",
          action: "report",
          target: `settings:model:${result.default_model}`,
          outcome: "ok",
        });
        return result;
      }
      case "task.status": {
        // 任务状态卡 data: phase → 下一步动作唯一化 (运行中→查看研究 / 收敛→报告+冻结 / 提交后消失)
        const taskId = String(params.task_id);
        const latest = this.versions.listVersions(taskId).slice().sort((a, b) => b.v - a.v)[0] ?? null;
        return {
          phase: this.machine.phaseOf(taskId) ?? this.persistedPhase(taskId),
          latest: latest !== null ? { v: latest.v, verdict: latest.verdict, commit_hash: latest.commit_hash } : null,
          routed_count: this.routedCount(taskId),
        };
      }
      case "decompose.fromChat": {
        // #655 REAL extraction: the hub transcript → pi session → strict
        // six-element JSON → quotes mapped back to transcript messages →
        // 溯源律 drops anything unmapped (honest count). Fail-closed when
        // the keyed session is not ready — never a guessed extraction.
        const taskId = String(params.task_id);
        const decompositionId = String(params.decomposition_id ?? `dc-${taskId}`);
        const summary = readPiConfig(this.options.piConfigDir);
        if (!summary.keyed_session_ready) {
          throw new ProjectHomeError(
            "pi 密钥未配置：请先到设置页配置 provider key，再进行要素抽取（不做模拟抽取）。",
          );
        }
        const command = this.resolvePiCommand();
        if (command === null) {
          throw new ProjectHomeError("pi binary not found (set RT_PI_CMD) — cannot run the keyed extraction");
        }
        const transcript = this.ledger.connection
          .prepare("SELECT seq, role, kind, text, receipt_json, created_at FROM chat_messages WHERE task_id = ? ORDER BY seq")
          .all(taskId) as TranscriptMessage[];
        if (transcript.filter((m) => m.role === "user").length === 0) {
          throw new ProjectHomeError("no conversation to extract from — talk in the hub first");
        }
        const prompt = extractionPrompt(transcript);
        const stdout =
          this.options.piRunner !== undefined
            ? await this.options.piRunner(command, prompt)
            : await runPi(command, prompt, this.options.piTimeoutMs ?? 300_000, ["-nt", "-ne", "--no-session", "--no-skills"]);
        const extraction = parseExtraction(stdout, transcript);
        const parsed = parseDecomposition(extraction);
        const notes = { refusals: typeof params.refusals_note === "string" ? params.refusals_note : undefined };
        const row = saveDraftDecomposition(this.ledger, taskId, parsed, notes, { decomposition_id: decompositionId });
        this.ledger.appendGraphEvent("provider.action", {
          id: `fromchat-${Date.now()}`,
          provider: "pi-session",
          action: "report",
          target: `decompose:${taskId}/${decompositionId}`,
          outcome: "ok",
        });
        return { checklist: row.checklist_state, elements: row.elements, dropped: parsed.dropped };
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
      case "research.start": {
        // #655 REAL start: requires a CONFIRMED decomposition; builds the
        // mechanical plan (claims_preview → stages), registers the DAG, and
        // walks birth→…→research. No fixtures; the verdict comes later
        // through research.freeze (问句不是判决).
        const taskId = String(params.task_id);
        const decompositionId = String(params.decomposition_id ?? `dc-${taskId}`);
        const row = this.ledger.getDecomposition(taskId, decompositionId);
        if (row === null || row.status !== "confirmed") {
          throw new ProjectHomeError(`research.start requires a confirmed decomposition: ${decompositionId}`);
        }
        const elements = row.elements as Record<string, unknown>;
        const plan = mechanicalPlan(elements);
        const stages: ParallelStage[] = plan.stages.map((stage) => ({
          stage_id: `${taskId}/${stage.id}`,
          title: stage.title,
          status: "pending",
          claim_ids: stage.claim_ids,
          depends_on: stage.depends_on,
          assigned_worker_class: "retrieval",
          retries: 0,
          max_retries: 2,
          outputs: [],
        }));
        if (stages.length > 0) {
          this.schedulerFor(taskId).registerStages(stages);
        }
        const previewClaims = Array.isArray(elements.claims_preview)
          ? (elements.claims_preview as Array<Record<string, unknown>>)
          : [];
        // A7 rule 3 (版本+1 = 继承 + delta): a LIVE draft is the continued
        // working set — starting research must keep it, never reseed it with
        // the preview claims (that would clobber inheritance and make a v+1
        // freeze a duplicate of v0). Only a draftless task opens fresh.
        const steps: HeadlessScript["steps"] = [];
        if (this.versions.draftOf(taskId) === null) {
          steps.push({
            event: "open-draft",
            snapshot: {
              elements: {},
              claims: previewClaims.map((c) => ({ id: String(c.id), text: String(c.text), posterior: 0.5 })),
              evidence_refs: [],
              report: {},
              deleted_nodes: [],
            },
            base_v: null,
          });
        }
        steps.push(
          { event: "attach", decomposition: elements, decomposition_id: decompositionId, plan },
          { event: "confirm" },
          { event: "sign" },
        );
        const script: HeadlessScript = {
          task_id: taskId,
          pre_signed: {},
          steps,
        };
        const result = await runHeadless({
          ledger: this.ledger,
          machine: this.machine,
          versions: this.versions,
          script,
          emit: (line) => {
            for (const client of this.wss.clients) {
              client.send(JSON.stringify({ event: "engine", line }));
            }
          },
        });
        const dispatched = stages.length > 0 ? this.schedulerFor(taskId).tick() : [];
        return { ...result, phase: this.machine.phaseOf(taskId), stages: stages.length, dispatched: dispatched.length };
      }
      case "research.freeze": {
        // 人工裁决门: the verdict is ALWAYS human-signed (问句不是判决).
        const taskId = String(params.task_id);
        const verdict = String(params.verdict ?? "");
        if (!(VERDICTS as readonly string[]).includes(verdict)) {
          throw new ProjectHomeError(`verdict must be one of ${VERDICTS.join("|")}`);
        }
        const phase = this.machine.phaseOf(taskId);
        if (phase !== "research" && phase !== "converged") {
          throw new ProjectHomeError(`freeze requires the research or converged phase, got: ${phase ?? "unknown"}`);
        }
        if (phase === "research") {
          this.machine.transition(taskId, { event: "research-completed" });
        }
        const committed = this.machine.freezeTask(taskId, {
          verdict,
          summary: String(params.summary ?? `${verdict} by human sign-off`),
        });
        return { committed: true, v: committed.v, commit_hash: committed.commit_hash, verdict };
      }
      case "mindmap.generate": {
        // 确认阶段: transcript → pi → mindmap tree (quote 回查溯源), draft only
        const taskId = String(params.task_id);
        const summary = readPiConfig(this.options.piConfigDir);
        if (!summary.keyed_session_ready) {
          throw new ProjectHomeError("pi 密钥未配置：请先到设置页配置 provider key，再生成思维导图。");
        }
        const command = this.resolvePiCommand();
        if (command === null) {
          throw new ProjectHomeError("pi binary not found (set RT_PI_CMD) — mindmap generation fails closed");
        }
        const transcript = this.ledger.connection
          .prepare("SELECT seq, role, kind, text, receipt_json, created_at FROM chat_messages WHERE task_id = ? ORDER BY seq")
          .all(taskId) as TranscriptMessage[];
        const prompt = mindmapPrompt(transcript);
        const stdout =
          this.options.piRunner !== undefined
            ? await this.options.piRunner(command, prompt)
            : await runPi(command, prompt, this.options.piTimeoutMs ?? 300_000, ["-nt", "-ne", "--no-session", "--no-skills"]);
        const parsed = parseMindmap(stdout, transcript);
        const now = new Date().toISOString();
        this.ledger.connection
          .prepare(
            "INSERT INTO mindmaps (task_id, tree_json, status, created_at, updated_at) VALUES (?, ?, 'draft', ?, ?) "
            + "ON CONFLICT(task_id) DO UPDATE SET tree_json = excluded.tree_json, status = 'draft', updated_at = excluded.updated_at",
          )
          .run(taskId, JSON.stringify(parsed.tree), now, now);
        return { tree: parsed.tree, dropped: parsed.dropped, depth: parsed.depth };
      }
      case "mindmap.get": {
        const row = this.ledger.connection
          .prepare("SELECT tree_json, status, updated_at FROM mindmaps WHERE task_id = ? LIMIT 1")
          .get(String(params.task_id)) as { tree_json: string; status: string; updated_at: string } | undefined;
        return row !== undefined ? { tree: JSON.parse(row.tree_json), status: row.status, updated_at: row.updated_at } : { tree: null, status: null };
      }
      case "mindmap.editNode": {
        // 编辑权在确认前 — confirmed trees are frozen (变更=重大转向)
        const taskId = String(params.task_id);
        const row = this.ledger.connection
          .prepare("SELECT tree_json, status FROM mindmaps WHERE task_id = ? LIMIT 1")
          .get(taskId) as { tree_json: string; status: string } | undefined;
        if (row === undefined) {
          throw new ProjectHomeError(`no mindmap for task: ${taskId}`);
        }
        if (row.status === "confirmed") {
          throw new ProjectHomeError("mindmap is confirmed; editing is a major pivot (re-confirm)");
        }
        const tree = JSON.parse(row.tree_json) as MindTree;
        const op = {
          action: String(params.action) as "rename" | "addChild" | "delete",
          nodeId: String(params.node_id),
          text: typeof params.text === "string" ? params.text : undefined,
        };
        if (!editNode(tree, op)) {
          throw new ProjectHomeError(`edit refused: ${op.action} on ${op.nodeId}`);
        }
        this.ledger.connection
          .prepare("UPDATE mindmaps SET tree_json = ?, updated_at = ? WHERE task_id = ?")
          .run(JSON.stringify(tree), new Date().toISOString(), taskId);
        return { tree, edited: true };
      }
      case "mindmap.confirm": {
        // 确认思维导图 → 叶子=调研命题 → 机械 stages 注册 → research 相位
        const taskId = String(params.task_id);
        const row = this.ledger.connection
          .prepare("SELECT tree_json, status FROM mindmaps WHERE task_id = ? LIMIT 1")
          .get(taskId) as { tree_json: string; status: string } | undefined;
        if (row === undefined) {
          throw new ProjectHomeError(`no mindmap for task: ${taskId}`);
        }
        if (row.status === "confirmed") {
          throw new ProjectHomeError("mindmap already confirmed");
        }
        const tree = JSON.parse(row.tree_json) as MindTree;
        // 原子性（issue #702 走查发现）：status='confirmed' 必须**最后**写——
        // 先翻转状态后做其余步骤，任何一步抛错都会留下半成品
        // （confirmed 但 stages 空/相位卡死），用户永远无法重试确认
        if (this.machine.phaseOf(taskId) === undefined) {
          this.machine.openTask(taskId); // task birth → chat (same as runHeadless)
        }
        // the mindmap IS the user-facing structure of the six-element
        // decomposition (docs/product/05 §2): depth-1 branches map to classes,
        // every node carries its provenance quote
        const src = (node: MindNode): Array<Record<string, unknown>> =>
          [node, ...node.children].map((n) => ({
            text: n.text,
            source: { kind: "chat-message", ref: `mindmap:${n.id}`, quote: n.quote ?? n.text },
          }));
        const branch = (name: string): Array<Record<string, unknown>> => {
          const b = tree.root.children.find((c) => c.branch === name || c.text === name);
          return b !== undefined ? src(b) : [];
        };
        const leaves: Array<Record<string, unknown>> = [];
        const collectLeaves = (node: MindNode): void => {
          if (node.children.length === 0) {
            leaves.push({ text: node.text, source: { kind: "chat-message", ref: `mindmap:${node.id}`, quote: node.quote ?? node.text } });
          }
          for (const c of node.children) {
            collectLeaves(c);
          }
        };
        collectLeaves(tree.root);
        const difficulties = branch("难点").length > 0
          ? branch("难点").map((n) => ({ ...n, kill_candidates: [`verify: ${n.text}`] }))
          : leaves.map((n) => ({ text: String(n.text), source: n.source, kill_candidates: [`verify: ${n.text}`] }));
        const extraction: DecompositionElements = {
          requirements: tree.root.children.flatMap((c) => src(c)),
          constraints: branch("限制条件"),
          background: branch("任务背景"),
          intents: branch("调研目标"),
          refusals: branch("拒绝点"),
          difficulties,
          claims_preview: [],
        };
        const parsed = parseDecomposition(extraction);
        // 六要素 checklist：思维导图是诚实抽取——对话中未出现的类别由确认
        // 动作显式声明 "none"（不编造凑数），沿用 refusals:none 先例（#702）
        const notes: Record<string, string> = { refusals: "none" };
        for (const cls of ["constraints", "background", "intents"] as const) {
          if ((extraction[cls] as Array<unknown>).length === 0) {
            notes[cls] = "none";
          }
        }
        confirmDecomposition(this.ledger, taskId, parsed, notes, { decomposition_id: `dc-${taskId}` });
        const decompositionId = `dc-${taskId}`;
        this.machine.attachDecomposition(taskId, decompositionId);
        // A7 rule 3（同 research.start）：draftless 任务开一份以叶子命题为
        // claims（posterior 0.5，id 对齐 mechanicalPlan 的 claim_ids）的
        // 工作集——否则确认后的调研永远 freeze refused（issue #690 e2e）
        if (this.versions.draftOf(taskId) === null) {
          const leafClaims: Array<{ id: string; text: string; posterior: number }> = [];
          const collect = (node: MindNode): void => {
            if (node.children.length === 0) {
              leafClaims.push({ id: node.id, text: node.text, posterior: 0.5 });
            }
            for (const child of node.children) collect(child);
          };
          collect(tree.root);
          this.versions.openDraft(taskId, {
            snapshot: {
              elements: {},
              claims: leafClaims,
              evidence_refs: [],
              report: {},
              deleted_nodes: [],
            },
            baseV: null,
          });
        }
        const plan = planFromTree(tree);
        this.machine.attachRunPlan(taskId, {
          plan_id: `plan-${decompositionId}`,
          stages: plan.map((st) => ({ id: st.id, title: st.title, claim_ids: st.claim_ids, depends_on: st.depends_on })),
          budget: { capMs: 12 * 3600 * 1000 },
          yaw_checks: [
            { slot: "plan-level", mode: "auto" },
            { slot: "problem-level", mode: "human" },
            { slot: "knowledge-level", mode: "auto" },
          ],
        });
        const dagStages: ParallelStage[] = plan.map((stage) => ({
          stage_id: `${taskId}/${stage.id}`,
          title: stage.title,
          status: "pending",
          claim_ids: stage.claim_ids,
          depends_on: stage.depends_on,
          assigned_worker_class: "retrieval",
          retries: 0,
          max_retries: 2,
          outputs: [],
        }));
        if (dagStages.length > 0) {
          this.schedulerFor(taskId).registerStages(dagStages);
          this.schedulerFor(taskId).tick();
          // 首轮即时触发（#709）——不等 5s 间隔泵
          void this.researchRunner.pumpOnce().catch(() => {});
        }
        // walk: chat → decompose(语义确认) → research；全链成功后翻转导图状态
        this.machine.transition(taskId, { event: "confirm" });
        this.machine.transition(taskId, { event: "sign" });
        this.ledger.connection.prepare("UPDATE mindmaps SET status = 'confirmed', updated_at = ? WHERE task_id = ?").run(new Date().toISOString(), taskId);
        return { confirmed: true, stages: dagStages.length, phase: this.machine.phaseOf(taskId) };
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
