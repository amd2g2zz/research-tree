/** Background research worker (issue #709 — PM 审计 P0-1：调研阶段无执行器).

确认导图后注册的阶段此前只被 tick() 翻转到 in_progress 就永远停住——
前端离开等于调研结束。本 runner 在**服务端进程**里跑一个后台循环：

- 每 pump：tick() 全局分发就绪阶段（跨任务——多个调研后台任务并发），
  in-flight 集合防重入；重启残留的 in_progress 孤儿经 failStage 自动重排
- 每个 worker = **真实检索**（DataSourceProvider / anysearch）→ **模型综合**
  （piRunner，可降级）→ completeStage 落账产出 → broadcast 事件行
- 检索失败 → failStage 重试计数（耗尽自动停泊）；综合失败 → 诚实降级，
  原始检索结果即为产出
- 进度全部在 ledger：前端离开不影响，重开即见最新状态

并发由 tick() 的 maxConcurrency 与 in-flight 集合共同约束。

#742 任务级 stop 控制面：每个派发/完成边界检查 TaskControlPlane——
stopped/stopping 任务零新派发、零重试、零生长；可取消的 in-flight 调用
（pi 综合/仲裁）经取消注册表取消（真 pi 进程 SIGTERM→宽限→SIGKILL）；
不可取消的检索调用**如实广播上报**，其迟到结果被完成前检查点丢弃（阶段落
cancelled 终态，产出永不落账）。stop 幂等；stopping 排干（in-flight 归零）
后落 stopped 并持久化——重启后由 plane hydrate 恢复，重新注册不复燃。 */

import type { DataSourceProvider } from "../../rt-core/src/providers/types.js";
import { ParallelDagScheduler } from "../../rt-core/src/scheduler/parallel_dag.js";
import { TaskControlPlane } from "../../rt-core/src/state/task_control.js";
import type { LedgerStore } from "../../rt-core/src/store/ledger.js";
import type { VersionStore } from "../../rt-core/src/versions/store.js";
import { reconToText, runRecon } from "./chat-turn.js";
import { arbiterPlan, validateProposed } from "./graph_arbiter.js";
import { extractJsonObject } from "./mindmap.js";

export interface WorkerDeps {
  ledger: LedgerStore;
  versions: VersionStore;
  /** 每次使用时解析——server 注入 options.provider ?? defaultProvider() */
  provider: () => DataSourceProvider;
  /** 每次 pi 综合时解析——null 表示 pi 不可用（跳过综合，诚实降级） */
  piCommand: () => string | null;
  /** 测试注入；生产走 runPi。与 server options 同签名（可同步返回） */
  piRunner?: (command: string, prompt: string) => string | Promise<string>;
  piTimeoutMs?: number;
  broadcast: (line: string) => void;
  maxConcurrent?: number;
  /** 任务级 stop 控制面（#742）——缺省时自建（测试便捷） */
  control?: TaskControlPlane;
}

interface StageRow {
  stage_id: string;
  title: string;
  status: string;
  claim_ids: string;
}

/** 综合员 prompt（#729 缓存前缀律）：稳定规则+输出格式在前，任务级上下文
 * （命题+上游发现，同任务跨节点共享）居中，逐节点变化的检索词+检索结果
 * 压到最后——跨节点调用共享长前缀，DeepSeek context caching 才有收益。 */
export function buildSynthPrompt(
  query: string,
  claims: string[],
  upstream: string,
  sources: Array<{ title: string; url?: string; snippet?: string }>,
): string {
  return (
    "你是研究综合员。把检索结果归纳成对命题的回答：只依据资料本身，资料不直接相关时如实说明，不得编造。\n" +
    '只输出 JSON：{"findings":"用 3-5 条要点归纳上述资料对该命题的回答；资料不直接相关时如实说明，不得编造。","relevance":0.5,"coverage":0.5}（relevance/coverage = 你对相关度与覆盖度的诚实自评，0~1）\n' +
    "\n【本次综合输入】\n" +
    "命题：" +
    claims.join("；") +
    (upstream !== "" ? `\n上游阶段发现（供参考）：\n${upstream}` : "") +
    "\n检索词：" +
    query +
    "\n检索结果：\n" +
    sources
      .map((s, i) => `${i + 1}. ${s.title}${s.snippet ? ` — ${s.snippet}` : ""}`)
      .join("\n") +
    "\n"
  );
}

function clamp01(v: number): number {
  return Math.min(Math.max(v, 0), 1);
}

/** bigram Jaccard 相似度（无嵌入的 novelty 机械信号） */
function maxJaccard(text: string, corpus: string[]): number {
  const grams = (t: string): Set<string> => {
    const s = t.replace(/\s+/g, "");
    const out = new Set<string>();
    for (let i = 0; i + 2 <= s.length; i += 1) out.add(s.slice(i, i + 2));
    return out;
  };
  const a = grams(text);
  let worst = 0;
  for (const other of corpus) {
    const b = grams(other);
    let inter = 0;
    for (const g of a) if (b.has(g)) inter += 1;
    const union = a.size + b.size - inter;
    if (union > 0) worst = Math.max(worst, inter / union);
  }
  return worst;
}

/** stage_id → 任务前缀（stage_id = `${taskId}/${stage.id}`）。 */
function taskPrefixOf(stageId: string): string {
  const i = stageId.indexOf("/");
  return i >= 0 ? stageId.slice(0, i) : stageId;
}

/** 按任务前缀分组（#742 逐任务闭合/生长的基础）。 */
function groupByTask<T extends { stage_id: string }>(rows: T[]): Array<[string, T[]]> {
  const map = new Map<string, T[]>();
  for (const row of rows) {
    const taskId = taskPrefixOf(row.stage_id);
    const list = map.get(taskId);
    if (list !== undefined) {
      list.push(row);
    } else {
      map.set(taskId, [row]);
    }
  }
  return [...map.entries()];
}

/** 可取消包装：stop 时对注册中的调用触发 cancel（注入式 runner 的取消
 * 是包装层拒绝；真 pi 进程走 runPiCancellable 的 SIGTERM→宽限→SIGKILL）。 */
function makeCancellable<T>(p: Promise<T>): { promise: Promise<T>; cancel: (reason: string) => void } {
  let doReject: ((e: Error) => void) | null = null;
  const promise = new Promise<T>((resolve, reject) => {
    doReject = reject;
    p.then(resolve, reject); // 底层 promise 始终有 handler——取消后迟到 settle 无害
  });
  return {
    promise,
    cancel: (reason: string) => {
      doReject?.(new Error(`call cancelled (${reason})`));
    },
  };
}

export class BackgroundResearchRunner {
  private readonly scheduler: ParallelDagScheduler;
  private readonly inFlight = new Map<string, Promise<void>>();
  /** 任务级 stop 控制面（#742）：状态权威，无行 ≡ running */
  private readonly control: TaskControlPlane;
  /** 每任务的在飞可取消调用注册表：taskId → cancel 句柄集 */
  private readonly cancellableCalls = new Map<string, Set<(reason: string) => void>>();
  /** 已响应过 stop 请求的任务（幂等：不重复广播/翻转） */
  private readonly stopHandled = new Set<string>();
  // 增益引擎（#715 用户裁定：收益递增生长/收益递减抑制——不用硬上限）
  /** 每任务阻尼系数：后验/先验比滚动更新，压制收益递减的分支 */
  private readonly taskDamping = new Map<string, number>();
  /** 每阶段 spawn 时的先验增益（供后验对比） */
  private readonly priorByStage = new Map<string, number>();
  /** 每任务已产出的 findings 文本——novelty（新颖度）计算基准 */
  private readonly taskFindings = new Map<string, string[]>();
  private timer?: ReturnType<typeof setInterval>;

  constructor(private readonly deps: WorkerDeps) {
    this.scheduler = new ParallelDagScheduler(deps.ledger, {
      maxConcurrency: deps.maxConcurrent ?? 3,
    });
    this.control = deps.control ?? new TaskControlPlane(deps.ledger);
  }

  start(intervalMs = 5000): void {
    if (this.timer !== undefined) return;
    this.timer = setInterval(() => {
      void this.pumpOnce().catch(() => {
        /* pump 内部已 broadcast 错误；循环必须存活 */
      });
    }, intervalMs);
    // 允许进程在只剩定时器时自然退出（测试/单命令场景）
    this.timer.unref?.();
  }

  /** 进程级停泵（server shutdown 专用，#742 前的既有语义——保留给 close）。 */
  stop(): void {
    if (this.timer !== undefined) {
      clearInterval(this.timer);
      this.timer = undefined;
    }
  }

  /** 任务级 stop 的即时响应（research.stop RPC 触发，不等 5s 泵）：
   * 取消可取消 in-flight 调用；不可取消的检索如实上报；pending/in_progress
   * 阶段落 cancelled 终态；无 in-flight 时立即排干落 stopped。幂等。 */
  handleStop(taskId: string): void {
    if (this.control.statusOf(taskId) === "running") return;
    if (this.stopHandled.has(taskId)) return; // 幂等：不重复广播/翻转
    this.stopHandled.add(taskId);
    // 如实上报不可取消的检索调用（#742 验收原文：report any non-cancellable request honestly）
    for (const stageId of this.inFlight.keys()) {
      if (taskPrefixOf(stageId) === taskId) {
        this.deps.broadcast(
          `[worker] stop：${stageId} 的检索调用不可取消——结果返回后将丢弃，不综合不落账`,
        );
      }
    }
    // 取消可取消调用（pi 综合/仲裁）
    const cancels = this.cancellableCalls.get(taskId);
    if (cancels !== undefined) {
      for (const cancel of [...cancels]) cancel("task stop");
    }
    // 阶段落 cancelled 终态（pending 立即翻转；in_progress 由取消/守卫收尾）
    const rows = this.deps.ledger.connection
      .prepare("SELECT stage_id, status FROM parallel_stages WHERE stage_id LIKE ?")
      .all(`${taskId}/%`) as Array<{ stage_id: string; status: string }>;
    for (const row of rows) {
      if (row.status === "pending" || row.status === "in_progress") {
        this.scheduler.cancelStage(row.stage_id);
        this.deps.broadcast(`[worker] stop：${row.stage_id} 已取消`);
      }
    }
    this.maybeDrain(taskId);
  }

  /** stopping → stopped 仅当该任务全部 in-flight 工作排干（#742：
   * stopping 状态保持到可取消的取消、不可取消的返回并丢弃）。 */
  private maybeDrain(taskId: string): void {
    if (this.control.statusOf(taskId) !== "stopping") return;
    for (const stageId of this.inFlight.keys()) {
      if (taskPrefixOf(stageId) === taskId) return; // 还有在飞工作
    }
    this.control.markStopped(taskId);
    this.stopHandled.add(taskId);
    this.deps.broadcast(`[worker] stop：${taskId} 已停止（stopped，重启后保持）`);
  }

  /** 全部 stopping 任务的排干检查（泵边界调用）。 */
  private drainStoppingTasks(): void {
    for (const taskId of this.control.controlledTaskIds()) {
      this.maybeDrain(taskId);
    }
  }

  /** 在飞可取消调用：注册进取消注册表，stop 触发句柄；注册前的取消请求
   * 在句柄就位时补触发（无竞态窗口）。 */
  private async cancellableCall<T>(
    taskId: string,
    start: (registerCancel: (cancel: (reason: string) => void) => void) => Promise<T>,
  ): Promise<T> {
    let cancelFn: ((reason: string) => void) | null = null;
    const entry = {
      cancelled: null as string | null,
      cancel: (reason: string): void => {
        if (entry.cancelled === null) entry.cancelled = reason;
        cancelFn?.(reason);
      },
    };
    let set = this.cancellableCalls.get(taskId);
    if (set === undefined) {
      set = new Set();
      this.cancellableCalls.set(taskId, set);
    }
    set.add(entry.cancel);
    try {
      return await start((cancel) => {
        cancelFn = cancel;
        if (entry.cancelled !== null) cancel(entry.cancelled); // 注册前已请求取消——补触发
      });
    } finally {
      set.delete(entry.cancel);
      if (set.size === 0) this.cancellableCalls.delete(taskId);
    }
  }

  /** pi 调用（综合/仲裁共用）：注入 runner 走可取消包装；真 pi 走
   * runPiCancellable（SIGTERM→宽限→SIGKILL）。两者取消语义一致。 */
  private callPi(taskId: string, command: string, prompt: string): Promise<string> {
    return this.cancellableCall(taskId, (registerCancel) => {
      if (this.deps.piRunner !== undefined) {
        const handle = makeCancellable(Promise.resolve(this.deps.piRunner(command, prompt)));
        registerCancel((reason) => handle.cancel(reason));
        return handle.promise;
      }
      return import("./pi-run.js").then((m) => {
        const handle = m.runPiCancellable(
          command,
          prompt,
          this.deps.piTimeoutMs ?? 300_000,
          ["-nt", "-ne", "--no-session", "--no-skills"],
        );
        registerCancel((reason) => handle.cancel(reason));
        return handle.promise;
      });
    });
  }

  /** 单次泵：孤儿重排 → tick 分发 → 派发执行。测试与即时触发用。 */
  async pumpOnce(): Promise<void> {
    this.requeueOrphans();
    // #742 派发边界：stopped/stopping 任务的阶段不参与派发（其它任务不受扰）
    const dispatched = this.scheduler.tick({ excludeTaskIds: this.control.controlledTaskIds() });
    for (const record of dispatched) {
      if (this.inFlight.has(record.stage_id)) continue;
      const taskId = taskPrefixOf(record.stage_id);
      const task = this.execute(record.stage_id).finally(() => {
        this.inFlight.delete(record.stage_id);
        this.maybeDrain(taskId); // 排干检查（in-flight 归零 → stopped）
      });
      this.inFlight.set(record.stage_id, task);
    }
    await this.waitForIdle();
    this.drainStoppingTasks();

    // wave 边界：按任务分组判定（#742——stopped 任务图冻结，其它任务的
    // 闭合/生长不受其 cancelled/parked 阶段干扰）
    const rows = this.stageRows();
    if (rows.length === 0) return;
    const groups = groupByTask(rows);
    const active = groups.filter(([taskId]) => this.control.statusOf(taskId) === "running");
    if (active.length === 0) return; // 全部任务停止中——图冻结
    const completeActive = active.filter(([, group]) => group.every((r) => r.status === "complete"));
    if (completeActive.length > 0) {
      this.closeCompleteGraphs(rows);
      if (completeActive.length === active.length) {
        return; // 全部 active 图完成：汇总已注册，下轮泵执行（#709 时序）
      }
    }
    const nextWave = this.scheduler.tick({ excludeTaskIds: this.control.controlledTaskIds() });
    if (nextWave.length > 0) {
      // 依赖已解除的节点自动滚入下一 stage——无需仲裁
      for (const record of nextWave) {
        if (this.inFlight.has(record.stage_id)) continue;
        const taskId = taskPrefixOf(record.stage_id);
        const task = this.execute(record.stage_id).finally(() => {
          this.inFlight.delete(record.stage_id);
          this.maybeDrain(taskId);
        });
        this.inFlight.set(record.stage_id, task);
      }
      await this.waitForIdle();
      this.drainStoppingTasks();
      this.closeCompleteGraphs(this.stageRows());
      return;
    }
    // 无可派发且未完成 → 仲裁员决定生长或收尾（LLM 失败时诚实闭合）
    await this.arbiterWave();
    this.drainStoppingTasks();
    this.closeCompleteGraphs(this.stageRows());
  }

  private stageRows(): Array<{ stage_id: string; title: string; status: string }> {
    return this.deps.ledger.connection
      .prepare("SELECT stage_id, title, status FROM parallel_stages ORDER BY stage_id")
      .all() as Array<{ stage_id: string; title: string; status: string }>;
  }

  /** 仲裁 wave：收集图状态与发现 → 仲裁 subagent → 校验注册新节点。
   * #742：按任务分组，只为第一个非停止中的任务仲裁（stopped 任务的图
   * 冻结——零生长）；仲裁调用经取消注册表，stop 即取消（诚实闭合）。 */
  private async arbiterWave(): Promise<void> {
    const all = this.stageRows().filter((r) => !r.title.startsWith("汇总｜"));
    let taskId = "";
    let rows: Array<{ stage_id: string; title: string; status: string }> = [];
    for (const [groupTaskId, group] of groupByTask(all)) {
      if (this.control.statusOf(groupTaskId) !== "running") continue;
      taskId = groupTaskId;
      rows = group;
      break;
    }
    if (taskId === "" || rows.length === 0) return; // 全部停止中/无行——零生长
    const branches = this.branchesOf.get(taskId) ?? [];
    const question = rows[0] !== undefined ? rows[0]!.title.replace(/^探索｜/, "") : "";
    const nodes = rows.map((r) => ({
      stage_id: r.stage_id,
      title: r.title,
      status: r.status,
      findings: this.findingsOf(taskId, r.stage_id),
    }));
    const wave = this.wave + 1;
    // 仲裁调用可取消（#742）：注入/真 pi 都经取消注册表
    const plan = await arbiterPlan(
      {
        piRunner: (command: string, prompt: string) => this.callPi(taskId, command, prompt),
        piCommand: this.deps.piCommand,
        piTimeoutMs: this.deps.piTimeoutMs,
      },
      question,
      branches,
      nodes,
      wave,
    );
    if (plan === null) {
      this.deps.broadcast("[worker] 仲裁员不可用——图按当前状态诚实闭合");
      return;
    }
    if (plan.done) {
      this.deps.broadcast(`[worker] 仲裁员宣布图完成（${plan.note ?? ""}）`);
      return;
    }
    const damping = this.taskDamping.get(taskId) ?? 1;
    const fresh = validateProposed(
      rows.map((r) => ({ stage_id: r.stage_id, title: r.title })),
      plan.nodes,
      taskId,
      wave,
      damping,
    );
    if (fresh.length === 0) {
      this.deps.broadcast("[worker] 仲裁员的新节点增益全部被阻尼抑制——图收敛");
      return;
    }
    this.scheduler.registerStages(
      fresh.map((f) => ({
        stage_id: f.stage_id,
        title: f.title,
        status: "pending" as const,
        claim_ids: f.claim_ids,
        depends_on: f.depends_on,
        assigned_worker_class: "retrieval" as const,
        retries: 0,
        max_retries: 2,
        outputs: [],
      })),
    );
    for (const f of fresh) {
      this.priorByStage.set(f.stage_id, damping);
    }
    this.wave = wave;
    this.deps.broadcast(`[worker] 仲裁员生长 ${fresh.length} 个新节点：${fresh.map((f) => f.title).join("、")}`);
  }

  /** 任务的 branches（seedGraph 登记）；仲裁 prompt 输入 */
  private readonly branchesOf = new Map<string, string[]>();
  private wave = 0;

  /** seed：确认导图后由 server 调用——机械分分支种子（仲裁员在 wave 边界生长） */
  seedBranches(taskId: string, branches: string[]): void {
    this.branchesOf.set(taskId, branches);
    this.taskDamping.set(taskId, 1);
  }

  findingsOf(taskId: string, stageId: string): string | null {
    const row = this.deps.ledger.connection
      .prepare("SELECT outputs FROM parallel_stages WHERE stage_id = ?")
      .get(stageId) as { outputs: string } | undefined;
    if (row === undefined) return null;
    try {
      const raw = JSON.parse(row.outputs) as string[];
      const artifact = raw.length > 0 ? (JSON.parse(raw[0] ?? "{}") as { findings?: string }) : null;
      return artifact?.findings ?? null;
    } catch {
      return null;
    }
  }

  /** 图闭合（graph engineering）：逐任务判定——running 任务的图全部完成
   * 且尚无汇总节点时注册「汇总」节点（下一轮 pump 执行并产出研究底稿）。
   * #742：停止中/已停止任务的图冻结（不注册汇总）；其它任务不受其
   * cancelled/parked 阶段干扰（原来查全表——跨任务耦合）。 */
  private closeCompleteGraphs(rows: Array<{ stage_id: string; title: string; status: string }>): void {
    for (const [taskId, group] of groupByTask(rows)) {
      if (this.control.statusOf(taskId) !== "running") continue; // 停止中：图冻结
      if (group.some((r) => r.status !== "complete")) continue; // 还有未完成节点
      if (group.some((r) => r.title.startsWith("汇总｜"))) continue; // 已闭合
      const completed = group.filter((r) => !r.title.startsWith("汇总｜"));
      if (completed.length === 0) continue;
      const rootText = completed[0]!.title.replace(/^探索｜/, "");
      this.scheduler.registerStages([
        {
          stage_id: `${taskId}/summary-${Date.now()}`,
          title: `汇总｜${rootText.slice(0, 40)}`,
          status: "pending",
          claim_ids: [],
          depends_on: completed.map((r) => r.stage_id),
          assigned_worker_class: "retrieval",
          retries: 0,
          max_retries: 1,
          outputs: [],
        },
      ]);
      this.deps.broadcast("[worker] 图闭合：全部节点完成，注册汇总节点");
    }
  }

  async waitForIdle(): Promise<void> {
    while (this.inFlight.size > 0) {
      await Promise.all([...this.inFlight.values()]);
    }
  }

  /** 重启残留：in_progress 且无 in-flight worker 的阶段 → failStage
   * （重试计数+1 回 pending，耗尽停泊）——下轮 tick 自动重派。
   * #742：停止中/已停止任务的孤儿阶段取消而非重排（零重试）。 */
  private requeueOrphans(): void {
    const rows = this.deps.ledger.connection
      .prepare("SELECT stage_id FROM parallel_stages WHERE status = 'in_progress'")
      .all() as Array<{ stage_id: string }>;
    for (const row of rows) {
      if (this.inFlight.has(row.stage_id)) continue;
      const taskId = taskPrefixOf(row.stage_id);
      if (this.control.statusOf(taskId) !== "running") {
        this.scheduler.cancelStage(row.stage_id);
        this.deps.broadcast(`[worker] stop：孤儿阶段 ${row.stage_id} 属于停止中的任务——取消而非重排`);
        continue;
      }
      this.scheduler.failStage(row.stage_id, "interrupted (server restart) — auto retry");
      this.deps.broadcast(`[worker] 恢复：${row.stage_id} 因重启中断，已自动重排`);
    }
  }

  private async execute(stageId: string): Promise<void> {
    const row = this.deps.ledger.connection
      .prepare("SELECT title, claim_ids FROM parallel_stages WHERE stage_id = ?")
      .get(stageId) as { title: string; claim_ids: string } | undefined;
    if (row === undefined) {
      return;
    }
    const title = row.title;
    const claimIds = JSON.parse(row.claim_ids) as string[];
    const taskId = taskPrefixOf(stageId);
    // #742 派发边界守卫：停止中/已停止任务拒绝执行（tick 已过滤，这里是竞态兜底）
    if (this.control.statusOf(taskId) !== "running") {
      this.scheduler.cancelStage(stageId);
      this.deps.broadcast(`[worker] stop：${stageId} 的任务已停止——拒绝执行`);
      return;
    }
    const claimTexts = this.claimTexts(taskId, claimIds);
    const query = title.replace(/^verify:\s*/, "");

    this.deps.broadcast(`[worker] 开始检索：${query}`);
    let sources: Array<{ title: string; url?: string; snippet?: string }>;
    try {
      sources = await runRecon(this.deps.provider(), query);
    } catch (error) {
      const reason = String(error instanceof Error ? error.message : error);
      this.deps.broadcast(`[worker] ✗ ${title} 检索失败（${reason}）——自动重试`);
      this.scheduler.failStage(stageId, `recon failed: ${reason}`);
      return;
    }
    // #742 检索后检查点：不可取消调用的迟到结果——任务停止即丢弃
    if (this.control.statusOf(taskId) !== "running") {
      this.scheduler.cancelStage(stageId);
      this.deps.broadcast(`[worker] stop：${title} 的检索结果已返回，任务停止中——结果丢弃，不综合不落账`);
      return;
    }
    this.deps.broadcast(`[worker] 检索完成（${sources.length} 条来源）：${title} —— 综合中`);

    let findings = reconToText(sources); // 诚实降级底座：综合不可用即用原始检索
    const command = this.deps.piCommand();
    if (command !== null) {
      // 上游发现作为上下文（#715：导图/依赖驱动的调研——不是孤立检索）
      const upstream = this.upstreamFindings(taskId, stageId);
      try {
        // #729 缓存前缀律：稳定规则在前，任务级上下文居中，逐节点变化的
        // 检索词+结果压尾（buildSynthPrompt）——跨节点调用共享长前缀
        const prompt = buildSynthPrompt(query, claimTexts, upstream, sources);
        // #742：综合调用经取消注册表——stop 即取消（SIGTERM→宽限→SIGKILL）
        const stdout = await this.callPi(taskId, command, prompt);
        const json = extractJsonObject(stdout);
        if (json !== null) {
          const parsed = JSON.parse(json) as {
            findings?: string;
            relevance?: number;
            coverage?: number;
          };
          if (typeof parsed.findings === "string" && parsed.findings.trim() !== "") {
            findings = parsed.findings;
          }
          this.updateGain(taskId, parsed.relevance, parsed.coverage, findings);
        }
      } catch {
        if (this.control.statusOf(taskId) !== "running") {
          // #742：综合调用被 stop 取消——结果丢弃，阶段保持取消
          this.scheduler.cancelStage(stageId);
          this.deps.broadcast(`[worker] stop：${title} 的综合调用已取消——结果丢弃，阶段保持取消`);
          return;
        }
        // 综合失败不杀阶段——检索结果本身就是真实产出
        this.deps.broadcast(`[worker] 综合模型不可用，${title} 以原始检索结果落账`);
      }
    }

    // #742 完成前检查点：迟到完成被拒——产出永不落账
    if (this.control.statusOf(taskId) !== "running") {
      this.scheduler.cancelStage(stageId);
      this.deps.broadcast(`[worker] stop：${title} 迟到完成被拒——产出不落账`);
      return;
    }
    const stageNow = this.deps.ledger.connection
      .prepare("SELECT status FROM parallel_stages WHERE stage_id = ?")
      .get(stageId) as { status: string } | undefined;
    if (stageNow?.status === "cancelled") {
      // 防御：cancelled 终态永不完成（handleStop 已翻转而守卫未见的竞态）
      this.deps.broadcast(`[worker] stop：${title} 已取消——完成被拒`);
      return;
    }
    const output = JSON.stringify({
      title,
      query,
      findings,
      sources,
      completed_at: new Date().toISOString(),
    });
    this.scheduler.completeStage(stageId, output);
    this.deps.broadcast(`[worker] ✓ ${title} 完成（${sources.length} 条来源）`);
  }

  /** 增益引擎（#715）：relevance/coverage 模型自评 × novelty（与既有发现的
   * bigram Jaccard 新颖度）→ 后验增益；后验/先验比滚动更新任务阻尼——
   * 收益递减的分支后续节点估值被自动压低，收益递增则自由生长。 */
  private updateGain(
    taskId: string,
    relevance: number | undefined,
    coverage: number | undefined,
    findings: string,
  ): void {
    const rel = clamp01(relevance ?? 0.5);
    const cov = clamp01(coverage ?? 0.5);
    const prev = this.taskFindings.get(taskId) ?? [];
    const novelty = prev.length === 0 ? 1 : 1 - maxJaccard(findings, prev);
    const posterior = clamp01(rel * 0.5 + cov * 0.25 + novelty * 0.25);
    const prior = this.priorByStage.size > 0 ? this.lastPrior : 0.6;
    const ratio = posterior / Math.max(prior, 0.15);
    const d = clamp01((this.taskDamping.get(taskId) ?? 1) * Math.min(Math.max(ratio, 0.3), 1.3));
    this.taskDamping.set(taskId, Math.max(d, 0.1));
    this.lastPrior = posterior;
    const texts = this.taskFindings.get(taskId) ?? [];
    texts.push(findings);
    this.taskFindings.set(taskId, texts.slice(-8));
    this.deps.broadcast(
      `[worker] 增益：后验 ${posterior.toFixed(2)}（novelty ${novelty.toFixed(2)}）→ 任务阻尼 ${(this.taskDamping.get(taskId) ?? 1).toFixed(2)}`,
    );
  }

  private lastPrior = 0.6;

  /** 上游阶段发现（depends_on 的 findings，供综合参考——导图/依赖驱动） */
  private upstreamFindings(taskId: string, stageId: string): string {
    const row = this.deps.ledger.connection
      .prepare("SELECT depends_on FROM parallel_stages WHERE stage_id = ?")
      .get(stageId) as { depends_on: string } | undefined;
    if (row === undefined) return "";
    const deps = JSON.parse(row.depends_on) as string[];
    const parts: string[] = [];
    for (const dep of deps) {
      const f = this.findingsOf(taskId, dep);
      if (f !== null) parts.push(`【${dep}】${f.slice(0, 300)}`);
    }
    return parts.join("\n");
  }

  private claimTexts(taskId: string, claimIds: string[]): string[] {
    const draft = this.deps.versions.draftOf(taskId);
    const claims = (
      draft as unknown as {
        snapshot?: { claims?: Array<{ id: string; text: string }> };
      }
    )?.snapshot?.claims;
    if (claims === undefined || claims === null) return claimIds;
    const byId = new Map(claims.map((c) => [c.id, c.text]));
    return claimIds.map((id) => byId.get(id) ?? id);
  }
}
