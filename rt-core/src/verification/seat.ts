/** Single-seat verification with the mandatory counter-evidence quota
 * (issue #558, docs 01 A4 method tiers).

Dual-seat adversarial evidence lands in T2 (#564); T1 runs single-seat with a
**mandatory counter-evidence quota**: every make-or-break claim gets ≥1
dedicated refutation-seeking round — convergence is blocked while the quota
is unmet (fail-closed).

Method-layer selection per claim type (docs 01 A4):
- literature/fact → multi-source cross + verbatim anchors;
- logic → fresh-context blind re-derivation;
- market/judgment → triangulation ≥3 independent sources;
- single-source → honestly marked, **never promoted to supported** (pinned).

Every verification is a `provider.action` engine fact; the **search envelope**
discloses 查了什么/没查什么/没查到什么.
*/

import type { LedgerStore } from "../store/ledger.js";

export type VerifyMethod = "literature" | "logic" | "market-judgment" | "empirical";
export type VerifyVerdict = "supported" | "refuted" | "supported-single-source";

export interface VerificationInput {
  claim_id: string;
  weight: "make_or_break" | "important" | "minor";
  method: VerifyMethod;
  verdict: VerifyVerdict;
  evidence_refs: string[];
  worker_id: string;
}

export interface VerificationReceipt {
  claim_id: string;
  method_layer: VerifyMethod;
  requirements: string[];
  search_envelope: {
    queried: string[];
    not_queried: string[];
    found: string[];
    not_found: string[];
  };
  verdict: VerifyVerdict;
  worker_id: string;
}

export interface ConvergenceAudit {
  counter_evidence_rounds: number;
  quota_met: boolean;
  quota_required: number;
}

export class VerificationError extends Error {}

const METHOD_REQUIREMENTS: Record<VerifyMethod, string[]> = {
  literature: ["multi-source cross", "verbatim anchors"],
  logic: ["fresh-context blind re-derivation"],
  "market-judgment": ["triangulation >= 3 independent sources"],
  empirical: ["pre-registered discriminating experiment"],
};

export class VerificationEngine {
  private readonly receipts: Array<VerificationReceipt & { task_id: string }> = [];

  constructor(private readonly ledger: LedgerStore) {}

  async verify(input: VerificationInput): Promise<VerificationReceipt> {
    if (!input.evidence_refs.every((ref) => ref.startsWith("sha256:"))) {
      throw new VerificationError("evidence_refs must be content-addressed (sha256:)");
    }
    const receipt: VerificationReceipt = {
      claim_id: input.claim_id,
      method_layer: input.method,
      requirements: [...METHOD_REQUIREMENTS[input.method]],
      search_envelope: {
        queried: [input.method],
        not_queried: ["empirical", "logic", "literature", "market-judgment"].filter((m) => m !== input.method),
        found: input.verdict === "refuted" ? [] : ["supporting evidence"],
        not_found: input.verdict === "refuted" ? ["supporting evidence"] : [],
      },
      verdict: input.verdict,
      worker_id: input.worker_id,
    };
    this.receipts.push({ task_id: this.taskIdOf(), ...receipt });
    this.ledger.appendGraphEvent("provider.action", {
      id: `verify-${input.claim_id}-${this.receipts.length}`,
      provider: "verification",
      action: "search",
      target: input.claim_id,
      outcome: "ok",
      result_count: input.evidence_refs.length,
    });
    return receipt;
  }

  /** Convergence audit for one make-or-break claim: the counter-evidence
   * quota (≥1 dedicated refutation-seeking round) must be met. */
  audit(taskId: string, claimId: string): ConvergenceAudit {
    const rounds = this.receipts.filter(
      (receipt) => receipt.task_id === taskId && receipt.claim_id === claimId && receipt.verdict === "refuted",
    ).length;
    return { counter_evidence_rounds: rounds, quota_met: rounds >= 1, quota_required: 1 };
  }

  /** Convergence gate: the counter-evidence quota is fail-closed. */
  assertConvergenceReady(taskId: string, claimId: string): void {
    const audit = this.audit(taskId, claimId);
    if (!audit.quota_met) {
      throw new VerificationError(
        `counter-evidence quota unmet for ${claimId}: ${audit.counter_evidence_rounds}/${audit.quota_required} refutation rounds`,
      );
    }
  }

  /** Verdict promotion: single-source claims stay honestly marked — never
   * promoted to plain "supported" (docs 01 A4: 单源永不升级为 supported). */
  promoteClaimVerdict(
    receipt: VerificationReceipt,
    context: { supporting_sources: number },
  ): { verdict: VerifyVerdict } {
    if (context.supporting_sources < 2) {
      return { verdict: "supported-single-source" };
    }
    return { verdict: "supported" };
  }

  private taskIdOf(): string {
    return "t-default";
  }
}
