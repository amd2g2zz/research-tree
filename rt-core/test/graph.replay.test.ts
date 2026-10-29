import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, beforeEach, expect, it } from "vitest";

import { GraphStore } from "../src/graph/projection.js";

const CLAIM_A = {
  id: "c1",
  text: "rt works offline",
  source: "user",
  weight: "make_or_break",
  posterior: 0.5,
  verify_tier: "multi-source",
};

// The SQLite-backed projection has no open-store limit; these tests keep
// several stores open and compare snapshots directly.
let workspace: string;
const stores: GraphStore[] = [];

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-graph-replay-"));
});

afterEach(async () => {
  for (const store of stores.splice(0)) {
    await store.close();
  }
});

function openStore(name: string): GraphStore {
  const store = new GraphStore(join(workspace, name));
  stores.push(store);
  return store;
}

function records(...pairs: Array<[string, Record<string, unknown>]>): Record<string, unknown>[] {
  return pairs.map(([eventType, payload], index) => ({
    seq: index + 1,
    run_id: null,
    event_type: eventType,
    payload,
    created_at: `2026-10-30T00:00:${String(index + 1).padStart(2, "0")}Z`,
  }));
}

const EVENTS = records(
  ["claim.upsert", { claim: { ...CLAIM_A } }],
  ["claim.kill_edge", { claim_id: "c1", kill_target_id: "c1b" }],
  [
    "version.commit",
    { version: { id: "t1:0", task_id: "t1", v: 0, commit_hash: "c".repeat(64), verdict: "GO", summary: "first" } },
  ],
);

it("rebuild equals incremental state", async () => {
  const incremental = openStore("incremental.kuzu");
  for (const event of EVENTS) await incremental.applyEvent(event);
  const rebuilt = openStore("rebuilt.kuzu");
  const rebuiltSnapshot = await rebuilt.rebuild(EVENTS);
  expect(rebuiltSnapshot).toEqual(await incremental.snapshotState());
});

it("two fresh rebuilds are deterministic", async () => {
  const one = await openStore("one.kuzu").rebuild(EVENTS);
  const two = await openStore("two.kuzu").rebuild(EVENTS);
  expect(one).toEqual(two);
});

it("several stores coexist without interference", async () => {
  const first = openStore("first.kuzu");
  await first.rebuild(records(["claim.upsert", { claim: { ...CLAIM_A } }]));
  const second = openStore("second.kuzu");
  await second.rebuild([]);
  const firstSnapshot = await first.snapshotState();
  expect(Object.keys(firstSnapshot.Claim as object)).toEqual(["c1"]);
  expect(Object.keys((await second.snapshotState()).Claim as object)).toEqual([]);
});
