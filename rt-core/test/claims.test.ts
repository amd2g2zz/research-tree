import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GraphStore } from "../src/graph/projection.js";
import { EngineCore } from "../src/store/engine.js";
import { LedgerStore } from "../src/store/ledger.js";

const CLAIM = {
  claim_id: "c1",
  text: "rt works offline",
  source: "user",
  weight: "make_or_break",
  posterior: 0.5,
  verify_tier: "multi-source",
  kill_edges: ["c2", "c3"],
  incentive_flag: false,
};

let workspace: string;
let ledger: LedgerStore;
const stores: GraphStore[] = [];

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-claims-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
});

afterEach(async () => {
  for (const store of stores.splice(0)) {
    await store.close();
  }
  vi.restoreAllMocks();
});

describe("coordinator claim round-trip (dual-write)", () => {
  it("lands the row, the log events and the projection edges", async () => {
    const store = new GraphStore(join(workspace, "graph.kuzu"));
    stores.push(store);
    const engine = new EngineCore(ledger, store);
    const row = engine.upsertClaim("t1", { ...CLAIM });
    expect(row.claim_id).toBe("c1");
    expect(ledger.getClaim("t1", "c1")).toEqual(row);

    const events = engine.graphEvents();
    expect(events.map((event) => event.event_type)).toEqual([
      "claim.upsert",
      "claim.kill_edge",
      "claim.kill_edge",
    ]);
    expect(events[0]!.payload).toMatchObject({ claim: { posterior: 0.5, id: "c1" } });

    const snapshot = await store.snapshotState();
    expect((snapshot.Claim as Record<string, any>)["c1"]["text"]).toBe("rt works offline");
    // kill edges to unregistered claims are deferred by the projection's
    // pending queue (#546 semantics) until the endpoints arrive
    expect(snapshot.KILL_EDGE).toEqual([]);
  });

  it("materializes deferred kill edges when the referenced claims arrive", async () => {
    const store = new GraphStore(join(workspace, "graph.kuzu"));
    stores.push(store);
    const engine = new EngineCore(ledger, store);
    engine.upsertClaim("t1", { ...CLAIM });
    engine.upsertClaim("t1", { ...CLAIM, claim_id: "c2", text: "endpoint", kill_edges: [] });
    expect(await store.forkChildren("t1:0")).toEqual([]); // no-op read keeps store warm
    const snapshot = await store.snapshotState();
    expect(snapshot.KILL_EDGE).toEqual([["c1", "c2"]]);
  });

  it("writes the log even without a projection attached", () => {
    const engine = new EngineCore(ledger);
    const row = engine.upsertClaim("t1", { ...CLAIM });
    expect(row.claim_id).toBe("c1");
    expect(engine.graphEvents().map((event) => event.event_type)).toEqual([
      "claim.upsert",
      "claim.kill_edge",
      "claim.kill_edge",
    ]);
  });

  it("does not duplicate graph edges across re-upserts", async () => {
    const store = new GraphStore(join(workspace, "graph.kuzu"));
    stores.push(store);
    const engine = new EngineCore(ledger, store);
    engine.upsertClaim("t1", { ...CLAIM });
    engine.upsertClaim("t1", { ...CLAIM, posterior: 0.8 });
    engine.upsertClaim("t1", { ...CLAIM, claim_id: "c2", text: "endpoint", kill_edges: [] });
    expect(() => ledger.verifyGraphChain()).not.toThrow();
    const snapshot = await store.snapshotState();
    expect(snapshot.KILL_EDGE).toEqual([["c1", "c2"]]);
    expect((snapshot.Claim as Record<string, any>)["c1"]["posterior"]).toBe(0.8);
  });
});
