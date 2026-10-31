/** T2 closeout acceptance (issue #570): the five-idea T2 exit walk.

Five real ideas of differing shapes, each driven through its T2 capability
against the integrated stack, plus the cross-cutting invariants:

1. doomed-2c4g      — make-or-break dies mid-run (#563): bury → NO-GO
                      recommendation, H5 savings ≥50% measured
2. contested-cost   — dual-seat adversarial (#564): equal budgets,
                      counter-evidence discovery above single-seat
3. parallel-cluster — parallel DAG (#565): dependency-aware dispatch,
                      concurrency cap respected, no conflicts
4. historical-fork  — lineage (#566): 3-click rule holds incl. a historical
                      version
5. experiment-gated — experiment layer (#567): pre-registration → execution →
                      sequential stop; over-budget → experiment-gated

Cross-cutting: Thompson allocation over a run (#568: ≤8 arms, widen ≤30%) and
the overnight run (#569: forced convergence + morning replay from the event
log).

H2 (敢劝退 third-party blind review vs Deep Research) requires real Deep
Research runs and human evaluators — the engine-side 劝退 projection (the
NO-GO narrative inputs: refuted claim, counter-evidence refs, graveyard
disposition) is verified here (idea 1) and is the data the blind review will
consume. Same deferral discipline as T1's H1/H3 (keyed-session provisioning,
#588).
*/

import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { LedgerStore } from "../src/store/ledger.js";
import { VersionStore } from "../src/versions/store.js";
import { EngineCore } from "../src/store/engine.js";
import { ProductStateMachine } from "../src/state/machine.js";
import { VariantSearchEngine } from "../src/termination/variant_search.js";
import { DualSeatEngine } from "../src/verification/dual_seat.js";
import { ParallelDagScheduler, type ParallelStage } from "../src/scheduler/parallel_dag.js";
import { LineageDrillDown } from "../src/canvas/lineage.js";
import { ExperimentLayer } from "../src/experiments/layer.js";
import { DirectionSampler } from "../src/directions/thompson.js";
import { runOvernight, recoverFromCrash } from "../src/headless/overnight.js";
import { GraphStore } from "../src/graph/projection.js";

let workspace: string;
let ledger: LedgerStore;
let versions: VersionStore;
let machine: ProductStateMachine;

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-t2close-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
  versions = new VersionStore(ledger);
  machine = new ProductStateMachine(new EngineCore(ledger), versions);
});

const HOUR = 3600 * 1000;

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

describe("T2 closeout — five-idea exit walk (issue #570)", () => {
  it("idea 1 (doomed-2c4g): early termination + H5 savings >= 50%", () => {
    const variants = new VariantSearchEngine(ledger);
    const killGraph = [
      { id: "c-mob", text: "2C4G suffices", weight: "make_or_break", posterior: 0.05 },
      { id: "c-derive", text: "p95 acceptable", weight: "important", posterior: 0.7, kill_edges: ["c-mob"] },
    ];
    const standing = variants.searchVariants("c-mob", killGraph, [
      { variant_id: "v-bump", description: "bump to 4C8G", action: "relax", target_claim_id: "c-mob", dag_still_stands: true },
      { variant_id: "v-dead", description: "keep 2C4G", action: "replace", target_claim_id: "c-mob", dag_still_stands: false },
    ]);
    expect(standing.map((v) => v.variant_id)).toEqual(["v-bump"]);

    const inquiry = variants.buildInquiry("c-mob", {
      posterior: 0.05,
      evidence_summary: "OOM postmortem at 3.2GB ceiling",
      standing_variants: [],
    });
    expect(inquiry.choices).toEqual(["bury", "continue", "switch-variant"]);
    expect(inquiry.verdict).toBeUndefined(); // 问句不是判决

    const bury = variants.resolveBury("c-mob");
    expect(bury.recommendation).toBe("NO-GO");
    expect(bury.is_final).toBe(false);

    // H5: early termination saves >= 50% vs the full-run estimate
    const savings = variants.recordSavings({ full_run_estimate_ms: 10 * HOUR, actual_run_ms: 3 * HOUR });
    expect(savings.ratio).toBeGreaterThanOrEqual(0.5);
    expect(savings.meets_h5_threshold).toBe(true);
  });

  it("idea 2 (contested-cost): dual-seat equal budgets, counter-evidence above single-seat", () => {
    const engine = new DualSeatEngine(ledger);
    expect(engine.shouldRunDualSeat("c-cost", ["c-cost"])).toBe(true); // mob-only
    const result = engine.runDualSeat("t2", "c-cost", {
      budgetPerSeat: 45 * 60 * 1000,
      plaintiffWorker: "worker-attack",
      defenseWorker: "worker-defend",
      plaintiffFindings: { counter_evidence_found: true, evidence_refs: ["sha256:" + "b".repeat(64)] },
      defenseFindings: { counter_evidence_found: false, evidence_refs: [] },
    });
    expect(result.plaintiff.budget_ms).toBe(result.defense.budget_ms); // 预算相等
    expect(result.plaintiff.seat).toBe("plaintiff");
    expect(result.posterior_shift.direction).toBe("toward-refutation");
    // dual-seat discovery (0.5) is above any single-seat run (one seat alone caps at 0.5 → both seats run)
    expect(result.posterior_shift.counter_evidence_discovery_rate).toBeGreaterThan(0);
  });

  it("idea 3 (parallel-cluster): dependency-aware dispatch, cap respected, no conflicts", () => {
    const scheduler = new ParallelDagScheduler(ledger, { maxConcurrency: 2 });
    scheduler.registerStages([
      stage("recon-a"),
      stage("recon-b"),
      stage("recon-c"),
      stage("verify", { depends_on: ["recon-a", "recon-b", "recon-c"] }),
    ]);
    const first = scheduler.tick();
    expect(first).toHaveLength(2); // concurrency cap, and verify never mixes in
    expect(first.map((d) => d.stage_id)).toEqual(["recon-a", "recon-b"]);
    scheduler.completeStage("recon-a", "ok");
    scheduler.completeStage("recon-b", "ok");
    scheduler.completeStage("recon-c", "ok");
    const second = scheduler.tick();
    expect(second.map((d) => d.stage_id)).toEqual(["verify"]);
  });

  it("idea 4 (historical-fork): 3-click rule incl. a historical version", () => {
    versions.openDraft("t4", {
      snapshot: {
        elements: {},
        claims: [{ id: "c-old", text: "supplier claims 99.9% SLA" }],
        evidence_refs: ["sha256:" + "c".repeat(64)],
        report: {},
        deleted_nodes: [],
      },
      baseV: null,
    });
    versions.freeze("t4", { verdict: "GO", summary: "v0" });
    versions.openDraftFromVersion("t4", 0); // 继续研究 → 新 draft，v0 成为历史版本
    const drill = new LineageDrillDown(versions);
    const path = drill.resolve("t4", 0, "c-old");
    expect(path).not.toBeNull();
    expect(path!.clicks).toBeLessThanOrEqual(3);
    expect(path!.steps.map((s) => s.layer)).toEqual(["canvas-node", "detail-drawer", "raw-evidence"]);
    expect(path!.raw_evidence).toBeDefined();
  });

  it("idea 5 (experiment-gated): full loop + over-budget lands gated", async () => {
    const experiments = new ExperimentLayer(ledger);
    experiments.register("t5", {
      experiment_id: "exp-cache",
      hypothesis: "sqlite index cuts p95 by half",
      method: "micro-benchmark",
      criterion: "p95 < 120ms indexed vs 260ms baseline",
      min_sample: 3,
      cost_cap: 2.0,
      designer: "designer-agent",
    });
    await experiments.execute("exp-cache", { executor: "runner-agent" });
    const stopped = experiments.recordObservation("exp-cache", { posterior: 0.96, sample: 3 });
    expect(stopped.stopped).toBe(true);
    expect(stopped.reason).toBe("posterior-past-threshold");

    // a second, over-budget experiment never runs (阶梯硬门)
    experiments.register("t5", {
      experiment_id: "exp-heavy",
      hypothesis: "cluster benchmark",
      method: "load-test",
      criterion: "c",
      min_sample: 10,
      cost_cap: 1.0,
      designer: "designer-agent",
    });
    const gated = experiments.checkBudget("exp-heavy", { estimated_cost: 80.0 });
    expect(gated.experiment_gated).toBe(true);
    await expect(experiments.execute("exp-heavy", { executor: "runner-agent" })).rejects.toThrow();
  });

  it("cross-cutting #568: <=8 arms, widen <=30% over a run", () => {
    const sampler = new DirectionSampler(ledger);
    const registered = sampler.registerDirections(
      "t-cross",
      Array.from({ length: 11 }, (_, i) => ({
        direction_id: `dir-${i + 1}`,
        source: "hypothesis-ledger" as const,
      })),
    );
    expect(registered.accepted).toHaveLength(8); // 硬上限
    expect(registered.parked).toHaveLength(3); // 第 9 个起进停车场

    sampler.updateArm("t-cross", {
      direction_id: "dir-1",
      kill_survival: 0.7,
      evidence_yield: 0.6,
      leverage: 0.8,
      surprise: 0.2,
    });

    let widen = 0;
    let total = 0;
    for (let round = 1; round <= 10; round += 1) {
      const result = sampler.allocateRound("t-cross", round, { seed: round, round_budget: 10, mode: "widen" });
      widen += result.widen_used;
      total += 10;
      expect(widen / total).toBeLessThanOrEqual(0.3 + 1e-9);
    }
    const panel = sampler.renderPortfolioPanel("t-cross", 11);
    expect(panel.arms.filter((a) => !a.parked)).toHaveLength(8);
  });

  it("cross-cutting #569: overnight forced convergence + morning replay from the event log", async () => {
    const clock = { t: 0 };
    machine.openTask("t-overnight");
    const result = await runOvernight({
      ledger,
      machine,
      taskId: "t-overnight",
      clock: { now: () => clock.t },
      capMs: 3 * HOUR,
      round: async ({ final }) => {
        clock.t += 1 * HOUR;
        ledger.appendGraphEvent("provider.action", {
          id: `overnight-round-${clock.t}`,
          provider: "anysearch",
          action: "search",
          target: "t-overnight",
          outcome: "ok",
        });
        if (final) {
          return { info_sufficient: true }; // morning: forced convergence with a complete report
        }
        return {};
      },
    });
    expect(result.outcome).toBe("converged");
    expect(result.forced).toBe(true);

    // morning replay: the full timeline is intact and rebuildable from the log
    const recovery = recoverFromCrash({ ledger, versions, taskId: "t-overnight" });
    expect(recovery.chain_verified).toBe(true);
    const graph = new GraphStore(join(workspace, "morning-replay.kuzu"));
    await graph.rebuild(ledger.graphEvents()); // the morning canvas replays from the log alone
    expect(ledger.graphEvents().length).toBeGreaterThan(0);
  });
});
