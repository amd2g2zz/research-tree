import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { renderReport, renderDeliverable } from "../src/rendering/dual.js";
import { LedgerStore } from "../src/store/ledger.js";
import { VersionStore } from "../src/versions/store.js";

const SNAPSHOT = {
  elements: {
    requirements: [{ id: "r1", text: "deploy on 2C4G" }],
    constraints: [{ id: "c1", text: "on-prem only", hardness: "hard" }],
    background: [],
    intents: [{ id: "i1", text: "ship fast" }],
    refusals: [{ id: "x1", text: "no public cloud" }],
    difficulties: [{ id: "d1", text: "memory ceiling" }],
  },
  claims: [
    { id: "c-mob", text: "2C4G suffices", posterior: 0.95, verify_tier: "multi-source", weight: "make_or_break" },
    { id: "c-min", text: "1GB is enough", posterior: 0.3, verify_tier: "single-source", weight: "minor" },
  ],
  evidence_refs: ["sha256:" + "a".repeat(64)],
  report: { verdict_narrative: "viable with memory ceiling caveat" },
  deleted_nodes: ["node-early-sketch"],
};

let workspace: string;
let versions: VersionStore;

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-render-"));
  const ledger = new LedgerStore(workspace);
  ledger.initialize();
  versions = new VersionStore(ledger);
});

describe("dual rendering — same-source projection (issue #560)", () => {
  it("renders the report narrative with all 7 sections", () => {
    const report = renderReport(SNAPSHOT, { verdict: "GO", confidence: "moderate" });
    expect(report).toContain("## 1. 你的想法");
    expect(report).toContain("## 2. 我们怎么验证的");
    expect(report).toContain("## 3. 主张账本");
    expect(report).toContain("## 4. 反证与让步");
    expect(report).toContain("## 5. 信心与不确定性");
    expect(report).toContain("## 6. 最便宜的下一步");
    expect(report).toContain("## 7. 三元裁决");
  });

  it("reports carry no fake percentages (qualitative bands only)", () => {
    const report = renderReport(SNAPSHOT, { verdict: "GO", confidence: "moderate" });
    expect(report).not.toMatch(/\d+% confidence/);
    expect(report).toContain("moderate");
  });

  it("renders the 底稿 with frozen schema v1", () => {
    const deliverable = renderDeliverable(SNAPSHOT, { verdict: "GO" });
    expect(deliverable.clarified_question).toBeDefined();
    expect(deliverable.supported_claims).toHaveLength(1); // only c-mob (>= 0.9)
    expect(deliverable.supported_claims[0]).toMatchObject({ text: "2C4G suffices", verify_tier: "multi-source" });
    expect(deliverable.unverified_assumptions).toHaveLength(1); // c-min single-source
    expect(deliverable.refuted_and_disposition).toEqual([]);
    expect(deliverable.capability_outline.length).toBeGreaterThan(0);
    expect(deliverable.constraints.hard).toEqual(["on-prem only"]);
    expect(deliverable.constraints.guessed).toEqual([]);
  });

  it("same source: report and 底稿 never contradict", () => {
    const report = renderReport(SNAPSHOT, { verdict: "GO", confidence: "moderate" });
    const deliverable = renderDeliverable(SNAPSHOT, { verdict: "GO" });
    // the mob claim appears in both with the same verdict
    expect(report).toContain("2C4G suffices");
    expect(deliverable.supported_claims[0]!.text).toBe("2C4G suffices");
    // the ledger narrative lists ALL claims (transparency); the 底稿's
    // supported_claims projection excludes the unverified minor claim
    expect(deliverable.supported_claims.find((c) => c.text === "1GB is enough")).toBeUndefined();
  });

  it("deleted nodes are disclosed in the report (产物删除 auditable)", () => {
    const report = renderReport(SNAPSHOT, { verdict: "GO", confidence: "moderate" });
    expect(report).toContain("node-early-sketch");
  });

  it("refuted and disposition section grounds downstream", () => {
    const snapshot = {
      ...SNAPSHOT,
      claims: [
        ...SNAPSHOT.claims,
        { id: "c-ref", text: "k8s required", posterior: 0.05, verify_tier: "multi-source", weight: "important" },
      ],
    };
    const deliverable = renderDeliverable(snapshot, { verdict: "GO" });
    expect(deliverable.refuted_and_disposition).toContainEqual(
      expect.objectContaining({ text: "k8s required" }),
    );
  });

  it("confidence bands are qualitative only", () => {
    for (const band of ["high", "moderate", "low"] as const) {
      const report = renderReport(SNAPSHOT, { verdict: "GO", confidence: band });
      expect(report).toContain(band);
    }
  });
});

describe("version integration", () => {
  it("committed versions expose the deliverable paths", () => {
    versions.openDraft("t1", { snapshot: SNAPSHOT, baseV: null });
    const committed = versions.freeze("t1", { verdict: "GO", summary: "v0" });
    expect(committed.snapshot.report).toBeDefined();
    const deliverable = renderDeliverable(committed.snapshot, { verdict: "GO" });
    expect(deliverable.supported_claims[0]!.text).toBe("2C4G suffices");
  });
});
