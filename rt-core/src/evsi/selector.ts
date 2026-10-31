/** A3 unified EVSI action selection (issue #557, docs 01 A3).

"再读一篇论文还是跑五分钟 benchmark" is decided by ONE formula: EVSI/cost.
Candidate actions are scored uniformly; the highest EVSI/cost ratio wins —
except make-or-break claims, which always go first (early kill saves the
most). Every selection is replayable: the candidate table, the scores, the
chosen action, and the hindsight regret gap are disclosed.

The T0 scorer is the interface + selection mechanics; the EVSI estimation
itself is a pluggable scorer (the mock-e2e harness injects one; the real
estimator lands with the evidence-engine calibration).

TODO(issue-557 acceptance note): experiment tier-k actions are slotted but
gated off until T2 (#567).
*/

export interface ActionCandidate {
  action_id: string;
  claim_id: string;
  /** expected value of sample information (information gain) */
  evsi: number;
  /** cost units (money, latency, quota — caller-normalized) */
  cost: number;
  kind: "read-source" | "cross-check" | "ask-user" | "re-derive" | "experiment";
}

export interface ActionReplay {
  chosen: string;
  candidates: Array<{ action_id: string; evsi: number; cost: number; evsi_per_cost: number; is_make_or_break: boolean }>;
  /** hindsight-best action by EVSI/cost (regret disclosure) */
  hindsight_best: string;
}

export interface ActionDecision {
  action_id: string;
  claim_id: string;
  evsi_per_cost: number;
  replay: ActionReplay;
}

export class EVSIError extends Error {}

function isMakeOrBreak(candidate: ActionCandidate, makeOrBreakIds: string[]): boolean {
  return makeOrBreakIds.includes(candidate.claim_id);
}

/** Select the next action by EVSI/cost; make-or-break claims first. */
export function selectAction(
  candidates: ActionCandidate[],
  options: { makeOrBreakIds: string[]; claimId?: string },
): ActionDecision | null {
  if (candidates.length === 0) {
    return null;
  }
  const scored = candidates.map((candidate) => ({
    candidate,
    evsi_per_cost: candidate.cost > 0 ? candidate.evsi / candidate.cost : Number.NaN,
    is_make_or_break: isMakeOrBreak(candidate, options.makeOrBreakIds),
  }));
  for (const entry of scored) {
    if (Number.isNaN(entry.evsi_per_cost)) {
      // zero-cost actions are rejected: nothing is free (guard vs div-by-zero
      // picking a degenerate winner)
      throw new EVSIError(`zero-cost candidate rejected: ${entry.candidate.action_id} (cost must be > 0)`);
    }
  }
  const mob = scored.filter((entry) => entry.is_make_or_break);
  const pool = mob.length > 0 ? mob : scored;
  const best = pool.reduce((a, b) => (b.evsi_per_cost > a.evsi_per_cost ? b : a));
  const hindsightBest = scored.reduce((a, b) => (b.evsi_per_cost > a.evsi_per_cost ? b : a));
  return {
    action_id: best.candidate.action_id,
    claim_id: best.candidate.claim_id,
    evsi_per_cost: best.evsi_per_cost,
    replay: {
      chosen: best.candidate.action_id,
      candidates: scored.map((entry) => ({
        action_id: entry.candidate.action_id,
        evsi: entry.candidate.evsi,
        cost: entry.candidate.cost,
        evsi_per_cost: entry.evsi_per_cost,
        is_make_or_break: entry.is_make_or_break,
      })),
      hindsight_best: hindsightBest.candidate.action_id,
    },
  };
}
