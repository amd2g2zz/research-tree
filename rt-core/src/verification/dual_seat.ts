/** Adversarial dual-seat (issue #564, docs 01 A4 对抗搜索).

make-or-break claims get **dual-seat evidence**: a plaintiff agent seeking
only counter-evidence, a defense agent seeking only support — **equal
budgets**, EVSI settled **independently** per seat, **attack goes first**
(先攻后守). Non-make-or-break claims stay single-seat with the counter-
evidence quota (#558).

Every seat report is a `provider.action` engine fact (the audit trail).
Posterior shift: the seats' findings combine into a direction + discovery
rate (refutation discovery rate is the H2-adjacent metric).
*/

import type { LedgerStore } from "../store/ledger.js";

export interface SeatReport {
  seat: "plaintiff" | "defense";
  worker_id: string;
  budget_ms: number;
  counter_evidence_found: boolean;
  evidence_refs: string[];
  evsi_settlement: number;
}

export interface PosteriorShift {
  direction: "toward-refutation" | "toward-support" | "unchanged";
  counter_evidence_discovery_rate: number;
}

export interface DualSeatResult {
  plaintiff: SeatReport;
  defense: SeatReport;
  settlement: "independent";
  posterior_shift: PosteriorShift;
}

export interface DualSeatOptions {
  plaintiffWorker: string;
  defenseWorker: string;
  budgetPerSeat: number;
  plaintiffFindings?: { counter_evidence_found: boolean; evidence_refs: string[] };
  defenseFindings?: { counter_evidence_found: boolean; evidence_refs: string[] };
  onSeatStart?: (seat: "plaintiff" | "defense") => void;
}

export class DualSeatEngine {
  constructor(private readonly ledger: LedgerStore) {}

  /** Only make-or-break claims run dual-seat (cost control: 双席成本翻倍 —
   * the risk-register mitigation). */
  shouldRunDualSeat(claimId: string, makeOrBreakIds: string[]): boolean {
    return makeOrBreakIds.includes(claimId);
  }

  runDualSeat(taskId: string, claimId: string, options: DualSeatOptions): DualSeatResult {
    const findings = {
      plaintiff: options.plaintiffFindings ?? { counter_evidence_found: false, evidence_refs: [] },
      defense: options.defenseFindings ?? { counter_evidence_found: false, evidence_refs: [] },
    };

    // attack goes first (先攻后守)
    options.onSeatStart?.("plaintiff");
    const plaintiff = this.buildSeat("plaintiff", options.plaintiffWorker, options.budgetPerSeat, findings.plaintiff);
    this.auditSeat(taskId, claimId, plaintiff);

    options.onSeatStart?.("defense");
    const defense = this.buildSeat("defense", options.defenseWorker, options.budgetPerSeat, findings.defense);
    this.auditSeat(taskId, claimId, defense);

    return {
      plaintiff,
      defense,
      settlement: "independent",
      posterior_shift: this.computeShift(findings),
    };
  }

  private buildSeat(
    seat: "plaintiff" | "defense",
    workerId: string,
    budgetMs: number,
    findings: { counter_evidence_found: boolean; evidence_refs: string[] },
  ): SeatReport {
    return {
      seat,
      worker_id: workerId,
      budget_ms: budgetMs,
      counter_evidence_found: findings.counter_evidence_found,
      evidence_refs: findings.evidence_refs,
      // EVSI settlement per seat: counter-evidence found → high info gain
      evsi_settlement: findings.counter_evidence_found ? 0.8 : 0.1,
    };
  }

  private auditSeat(taskId: string, claimId: string, seat: SeatReport): void {
    this.ledger.appendGraphEvent("provider.action", {
      id: `dual-seat-${seat.seat}-${Date.now()}`,
      provider: `dual-seat-${seat.seat}`,
      action: "search",
      target: `${taskId}/${claimId}`,
      outcome: "ok",
      result_count: seat.evidence_refs.length,
    });
  }

  private computeShift(findings: {
    plaintiff: { counter_evidence_found: boolean; evidence_refs: string[] };
    defense: { counter_evidence_found: boolean; evidence_refs: string[] };
  }): PosteriorShift {
    const plaintiffFound = findings.plaintiff.counter_evidence_found;
    const defenseFound = findings.defense.counter_evidence_found;
    const discoveryRate = (plaintiffFound ? 0.5 : 0) + (defenseFound ? 0.5 : 0);
    let direction: PosteriorShift["direction"] = "unchanged";
    if (plaintiffFound && !defenseFound) {
      direction = "toward-refutation";
    } else if (defenseFound && !plaintiffFound) {
      direction = "toward-support";
    }
    return { direction, counter_evidence_discovery_rate: discoveryRate };
  }
}
