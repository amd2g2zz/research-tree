import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import Database from "better-sqlite3";
import { beforeEach, describe, expect, it } from "vitest";

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
const FORK_RECORD: [string, Record<string, unknown>] = [
  "fork.edge",
  { child_version_id: "t2:0", parent_version_id: "t1:0" },
];

let workspace: string;
let ledger: LedgerStore;

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-engine-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
});

describe("engine ports", () => {
  it("enforces the GraphProjection contract structurally", () => {
    expect(() => new EngineCore(ledger, {} as never)).toThrow(/GraphProjection/);
  });

  it("writes only the log without a projection", async () => {
    const engine = new EngineCore(ledger);
    const record = await engine.appendGraphEvent(...CLAIM_RECORD);
    expect(record.seq).toBe(1);
    expect(engine.graphEvents()).toHaveLength(1);
  });
});

describe("event chain integrity", () => {
  it("detects a tampered payload", async () => {
    const engine = new EngineCore(ledger);
    await engine.appendGraphEvent(...CLAIM_RECORD);
    const raw = new Database(ledger.databasePath);
    raw.prepare("UPDATE graph_events SET payload_json = ? WHERE seq = 1").run('{"claim":{"id":"tampered"}}');
    raw.close();
    expect(() => ledger.verifyGraphChain()).toThrow(/hash mismatch/);
  });

  it("detects a deleted row", async () => {
    const engine = new EngineCore(ledger);
    await engine.appendGraphEvent(...CLAIM_RECORD);
    await engine.appendGraphEvent(...FORK_RECORD);
    const raw = new Database(ledger.databasePath);
    raw.prepare("DELETE FROM graph_events WHERE seq = 1").run();
    raw.close();
    expect(() => ledger.verifyGraphChain()).toThrow(/gap/);
  });

  it("chains appends from genesis", async () => {
    const engine = new EngineCore(ledger);
    await engine.appendGraphEvent(...CLAIM_RECORD);
    await engine.appendGraphEvent(...FORK_RECORD);
    expect(() => ledger.verifyGraphChain()).not.toThrow();
    const records = engine.graphEvents();
    expect(records[0]!.prev_hash).toBe("0".repeat(64));
    expect(records[1]!.prev_hash).toBe(records[0]!.content_hash);
  });
});
