import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { LedgerStore } from "../src/store/ledger.js";
import { VersionStore } from "../src/versions/store.js";
import { EngineCore } from "../src/store/engine.js";
import { ProductStateMachine } from "../src/state/machine.js";
import { FourStateArchive, ArchiveError } from "../src/versions/archive.js";

let workspace: string;
let ledger: LedgerStore;
let versions: VersionStore;
let machine: ProductStateMachine;
let archive: FourStateArchive;

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-arch-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
  versions = new VersionStore(ledger);
  machine = new ProductStateMachine(new EngineCore(ledger), versions);
  archive = new FourStateArchive(ledger, versions, machine);
});

function commit(taskId: string, verdict: string, report: Record<string, unknown> = {}) {
  versions.openDraft(taskId, {
    snapshot: { elements: {}, claims: [], evidence_refs: ["sha256:" + "a".repeat(64)], report, deleted_nodes: [] },
    baseV: null,
  });
  return versions.freeze(taskId, { verdict, summary: `${taskId} ${verdict}` });
}

describe("four-state archival (issue #573)", () => {
  it("GO archives with a 底稿 handoff pointer", () => {
    const report = { deliverable_schema: "v1", supported_claims: [{ text: "x" }] };
    commit("t-go", "GO", report);
    const entry = archive.archive("t-go", 0);
    expect(entry.verdict).toBe("GO");
    expect(entry.disposition.kind).toBe("deliverable");
    expect((entry.disposition as { report: unknown }).report).toMatchObject({ deliverable_schema: "v1" });
  });

  it("NO-GO lands in the graveyard with reason + revival conditions; browsable", () => {
    commit("t-no", "NO-GO");
    const entry = archive.archive("t-no", 0, {
      reason: "OOM postmortem: 2C4G ceiling at 3.2GB",
      revival_conditions: ["budget for a 4C8G pilot", "workload shrink to 2C-only paths"],
    });
    expect(entry.disposition.kind).toBe("graveyard");
    expect(archive.graveyard().map((e) => e.task_id)).toContain("t-no");
    expect(archive.entry("t-no", 0)?.disposition).toMatchObject({ kind: "graveyard" });
  });

  it("NO-GO without revival conditions is rejected (pinned)", () => {
    commit("t-no", "NO-GO");
    expect(() => archive.archive("t-no", 0, { reason: "dead" })).toThrow(ArchiveError);
    expect(() => archive.archive("t-no", 0, { reason: "dead", revival_conditions: [] })).toThrow(/revival/);
  });

  it("PARK requires a frozen brief + mandatory revival conditions (red line)", () => {
    commit("t-park", "PARK");
    expect(() => archive.archive("t-park", 0, { brief: "waiting on budget" })).toThrow(/revival/);
    const entry = archive.archive("t-park", 0, {
      brief: "frozen brief: recon done, benchmark unfunded",
      revival_conditions: ["next quarter budget window"],
    });
    expect(entry.disposition.kind).toBe("frozen-brief");
  });

  it("REFRAMED forks a new task that inherits the ledger, with a delta report", () => {
    commit("t-ref", "REFRAMED");
    const entry = archive.archive("t-ref", 0, {
      delta_report: "the real question is memory ceiling, not p95",
      new_task_id: "t-reframed",
    });
    expect(entry.disposition.kind).toBe("inherited");
    expect(entry.disposition).toMatchObject({ inherited_to: "t-reframed" });
    // the new task starts at chat with an inherited v0 snapshot (fork semantics)
    expect(machine.phaseOf("t-reframed")).toBe("chat");
    expect(versions.getVersion("t-reframed", 0)).not.toBeNull();
    const inherited = versions.getVersion("t-reframed", 0)!;
    expect(inherited.snapshot.evidence_refs).toEqual(["sha256:" + "a".repeat(64)]);
  });

  it("graveyard revival forks from the graveyard version with the inherited snapshot", () => {
    commit("t-dead", "NO-GO");
    archive.archive("t-dead", 0, { reason: "no budget", revival_conditions: ["budget returns"] });
    const revived = archive.revive("t-dead", 0, "t-reborn");
    expect(revived.snapshot.evidence_refs).toEqual(["sha256:" + "a".repeat(64)]); // 分叉即继承
    expect(machine.phaseOf("t-reborn")).toBe("chat");
    // the lineage edge is recorded and queryable
    const children = versions.forkChildren("t-dead", 0);
    expect(children.map((e) => e.task_id)).toContain("t-reborn");
    // the graveyard entry records the revival
    expect(archive.entry("t-dead", 0)?.revived_to).toBe("t-reborn");
  });

  it("all four states are archived and browsable in one ledger", () => {
    commit("t1", "GO");
    commit("t2", "NO-GO");
    commit("t3", "PARK");
    commit("t4", "REFRAMED");
    archive.archive("t1", 0);
    archive.archive("t2", 0, { reason: "r", revival_conditions: ["c"] });
    archive.archive("t3", 0, { brief: "b", revival_conditions: ["c"] });
    archive.archive("t4", 0, { delta_report: "d", new_task_id: "t4b" });
    const all = archive.list();
    expect(all.map((e) => e.disposition.kind).sort()).toEqual(["deliverable", "frozen-brief", "graveyard", "inherited"]);
  });

  it("archiving an uncommitted version or unknown verdict is rejected", () => {
    expect(() => archive.archive("ghost", 0)).toThrow(ArchiveError);
    versions.openDraft("t5", {
      snapshot: { elements: {}, claims: [], evidence_refs: [], report: {}, deleted_nodes: [] },
      baseV: null,
    });
    // draft-only (no freeze): nothing to archive
    expect(() => archive.archive("t5", 0)).toThrow(ArchiveError);
  });
});
