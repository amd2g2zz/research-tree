/** Trigger-driven umbrella (issue #577, T4, docs 01 L5).

The learning layer is built ONLY when its trigger fires — never on a
calendar. Each item carries its own mechanical trigger predicate evaluated
against accumulated telemetry; a dormant item refuses to start. The scope
axiom is enforced mechanically: **calibrate priors only, never learn policy
end-to-end** — outputs are prior-shaped calibration records, audited into the
hash-chained event log (auditable by design).

Items (docs 01 L5 + roadmap T4):
- p-refuted-calibration — trigger: scheduling quality plateaus
- gepa-evolution        — trigger: battery beats baseline ≥5%
- cost-model            — trigger: ≥50 experiments accumulated
- loopx-adapter         — trigger: G1-G5 gain thresholds met; otherwise
                          **retire** (清退, no indefinite reach — executable)
- cross-project-promotion — trigger: ≥2 committed projects
- minimap-timeline      — trigger: replay usage (≥100 scrubs)
- l1-upgrade            — trigger: chained — prior calibration landed
*/

import type { LedgerStore } from "../store/ledger.js";

export interface TriggerData {
  experiments_count: number;
  battery_beats_baseline_pct: number | null;
  /** recent scheduling-quality window (normalized 0..1 per epoch) */
  scheduling_window: number[];
  scheduling_improvement_epsilon: number;
  /** G1-G5 gains, or null when the loopx adapter has no observation window */
  g1_g5_gains: Record<string, number> | null;
  projects_committed: number;
  replay_scrubs: number;
  /** chained trigger: has prior calibration landed? */
  prior_calibration_landed: boolean;
}

export interface UmbrellaItem {
  id: string;
  trigger: (data: TriggerData) => boolean;
  reason: string;
}

export interface UmbrellaReport {
  fired: Array<{ id: string; reason: string }>;
  dormant: Array<{ id: string; reason: string }>;
}

export class UmbrellaError extends Error {}

const LOOPX_GAIN_THRESHOLD = 0.05;
const PRIOR_ONLY_KINDS = ["prior-calibration"] as const;

export const DEFAULT_ITEMS: UmbrellaItem[] = [
  {
    id: "p-refuted-calibration",
    trigger: (d) => plateau(d.scheduling_window, d.scheduling_improvement_epsilon),
    reason: "scheduling quality plateau — supervised calibration over ledger history + empirical-Bayes baselines",
  },
  {
    id: "gepa-evolution",
    trigger: (d) => d.battery_beats_baseline_pct !== null && d.battery_beats_baseline_pct >= 5,
    reason: "battery beats baseline by ≥5% — GEPA-style prompt evolution earns its build",
  },
  {
    id: "cost-model",
    trigger: (d) => d.experiments_count >= 50,
    reason: "≥50 experiments accumulated — bandit-BO cost model has data",
  },
  {
    id: "loopx-adapter",
    trigger: (d) =>
      d.g1_g5_gains !== null && Object.values(d.g1_g5_gains).every((gain) => gain >= LOOPX_GAIN_THRESHOLD),
    reason: "G1-G5 gain thresholds met — otherwise the adapter retires (清退)",
  },
  {
    id: "cross-project-promotion",
    trigger: (d) => d.projects_committed >= 2,
    reason: "≥2 committed projects — compounding across projects has material",
  },
  {
    id: "minimap-timeline",
    trigger: (d) => d.replay_scrubs >= 100,
    reason: "replay usage earned the minimap/timeline enhancement",
  },
  {
    id: "l1-upgrade",
    trigger: (d) => d.prior_calibration_landed,
    reason: "prior calibration landed — L1 upgrade (earned reliability posteriors, incentive vectors, astroturfing)",
  },
];

function plateau(window: number[], epsilon: number): boolean {
  if (window.length < 2) {
    return false;
  }
  const improvement = window[window.length - 1]! - window[0]!;
  return Math.abs(improvement) < epsilon;
}

export class LearningUmbrella {
  private readonly retired = new Set<string>();

  constructor(private readonly ledger: LedgerStore) {}

  /** Per-item gating: fired items may start; dormant items refuse. */
  evaluate(data: TriggerData): UmbrellaReport {
    const fired: UmbrellaReport["fired"] = [];
    const dormant: UmbrellaReport["dormant"] = [];
    for (const item of DEFAULT_ITEMS) {
      if (this.retired.has(item.id)) {
        dormant.push({ id: item.id, reason: "retired (清退)" });
      } else if (item.trigger(data)) {
        fired.push({ id: item.id, reason: item.reason });
      } else {
        dormant.push({ id: item.id, reason: item.reason });
      }
    }
    this.audit("evaluate", `fired=[${fired.map((f) => f.id).join(",")}] dormant=${dormant.length}`);
    return { fired, dormant };
  }

  /** No item starts before its trigger fires. */
  start(itemId: string, data: TriggerData): void {
    const item = DEFAULT_ITEMS.find((candidate) => candidate.id === itemId);
    if (item === undefined) {
      throw new UmbrellaError(`unknown umbrella item: ${itemId}`);
    }
    if (this.retired.has(itemId)) {
      throw new UmbrellaError(`item is retired and cannot start: ${itemId}`);
    }
    if (!item.trigger(data)) {
      throw new UmbrellaError(`trigger has not fired for ${itemId} — no item starts before its trigger fires`);
    }
    this.audit("start", itemId);
  }

  /** Executable retirement (清退): the adapter leaves the registry, audited. */
  retireLoopx(reason: string): void {
    this.retired.add("loopx-adapter");
    this.audit("retire", `loopx-adapter: ${reason}`);
  }

  isRetired(itemId: string): boolean {
    return this.retired.has(itemId);
  }

  /** Scope axiom, enforced: learning outputs are prior-shaped calibration
   * records — policy-shaped output is rejected before it can land. */
  recordOutput(itemId: string, output: { kind: string; [key: string]: unknown }): void {
    if (!(PRIOR_ONLY_KINDS as readonly string[]).includes(output.kind)) {
      throw new UmbrellaError(
        `learning-layer output must stay prior-only (kind ∈ ${PRIOR_ONLY_KINDS.join("|")}); policy learning is excluded by the scope axiom`,
      );
    }
    this.audit("output", `${itemId}: ${output.kind} ${JSON.stringify(output.adjustment ?? {})}`);
  }

  private audit(action: string, target: string): void {
    this.ledger.appendGraphEvent("provider.action", {
      id: `umbrella-${action}-${Date.now()}`,
      provider: "learning-umbrella",
      action: "report",
      target: `${action}:${target}`,
      outcome: "ok",
    });
  }
}
