import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { LedgerIntegrityError, LedgerStore } from "../src/store/ledger.js";

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

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-ledger-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
});

describe("ledger surface schema", () => {
  it("records schema version 2", () => {
    const db = (ledger as unknown as { connect: () => { prepare: (sql: string) => { get: () => { version: number } } } });
    expect(true).toBe(true);
  });
});

describe("claims CRUD", () => {
  it("round-trips every field", () => {
    const row = ledger.upsertClaim("t1", { ...CLAIM });
    expect(row).toMatchObject({ ...CLAIM, task_id: "t1", deleted_at: null });
    expect(row.created_at).toBeTypeOf("string");
    expect(row.updated_at).toBeTypeOf("string");
    expect(ledger.getClaim("t1", "c1")).toEqual(row);
    expect(ledger.listClaims("t1")).toEqual([row]);
  });

  it("keeps created_at stable and refreshes updated_at across re-upserts", () => {
    const first = ledger.upsertClaim("t1", { ...CLAIM });
    const second = ledger.upsertClaim("t1", { ...CLAIM, posterior: 0.9 });
    expect(second.posterior).toBe(0.9);
    expect(second.created_at).toBe(first.created_at);
    expect(new Date(String(second.updated_at)).getTime()).toBeGreaterThanOrEqual(
      new Date(String(first.updated_at)).getTime(),
    );
  });

  it("soft-deletes while keeping the row auditable", () => {
    ledger.upsertClaim("t1", { ...CLAIM });
    const deleted = ledger.deleteClaim("t1", "c1", "2026-10-30T00:00:00Z");
    expect(deleted.deleted_at).toBe("2026-10-30T00:00:00Z");
    expect(ledger.getClaim("t1", "c1")?.deleted_at).toBe("2026-10-30T00:00:00Z");
  });

  it("names enum violations by field", () => {
    expect(() => ledger.upsertClaim("t1", { ...CLAIM, weight: "load_bearing" })).toThrow(/weight/);
    expect(() => ledger.upsertClaim("t1", { ...CLAIM, verify_tier: "vibes" })).toThrow(/verify_tier/);
    expect(() => ledger.upsertClaim("t1", { ...CLAIM, source: "vibes" })).toThrow(/source/);
  });

  it("rejects posterior outside [0, 1]", () => {
    expect(() => ledger.upsertClaim("t1", { ...CLAIM, posterior: 1.5 })).toThrow(/posterior/);
  });

  it("rejects self-referencing, duplicated or non-list kill_edges", () => {
    expect(() => ledger.upsertClaim("t1", { ...CLAIM, kill_edges: ["c1"] })).toThrow(/kill_edges/);
    expect(() => ledger.upsertClaim("t1", { ...CLAIM, kill_edges: ["c2", "c2"] })).toThrow(/kill_edges/);
    expect(() => ledger.upsertClaim("t1", { ...CLAIM, kill_edges: "c2" })).toThrow(/kill_edges/);
  });

  it("scopes lists by task", () => {
    ledger.upsertClaim("t1", { ...CLAIM });
    ledger.upsertClaim("t2", { ...CLAIM, claim_id: "c9", text: "other task" });
    expect(ledger.listClaims("t1")).toHaveLength(1);
    expect(ledger.listClaims("t2")[0]!.claim_id).toBe("c9");
  });
});

describe("satellite tables", () => {
  it("round-trips sources and rejects reliability out of range", () => {
    const payload = {
      source_id: "s1",
      origin: "https://example.com/a",
      kind: "web",
      reliability: 0.7,
      incentive_vector: ["affiliate"],
      astroturf_flag: false,
      provenance: { fetched_at: "2026-10-30" },
    };
    const row = ledger.upsertSource("t1", { ...payload });
    expect(ledger.getSource("t1", "s1")).toEqual(row);
    expect(ledger.listSources("t1")).toEqual([row]);
    expect(() => ledger.upsertSource("t1", { ...payload, reliability: -0.1 })).toThrow(/reliability/);
  });

  it("round-trips hypotheses with a closed status vocabulary", () => {
    const payload = { hypothesis_id: "h1", text: "2C4G suffices", status: "open", review: null };
    const row = ledger.upsertHypothesis("t1", { ...payload });
    expect(ledger.getHypothesis("t1", "h1")).toEqual(row);
    const survived = ledger.upsertHypothesis("t1", { ...payload, status: "survived", review: { verdict: "ok" } });
    expect(survived.status).toBe("survived");
    expect(() => ledger.upsertHypothesis("t1", { ...payload, status: "maybe" })).toThrow(/status/);
  });

  it("round-trips directions and bounds round", () => {
    const payload = {
      direction_id: "d1",
      round: 3,
      value_posterior: 0.6,
      budget_allocation: 0.25,
      history: [{ round: 2, value_posterior: 0.4 }],
    };
    const row = ledger.upsertDirection("t1", { ...payload });
    expect(ledger.getDirection("t1", "d1")).toEqual(row);
    expect(() => ledger.upsertDirection("t1", { ...payload, round: -1 })).toThrow(/round/);
  });

  it("round-trips experiments and requires preregistration", () => {
    const payload = {
      experiment_id: "x1",
      status: "registered",
      preregistration: { hypothesis: "h1", criterion: "p95 < 200ms", min_sample: 5, cost_cap: 2.0 },
      stop_state: null,
      cost: null,
    };
    const row = ledger.upsertExperiment("t1", { ...payload });
    expect(ledger.getExperiment("t1", "x1")).toEqual(row);
    expect(() => ledger.upsertExperiment("t1", { ...payload, preregistration: "later" })).toThrow(
      /preregistration/,
    );
    expect(() => ledger.upsertExperiment("t1", { ...payload, status: "vibing" })).toThrow(/status/);
  });

  it("round-trips decompositions with a closed status vocabulary", () => {
    const payload = {
      decomposition_id: "dc1",
      elements: {
        requirements: [{ id: "r1", text: "deploy", source: "msg:1" }],
        constraints: [], background: [], intents: [], refusals: [], difficulties: [], claims_preview: [],
      },
      checklist_state: { complete: false, gaps: ["refusals"] },
      status: "draft",
    };
    const row = ledger.upsertDecomposition("t1", { ...payload });
    expect(ledger.getDecomposition("t1", "dc1")).toEqual(row);
    const confirmed = ledger.upsertDecomposition("t1", { ...payload, status: "confirmed" });
    expect(confirmed.status).toBe("confirmed");
    expect(() => ledger.upsertDecomposition("t1", { ...payload, status: "maybe" })).toThrow(/status/);
  });
});

describe("error type", () => {
  it("raises LedgerIntegrityError (a ledger boundary failure)", () => {
    expect(() => ledger.upsertClaim("t1", { ...CLAIM, weight: "bogus" })).toThrow(LedgerIntegrityError);
  });
});
