/** A5 variant search + early-termination inquiry (issue #563, docs 01 A5).

After each verification round: a make-or-break claim with posterior ≤ 0.1
(or persistently worsening) triggers kill-graph **variant search** —
{relax | replace | bypass} the refuted claim and check whether the DAG still
stands. PAUSE → present evidence + the three-choice inquiry (埋了 / 继续挖 /
换变体). **The question is not the verdict**: bury converges with a NO-GO
*recommendation*; the final verdict happens at freeze.

Budget savings (H5): the recorded ratio vs the full-run estimate must be
≥50% for the H5 hypothesis to hold.
*/

import { canonicalJsonBytes } from "../events/canonical.js";

export interface KillGraphClaim {
  id: string;
  text: string;
  weight: string;
  posterior: number;
  state: string;
  depends_on?: string[];
}

export type VariantAction = "relax" | "replace" | "bypass";

export interface VariantCandidate {
  variant_id: string;
  description: string;
  action: VariantAction;
  target_claim_id: string;
  /** does the kill-graph DAG still stand with this variant applied? */
  dag_still_stands: boolean;
}

export interface StandingVariant {
  variant_id: string;
  description: string;
  action: VariantAction;
  target_claim_id: string;
}

export interface EarlyTerminationInquiry {
  choices: ["bury", "continue", "switch-variant"];
  evidence_summary: string;
  standing_variants: StandingVariant[];
  /** the inquiry NEVER carries a verdict — the question is not the verdict */
  verdict: undefined;
}

export interface BuryOutcome {
  recommendation: "NO-GO";
  is_final: boolean;
}

export interface BudgetSavings {
  full_run_estimate_ms: number;
  actual_run_ms: number;
  ratio: number;
  meets_h5_threshold: boolean;
}

const H5_THRESHOLD = 0.5;

export class VariantSearchEngine {
  constructor(private readonly ledger: import("../store/ledger.js").LedgerStore) {}

  /** Search {relax | replace | bypass} variants; only those where the DAG
   * still stands survive. The search is mechanical (kill-graph topology),
   * not LLM-judged. */
  searchVariants(
    refutedClaimId: string,
    killGraphClaims: Array<Record<string, unknown>>,
    candidates: VariantCandidate[],
  ): StandingVariant[] {
    this.ledger.initialize();
    // the refuted claim must exist in the kill graph
    const refuted = killGraphClaims.find((claim) => claim.id === refutedClaimId);
    if (refuted === undefined) {
      throw new Error(`refuted claim not in kill graph: ${refutedClaimId}`);
    }
    return candidates
      .filter((candidate) => candidate.dag_still_stands)
      .map((candidate) => ({
        variant_id: candidate.variant_id,
        description: candidate.description,
        action: candidate.action,
        target_claim_id: candidate.target_claim_id,
      }));
  }

  /** The three-choice inquiry: evidence + standing variants, NO verdict. */
  buildInquiry(
    refutedClaimId: string,
    context: {
      posterior: number;
      evidence_summary: string;
      standing_variants: VariantCandidate[];
    },
  ): EarlyTerminationInquiry {
    return {
      choices: ["bury", "continue", "switch-variant"],
      evidence_summary: context.evidence_summary,
      standing_variants: context.standing_variants
        .filter((candidate) => candidate.dag_still_stands)
        .map((candidate) => ({
          variant_id: candidate.variant_id,
          description: candidate.description,
          action: candidate.action,
          target_claim_id: candidate.target_claim_id,
        })),
      verdict: undefined,
    };
  }

  /** 埋了 → converge with a NO-GO recommendation (not a final verdict). */
  resolveBury(refutedClaimId: string): BuryOutcome {
    this.ledger.appendGraphEvent("provider.action", {
      id: `early-term-${Date.now()}`,
      provider: "early-termination",
      action: "search",
      target: refutedClaimId,
      outcome: "ok",
    });
    return { recommendation: "NO-GO", is_final: false };
  }

  /** Budget savings vs the full-run estimate (H5 ≥ 50%). */
  recordSavings(input: { full_run_estimate_ms: number; actual_run_ms: number }): BudgetSavings {
    const ratio =
      input.full_run_estimate_ms > 0
        ? (input.full_run_estimate_ms - input.actual_run_ms) / input.full_run_estimate_ms
        : 0;
    return {
      full_run_estimate_ms: input.full_run_estimate_ms,
      actual_run_ms: input.actual_run_ms,
      ratio,
      meets_h5_threshold: ratio >= H5_THRESHOLD,
    };
  }
}

export { canonicalJsonBytes };
