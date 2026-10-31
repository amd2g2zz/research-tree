/** Thompson direction sampling (issue #568, docs 01 §方向策略).

Direction-level portfolio management on top of the #547 directions table and
the #557 EVSI selector. Mechanical rules only:

- **Closed direction sources** (structured generation): hypothesis-ledger
  candidates, kill-graph branches, refuted variants, survivor-adjacency
  extensions. Hard cap 8 arms — the 9th direction parks (pinned), it never
  displaces an arm.
- **Four-signal arm value posterior**: kill-survival rate, evidence yield,
  decision leverage (kill-graph centrality), surprise (KL vs prior) — pooled
  into a Beta posterior whose mean is the persisted value_posterior.
- **Allocation**: each round every arm is sampled from its posterior (seeded,
  reproducible); the whole round budget goes to the sampled highest.
  Exploration/exploitation emerges from the sampling, no hand-tuned rules.
- **Triggers**: deepen when a make-or-break hangs near 0.5 (a cheap experiment
  can flip the global verdict); widen when every arm's EVSI is below the
  floor. Widen budget is STRUCTURALLY capped at 30% of the cumulative run
  budget — divergence is prevented by budget structure, not willpower.
- **Portfolio panel** at round boundaries: directions × value posterior ×
  allocation, every allocation traceable to the four signals in history.
*/

import { LedgerStore } from "../store/ledger.js";

export const DIRECTION_SOURCES = [
  "hypothesis-ledger",
  "kill-graph-branch",
  "refuted-variant",
  "survivor-adjacency",
] as const;

export type DirectionSource = (typeof DIRECTION_SOURCES)[number];

export const ARM_HARD_CAP = 8;
export const WIDEN_SHARE_CAP = 0.3;
/** pseudo-count strength of the Beta prior over arm value */
const POSTERIOR_KAPPA = 8;

export interface DirectionCandidate {
  direction_id: string;
  source: DirectionSource;
}

export interface ArmSignals {
  direction_id: string;
  /** attacked-and-survived rate of the direction's load-bearing claims */
  kill_survival: number;
  /** normalized evidence production (G3-like) */
  evidence_yield: number;
  /** kill-graph centrality, normalized */
  leverage: number;
  /** KL divergence vs the prior, normalized */
  surprise: number;
}

export interface RegisterResult {
  accepted: Array<Record<string, unknown>>;
  parked: Array<Record<string, unknown>>;
}

export interface RoundDecision {
  mode: "deepen" | "widen" | "hold";
  reason: string;
}

export interface RoundAllocation {
  round: number;
  winner: string;
  samples: Record<string, number>;
  allocation: Record<string, number>;
  mode: RoundDecision["mode"];
  /** portion of this round's budget earmarked as widen spend (cap-enforced) */
  widen_used: number;
}

export interface PortfolioPanel {
  round: number;
  arms: Array<{
    direction_id: string;
    value_posterior: number;
    allocation: number;
    source: DirectionSource;
    parked: boolean;
  }>;
  lines: string[];
}

export class DirectionSamplerError extends Error {}

/** mulberry32 — small seeded PRNG so allocation is reproducible from the seed. */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function standardNormal(rng: () => number): number {
  const u1 = Math.max(rng(), Number.EPSILON);
  const u2 = rng();
  return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
}

/** Marsaglia-Tsang gamma sampling; supports shape < 1 via the boost trick. */
function sampleGamma(shape: number, rng: () => number): number {
  if (shape < 1) {
    const u = Math.max(rng(), Number.EPSILON);
    return sampleGamma(shape + 1, rng) * Math.pow(u, 1 / shape);
  }
  const d = shape - 1 / 3;
  const c = 1 / Math.sqrt(9 * d);
  for (;;) {
    const x = standardNormal(rng);
    const v = Math.pow(1 + c * x, 3);
    if (v <= 0) {
      continue;
    }
    const u = Math.max(rng(), Number.EPSILON);
    if (Math.log(u) < 0.5 * x * x + d - d * v + d * Math.log(v)) {
      return d * v;
    }
  }
}

function sampleBeta(alpha: number, beta: number, rng: () => number): number {
  const x = sampleGamma(alpha, rng);
  const y = sampleGamma(beta, rng);
  return x / (x + y);
}

function fourSignalMean(s: Omit<ArmSignals, "direction_id">): number {
  const mean = (s.kill_survival + s.evidence_yield + s.leverage + s.surprise) / 4;
  return Math.min(0.95, Math.max(0.05, mean));
}

interface ArmState {
  direction_id: string;
  source: DirectionSource;
  value_posterior: number;
  alpha: number;
  beta: number;
  budget_allocation: number;
  parked: boolean;
  history: Array<Record<string, unknown>>;
}

export class DirectionSampler {
  private readonly widenSpend = new Map<string, number>();
  private readonly totalSpend = new Map<string, number>();

  constructor(private readonly ledger: LedgerStore) {}

  registerDirections(taskId: string, candidates: DirectionCandidate[]): RegisterResult {
    const accepted: Array<Record<string, unknown>> = [];
    const parked: Array<Record<string, unknown>> = [];
    for (const candidate of candidates) {
      if (!DIRECTION_SOURCES.includes(candidate.source)) {
        throw new DirectionSamplerError(
          `direction source "${String(candidate.source)}" is not one of the closed sources (${DIRECTION_SOURCES.join(", ")})`,
        );
      }
    }
    for (const candidate of candidates) {
      if (accepted.length < ARM_HARD_CAP) {
        const row = this.ledger.upsertDirection(taskId, {
          direction_id: candidate.direction_id,
          round: 0,
          value_posterior: 0.5,
          budget_allocation: 0,
          history: [{ status: "registered", source: candidate.source }],
        });
        accepted.push(row);
      } else {
        const row = this.ledger.upsertDirection(taskId, {
          direction_id: candidate.direction_id,
          round: 0,
          value_posterior: 0,
          budget_allocation: 0,
          history: [{ status: "parked", source: candidate.source }],
        });
        parked.push(row);
      }
    }
    return { accepted, parked };
  }

  updateArm(taskId: string, signals: ArmSignals): Record<string, unknown> {
    const row = this.ledger.getDirection(taskId, signals.direction_id);
    if (!row) {
      throw new DirectionSamplerError(`unknown direction "${signals.direction_id}"`);
    }
    const history = (row.history as Array<Record<string, unknown>>) ?? [];
    if (history.at(-1)?.status === "parked") {
      throw new DirectionSamplerError(`direction "${signals.direction_id}" is parked and cannot receive signals`);
    }
    const mean = fourSignalMean(signals);
    const alpha = POSTERIOR_KAPPA * mean;
    const beta = POSTERIOR_KAPPA * (1 - mean);
    return this.ledger.upsertDirection(taskId, {
      direction_id: signals.direction_id,
      round: Number(row.round ?? 0),
      value_posterior: mean,
      budget_allocation: Number(row.budget_allocation ?? 0),
      history: [
        ...history,
        {
          status: "signal",
          signals: {
            kill_survival: signals.kill_survival,
            evidence_yield: signals.evidence_yield,
            leverage: signals.leverage,
            surprise: signals.surprise,
          },
          alpha,
          beta,
          posterior_mean: mean,
        },
      ],
    });
  }

  decideRound(taskId: string, options: { make_or_break_posterior?: number; arm_evsis?: number[]; evsi_floor?: number } = {}): RoundDecision {
    if (options.arm_evsis !== undefined && options.arm_evsis.length > 0) {
      const floor = options.evsi_floor ?? 0;
      if (options.arm_evsis.every((evsi) => evsi < floor)) {
        return { mode: "widen", reason: "all-arm EVSI below threshold — widen the direction set" };
      }
    }
    const mob = options.make_or_break_posterior;
    if (mob !== undefined && mob >= 0.4 && mob <= 0.6) {
      return { mode: "deepen", reason: "make-or-break hanging near 0.5 — a cheap experiment can flip the verdict" };
    }
    return { mode: "hold", reason: "no trigger fired" };
  }

  allocateRound(taskId: string, round: number, options: { seed: number; round_budget: number; mode?: RoundDecision["mode"] }): RoundAllocation {
    const arms = this.loadArms(taskId).filter((arm) => !arm.parked);
    if (arms.length === 0) {
      throw new DirectionSamplerError("no active arms to allocate");
    }
    const rng = mulberry32(options.seed);
    const samples: Record<string, number> = {};
    for (const arm of arms) {
      samples[arm.direction_id] = sampleBeta(arm.alpha, arm.beta, rng);
    }
    const winner = Object.entries(samples).reduce(
      (best, [id, value]) => (value > (samples[best] ?? 0) ? id : best),
      Object.keys(samples)[0]!,
    );

    // widen earmark: structurally capped at WIDEN_SHARE_CAP of cumulative spend
    const mode = options.mode ?? "hold";
    const totalBefore = this.totalSpend.get(taskId) ?? 0;
    const widenBefore = this.widenSpend.get(taskId) ?? 0;
    let widenUsed = 0;
    if (mode === "widen") {
      widenUsed = Math.max(0, Math.min(options.round_budget, WIDEN_SHARE_CAP * (totalBefore + options.round_budget) - widenBefore));
    }
    this.totalSpend.set(taskId, totalBefore + options.round_budget);
    this.widenSpend.set(taskId, widenBefore + widenUsed);

    const allocation: Record<string, number> = {};
    for (const arm of arms) {
      allocation[arm.direction_id] = arm.direction_id === winner ? options.round_budget : 0;
    }
    this.persistRound(taskId, round, winner, samples, allocation, mode, widenUsed);
    return { round, winner, samples, allocation, mode, widen_used: widenUsed };
  }

  renderPortfolioPanel(taskId: string, round: number): PortfolioPanel {
    const arms = this.loadArms(taskId);
    const lines = arms.map((arm) => {
      const state = arm.parked ? "parked" : `posterior=${arm.value_posterior.toFixed(3)} allocation_share=${arm.budget_allocation.toFixed(2)}`;
      return `${arm.direction_id} [${arm.source}] ${state}`;
    });
    return {
      round,
      arms: arms.map((arm) => ({
        direction_id: arm.direction_id,
        value_posterior: arm.value_posterior,
        allocation: arm.budget_allocation,
        source: arm.source,
        parked: arm.parked,
      })),
      lines,
    };
  }

  private loadArms(taskId: string): ArmState[] {
    return this.ledger.listDirections(taskId).map((row) => {
      const history = (row.history as Array<Record<string, unknown>>) ?? [];
      const lastSignal = [...history].reverse().find((entry) => entry.status === "signal");
      const alpha = Number(lastSignal?.alpha ?? POSTERIOR_KAPPA / 2);
      const beta = Number(lastSignal?.beta ?? POSTERIOR_KAPPA / 2);
      const lastRound = [...history].reverse().find((entry) => entry.status === "round");
      return {
        direction_id: String(row.direction_id),
        source: (lastRound?.source ?? history[0]?.source ?? "hypothesis-ledger") as DirectionSource,
        value_posterior: Number(row.value_posterior ?? 0.5),
        alpha,
        beta,
        budget_allocation: Number(row.budget_allocation ?? 0),
        parked: history.at(-1)?.status === "parked",
        history,
      };
    });
  }

  private persistRound(
    taskId: string,
    round: number,
    winner: string,
    samples: Record<string, number>,
    allocation: Record<string, number>,
    mode: RoundDecision["mode"],
    widenUsed: number,
  ): void {
    for (const row of this.ledger.listDirections(taskId)) {
      const directionId = String(row.direction_id);
      const history = (row.history as Array<Record<string, unknown>>) ?? [];
      const isWinner = directionId === winner;
      const parked = history.at(-1)?.status === "parked";
      if (parked) {
        continue;
      }
      this.ledger.upsertDirection(taskId, {
        direction_id: directionId,
        round,
        value_posterior: Number(row.value_posterior ?? 0.5),
        budget_allocation: isWinner ? 1 : 0,
        history: [
          ...history,
          {
            status: "round",
            round,
            sampled: Number(samples[directionId]?.toFixed(6) ?? 0),
            allocation_share: isWinner ? 1 : 0,
            allocation_budget: allocation[directionId] ?? 0,
            mode,
            widen_used: isWinner ? widenUsed : 0,
            winner: isWinner,
          },
        ],
      });
    }
  }
}
