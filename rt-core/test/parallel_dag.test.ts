import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { ParallelDagScheduler, type ParallelStage } from "../src/scheduler/parallel_dag.js";
import { LedgerStore } from "../src/store/ledger.js";

let ledger: LedgerStore;

beforeEach(() => {
  ledger = new LedgerStore(mkdtempSync(join(tmpdir(), "rt-par-")));
  ledger.initialize();
});

function stage(id: string, overrides: Partial<ParallelStage> = {}): ParallelStage {
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
    scheduler.completeStage("upstream", "done");
    const dispatched = scheduler.tick();
    expect(dispatched.map((d) => d.stage_id)).toEqual(["downstream"]);
  });

  it("caps concurrency at 4", () => {
    const scheduler = new ParallelDagScheduler(ledger, { maxConcurrency: 4 });
    scheduler.registerStages(["a", "b", "c", "d", "e", "f"].map((id) => stage(id)));
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
