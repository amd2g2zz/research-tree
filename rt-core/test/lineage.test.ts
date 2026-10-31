import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { LineageDrillDown } from "../src/canvas/lineage.js";
import { LedgerStore } from "../src/store/ledger.js";
import { VersionStore } from "../src/versions/store.js";

let workspace: string;
let ledger: LedgerStore;
let versions: VersionStore;

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-lineage-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
  versions = new VersionStore(ledger);
});

describe("lineage drill-down (issue #566, 3-click rule)", () => {
  it("resolves the lineage path for a committed claim in <= 3 clicks", () => {
    versions.openDraft("t1", {
      snapshot: {
        elements: {}, claims: [{ id: "c1", text: "claim" }], evidence_refs: ["sha256:" + "a".repeat(64)],
        report: {}, deleted_nodes: [],
      },
      baseV: null,
    });
    versions.freeze("t1", { verdict: "GO", summary: "v0" });
    const drill = new LineageDrillDown(versions);
    const path = drill.resolve("t1", 0, "c1");
    expect(path).not.toBeNull();
    expect(path!.clicks).toBeLessThanOrEqual(3);
    expect(path!.steps.map((s) => s.layer)).toEqual(["canvas-node", "detail-drawer", "raw-evidence"]);
    expect(path!.raw_evidence).toBeDefined();
  });

  it("resolves lineage for a historical version (snapshot preserves evidence refs)", () => {
    versions.openDraft("t1", {
      snapshot: {
        elements: {}, claims: [{ id: "c-old", text: "old claim" }], evidence_refs: ["sha256:old"],
        report: {}, deleted_nodes: [],
      },
      baseV: null,
    });
    versions.freeze("t1", { verdict: "GO", summary: "v0" });
    versions.openDraftFromVersion("t1", 0);
    const drill = new LineageDrillDown(versions);
    const path = drill.resolve("t1", 0, "c-old");
    expect(path).not.toBeNull();
    expect(path!.clicks).toBeLessThanOrEqual(3);
    expect(path!.raw_evidence).toBeDefined();
  });

  it("returns null for unknown claims (no fake lineage)", () => {
    const drill = new LineageDrillDown(versions);
    expect(drill.resolve("t1", 0, "nonexistent")).toBeNull();
  });
});
