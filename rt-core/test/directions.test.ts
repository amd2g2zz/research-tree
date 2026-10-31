import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { DirectionSampler } from "../src/directions/thompson.js";
import { LedgerStore } from "../src/store/ledger.js";

let workspace: string;
let ledger: LedgerStore;

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-dir-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
});

function signals(directionId: string, over: Partial<Record<string, number>> = {}) {
  return {
    direction_id: directionId,
    kill_survival: 0.5,
    evidence_yield: 0.5,
    leverage: 0.5,
    surprise: 0.5,
    ...over,
  };
}

describe("thompson direction sampling (issue #568)", () => {
  it("hard cap 8 arms: the 9th direction parks (pinned)", () => {
    const engine = new DirectionSampler(ledger);
    const candidates = Array.from({ length: 9 }, (_, i) => ({
      direction_id: `d${i + 1}`,
      source: "hypothesis-ledger" as const,
    }));
    const result = engine.registerDirections("t1", candidates);
    expect(result.accepted).toHaveLength(8);
    expect(result.parked.map((p) => p.direction_id)).toEqual(["d9"]);
    // parked directions persist but carry zero allocation and a parked marker
    const parkedRow = ledger.getDirection("t1", "d9");
    expect(parkedRow).not.toBeNull();
    const history = parkedRow!.history as Array<Record<string, unknown>>;
    expect(history.at(-1)?.status).toBe("parked");
  });

  it("direction sources are closed (structured generation only)", () => {
    const engine = new DirectionSampler(ledger);
    expect(() =>
      engine.registerDirections("t1", [{ direction_id: "d1", source: "freeform-idea" as never }]),
    ).toThrow(/source/);
  });

  it("arm value posterior is computed from the four signals and persisted with history", () => {
    const engine = new DirectionSampler(ledger);
    engine.registerDirections("t1", [
      { direction_id: "d1", source: "hypothesis-ledger" },
      { direction_id: "d2", source: "kill-graph-branch" },
    ]);
    engine.updateArm("t1", signals("d1", { kill_survival: 0.9, evidence_yield: 0.8, leverage: 0.7, surprise: 0.2 }));
    engine.updateArm("t1", signals("d2", { kill_survival: 0.1, evidence_yield: 0.2, leverage: 0.3, surprise: 0.8 }));

    const strong = ledger.getDirection("t1", "d1");
    const weak = ledger.getDirection("t1", "d2");
    const strongMean = strong!.value_posterior as number;
    const weakMean = weak!.value_posterior as number;
    expect(strongMean).toBeGreaterThan(weakMean);
    // the four signals are traceable in the persisted history
    const history = strong!.history as Array<Record<string, unknown>>;
    const last = history.at(-1) as Record<string, unknown>;
    expect(last.signals).toMatchObject({ kill_survival: 0.9, evidence_yield: 0.8, leverage: 0.7, surprise: 0.2 });
  });

  it("allocation is reproducible from the seed and budget goes to the sampled highest", () => {
    const engine = new DirectionSampler(ledger);
    engine.registerDirections("t1", [
      { direction_id: "d1", source: "hypothesis-ledger" },
      { direction_id: "d2", source: "hypothesis-ledger" },
    ]);
    engine.updateArm("t1", signals("d1", { kill_survival: 0.95, evidence_yield: 0.9, leverage: 0.9, surprise: 0.3 }));
    engine.updateArm("t1", signals("d2", { kill_survival: 0.2, evidence_yield: 0.2, leverage: 0.2, surprise: 0.1 }));

    const a = engine.allocateRound("t1", 1, { seed: 42, round_budget: 10 });
    const b = engine.allocateRound("t1", 1, { seed: 42, round_budget: 10 });
    expect(a.winner).toBe(b.winner);
    expect(a.samples).toEqual(b.samples);
    // budget goes to the sampled highest, disclosed per arm
    const total = Object.values(a.allocation).reduce((s, v) => s + v, 0);
    expect(total).toBeCloseTo(10);
    expect(a.allocation[a.winner]).toBeCloseTo(10);
    expect(a.samples[a.winner]).toBeGreaterThanOrEqual(Math.max(...Object.values(a.samples)));
  });

  it("deepen trigger: make-or-break hanging near 0.5 deepens the leading arm", () => {
    const engine = new DirectionSampler(ledger);
    engine.registerDirections("t1", [{ direction_id: "d1", source: "hypothesis-ledger" }]);
    engine.updateArm("t1", signals("d1"));
    const decision = engine.decideRound("t1", { make_or_break_posterior: 0.52 });
    expect(decision.mode).toBe("deepen");
    expect(decision.reason).toContain("make-or-break");
  });

  it("widen trigger: all-arm EVSI below threshold widens — structurally capped at 30%", () => {
    const engine = new DirectionSampler(ledger);
    engine.registerDirections("t1", [
      { direction_id: "d1", source: "hypothesis-ledger" },
      { direction_id: "d2", source: "survivor-adjacency" },
    ]);
    engine.updateArm("t1", signals("d1"));
    engine.updateArm("t1", signals("d2"));
    const decision = engine.decideRound("t1", { arm_evsis: [0.01, 0.02], evsi_floor: 0.1 });
    expect(decision.mode).toBe("widen");

    // widen share over a run is structurally capped: rounds 1-9 widen, the cap trims round 10+
    let widenBudget = 0;
    let totalBudget = 0;
    for (let round = 1; round <= 10; round += 1) {
      const result = engine.allocateRound("t1", round, { seed: round, round_budget: 10, mode: decision.mode });
      widenBudget += result.widen_used;
      totalBudget += 10;
      expect(widenBudget / totalBudget).toBeLessThanOrEqual(0.3 + 1e-9);
    }
    expect(widenBudget / totalBudget).toBeCloseTo(0.3, 5);
  });

  it("portfolio panel renders directions × value posterior × next-round allocation", () => {
    const engine = new DirectionSampler(ledger);
    engine.registerDirections("t1", [
      { direction_id: "d1", source: "hypothesis-ledger" },
      { direction_id: "d2", source: "refuted-variant" },
    ]);
    engine.updateArm("t1", signals("d1", { kill_survival: 0.9 }));
    engine.updateArm("t1", signals("d2", { kill_survival: 0.2 }));
    engine.allocateRound("t1", 1, { seed: 7, round_budget: 10 });

    const panel = engine.renderPortfolioPanel("t1", 2);
    expect(panel.round).toBe(2);
    expect(panel.arms).toHaveLength(2);
    const d1 = panel.arms.find((a) => a.direction_id === "d1")!;
    expect(d1.value_posterior).toBeGreaterThan(panel.arms.find((a) => a.direction_id === "d2")!.value_posterior);
    expect(d1.allocation).toBeTypeOf("number");
    expect(panel.lines.join("\n")).toContain("d1");
  });
});
