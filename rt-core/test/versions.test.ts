import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import Database from "better-sqlite3";
import { beforeEach, describe, expect, it } from "vitest";

import { LedgerIntegrityError, LedgerStore } from "../src/store/ledger.js";
import { VersionStore } from "../src/versions/store.js";

const SNAPSHOT = {
  elements: { requirements: [{ id: "r1", text: "deploy" }] },
  claims: [{ id: "c1", posterior: 0.9 }],
  evidence_refs: ["sha256:" + "a".repeat(64)],
  report: { verdict_narrative: "solid" },
  deleted_nodes: [],
};

let workspace: string;
let ledger: LedgerStore;
let versions: VersionStore;

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-versions-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
  versions = new VersionStore(ledger);
});

describe("draft working state", () => {
  it("opens a draft, mutates it, and never creates a version row", () => {
    versions.openDraft("t1", { snapshot: SNAPSHOT, baseV: null });
    versions.mutateDraft("t1", (draft) => {
      (draft.snapshot.report as Record<string, unknown>).extra = "progress";
    });
    expect(
      (versions.draftOf("t1")!.snapshot.report as Record<string, unknown>).extra,
    ).toBe("progress");
    const db = new Database(ledger.databasePath, { readonly: true });
    const count = (db.prepare("SELECT count(*) AS n FROM versions").get() as { n: number }).n;
    db.close();
    expect(count).toBe(0);
  });

  it("inherits copy-on-write from a version snapshot", () => {
    versions.openDraft("t1", { snapshot: SNAPSHOT, baseV: null });
    const frozen = versions.freeze("t1", { verdict: "GO", summary: "first" });
    expect(frozen.v).toBe(0);
    versions.openDraftFromVersion("t1", frozen.v);
    const draft = versions.draftOf("t1")!;
    expect(draft.snapshot).toEqual(SNAPSHOT); // copied, not referenced
    expect(draft.base_v).toBe(0);
  });

  it("fails closed when freezing without a draft", () => {
    expect(() => versions.freeze("missing", { verdict: "GO", summary: "s" })).toThrow(LedgerIntegrityError);
  });
});

describe("commit immutability", () => {
  it("creates versions with a verifying content hash and monotonic v", () => {
    versions.openDraft("t1", { snapshot: SNAPSHOT, baseV: null });
    const v0 = versions.freeze("t1", { verdict: "GO", summary: "first" });
    expect(v0.v).toBe(0);
    expect(v0.commit_hash).toMatch(/^[0-9a-f]{64}$/);
    versions.openDraftFromVersion("t1", 0);
    versions.mutateDraft("t1", (draft) => {
      (draft.snapshot.claims as Array<Record<string, unknown>>).push({ id: "c2", posterior: 0.4 });
    });
    const v1 = versions.freeze("t1", { verdict: "PARK", summary: "second" });
    expect(v1.v).toBe(1);
    expect(v1.commit_hash).not.toBe(v0.commit_hash);
  });

  it("rejects duplicate-content commits (same hash)", () => {
    versions.openDraft("t1", { snapshot: SNAPSHOT, baseV: null });
    versions.freeze("t1", { verdict: "GO", summary: "first" });
    versions.openDraftFromVersion("t1", 0);
    // unchanged working set → identical hash → rejected
    expect(() => versions.freeze("t1", { verdict: "GO", summary: "first" })).toThrow(/duplicate/);
  });

  it("detects tampering with a committed version", () => {
    versions.openDraft("t1", { snapshot: SNAPSHOT, baseV: null });
    versions.freeze("t1", { verdict: "GO", summary: "first" });
    const raw = new Database(ledger.databasePath);
    raw.prepare("UPDATE versions SET snapshot_json = ? WHERE task_id = ? AND v = 0").run('{"hacked": true}', "t1");
    raw.close();
    expect(() => versions.verifyIntegrity()).toThrow(LedgerIntegrityError);
  });

  it("appends only: v must be the next in sequence", () => {
    versions.openDraft("t1", { snapshot: SNAPSHOT, baseV: null });
    versions.freeze("t1", { verdict: "GO", summary: "first" });
    expect(() => versions.insertVersion("t1", { v: 5, snapshot: SNAPSHOT, verdict: "GO", summary: "skip" })).toThrow(
      /append-only/,
    );
  });
});

describe("fork lineage", () => {
  it("forks a version into a new task with an inherited v0 and bidirectional lineage", () => {
    versions.openDraft("t1", { snapshot: SNAPSHOT, baseV: null });
    versions.freeze("t1", { verdict: "GO", summary: "first" });
    const forked = versions.fork({ fromTask: "t1", fromV: 0, toTask: "t2" });
    expect(forked.task_id).toBe("t2");
    expect(forked.v).toBe(0);
    expect(forked.snapshot).toEqual(SNAPSHOT); // shallow copy of the source snapshot
    expect(versions.forkParent("t2")).toEqual({ task_id: "t1", v: 0 });
    expect(versions.forkChildren("t1", 0)).toEqual([{ task_id: "t2", v: 0 }]);
  });

  it("supports multiple children and a chain", () => {
    versions.openDraft("t1", { snapshot: SNAPSHOT, baseV: null });
    versions.freeze("t1", { verdict: "GO", summary: "first" });
    versions.fork({ fromTask: "t1", fromV: 0, toTask: "t2" });
    versions.fork({ fromTask: "t1", fromV: 0, toTask: "t3" });
    expect(versions.forkChildren("t1", 0)).toHaveLength(2);
    versions.openDraft("t2", { snapshot: SNAPSHOT, baseV: 0 });
    versions.mutateDraft("t2", (draft) => {
      (draft.snapshot.claims as Array<Record<string, unknown>>).push({ id: "c9", posterior: 0.1 });
    });
    versions.freeze("t2", { verdict: "PARK", summary: "t2 work" });
    versions.fork({ fromTask: "t2", fromV: 1, toTask: "t4" });
    expect(versions.forkParent("t4")).toEqual({ task_id: "t2", v: 1 });
  });

  it("refuses forks from nonexistent versions", () => {
    expect(() => versions.fork({ fromTask: "tX", fromV: 3, toTask: "tY" })).toThrow(LedgerIntegrityError);
  });
});

describe("deleted_nodes disclosure", () => {
  it("records deleted nodes with the version snapshot", () => {
    versions.openDraft("t1", { snapshot: { ...SNAPSHOT, deleted_nodes: ["node-7"] }, baseV: null });
    const frozen = versions.freeze("t1", { verdict: "NO-GO", summary: "buried node-7" });
    expect(frozen.snapshot.deleted_nodes).toEqual(["node-7"]);
    expect(versions.latestVersion("t1")?.snapshot.deleted_nodes).toEqual(["node-7"]);
  });
});

describe("latest and listing", () => {
  it("returns the latest version per task", () => {
    versions.openDraft("t1", { snapshot: SNAPSHOT, baseV: null });
    versions.freeze("t1", { verdict: "GO", summary: "first" });
    versions.openDraftFromVersion("t1", 0);
    versions.mutateDraft("t1", (draft) => {
      (draft.snapshot.claims as Array<Record<string, unknown>>).push({ id: "c2", posterior: 0.4 });
    });
    versions.freeze("t1", { verdict: "PARK", summary: "second" });
    expect(versions.latestVersion("t1")?.v).toBe(1);
    expect(versions.listVersions("t1").map((v) => v.v)).toEqual([0, 1]);
    expect(versions.latestVersion("tX")).toBeNull();
  });
});
