/** Task control plane — per-task stop state machine (issue #742).

#742 根因：BackgroundResearchRunner.stop() 只停泵（clearInterval），既不按
taskId 取消进行中的工作，也不持久化——用户离开等于调研永远停不下来。

本模块是控制面的**权威状态机**（machine.ts 转换矩阵同款模式）：

    running（无行 ≡ running，存量任务兼容）→(requestStop) stopping
    stopping →(markStopped, 仅当 in-flight 排干) stopped

不变量：
- **单向**：stopping 不可回 running；markStopped 仅自 stopping 合法
  （从 running 直接落 stopped = 跳过状态，fail-closed 拒绝）。
- **幂等**：重复 requestStop 返回现状、不刷新时间戳、不覆盖首个 reason；
  stopped 后 requestStop 是 no-op。
- **持久化**：每次转换即时落 task_control 表（migration v11），构造时
  hydrate——进程重启后状态保持（issue 验收原文）。

表是操作面权威（stages 表同级），无行任务 = running；CHECK 约束拒绝域外
状态值，转换方向由本类在代码层强制。
*/

import { LedgerIntegrityError } from "../store/integrity.js";
import type { LedgerStore } from "../store/ledger.js";

export type TaskControlStatus = "running" | "stopping" | "stopped";

export interface TaskControlState {
	taskId: string;
	status: TaskControlStatus;
	stopReason: string | null;
	stopRequestedAt: string | null;
	updatedAt: string;
}

interface ControlRow {
	task_id: string;
	status: string;
	stop_reason: string | null;
	stop_requested_at: string | null;
	updated_at: string;
}

export class TaskControlPlane {
	/** 内存权威映射（构造时 hydrate，转换时双写）——statusOf 不查库。 */
	private readonly states = new Map<string, TaskControlState>();

	constructor(private readonly ledger: LedgerStore) {
		this.ledger.initialize();
		this.hydrate();
	}

	/** 重启恢复：task_control 表 → 内存映射（machine.ts hydrate 模式）。 */
	private hydrate(): void {
		const rows = this.ledger.connection
			.prepare("SELECT task_id, status, stop_reason, stop_requested_at, updated_at FROM task_control")
			.all() as ControlRow[];
		for (const row of rows) {
			this.states.set(row.task_id, {
				taskId: row.task_id,
				status: row.status as TaskControlStatus,
				stopReason: row.stop_reason,
				stopRequestedAt: row.stop_requested_at,
				updatedAt: row.updated_at,
			});
		}
	}

	// ------------------------------------------------------------------ queries

	statusOf(taskId: string): TaskControlStatus {
		return this.states.get(taskId)?.status ?? "running";
	}

	stateOf(taskId: string): TaskControlState | null {
		return this.states.get(taskId) ?? null;
	}

	/** 全部非 running 任务的 id（派发守卫的排除集）。 */
	controlledTaskIds(): string[] {
		return [...this.states.values()]
			.filter((s) => s.status !== "running")
			.map((s) => s.taskId);
	}

	// ------------------------------------------------------------------ transitions

	/** stop 请求：running → stopping。幂等：stopping/stopped 原样返回，
	 * 不刷新 stop_requested_at、不覆盖首个 stop_reason（#742 验收）。 */
	requestStop(taskId: string, reason?: string): TaskControlState {
		const current = this.states.get(taskId);
		if (current !== undefined) {
			return current; // stopping/stopped：幂等 no-op
		}
		const now = new Date().toISOString();
		const state: TaskControlState = {
			taskId,
			status: "stopping",
			stopReason: reason ?? null,
			stopRequestedAt: now,
			updatedAt: now,
		};
		this.persist(state);
		this.states.set(taskId, state);
		return state;
	}

	/** stopping → stopped（in-flight 排干后由 runner 调用）。
	 * 从 running 直接调用 = 跳过状态，fail-closed 拒绝；stopped 重复调用幂等。 */
	markStopped(taskId: string, reason?: string): TaskControlState {
		const current = this.states.get(taskId);
		if (current !== undefined && current.status === "stopped") {
			return current; // 幂等
		}
		if (current === undefined || current.status !== "stopping") {
			throw new LedgerIntegrityError(
				`illegal control transition: markStopped requires status "stopping" (task ${taskId} is "${current?.status ?? "running (no row)"}")`,
			);
		}
		const state: TaskControlState = {
			...current,
			status: "stopped",
			stopReason: reason ?? current.stopReason,
			updatedAt: new Date().toISOString(),
		};
		this.persist(state);
		this.states.set(taskId, state);
		return state;
	}

	// ------------------------------------------------------------------ persistence

	private persist(state: TaskControlState): void {
		this.ledger.connection
			.prepare(
				"INSERT INTO task_control(task_id, status, stop_reason, stop_requested_at, updated_at) VALUES(?, ?, ?, ?, ?) " +
					"ON CONFLICT(task_id) DO UPDATE SET status = excluded.status, stop_reason = excluded.stop_reason, " +
					"stop_requested_at = excluded.stop_requested_at, updated_at = excluded.updated_at",
			)
			.run(state.taskId, state.status, state.stopReason, state.stopRequestedAt, state.updatedAt);
	}
}
