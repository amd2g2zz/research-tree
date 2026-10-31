import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { ExperimentLayer } from "../src/experiments/layer.js";
import { LedgerStore } from "../src/store/ledger.js";
import { EngineCore } from "../src/store/engine.js";

let workspace: string;
let ledger: LedgerStore;

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-exp-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
});

const PREREG = {
  hypothesis: "caching improves p95",
  criterion: "p95 < 200ms with cache vs 400ms without",
  min_sample: 5,
  cost_cap: 2.0,
};

describe("experiment layer v1 (issue #567)", () => {
  it("pre-registration happens before execution (registered first, run second)", async () => {
    const engine = new ExperimentLayer(ledger);
    const experiment = engine.register("t1", {
      experiment_id: "x1",
      hypothesis: "caching improves p95",
      method: "benchmark",
      criterion: "p95 < 200ms with cache",
      min_sample: 5,
      cost_cap: 2.0,
      designer: "agent-a",
    });
    expect(experiment.status).toBe("registered");
    expect(experiment.preregistration).toMatchObject({ hypothesis: "caching improves p95", min_sample: 5 });
    // execution only after registration
    await engine.execute(String(experiment.experiment_id), { executor: "agent-b" });
    const row = ledger.getExperiment("t1", "x1");
    expect(row?.status).toBe("running");
  });

  it("sequential stop: posterior past threshold stops the experiment", async () => {
    const engine = new ExperimentLayer(ledger);
    engine.register("t1", {
      experiment_id: "x2",
      hypothesis: "h2",
      method: "benchmark",
      criterion: "p95 < 200ms",
      min_sample: 3,
      cost_cap: 5.0,
      designer: "a",
    });
    await engine.execute("x2", { executor: "agent-b" });
    const stopped = engine.recordObservation("x2", { posterior: 0.97, sample: 3 });
    expect(stopped.stopped).toBe(true);
    expect(stopped.reason).toBe("posterior-past-threshold");
  });

  it("designer != executor enforced (same identity rejected)", async () => {
    const engine = new ExperimentLayer(ledger);
    engine.register("t1", {
      experiment_id: "x3",
      hypothesis: "h3",
      method: "benchmark",
      criterion: "c",
      min_sample: 1,
      cost_cap: 1.0,
      designer: "agent-a",
    });
    await expect(engine.execute("x3", { executor: "agent-a" })).rejects.toThrow(/designer/);
  });

  it("over-budget claims land experiment-gated (not run)", async () => {
    const engine = new ExperimentLayer(ledger);
    engine.register("t1", {
      experiment_id: "x4",
      hypothesis: "h4",
      method: "benchmark",
      criterion: "c",
      min_sample: 100,
      cost_cap: 1.0,
      designer: "a",
    });
    const gated = engine.checkBudget("x4", { estimated_cost: 50.0 });
    expect(gated.experiment_gated).toBe(true);
    expect(gated.reason).toContain("cost");
  });

  it("experiments persist via the #547 experiments table", () => {
    const engine = new ExperimentLayer(ledger);
    engine.register("t1", {
      experiment_id: "x5",
      hypothesis: "h5",
      method: "benchmark",
      criterion: "c",
      min_sample: 1,
      cost_cap: 1.0,
      designer: "a",
    });
    const row = ledger.getExperiment("t1", "x5");
    expect(row).not.toBeNull();
    expect(row!.status).toBe("registered");
  });
});
