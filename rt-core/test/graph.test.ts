import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterAll, beforeAll, beforeEach, expect, it } from "vitest";

import { GraphStore } from "../src/graph/projection.js";

const CLAIM_A = {
  id: "c1",
  text: "rt works offline",
  source: "user",
  weight: "make_or_break",
  posterior: 0.5,
  verify_tier: "multi-source",
};
const CLAIM_B = {
  id: "c2",
  text: "kuzu replay is deterministic",
  source: "research",
  weight: "important",
  posterior: 0.9,
  verify_tier: "rederive",
};

// kuzu npm 0.11.x allows one open GraphStore per process and degrades under
// repeated open/close cycles — the file keeps ONE store open and isolates
// tests with the projection's deterministic rebuild (multi-store cases live in
// graph.replay.test.ts, which runs in its own fork).
let workspace: string;
let store: GraphStore;

beforeAll(async () => {
  workspace = mkdtempSync(join(tmpdir(), "rt-graph-"));
  store = new GraphStore(join(workspace, "graph.kuzu"));
});

afterAll(async () => {
  await store.close();
});

beforeEach(async () => {
  await store.rebuild([]);
});

function records(...pairs: Array<[string, Record<string, unknown>]>): Record<string, unknown>[] {
  return pairs.map(([eventType, payload], index) => ({
    seq: index + 1,
    run_id: null,
    event_type: eventType,
    payload,
    created_at: `2026-10-30T00:00:${String(index + 1).padStart(2, "0")}Z`,
  }));
}

function sampleEvents(): Record<string, unknown>[] {
  return records(
    ["claim.upsert", { claim: { ...CLAIM_A } }],
    ["claim.upsert", { claim: { ...CLAIM_B } }],
    ["claim.kill_edge", { claim_id: "c2", kill_target_id: "c1" }],
    ["stage.upsert", { stage: { id: "s1", title: "cluster", status: "open" } }],
    ["stage.contains", { stage_id: "s1", claim_id: "c1" }],
    ["evidence.upsert", { evidence: { id: "e1", digest: "a".repeat(64), origin: "origin.py" } }],
    ["evidence.attach", { evidence_id: "e1", claim_id: "c1" }],
    ["artifact.upsert", { artifact: { id: "a1", kind: "finding-pack", digest: "b".repeat(64) } }],
    ["artifact.link", { artifact_id: "a1", claim_id: "c1" }],
    [
      "version.commit",
      { version: { id: "t1:0", task_id: "t1", v: 0, commit_hash: "c".repeat(64), verdict: "GO", summary: "first" } },
    ],
    [
      "version.commit",
      { version: { id: "t2:0", task_id: "t2", v: 0, commit_hash: "d".repeat(64), verdict: "PARK", summary: "fork" } },
    ],
    ["fork.edge", { child_version_id: "t2:0", parent_version_id: "t1:0" }],
  );
}

it("applies a claim upsert and reads it back", async () => {
  await store.applyEvent(records(["claim.upsert", { claim: { ...CLAIM_A } }])[0]!);
  const snapshot = await store.snapshotState();
  expect((snapshot.Claim as Record<string, any>)["c1"]["text"]).toBe("rt works offline");
  expect((snapshot.Claim as Record<string, any>)["c1"]["posterior"]).toBe(0.5);
});

it("is idempotent when the same event is applied twice", async () => {
  const event = records(["claim.upsert", { claim: { ...CLAIM_A } }])[0]!;
  await store.applyEvent(event);
  const first = await store.snapshotState();
  await store.applyEvent(event);
  expect(await store.snapshotState()).toEqual(first);
});

it("keeps edges idempotent", async () => {
  const events = sampleEvents();
  for (const event of events) await store.applyEvent(event);
  const first = await store.snapshotState();
  for (const event of events.slice(0, 3)) await store.applyEvent(event);
  expect(await store.snapshotState()).toEqual(first);
});

it("rebuild wipes previous state", async () => {
  await store.rebuild(sampleEvents());
  const snapshot = await store.rebuild(sampleEvents().slice(0, 2));
  expect(Object.keys(snapshot.Claim as object).sort()).toEqual(["c1", "c2"]);
  expect(snapshot.VersionNode).toEqual({});
  expect(snapshot.FORKED_FROM).toEqual([]);
});

it("updates posterior via a second upsert", async () => {
  await store.applyEvent(records(["claim.upsert", { claim: { ...CLAIM_A } }])[0]!);
  await store.applyEvent(records(["claim.upsert", { claim: { ...CLAIM_A, posterior: 0.85, stale: true } }])[0]!);
  const snapshot = await store.snapshotState();
  expect((snapshot.Claim as Record<string, any>)["c1"]["posterior"]).toBe(0.85);
  expect((snapshot.Claim as Record<string, any>)["c1"]["stale"]).toBe(true);
  expect(Object.keys(snapshot.Claim as object)).toHaveLength(1);
});

it("resolves fork lineage in both directions", async () => {
  await store.rebuild(sampleEvents());
  expect(await store.forkParent("t2:0")).toBe("t1:0");
  expect(await store.forkParent("t1:0")).toBeNull();
  expect(await store.forkChildren("t1:0")).toEqual(["t2:0"]);
  expect(await store.forkChildren("t2:0")).toEqual([]);
});

it("revalidates payloads at the projection boundary", async () => {
  const bad = {
    seq: 1,
    created_at: "x",
    event_type: "claim.upsert",
    payload: { claim: { ...CLAIM_A, posterior: 7.0 } },
  };
  await expect(store.applyEvent(bad)).rejects.toThrow();
  expect((await store.snapshotState()).Claim).toEqual({});
});

it("covers all tables in counts", async () => {
  await store.rebuild(sampleEvents());
  expect(await store.counts()).toEqual({
    Claim: 2,
    Stage: 1,
    Evidence: 1,
    Artifact: 1,
    VersionNode: 2,
    KILL_EDGE: 1,
    STAGE_DEPENDS_ON: 0,
    CONTAINS: 1,
    EVIDENCE_FOR: 1,
    ARTIFACT_FOR: 1,
    FORKED_FROM: 1,
  });
});

it("defers forward-referenced edges until the endpoint arrives", async () => {
  await store.applyEvent(records(["claim.upsert", { claim: { ...CLAIM_A } }])[0]!);
  await store.applyEvent(records(["claim.kill_edge", { claim_id: "c1", kill_target_id: "c9" }])[0]!);
  expect((await store.snapshotState()).KILL_EDGE).toEqual([]);
  await store.applyEvent(records(["claim.upsert", { claim: { ...CLAIM_B, id: "c9" } }])[0]!);
  expect(await store.snapshotState()).toMatchObject({ KILL_EDGE: [["c1", "c9"]] });
  expect(await store.counts()).toMatchObject({ KILL_EDGE: 1 });
});
