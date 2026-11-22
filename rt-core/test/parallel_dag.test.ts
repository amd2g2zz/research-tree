import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import {
	ParallelDagScheduler,
	type ParallelStage,
} from "../src/scheduler/parallel_dag.js";
import { LedgerIntegrityError } from "../src/store/integrity.js";
import type { StageOutcome } from "../src/scheduler/stage_outcome.js";
import { LedgerStore } from "../src/store/ledger.js";

let ledger: LedgerStore;

beforeEach(() => {
	ledger = new LedgerStore(mkdtempSync(join(tmpdir(), "rt-par-")));
	ledger.initialize();
});

function stage(
	id: string,
	overrides: Partial<ParallelStage> = {},
): ParallelStage {
	return {
		stage_id: id,
		title: `stage ${id}`,
		status: "pending",
		claim_ids: [],
		depends_on: [],
		assigned_worker_class: "retrieval",
		retries: 0,
		max_retries: 2,
		outputs: [],
		...overrides,
	};
}


function sufficientOutcome(): StageOutcome {
	return {
		schema: 2,
		execution: "executed",
		sufficiency: "sufficient",
		relevance: [],
		unresolvedClaims: [],
		findings: [],
		sources: [],
	};
}

describe("heterogeneous parallel DAG (issue #565)", () => {
	it("never dispatches a stage with an open dependency (the #531 inversion, pinned)", () => {
		const scheduler = new ParallelDagScheduler(ledger, { maxConcurrency: 4 });
		scheduler.registerStages([
			stage("upstream"),
			stage("downstream", { depends_on: ["upstream"] }),
		]);
		const dispatched = scheduler.tick();
		expect(dispatched.map((d) => d.stage_id)).toEqual(["upstream"]);
	});

	it("admits the dependent in the same pass when the dependency closes", () => {
		const scheduler = new ParallelDagScheduler(ledger, { maxConcurrency: 4 });
		scheduler.registerStages([
			stage("upstream"),
			stage("downstream", { depends_on: ["upstream"] }),
		]);
		scheduler.tick();
		scheduler.completeStage("upstream", sufficientOutcome());
		const dispatched = scheduler.tick();
		expect(dispatched.map((d) => d.stage_id)).toEqual(["downstream"]);
	});

	it("caps concurrency at 4", () => {
		const scheduler = new ParallelDagScheduler(ledger, { maxConcurrency: 4 });
		scheduler.registerStages(
			["a", "b", "c", "d", "e", "f"].map((id) => stage(id)),
		);
		expect(scheduler.tick()).toHaveLength(4);
	});

	it("retries a failed task (task-level retry)", () => {
		const scheduler = new ParallelDagScheduler(ledger, { maxConcurrency: 4 });
		scheduler.registerStages([stage("s1")]);
		scheduler.tick();
		scheduler.failStage("s1", "worker crashed");
		const dispatched = scheduler.tick();
		expect(dispatched.map((d) => d.stage_id)).toEqual(["s1"]); // re-dispatched
		expect(scheduler.stageStatus("s1")).toBe("in_progress");
	});

	it("parks after retries exhaust", () => {
		const scheduler = new ParallelDagScheduler(ledger, { maxConcurrency: 4 });
		scheduler.registerStages([stage("s1", { max_retries: 1 })]);
		scheduler.tick();
		scheduler.failStage("s1", "crash 1");
		scheduler.tick();
		scheduler.failStage("s1", "crash 2");
		scheduler.tick();
		expect(scheduler.stageStatus("s1")).toBe("parked");
	});

	it("runs parallel stages without file conflicts (isolated outputs)", () => {
		const scheduler = new ParallelDagScheduler(ledger, { maxConcurrency: 4 });
		scheduler.registerStages([stage("a"), stage("b")]);
		const dispatched = scheduler.tick();
		const outputs = dispatched.map((d) => d.output_path);
		expect(new Set(outputs).size).toBe(outputs.length); // unique output paths
	});

	it("orphans park without blocking the critical path", () => {
		const scheduler = new ParallelDagScheduler(ledger, { maxConcurrency: 4 });
		scheduler.registerStages([
			stage("critical"),
			stage("orphan", { max_retries: 0 }),
		]);
		scheduler.tick();
		scheduler.failStage("orphan", "crash");
		// the critical path continues (in_progress); the orphan parked
		expect(scheduler.stageStatus("critical")).toBe("in_progress");
		expect(scheduler.stageStatus("orphan")).toBe("parked");
	});
});

describe("task-level stop control (#742 cancelled 终态 + 派发隔离)", () => {
	it("cancelStage 置 cancelled 终态；tick 永不派发 cancelled", () => {
		const scheduler = new ParallelDagScheduler(ledger, { maxConcurrency: 4 });
		scheduler.registerStages([stage("tA/s1")]);
		scheduler.tick();
		scheduler.cancelStage("tA/s1");
		expect(scheduler.stageStatus("tA/s1")).toBe("cancelled");
		expect(scheduler.tick()).toEqual([]); // cancelled 终态零派发
	});

	it("cancelStage 未知阶段 fail-closed；tick 按 excludeTaskIds 过滤（其它任务不受扰）", () => {
		const scheduler = new ParallelDagScheduler(ledger, { maxConcurrency: 4 });
		expect(() => scheduler.cancelStage("nope")).toThrow(LedgerIntegrityError);
		scheduler.registerStages([stage("tA/s1"), stage("tA/s2"), stage("tB/s1")]);
		const dispatched = scheduler.tick({ excludeTaskIds: ["tA"] });
		expect(dispatched.map((d) => d.stage_id)).toEqual(["tB/s1"]);
		// 排除任务的阶段保持 pending（未被动过）
		expect(scheduler.stageStatus("tA/s1")).toBe("pending");
	});
});
