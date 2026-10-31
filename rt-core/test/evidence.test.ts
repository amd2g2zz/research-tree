import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { EvidenceEngine } from "../src/evidence/engine.js";
import { LedgerStore } from "../src/store/ledger.js";

let ledger: LedgerStore;

beforeEach(() => {
  ledger = new LedgerStore(mkdtempSync(join(tmpdir(), "rt-ev-")));
  ledger.initialize();
});

function conflictingSources(): Array<{ source_id: string; origin: string; claim: string; verdict: string }> {
  return [
    { source_id: "s1", origin: "https://a.example.com", claim: "2C4G suffices", verdict: "supported" },
    { source_id: "s2", origin: "https://b.example.com", claim: "2C4G suffices", verdict: "refuted" },
  ];
}

describe("evidence engine L1-lite (issue #556)", () => {
  it("registers sources with provenance (origins.py promoted to reasoning input)", () => {
    const engine = new EvidenceEngine(ledger);
    engine.registerSource("t1", {
      source_id: "s1", origin: "https://a.example.com", kind: "web",
      reliability: 0.8, incentive_vector: [], astroturf_flag: false, provenance: { fetched_at: "t" },
    });
    expect(ledger.getSource("t1", "s1")).not.toBeNull();
  });

  it("weighted-vote point estimate resolves conflicting verdicts toward reliability", () => {
    const engine = new EvidenceEngine(ledger);
    engine.registerSource("t1", {
      source_id: "s1", origin: "https://high.example.com", kind: "web",
      reliability: 0.9, incentive_vector: [], astroturf_flag: false, provenance: {},
    });
    engine.registerSource("t1", {
      source_id: "s2", origin: "https://low.example.com", kind: "web",
      reliability: 0.2, incentive_vector: [], astroturf_flag: false, provenance: {},
    });
    const estimate = engine.pointEstimate("t1", [
      { source_id: "s1", verdict: "supports" },
      { source_id: "s2", verdict: "refutes" },
    ]);
    expect(estimate.posterior).toBeGreaterThan(0.5); // high-reliability source dominates
    expect(estimate.method).toBe("weighted-vote");
  });

  it("independence collapse merges citation chains to the independent root", () => {
    const engine = new EvidenceEngine(ledger);
    // s2 cites s1 — they are NOT independent evidence of the same claim
    engine.registerSource("t1", {
      source_id: "s1", origin: "https://original.example.com", kind: "web",
      reliability: 0.9, incentive_vector: [], astroturf_flag: false, provenance: {},
    });
    engine.registerSource("t1", {
      source_id: "s2", origin: "https://citing.example.com", kind: "web",
      reliability: 0.9, incentive_vector: [], astroturf_flag: false,
      provenance: { cites: "https://original.example.com" },
    });
    const roots = engine.independenceRoots("t1", ["s1", "s2"]);
    expect(roots).toEqual(["s1"]); // collapsed to the independent root
  });

  it("quick-check flags a contradiction inline (claim vs evidence index)", () => {
    const engine = new EvidenceEngine(ledger);
    engine.registerClaimEvidence("t1", "c1", [
      { source_id: "s1", verdict: "supports" },
    ]);
    const flag = engine.quickCheck("t1", "c1", { verdict: "refutes", source_id: "s2" });
    expect(flag.conflict).toBe(true);
  });

  it("quick-check passes consistent evidence without a flag", () => {
    const engine = new EvidenceEngine(ledger);
    engine.registerClaimEvidence("t1", "c1", [{ source_id: "s1", verdict: "supports" }]);
    const flag = engine.quickCheck("t1", "c1", { verdict: "supports", source_id: "s2" });
    expect(flag.conflict).toBe(false);
  });

  it("cites conflicting-source count per claim (conflict index)", () => {
    const engine = new EvidenceEngine(ledger);
    for (const s of conflictingSources()) {
      engine.registerClaimEvidence("t1", "c1", [{ source_id: s.source_id, verdict: s.verdict === "supported" ? "supports" : "refutes" }]);
    }
    const index = engine.conflictIndex("t1", "c1");
    expect(index.conflicting_pairs).toBe(1);
  });
});
