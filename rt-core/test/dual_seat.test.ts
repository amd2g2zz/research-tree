import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { DualSeatEngine, type SeatReport } from "../src/verification/dual_seat.js";
import { LedgerStore } from "../src/store/ledger.js";

let ledger: LedgerStore;

beforeEach(() => {
  ledger = new LedgerStore(mkdtempSync(join(tmpdir(), "rt-dual-")));
  ledger.initialize();
});

describe("adversarial dual-seat (issue #564)", () => {
  it("runs plaintiff and defense for a make-or-break claim with equal budgets", () => {
    const engine = new DualSeatEngine(ledger);
    const result = engine.runDualSeat("t1", "c-mob", {
      plaintiffWorker: "plaintiff-1",
      defenseWorker: "defense-1",
      budgetPerSeat: 5000,
    });
    expect(result.plaintiff.budget_ms).toBe(5000);
    expect(result.defense.budget_ms).toBe(5000);
    expect(result.plaintiff.worker_id).toBe("plaintiff-1");
    expect(result.defense.worker_id).toBe("defense-1");
  });

  it("attack goes first (先攻后守)", () => {
    const engine = new DualSeatEngine(ledger);
    const order: string[] = [];
    const result = engine.runDualSeat("t1", "c-mob", {
      plaintiffWorker: "p1",
      defenseWorker: "d1",
      budgetPerSeat: 5000,
      onSeatStart: (seat) => order.push(seat),
    });
    void result;
    expect(order).toEqual(["plaintiff", "defense"]);
  });

  it("EVSI settles each seat independently (budget per seat, not pooled)", () => {
    const engine = new DualSeatEngine(ledger);
    const result = engine.runDualSeat("t1", "c-mob", {
      plaintiffWorker: "p1",
      defenseWorker: "d1",
      budgetPerSeat: 5000,
      plaintiffFindings: { counter_evidence_found: true, evidence_refs: ["sha256:" + "a".repeat(64)] },
      defenseFindings: { counter_evidence_found: false, evidence_refs: [] },
    });
    expect(result.plaintiff.evsi_settlement).toBeGreaterThan(0); // found counter-evidence → high info gain
    expect(result.defense.evsi_settlement).toBeGreaterThanOrEqual(0);
    expect(result.settlement).toBe("independent");
  });

  it("combines seats into a posterior shift (refutation discovery rate)", () => {
    const engine = new DualSeatEngine(ledger);
    const result = engine.runDualSeat("t1", "c-mob", {
      plaintiffWorker: "p1",
      defenseWorker: "d1",
      budgetPerSeat: 5000,
      plaintiffFindings: { counter_evidence_found: true, evidence_refs: ["sha256:" + "a".repeat(64)] },
      defenseFindings: { counter_evidence_found: false, evidence_refs: [] },
    });
    // the posterior shifts toward refutation when the plaintiff finds counter-evidence
    expect(result.posterior_shift.direction).toBe("toward-refutation");
    expect(result.posterior_shift.counter_evidence_discovery_rate).toBeGreaterThan(0);
  });

  it("non-mob claims stay single-seat with the counter-evidence quota", () => {
    const engine = new DualSeatEngine(ledger);
    expect(engine.shouldRunDualSeat("c-minor", ["c-mob"])).toBe(false);
    expect(engine.shouldRunDualSeat("c-mob", ["c-mob"])).toBe(true);
  });

  it("every seat report is a provider.action engine fact", async () => {
    const engine = new DualSeatEngine(ledger);
    engine.runDualSeat("t1", "c-mob", {
      plaintiffWorker: "p1",
      defenseWorker: "d1",
      budgetPerSeat: 5000,
    });
    const events = ledger.graphEvents().map((e) => e.event_type);
    expect(events.filter((t) => t === "provider.action").length).toBeGreaterThanOrEqual(2);
  });
});
