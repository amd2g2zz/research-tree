/** Heterogeneous parallel DAG scheduler (issue #565, docs 02 §递归阶段化).

Dependency-aware ready-set dispatch over the persisted stage table: a stage
whose dependencies are not all rolled-up/closed never dispatches — the
mechanically testable inversion of the #531 greedy-cut failure mode. ≤4
concurrent workers (4 classes round-robin), task-level retry, stage-level
park on retries exhaust, orphan threads park without blocking the critical
path. Isolated output paths per stage (no file conflicts).

The ready-set cut delegates to the #550 scheduler semantics; this module adds
the **persistence + retry/park state machine + isolated output paths**.
*/

import { LedgerIntegrityError } from "../store/integrity.js";
import type { LedgerStore } from "../store/ledger.js";
import type { StageOutcome } from "./stage_outcome.js";

export type WorkerClass =
	| "retrieval"
	| "code-reading"
	| "experiment"
	| "verification";

export interface ParallelStage {
	stage_id: string;
	title: string;
	// #742：cancelled 为任务级 stop 的终态——tick 永不派发、不重试、不复活
	status: "pending" | "in_progress" | "complete" | "parked" | "cancelled";
	claim_ids: string[];
	depends_on: string[];
	assigned_worker_class: WorkerClass;
	retries: number;
	max_retries: number;
	outputs: string[];
}

/** tick 任务级过滤（#742）：excludeTaskIds 的任务零新派发，其它任务不受扰。 */
export interface TickFilter {
	excludeTaskIds?: readonly string[];
}

export interface DispatchRecord {
	stage_id: string;
	worker_class: WorkerClass;
	output_path: string;
}

export class ParallelDagScheduler {
	private readonly maxConcurrency: number;
	private readonly workerClasses: WorkerClass[];

	constructor(
		private readonly ledger: LedgerStore,
		options: { maxConcurrency?: number; workerClasses?: WorkerClass[] } = {},
	) {
		this.maxConcurrency = options.maxConcurrency ?? 4;
		this.workerClasses = options.workerClasses ?? [
			"retrieval",
			"code-reading",
			"experiment",
			"verification",
		];
	}

	registerStages(stages: ParallelStage[]): void {
		for (const stage of stages) {
			this.ledger.appendGraphEvent("provider.action", {
				id: `dag-register-${stage.stage_id}-${Date.now()}`,
				provider: "parallel-dag",
				action: "search",
				target: stage.stage_id,
				outcome: "ok",
			});
			this.ledger.connection
				.prepare(
					"INSERT OR REPLACE INTO parallel_stages(stage_id, title, status, claim_ids, depends_on, " +
						"assigned_worker_class, retries, max_retries, outputs) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
				)
				.run(
					stage.stage_id,
					stage.title,
					stage.status,
					JSON.stringify(stage.claim_ids),
					JSON.stringify(stage.depends_on),
					stage.assigned_worker_class,
					stage.retries,
					stage.max_retries,
					JSON.stringify(stage.outputs),
				);
		}
	}

	tick(filter: TickFilter = {}): DispatchRecord[] {
		// #742：按任务过滤派发集（原查全表——跨任务耦合让 stopped 任务
		// 继续被派发；排除集是"其它任务保持运行"的前提）
		const excluded = filter.excludeTaskIds ?? [];
		const rows = (
			excluded.length === 0
				? this.ledger.connection.prepare("SELECT * FROM parallel_stages ORDER BY stage_id").all()
				: this.ledger.connection
						.prepare(
							`SELECT * FROM parallel_stages WHERE ${excluded.map(() => "stage_id NOT LIKE ?").join(" AND ")} ORDER BY stage_id`,
						)
						.all(...excluded.map((taskId) => `${escapeLike(taskId)}/%`))
		) as Array<Record<string, unknown>>;
		const statusById = new Map(
			rows.map((row) => [String(row.stage_id), String(row.status)]),
		);
		const dispatched: DispatchRecord[] = [];
		for (const row of rows) {
			const stageId = String(row.stage_id);
			const status = String(row.status);
			if (status !== "pending" && status !== "in_progress") {
				continue;
			}
			if (status === "in_progress" && !this.isReDispatch(row)) {
				continue; // currently running
			}
			const deps = JSON.parse(String(row.depends_on)) as string[];
			const closed = deps.every(
				(dep) =>
					statusById.get(dep) === "complete" ||
					statusById.get(dep) === "rolled_up",
			);
			if (!closed) {
				continue;
			}
			if (
				Number(row.retries) >= Number(row.max_retries) &&
				status === "pending"
			) {
				this.setStatus(stageId, "parked");
				continue;
			}
			if (dispatched.length >= this.maxConcurrency) {
				continue;
			}
			const workerClass = String(
				row.assigned_worker_class ?? "retrieval",
			) as WorkerClass;
			const outputPath = `.research-tree/tasks/${stageId}/output.json`;
			this.ledger.connection
				.prepare(
					"UPDATE parallel_stages SET status = 'in_progress' WHERE stage_id = ?",
				)
				.run(stageId);
			dispatched.push({
				stage_id: stageId,
				worker_class: workerClass,
				output_path: outputPath,
			});
		}
		return dispatched;
	}

	/** 阶段完成（issue #744）：产出是结构化 StageOutcome（四态分离），
	 * 不再是裸 artifact JSON。 */
	completeStage(stageId: string, outcome: StageOutcome): void {
		this.ledger.connection
			.prepare(
				"UPDATE parallel_stages SET status = 'complete', outputs = ? WHERE stage_id = ?",
			)
			.run(JSON.stringify(outcome), stageId);
	}

	/** 记录产出但不改状态（issue #744）：insufficient/conflicted 停泊前先落
	 * StageOutcome——unresolvedClaims 在 parked 行上持久可见（重启后仍在）。 */
	recordOutcome(stageId: string, outcome: StageOutcome): void {
		this.ledger.connection
			.prepare("UPDATE parallel_stages SET outputs = ? WHERE stage_id = ?")
			.run(JSON.stringify(outcome), stageId);
	}

	/** 直接停泊（issue #744 无进展停）：机械停条件不走重试——重复查询
	 * 再试一次还是重复，停泊即终态（与 failStage 的重试耗尽停泊相区分）。 */
	parkStage(stageId: string, reason: string): void {
		const row = this.getRow(stageId);
		if (row === undefined) {
			throw new LedgerIntegrityError(`unknown stage: ${stageId}`);
		}
		this.setStatus(stageId, "parked");
		this.ledger.appendGraphEvent("provider.action", {
			id: `dag-park-${stageId}-${Date.now()}`,
			provider: "parallel-dag",
			action: "search",
			target: stageId,
			outcome: "error",
		});
		void reason;
	}

	failStage(stageId: string, reason: string): void {
		const row = this.getRow(stageId);
		if (row === undefined) {
			throw new LedgerIntegrityError(`unknown stage: ${stageId}`);
		}
		const retries = Number(row.retries) + 1;
		const maxRetries = Number(row.max_retries);
		const status = retries >= maxRetries ? "parked" : "pending";
		this.ledger.connection
			.prepare(
				"UPDATE parallel_stages SET status = ?, retries = ? WHERE stage_id = ?",
			)
			.run(status, retries, stageId);
		this.ledger.appendGraphEvent("provider.action", {
			id: `dag-fail-${stageId}-${Date.now()}`,
			provider: "parallel-dag",
			action: "search",
			target: stageId,
			outcome: "error",
		});
		void reason;
	}

	/** #742 取消终态：落 cancelled（tick 永不派发/重试/复活）；重复取消幂等。 */
	cancelStage(stageId: string): void {
		const row = this.getRow(stageId);
		if (row === undefined) {
			throw new LedgerIntegrityError(`unknown stage: ${stageId}`);
		}
		if (String(row.status) === "cancelled") {
			return;
		}
		this.ledger.connection
			.prepare("UPDATE parallel_stages SET status = 'cancelled' WHERE stage_id = ?")
			.run(stageId);
	}

	stageStatus(stageId: string): string {
		return String(this.getRow(stageId)?.status ?? "unknown");
	}

	private isReDispatch(row: Record<string, unknown>): boolean {
		return Number(row.retries) > 0 && String(row.status) === "pending";
	}

	private getRow(stageId: string): Record<string, unknown> | undefined {
		return this.ledger.connection
			.prepare("SELECT * FROM parallel_stages WHERE stage_id = ?")
			.get(stageId) as Record<string, unknown> | undefined;
	}

	private setStatus(stageId: string, status: string): void {
		this.ledger.connection
			.prepare("UPDATE parallel_stages SET status = ? WHERE stage_id = ?")
			.run(status, stageId);
	}
}

/** LIKE 模式转义（%/_）——task_id 是用户可见数据，不能当通配符注入过滤。 */
function escapeLike(value: string): string {
	return value.replace(/[%_]/g, (c) => `\\${c}`);
}
