/** Background research worker (issue #709 — PM 审计 P0-1：调研阶段无执行器).

确认导图后注册的阶段此前只被 tick() 翻转到 in_progress 就永远停住——
前端离开等于调研结束。本 runner 在**服务端进程**里跑一个后台循环：

- 每 pump：tick() 全局分发就绪阶段（跨任务——多个调研后台任务并发），
  in-flight 集合防重入；重启残留的 in_progress 孤儿经 failStage 自动重排
- 每个 worker = **真实检索**（DataSourceProvider / anysearch）→ **模型综合**
  （piRunner，可降级）→ completeStage 落账产出 → broadcast 事件行
- 检索失败 → failStage 重试计数（耗尽自动停泊）；综合失败 → 诚实降级，
  原始检索结果即为产出
- 进度全部在 ledger：前端离开不结束，重开即见最新状态

并发由 tick() 的 maxConcurrency 与 in-flight 集合共同约束。 */

import type { DataSourceProvider } from "../../rt-core/src/providers/types.js";
import { ParallelDagScheduler } from "../../rt-core/src/scheduler/parallel_dag.js";
import type { LedgerStore } from "../../rt-core/src/store/ledger.js";
import type { VersionStore } from "../../rt-core/src/versions/store.js";
import { runRecon, reconToText } from "./chat-turn.js";
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
}

interface StageRow {
	stage_id: string;
	title: string;
	status: string;
	claim_ids: string;
}

export class BackgroundResearchRunner {
	private readonly scheduler: ParallelDagScheduler;
	private readonly inFlight = new Map<string, Promise<void>>();
	private timer?: ReturnType<typeof setInterval>;

	constructor(private readonly deps: WorkerDeps) {
		this.scheduler = new ParallelDagScheduler(deps.ledger, {
			maxConcurrency: deps.maxConcurrent ?? 3,
		});
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

	stop(): void {
		if (this.timer !== undefined) {
			clearInterval(this.timer);
			this.timer = undefined;
		}
	}

	/** 单次泵：孤儿重排 → tick 分发 → 派发执行。测试与即时触发用。 */
	async pumpOnce(): Promise<void> {
		this.requeueOrphans();
		const dispatched = this.scheduler.tick();
		for (const record of dispatched) {
			if (this.inFlight.has(record.stage_id)) continue;
			const task = this.execute(record.stage_id).finally(() => {
				this.inFlight.delete(record.stage_id);
			});
			this.inFlight.set(record.stage_id, task);
		}
		await this.waitForIdle();
	}

	async waitForIdle(): Promise<void> {
		while (this.inFlight.size > 0) {
			await Promise.all([...this.inFlight.values()]);
		}
	}

	/** 重启残留：in_progress 且无 in-flight worker 的阶段 → failStage
	 * （重试计数+1 回 pending，耗尽停泊）——下轮 tick 自动重派。 */
	private requeueOrphans(): void {
		const rows = this.deps.ledger.connection
			.prepare("SELECT stage_id FROM parallel_stages WHERE status = 'in_progress'")
			.all() as Array<{ stage_id: string }>;
		for (const row of rows) {
			if (this.inFlight.has(row.stage_id)) continue;
			this.scheduler.failStage(row.stage_id, "interrupted (server restart) — auto retry");
			this.deps.broadcast(`[worker] 恢复：${row.stage_id} 因重启中断，已自动重排`);
		}
	}

	private async execute(stageId: string): Promise<void> {
		const row = this.deps.ledger.connection
			.prepare("SELECT title, claim_ids FROM parallel_stages WHERE stage_id = ?")
			.get(stageId) as { title: string; claim_ids: string } | undefined;
		if (row === undefined) return;
		const title = row.title;
		const claimIds = JSON.parse(row.claim_ids) as string[];
		const taskId = stageId.slice(0, stageId.indexOf("/"));
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
		this.deps.broadcast(
			`[worker] 检索完成（${sources.length} 条来源）：${title} —— 综合中`,
		);

		let findings = reconToText(sources); // 诚实降级底座：综合不可用即用原始检索
		const command = this.deps.piCommand();
		if (command !== null) {
			try {
				const prompt =
					"你是研究综合员。检索词：" +
					query +
					"\n命题：" +
					claimTexts.join("；") +
					"\n检索结果：\n" +
					sources.map((s, i) => `${i + 1}. ${s.title}${s.snippet ? ` — ${s.snippet}` : ""}`).join("\n") +
					'\n只输出 JSON：{"findings":"用 3-5 条要点归纳上述资料对该命题的回答；资料不直接相关时如实说明，不得编造。"}';
				const stdout =
					this.deps.piRunner !== undefined
						? await this.deps.piRunner(command, prompt)
						: await this.runPi(command, prompt);
				const json = extractJsonObject(stdout);
				if (json !== null) {
					const parsed = JSON.parse(json) as { findings?: string };
					if (typeof parsed.findings === "string" && parsed.findings.trim() !== "") {
						findings = parsed.findings;
					}
				}
			} catch {
				// 综合失败不杀阶段——检索结果本身就是真实产出
				this.deps.broadcast(`[worker] 综合模型不可用，${title} 以原始检索结果落账`);
			}
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

	private runPi(command: string, prompt: string): Promise<string> {
		// 延迟 import 避免 pi-run 在测试注入路径的加载成本（保持注入一致性）
		return import("./pi-run.js").then((m) =>
			m.runPi(command, prompt, this.deps.piTimeoutMs ?? 300_000, [
				"-nt",
				"-ne",
				"--no-session",
				"--no-skills",
			]),
		);
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
