import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import {
  VariantSearchEngine,
  type VariantCandidate,
} from "../src/termination/variant_search.js";
import { LedgerStore } from "../src/store/ledger.js";

let ledger: LedgerStore;

beforeEach(() => {
  ledger = new LedgerStore(mkdtempSync(join(tmpdir(), "rt-term-")));
  ledger.initialize();
});

const KILL_GRAPH = {
  claims: [
    { id: "c-mob", text: "2C4G suffices", weight: "make_or_break", posterior: 0.05, state: "refuted" },
    { id: "c-dep", text: "depends on c-mob", weight: "important", posterior: 0.8, state: "decided", depends_on: ["c-mob"] },
  ],
};

function variant(id: string, overrides: Partial<VariantCandidate> = {}): VariantCandidate {
  return {
    variant_id: id,
    description: `variant ${id}`,
    action: "relax",
    target_claim_id: "c-mob",
    dag_still_stands: true,
    ...overrides,
  };
}

describe("A5 variant search (issue #563)", () => {
  it("searches {relax | replace | bypass} for the refuted claim and finds a standing alternative", () => {
    const engine = new VariantSearchEngine(ledger);
    const alternatives = engine.searchVariants("c-mob", KILL_GRAPH.claims, [
      variant("v-relax", { action: "relax" }),
      variant("v-replace", { action: "replace", target_claim_id: "c-mob" }),
      variant("v-dead", { action: "bypass", dag_still_stands: false }),
    ]);
    // v-dead is excluded (DAG would not stand); two standing variants remain
    expect(alternatives.map((v) => v.variant_id)).toEqual(["v-relax", "v-replace"]);
  });

  it("returns empty when no variant keeps the DAG standing (埋了 is the honest answer)", () => {
    const engine = new VariantSearchEngine(ledger);
    const alternatives = engine.searchVariants("c-mob", KILL_GRAPH.claims, [
      variant("v-only", { dag_still_stands: false }),
    ]);
    expect(alternatives).toEqual([]);
  });
});

describe("early-termination inquiry (问句不是判决)", () => {
  it("presents the three-choice inquiry with evidence, not a verdict", () => {
    const engine = new VariantSearchEngine(ledger);
    const inquiry = engine.buildInquiry("c-mob", {
      posterior: 0.05,
      evidence_summary: "posterior 0.05 across 3 sources",
      standing_variants: [variant("v-relax")],
    });
    expect(inquiry.choices).toEqual(["bury", "continue", "switch-variant"]);
    expect(inquiry.evidence_summary).toContain("0.05");
    expect(inquiry.verdict).toBeUndefined(); // no verdict in the inquiry
  });

  it("bury converges with a NO-GO recommendation (final verdict still at freeze)", () => {
    const engine = new VariantSearchEngine(ledger);
    const outcome = engine.resolveBury("c-mob");
    expect(outcome.recommendation).toBe("NO-GO");
    expect(outcome.is_final).toBe(false); // verdict at freeze
  });
});

describe("budget savings measurement (H5)", () => {
  it("records the savings ratio vs the full-run baseline", () => {
    const engine = new VariantSearchEngine(ledger);
    const savings = engine.recordSavings({
      full_run_estimate_ms: 12 * 3600 * 1000,
      actual_run_ms: 4 * 3600 * 1000,
    });
    expect(savings.ratio).toBeCloseTo(2 / 3, 2);
    expect(savings.meets_h5_threshold).toBe(true); // ≥50%
  });

  it("flags when savings fall below the H5 threshold", () => {
    const engine = new VariantSearchEngine(ledger);
    const savings = engine.recordSavings({
      full_run_estimate_ms: 12 * 3600 * 1000,
      actual_run_ms: 10 * 3600 * 1000,
    });
    expect(savings.meets_h5_threshold).toBe(false);
  });
});
