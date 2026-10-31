import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { VerificationEngine, type VerificationInput } from "../src/verification/seat.js";
import { LedgerStore } from "../src/store/ledger.js";

let ledger: LedgerStore;

beforeEach(() => {
  ledger = new LedgerStore(mkdtempSync(join(tmpdir(), "rt-verify-")));
  ledger.initialize();
});

function input(overrides: Partial<VerificationInput> = {}): VerificationInput {
  return {
    claim_id: "c-mob",
    weight: "make_or_break",
    method: "literature",
    verdict: "supported",
    evidence_refs: ["sha256:" + "a".repeat(64)],
    worker_id: "verifier-1",
    ...overrides,
  };
}

describe("single-seat verification (issue #558)", () => {
  it("methods route by claim type (literature -> multi-source + anchors)", async () => {
    const engine = new VerificationEngine(ledger);
    const receipt = await engine.verify(input({ method: "literature" }));
    expect(receipt.method_layer).toBe("literature");
    expect(receipt.requirements).toContain("multi-source cross");
    expect(receipt.requirements).toContain("verbatim anchors");
  });

  it("market/judgment claims require triangulation >= 3 independent sources", async () => {
    const engine = new VerificationEngine(ledger);
    const receipt = await engine.verify(input({ method: "market-judgment" }));
    expect(receipt.requirements).toContain("triangulation >= 3 independent sources");
  });

  it("logic claims route to fresh-context blind re-derivation", async () => {
    const engine = new VerificationEngine(ledger);
    const receipt = await engine.verify(input({ method: "logic" }));
    expect(receipt.requirements).toContain("fresh-context blind re-derivation");
  });

  it("counter-evidence quota: a make-or-break claim without its refutation round blocks convergence", async () => {
    const engine = new VerificationEngine(ledger);
    await engine.verify(input({}));
    const audit = engine.audit("t-default", "c-mob");
    expect(audit.counter_evidence_rounds).toBe(0);
    expect(audit.quota_met).toBe(false);
    expect(() => engine.assertConvergenceReady("t-default", "c-mob")).toThrow(/counter-evidence quota/);
  });

  it("the refutation round satisfies the quota", async () => {
    const engine = new VerificationEngine(ledger);
    await engine.verify(input({}));
    await engine.verify(input({ verdict: "refuted", worker_id: "counter-agent" }));
    const audit = engine.audit("t-default", "c-mob");
    expect(audit.counter_evidence_rounds).toBe(1);
    expect(audit.quota_met).toBe(true);
    expect(() => engine.assertConvergenceReady("t-default", "c-mob")).not.toThrow();
  });

  it("single-source claims are honestly marked and never promoted to supported", async () => {
    const engine = new VerificationEngine(ledger);
    const receipt = await engine.verify(input({}));
    const promoted = engine.promoteClaimVerdict(receipt, { supporting_sources: 1 });
    expect(promoted.verdict).toBe("supported-single-source");
    expect(promoted.verdict).not.toBe("supported");
  });

  it("two independent supporting sources promote to supported", async () => {
    const engine = new VerificationEngine(ledger);
    const receipt = await engine.verify(input({}));
    const promoted = engine.promoteClaimVerdict(receipt, { supporting_sources: 2 });
    expect(promoted.verdict).toBe("supported");
  });

  it("search envelope discloses what was checked and what was not", async () => {
    const engine = new VerificationEngine(ledger);
    const receipt = await engine.verify(input({}));
    expect(receipt.search_envelope).toMatchObject({
      queried: expect.anything(),
      not_queried: expect.anything(),
      found: expect.anything(),
      not_found: expect.anything(),
    });
  });

  it("every verification is an engine fact in the event stream", async () => {
    const engine = new VerificationEngine(ledger);
    await engine.verify(input({}));
    const events = ledger.graphEvents().map((e) => e.event_type);
    expect(events).toContain("provider.action");
  });
});
