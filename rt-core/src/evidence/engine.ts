/** Evidence engine L1-lite (issue #556, docs 01 贝叶斯证据引擎 L1).

The lite layer that already de-ranks conflicting sources:
- **Source registry** with provenance — origins.py promoted to reasoning input
  (the #547 sources table is the persistence).
- **Reliability point estimate** via weighted voting (lite stand-in for the
  earned posterior; full L1 lands later).
- **Independence collapse** over citation chains: sources citing other listed
  sources collapse to the independent root — near-duplicates never count as
  distinct evidence.
- **Quick-check layer**: new claims × evidence index cheap comparison;
  conflicts flagged inline at extraction time (A1 pipeline slot).

Incentive vectors / astroturfing: schema-ready fields only (behavior lands
with calibration, T4).
*/

import type { LedgerStore } from "../store/ledger.js";

export interface SourceInput {
  source_id: string;
  origin: string;
  kind: string;
  reliability: number;
  incentive_vector: string[];
  astroturf_flag: boolean;
  provenance: Record<string, unknown>;
}

export interface VerdictInput {
  source_id: string;
  verdict: "supports" | "refutes";
}

export interface PointEstimate {
  posterior: number;
  method: "weighted-vote";
  supports: number;
  refutes: number;
  independent_sources: number;
}

export interface QuickCheckFlag {
  conflict: boolean;
  against?: { source_id: string; verdict: string };
}

export class EvidenceEngine {
  constructor(private readonly ledger: LedgerStore) {}

  registerSource(taskId: string, payload: SourceInput): void {
    this.ledger.upsertSource(taskId, {
      source_id: payload.source_id,
      origin: payload.origin,
      kind: payload.kind,
      reliability: payload.reliability,
      incentive_vector: payload.incentive_vector,
      astroturf_flag: payload.astroturf_flag,
      provenance: payload.provenance,
    });
  }

  registerClaimEvidence(taskId: string, claimId: string, evidence: Array<{ source_id: string; verdict: string }>): void {
    for (const entry of evidence) {
      this.ledger.upsertClaim(taskId, {
        claim_id: `ev-${claimId}-${entry.source_id}`,
        text: `${entry.verdict}: ${claimId} per ${entry.source_id}`,
        source: "research",
        weight: "minor",
        posterior: entry.verdict === "supports" ? 0.9 : 0.1,
        verify_tier: "multi-source",
        kill_edges: [],
        incentive_flag: false,
      });
    }
  }

  /** Weighted-vote point estimate: reliability-weighted verdicts. */
  pointEstimate(taskId: string, verdicts: VerdictInput[]): PointEstimate {
    let supportWeight = 0;
    let refuteWeight = 0;
    let supports = 0;
    let refutes = 0;
    for (const verdict of verdicts) {
      const row = this.ledger.getSource(taskId, verdict.source_id);
      const reliability = row === null ? 0.5 : Number(row.reliability);
      if (verdict.verdict === "supports") {
        supportWeight += reliability;
        supports += 1;
      } else {
        refuteWeight += reliability;
        refutes += 1;
      }
    }
    const total = supportWeight + refuteWeight;
    const posterior = total === 0 ? 0.5 : supportWeight / total;
    return { posterior, method: "weighted-vote", supports, refutes, independent_sources: verdicts.length };
  }

  /** Independence collapse: sources citing other listed sources collapse to
   * the independent root — citation chains are one piece of evidence. */
  independenceRoots(taskId: string, sourceIds: string[]): string[] {
    // a source whose provenance cites another listed source's origin is a
    // citation — collapse it in favor of the independent root
    const cited = new Set<string>();
    for (const id of sourceIds) {
      const row = this.ledger.getSource(taskId, id);
      const provenance = (row?.provenance ?? {}) as { cites?: string };
      if (provenance.cites === undefined) {
        continue;
      }
      for (const other of sourceIds) {
        const otherRow = this.ledger.getSource(taskId, other);
        if (otherRow !== null && otherRow.origin === provenance.cites) {
          cited.add(id);
        }
      }
    }
    return sourceIds.filter((id) => !cited.has(id));
  }

  /** Quick-check: a new verdict against the claim's evidence index — inline
   * conflict flag (A1 pipeline slot). */
  quickCheck(taskId: string, claimId: string, incoming: { verdict: string; source_id: string }): QuickCheckFlag {
    const rows = this.ledger.listClaims(taskId).filter((row) =>
      String(row.claim_id).startsWith(`ev-${claimId}-`),
    );
    for (const row of rows) {
      const existingVerdict = String(row.text).split(":")[0] ?? "";
      if ((existingVerdict === "supports") !== (incoming.verdict === "supports")) {
        return { conflict: true, against: { source_id: String(row.claim_id).split("-").pop() ?? "", verdict: existingVerdict } };
      }
    }
    return { conflict: false };
  }

  /** Conflict index: count contradicting verdict pairs per claim. */
  conflictIndex(taskId: string, claimId: string): { conflicting_pairs: number } {
    const evidence = this.ledger.listClaims(taskId).filter((row) =>
      String(row.claim_id).startsWith(`ev-${claimId}-`),
    );
    let supports = 0;
    let refutes = 0;
    for (const row of evidence) {
      const text = String(row.text);
      if (text.startsWith("supports")) {
        supports += 1;
      } else if (text.startsWith("refutes")) {
        refutes += 1;
      }
    }
    return { conflicting_pairs: Math.min(supports, refutes) };
  }
}
