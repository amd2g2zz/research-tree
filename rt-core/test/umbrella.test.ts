import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { LedgerStore } from "../src/store/ledger.js";
import { LearningUmbrella, UmbrellaError, DEFAULT_ITEMS } from "../src/learning/umbrella.js";
import type { TriggerData } from "../src/learning/umbrella.js";

let workspace: string;
let ledger: LedgerStore;

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-umbrella-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
});

const COLD: TriggerData = {
  experiments_count: 0,
  battery_beats_baseline_pct: null,
  scheduling_window: [0.5, 0.55, 0.6], // still improving — no plateau signal
  scheduling_improvement_epsilon: 0.01,
  g1_g5_gains: null,
  projects_committed: 1,
  replay_scrubs: 0,
  prior_calibration_landed: false,
};

describe("trigger-driven umbrella (issue #577, T4)", () => {
  it("no item starts before its trigger fires — cold telemetry leaves everything dormant", () => {
    const umbrella = new LearningUmbrella(ledger);
    const report = umbrella.evaluate(COLD);
    expect(report.fired).toHaveLength(0);
    expect(report.dormant.map((d) => d.id).sort()).toEqual(DEFAULT_ITEMS.map((i) => i.id).sort());
    expect(() => umbrella.start("cost-model", COLD)).toThrow(UmbrellaError);
  });

  it("each item is individually gated by its own trigger", () => {
    const umbrella = new LearningUmbrella(ledger);
    // cost model fires only at >=50 accumulated experiments
    expect(umbrella.evaluate({ ...COLD, experiments_count: 49 }).fired.map((f) => f.id)).toEqual([]);
    expect(umbrella.evaluate({ ...COLD, experiments_count: 50 }).fired.map((f) => f.id)).toEqual(["cost-model"]);
    // GEPA fires only at >=5% battery beat
    expect(umbrella.evaluate({ ...COLD, battery_beats_baseline_pct: 4.9 }).fired.map((f) => f.id)).toEqual([]);
    expect(umbrella.evaluate({ ...COLD, battery_beats_baseline_pct: 5 }).fired.map((f) => f.id)).toEqual(["gepa-evolution"]);
    // P(refuted) calibration fires only on a scheduling plateau (improvement < epsilon)
    expect(umbrella.evaluate({ ...COLD, scheduling_window: [0.5, 0.52, 0.6] }).fired.map((f) => f.id)).toEqual([]);
    expect(umbrella.evaluate({ ...COLD, scheduling_window: [0.5, 0.5, 0.505] }).fired.map((f) => f.id)).toEqual([
      "p-refuted-calibration",
    ]);
    // cross-project promotion fires at >=2 committed projects
    expect(umbrella.evaluate({ ...COLD, projects_committed: 2 }).fired.map((f) => f.id)).toEqual(["cross-project-promotion"]);
    // minimap/timeline enhancement fires on replay usage
    expect(umbrella.evaluate({ ...COLD, replay_scrubs: 100 }).fired.map((f) => f.id)).toEqual(["minimap-timeline"]);
  });

  it("the loopx adapter fires on G1-G5 gains — and retires otherwise (executable, recorded)", () => {
    const umbrella = new LearningUmbrella(ledger);
    const gains = { g1: 0.2, g2: 0.15, g3: 0.1, g4: 0.25, g5: 0.1 };
    expect(umbrella.evaluate({ ...COLD, g1_g5_gains: gains }).fired.map((f) => f.id)).toEqual(["loopx-adapter"]);

    // below threshold → the adapter retires (清退, no indefinite reach); retirement is executable + audited
    const weak = { g1: 0.2, g2: 0.01, g3: 0.1, g4: 0.25, g5: 0.1 };
    umbrella.evaluate({ ...COLD, g1_g5_gains: weak });
    umbrella.retireLoopx("g2 gain below threshold over the observation window");
    expect(umbrella.isRetired("loopx-adapter")).toBe(true);
    const retired = ledger
      .graphEvents()
      .filter((e) => e.event_type === "provider.action")
      .filter((e) => (e.payload as Record<string, unknown>).provider === "learning-umbrella")
      .filter((e) => String((e.payload as Record<string, unknown>).target).startsWith("retire:"));
    expect(retired).toHaveLength(1);
    // a retired item can never start again
    expect(() => umbrella.start("loopx-adapter", { ...COLD, g1_g5_gains: gains })).toThrow(/retired/);
  });

  it("L1 upgrade is chained: it unlocks only after prior calibration has landed", () => {
    const umbrella = new LearningUmbrella(ledger);
    const plateau = { ...COLD, scheduling_window: [0.5, 0.5, 0.505] };
    expect(umbrella.evaluate(plateau).fired.map((f) => f.id)).toEqual(["p-refuted-calibration"]);
    expect(umbrella.evaluate({ ...plateau, prior_calibration_landed: true }).fired.map((f) => f.id).sort()).toEqual([
      "l1-upgrade",
      "p-refuted-calibration",
    ]);
  });

  it("learning-layer outputs stay prior-only (no policy learning) — auditable by design", () => {
    const umbrella = new LearningUmbrella(ledger);
    umbrella.recordOutput("p-refuted-calibration", {
      kind: "prior-calibration",
      target: "P(refuted)",
      adjustment: { source_baseline: "empirical-bayes", shift: -0.03 },
    });
    // calibration record is audited as an event
    const audited = ledger
      .graphEvents()
      .filter((e) => e.event_type === "provider.action")
      .filter((e) => String((e.payload as Record<string, unknown>).target).startsWith("output:"));
    expect(audited).toHaveLength(1);

    // policy-shaped output is rejected — calibrate priors only, never learn policy
    expect(() =>
      umbrella.recordOutput("p-refuted-calibration", {
        kind: "policy",
        action_weights: { "read-source": 0.8 },
      } as never),
    ).toThrow(/prior-only/);
  });

  it("fired items can start; the start is audited", () => {
    const umbrella = new LearningUmbrella(ledger);
    const hot = { ...COLD, experiments_count: 50 };
    umbrella.evaluate(hot);
    umbrella.start("cost-model", hot);
    const started = ledger
      .graphEvents()
      .filter((e) => e.event_type === "provider.action")
      .filter((e) => String((e.payload as Record<string, unknown>).target).startsWith("start:"));
    expect(started).toHaveLength(1);
  });
});
