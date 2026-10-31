import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { LedgerStore } from "../src/store/ledger.js";
import { VersionStore } from "../src/versions/store.js";
import { AutoMemory, MemoryError, MEMORY_KINDS, type MemoryScope } from "../src/memory/store.js";

let workspace: string;
let ledger: LedgerStore;
let versions: VersionStore;
let memory: AutoMemory;

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-mem-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
  versions = new VersionStore(ledger);
  memory = new AutoMemory(ledger, versions);
});

const PROVENANCE = { task_id: "t1", claim_id: "c1", quote: "2C4G 越快上越好" };

function rememberLesson(id: string, text: string, scope: MemoryScope = "project:pA") {
  return memory.remember({ memory_id: id, scope, kind: "lesson", text, provenance: PROVENANCE });
}

describe("auto memory (simple, typed, append-only)", () => {
  it("remembers with provenance and recalls bounded + deterministic", () => {
    rememberLesson("m1", "lesson A");
    rememberLesson("m2", "lesson B");
    rememberLesson("m3", "lesson C");

    const first = memory.recall({ scope: "project:pA", limit: 2 });
    expect(first.total).toBe(3);
    expect(first.index).toHaveLength(2); // bounded
    expect(first.index.map((e) => e.text)).toEqual(["lesson C", "lesson B"]); // newest first, deterministic
    const again = memory.recall({ scope: "project:pA", limit: 2 });
    expect(again.index).toEqual(first.index); // same query → same result (KV-cache friendly)

    // char budget caps the total text volume
    const budgeted = memory.recall({ scope: "project:pA", char_budget: 16 });
    expect(budgeted.index.reduce((sum, e) => sum + e.text.length, 0)).toBeLessThanOrEqual(16);

    // lazy detail: provenance only via load
    expect(first.index[0]).not.toHaveProperty("provenance");
    expect(memory.load("m1")?.provenance).toMatchObject({ claim_id: "c1" });
  });

  it("user-scope memories are visible from any project scope; project scopes stay isolated", () => {
    memory.remember({ memory_id: "u1", scope: "user", kind: "preference", text: "prefers minimal deploys", provenance: PROVENANCE });
    rememberLesson("m1", "project lesson", "project:pA");
    rememberLesson("m2", "other project lesson", "project:pB");

    const inA = memory.recall({ scope: "project:pA" });
    expect(inA.index.map((e) => e.memory_id).sort()).toEqual(["m1", "u1"]); // user layer global
    const inB = memory.recall({ scope: "project:pB" });
    expect(inB.index.map((e) => e.memory_id).sort()).toEqual(["m2", "u1"]);
    expect(inB.index.some((e) => e.memory_id === "m1")).toBe(false); // zero cross-talk
  });

  it("three rejections pinned: missing provenance, non-closed kind (incl. user-profile red line), bad scope", () => {
    expect(() => memory.remember({ memory_id: "x1", scope: "user", kind: "lesson", text: "t", provenance: {} })).toThrow(/provenance/);
    expect(() => memory.remember({ memory_id: "x2", scope: "user", kind: "user-profile" as never, text: "t", provenance: PROVENANCE })).toThrow(
      /kind/,
    );
    expect(MEMORY_KINDS).not.toContain("user-profile"); // 永不按用户画像改变行为
    expect(() => rememberLesson("x3", "t", "workspace-wide" as MemoryScope)).toThrow(/scope/);
    expect(() => rememberLesson("x4", "t", "project:")).toThrow(/scope/);
  });

  it("idempotent dedupe: same content updates in place instead of duplicating", () => {
    const a = rememberLesson("m1", "identical lesson");
    const b = rememberLesson("m2", "identical lesson"); // different id, same content+scope+kind
    expect(b.memory_id).toBe(a.memory_id);
    expect(memory.recall({ scope: "project:pA" }).total).toBe(1);
  });

  it("harvest writes lessons from refuted claims and outcomes from commits — idempotently", () => {
    ledger.upsertClaim("t1", {
      claim_id: "c-ref",
      text: "2C4G suffices under load",
      source: "research",
      weight: "make_or_break",
      posterior: 0.05,
      verify_tier: "multi-source",
      kill_edges: [],
      incentive_flag: false,
    });
    ledger.upsertClaim("t1", {
      claim_id: "c-ok",
      text: "p95 acceptable",
      source: "research",
      weight: "important",
      posterior: 0.95,
      verify_tier: "multi-source",
      kill_edges: [],
      incentive_flag: false,
    });
    versions.openDraft("t1", {
      snapshot: { elements: {}, claims: [], evidence_refs: [], report: {}, deleted_nodes: [] },
      baseV: null,
    });
    versions.freeze("t1", { verdict: "NO-GO", summary: "OOM ceiling" });

    memory.harvest("t1", { project_scope: "project:pA" });
    const lessons = memory.recall({ scope: "project:pA", kinds: ["lesson"] });
    expect(lessons.index.map((e) => e.text)).toEqual(["2C4G suffices under load"]); // only refuted
    const outcomes = memory.recall({ scope: "project:pA", kinds: ["outcome"] });
    expect(outcomes.index).toHaveLength(1);
    expect(outcomes.index[0]?.text).toContain("NO-GO");

    // idempotent: harvesting again writes nothing new
    memory.harvest("t1", { project_scope: "project:pA" });
    expect(memory.recall({ scope: "project:pA" }).total).toBe(2);
  });

  it("forget is append-only: recall loses the entry, the row remains superseded", () => {
    rememberLesson("m1", "outdated lesson");
    memory.forget("m1", "superseded by new postmortem");
    expect(memory.recall({ scope: "project:pA" }).total).toBe(0);
    const row = memory.load("m1");
    expect(row?.status).toBe("superseded"); // never physically deleted
    const audited = ledger
      .graphEvents()
      .filter((e) => e.event_type === "provider.action")
      .filter((e) => String((e.payload as Record<string, unknown>).target).startsWith("memory:forget"));
    expect(audited).toHaveLength(1);
  });

  it("every write lands an audit event (prior-only, auditable by design)", () => {
    rememberLesson("m1", "lesson");
    const audited = ledger
      .graphEvents()
      .filter((e) => e.event_type === "provider.action")
      .filter((e) => String((e.payload as Record<string, unknown>).target).startsWith("memory:"));
    expect(audited.length).toBeGreaterThanOrEqual(1);
  });

  it("unknown memory: load returns null, forget throws typed", () => {
    expect(memory.load("ghost")).toBeNull();
    expect(() => memory.forget("ghost", "reason")).toThrow(MemoryError);
  });
});
