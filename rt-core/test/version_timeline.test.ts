import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { LedgerStore } from "../src/store/ledger.js";
import { VersionStore } from "../src/versions/store.js";
import { EngineCore } from "../src/store/engine.js";
import { ProductStateMachine } from "../src/state/machine.js";
import { VersionTimeline, VersionTimelineError } from "../src/versions/timeline.js";

let workspace: string;
let ledger: LedgerStore;
let versions: VersionStore;
let machine: ProductStateMachine;
let timeline: VersionTimeline;

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-vtl-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
  versions = new VersionStore(ledger);
  machine = new ProductStateMachine(new EngineCore(ledger), versions);
  timeline = new VersionTimeline(ledger, versions, machine);
});

function commit(taskId: string, verdict: string, claimText?: string) {
  const existing = versions.draftOf(taskId);
  const snapshot = {
    elements: {},
    claims: claimText !== undefined ? [{ id: `c-${claimText}`, text: claimText }] : (existing?.snapshot.claims ?? []),
    evidence_refs: existing?.snapshot.evidence_refs ?? ["sha256:" + "a".repeat(64)],
    report: {},
    deleted_nodes: [],
  };
  if (existing === null) {
    versions.openDraft(taskId, { snapshot, baseV: null });
  } else {
    versions.mutateDraft(taskId, (draft) => {
      draft.snapshot = snapshot;
    });
  }
  return versions.freeze(taskId, { verdict, summary: `${taskId} → ${verdict}` });
}

describe("version timeline + fork (issue #574, P5)", () => {
  it("timeline renders newest-first with hash/verdict/summary and fork markers", () => {
    commit("t1", "GO", "v0 claim");
    commit("t1", "GO", "v1 claim");
    timeline.fork("t1", 0, "t-fork");
    const view = timeline.timeline("t1");
    expect(view.versions.map((v) => v.v)).toEqual([1, 0]); // newest first
    expect(view.versions[1]).toMatchObject({ verdict: "GO" });
    expect(String(view.versions[1]?.commit_hash)).toHaveLength(64);
    const forked = view.versions.find((v) => v.v === 0);
    expect(forked?.forked).toBe(true); // ⑂ 已分叉 → 支线
    expect(view.versions.find((v) => v.v === 1)?.forked).toBe(false);
  });

  it("draft row (未冻结·不可跟踪) shows when present and vanishes after freeze", () => {
    commit("t1", "GO");
    versions.openDraftFromVersion("t1", 0);
    let view = timeline.timeline("t1");
    expect(view.draft).not.toBeNull();
    expect(view.draft?.base_v).toBe(0);
    commit("t1", "GO", "new claim");
    view = timeline.timeline("t1");
    expect(view.draft).toBeNull();
  });

  it("main branch = task without fork parent; default projection ignores branch tips", () => {
    commit("t-main", "PARK", "v0 claim");
    commit("t-main", "GO", "v1 claim");
    timeline.fork("t-main", 1, "t-branch");
    commit("t-branch", "NO-GO"); // the branch tip is newer — but never the default
    expect(timeline.isMainBranch("t-main")).toBe(true);
    expect(timeline.isMainBranch("t-branch")).toBe(false);
    const projection = timeline.defaultProjection("t-branch"); // explicit (task, latest) addressing
    expect(projection.task_id).toBe("t-main");
    expect(projection.v).toBe(1);
    expect(projection.verdict).toBe("GO");
  });

  it("继续研究 opens a version+1 draft from the latest committed version (H7 telemetry lands)", () => {
    commit("t1", "GO");
    timeline.continueResearch("t1");
    const draft = versions.draftOf("t1");
    expect(draft?.base_v).toBe(0);
    const events = ledger
      .graphEvents()
      .filter((e) => e.event_type === "provider.action")
      .filter((e) => String((e.payload as Record<string, unknown>).target).startsWith("version-continue"));
    expect(events.length).toBeGreaterThan(0);
  });

  it("回研究草稿 takes precedence over a mistaken +1 (resume the existing draft)", () => {
    commit("t1", "GO");
    versions.openDraftFromVersion("t1", 0);
    versions.mutateDraft("t1", (draft) => {
      draft.snapshot.claims = [{ id: "c-x", text: "wip" }];
    });
    // continueResearch must NOT clobber the live draft — it resumes it
    timeline.continueResearch("t1");
    expect(versions.draftOf("t1")?.snapshot.claims).toEqual([{ id: "c-x", text: "wip" }]);
  });

  it("从此分叉 forks with inherited ledger + evidence (H7 telemetry lands)", () => {
    commit("t1", "GO");
    timeline.fork("t1", 0, "t-fork");
    const inherited = versions.getVersion("t-fork", 0)!;
    expect(inherited.snapshot.evidence_refs).toEqual(["sha256:" + "a".repeat(64)]); // 分叉即继承
    expect(machine.phaseOf("t-fork")).toBe("chat");
    expect(versions.forkChildren("t1", 0).map((c) => c.task_id)).toContain("t-fork");
    const events = ledger
      .graphEvents()
      .filter((e) => e.event_type === "provider.action")
      .filter((e) => String((e.payload as Record<string, unknown>).target).startsWith("fork:"));
    expect(events.length).toBeGreaterThan(0);
  });

  it("snapshot view is read-only: frozen banner + full report; committed content never mutates", () => {
    commit("t1", "GO", "claim at v0");
    const hashBefore = versions.getVersion("t1", 0)!.commit_hash;
    const view = timeline.snapshotView("t1", 0);
    expect(view.banner).toMatchObject({ v: 0, verdict: "GO" });
    expect(String(view.banner.commit_hash)).toHaveLength(64);
    // mutation attempts are rejected: identical content re-freeze is refused (append-only)
    versions.openDraftFromVersion("t1", 0);
    expect(() => versions.freeze("t1", { verdict: "GO", summary: "same" })).toThrow();
    // and v0 is byte-identical after all subsequent activity
    expect(versions.getVersion("t1", 0)!.commit_hash).toBe(hashBefore);
  });

  it("unknown tasks/versions throw a typed error", () => {
    expect(() => timeline.timeline("ghost")).toThrow(VersionTimelineError);
    expect(() => timeline.snapshotView("ghost", 0)).toThrow(VersionTimelineError);
  });
});
