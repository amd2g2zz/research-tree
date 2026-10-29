import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { GraphStore } from "../src/graph/projection.js";
import { EngineCore } from "../src/store/engine.js";
import { LedgerStore } from "../src/store/ledger.js";

const CLAIM = {
  id: "c1",
  text: "rt works offline",
  source: "user",
  weight: "make_or_break",
  posterior: 0.5,
  verify_tier: "multi-source",
};
const CLAIM_RECORD: [string, Record<string, unknown>] = ["claim.upsert", { claim: { ...CLAIM } }];

// The SQLite-backed projection allows several open stores; cross-store
// comparisons are direct.
let workspace: string;
let ledger: LedgerStore;
let store: GraphStore;
let fresh: GraphStore;

beforeAll(async () => {
  workspace = mkdtempSync(join(tmpdir(), "rt-engine-replay-"));
  store = new GraphStore(join(workspace, "graph.kuzu"));
  fresh = new GraphStore(join(workspace, "fresh.kuzu"));
});

afterAll(async () => {
  await store.close();
  await fresh.close();
});

afterEach(() => {
  vi.restoreAllMocks();
});

beforeEach(async () => {
  ledger = new LedgerStore(workspace + "/" + String(Math.random()).slice(2));
  ledger.initialize();
  await store.rebuild([]);
  await fresh.rebuild([]);
});

describe("engine dual-write", () => {
  it("lands appends in both the log and the projection", async () => {
    const engine = new EngineCore(ledger, store);
    const record = await engine.appendGraphEvent(...CLAIM_RECORD);
    expect(record.seq).toBe(1);
    expect(engine.graphEvents()[0]!.event_type).toBe("claim.upsert");
    const snapshot = await store.snapshotState();
    expect((snapshot.Claim as Record<string, any>)["c1"]["text"]).toBe("rt works offline");
  });

  it("fails closed when the projection faults", async () => {
    const engine = new EngineCore(ledger, store);
    vi.spyOn(store, "applyEvent").mockImplementation(async () => {
      throw new Error("kuzu engine failure");
    });
    await expect(engine.appendGraphEvent(...CLAIM_RECORD)).rejects.toThrow(/resync/);
    expect(ledger.graphEvents()).toHaveLength(1);
  });
});

describe("replay integrity", () => {
  it("resync restores the projection after drift", async () => {
    const engine = new EngineCore(ledger, store);
    await engine.appendGraphEvent(...CLAIM_RECORD);
    await store.applyEvent({
      seq: 99,
      run_id: null,
      created_at: "x",
      event_type: "claim.upsert",
      payload: { claim: { ...CLAIM, id: "ghost" } },
    });
    expect(Object.keys((await store.snapshotState()).Claim as object)).toContain("ghost");
    const counts = await engine.resyncGraph();
    const liveSnapshot = await store.snapshotState();
    expect(Object.keys(counts.Claim as object)).not.toContain("ghost");
    const freshSnapshot = await fresh.rebuild(ledger.graphEvents());
    expect(liveSnapshot).toEqual(freshSnapshot);
  });

  it("rebuilds an identical graph from the log alone", async () => {
    const engine = new EngineCore(ledger, store);
    await engine.appendGraphEvent(...CLAIM_RECORD);
    await engine.appendGraphEvent(...CLAIM_RECORD);
    const liveSnapshot = await store.snapshotState();
    const freshSnapshot = await fresh.rebuild(engine.graphEvents());
    expect(freshSnapshot).toEqual(liveSnapshot);
  });
});
