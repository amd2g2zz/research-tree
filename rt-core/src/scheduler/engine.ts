/** Recursive stage DAG scheduler (issue #550, docs 01 偏航 + 02 §递归阶段化).

A **Stage is a kill-graph factor cluster**. The open-loop condition rolls a
stage up (已决 ∥ EVSI 饱和 ∥ 预算尽 → ROLLUP + belief propagation); unsatisfied
stages factorize and drill down. Belief propagation is **append-only**:
a refuted premise reopens descendants (stale) — 翻案靠重开不靠删除.

Dispatch is **dependency-aware ready-set cutting** (≤4 concurrent workers,
task-level retry, stage-level park) — the mechanically testable inversion of
the #531 greedy-cut failure mode: a stage whose dependencies are not closed
never dispatches. The global 12h hard cap forces convergence with a PARK
fallback (never hangs). Orphan threads park — the critical path never blocks.

EVSI: the scorer signature is fixed to the 01 A3 shape (EVSI/cost per claim);
the T0 implementation is a placeholder — the real selector lands with #557
(`TODO(issue-557)`); tests pin the signature so the swap is drop-in.

Pure functions over a plain state model — the state machine (#551) owns the
wiring to the ledger and the graph projection.
*/

import { VERDICTS } from "../events/schema.js";

export type ClaimLifecycle = "undecided" | "decided" | "refuted" | "stale";
export type StageStatus = "open" | "in_progress" | "rolled_up" | "parked";
export type WorkerClass = "retrieval" | "code-reading" | "experiment" | "verification";

export interface ClaimState {
  id: string;
  state: ClaimLifecycle;
  posterior: number;
  /** kill-graph premise links: this claim stands on these claims */
  depends_on_claims?: string[];
  /** append-only reopen counter (翻案靠重开) */
  reopen_count?: number;
}

export interface StageState {
  id: string;
  title: string;
  status: StageStatus;
  claim_ids: string[];
  /** scheduling dependencies: other stage ids that must be rolled up first */
  depends_on?: string[];
  retries?: number;
  max_retries?: number;
  assigned_worker_class?: WorkerClass;
}

export interface StageDecision {
  action: "drill-down" | "rollup" | "park";
  reason: "all-decided" | "evsi-saturated" | "budget-exhausted" | "has-signal" | "retries-exhausted";
}

export interface StageContext {
  budgetRemainingMs: number;
  /** EVSI/cost scorer per claim — placeholder until #557 (signature pinned) */
  evsi: (claimId: string) => number;
  /** EVSI saturation threshold (all-arm scores below → nothing to learn) */
  saturationThreshold?: number;
}

export interface GlobalCapCheck {
  forced: boolean;
  fallback_verdict?: (typeof VERDICTS)[number];
}

const EVSI_SATURATED = 0.05;
const DEFAULT_MAX_RETRIES = 3;

/** Open-loop condition for one stage. */
export function evaluateStage(
  stage: StageState,
  claims: ClaimState[],
  context: StageContext,
): StageDecision {
  const byId = new Map(claims.map((claim) => [claim.id, claim]));
  const stageClaims = stage.claim_ids
    .map((id) => byId.get(id))
    .filter((claim): claim is ClaimState => claim !== undefined);

  // vacuous truth: a stage with no open claims has nothing left to decide
  if (stageClaims.every((claim) => claim.state === "decided")) {
    return { action: "rollup", reason: "all-decided" };
  }
  if (context.budgetRemainingMs <= 0) {
    return { action: "rollup", reason: "budget-exhausted" };
  }
  const threshold = context.saturationThreshold ?? EVSI_SATURATED;
  const scores = stageClaims.map((claim) => context.evsi(claim.id));
  if (stageClaims.length > 0 && scores.every((score) => score < threshold)) {
    return { action: "rollup", reason: "evsi-saturated" };
  }
  return { action: "drill-down", reason: "has-signal" };
}

/** Belief propagation: a refuted premise reopens (marks stale, append-only)
 * every descendant claim — 翻案靠重开不靠删除. Unrelated claims are untouched. */
export function propagateRefutation(claims: ClaimState[], refutedId: string): ClaimState[] {
  const byId = new Map(claims.map((claim) => [claim.id, { ...claim }]));
  const dependents = new Map<string, string[]>();
  for (const claim of byId.values()) {
    for (const premise of claim.depends_on_claims ?? []) {
      dependents.set(premise, [...(dependents.get(premise) ?? []), claim.id]);
    }
  }
  const queue = [refutedId];
  while (queue.length > 0) {
    const current = queue.shift()!;
    for (const childId of dependents.get(current) ?? []) {
      const child = byId.get(childId);
      if (child === undefined || child.state === "stale") {
        continue;
      }
      child.state = "stale";
      child.reopen_count = (child.reopen_count ?? 0) + 1;
      queue.push(childId);
    }
  }
  return [...byId.values()];
}

/** Global 12h hard cap: forced convergence + PARK fallback (never hangs). */
export function checkGlobalCap(input: { elapsedMs: number; capMs: number }): GlobalCapCheck {
  if (input.elapsedMs >= input.capMs) {
    return { forced: true, fallback_verdict: "PARK" };
  }
  return { forced: false };
}

/** Dependency-aware ready-set dispatch: stages whose dependencies are all
 * rolled up (or none) and that still have budget of retries, cut to the
 * concurrency limit with worker classes assigned round-robin. Stages that
 * exhausted retries park here (never block the critical path). */
export function selectDispatchable(
  stages: StageState[],
  options: { maxConcurrency: number; workerClasses: WorkerClass[] },
): StageState[] {
  const statusById = new Map(stages.map((stage) => [stage.id, stage.status] as const));
  const ready: StageState[] = [];
  for (const stage of stages) {
    if (stage.status === "parked" || stage.status === "rolled_up") {
      continue;
    }
    const maxRetries = stage.max_retries ?? DEFAULT_MAX_RETRIES;
    if ((stage.retries ?? 0) >= maxRetries) {
      stage.status = "parked"; // orphan threads park, never block the critical path
      continue;
    }
    const dependenciesClosed = (stage.depends_on ?? []).every(
      (dependency) => statusById.get(dependency) === "rolled_up",
    );
    if (dependenciesClosed && ready.length < options.maxConcurrency) {
      const index = ready.length;
      stage.assigned_worker_class = options.workerClasses[index % options.workerClasses.length]!;
      ready.push(stage);
    }
  }
  return ready;
}
