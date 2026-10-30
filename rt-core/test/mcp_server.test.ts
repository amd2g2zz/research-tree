import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { createMcpServer, type McpToolCaller } from "../src/mcp/server.js";
import { LedgerStore } from "../src/store/ledger.js";
import { VersionStore } from "../src/versions/store.js";
import { ProductStateMachine } from "../src/state/machine.js";
import { EngineCore } from "../src/store/engine.js";
import { parseDecomposition, confirmDecomposition } from "../src/decomposition/engine.js";

const SOURCE = { kind: "chat-message" as const, ref: "msg:1", quote: "quote" };

let workspace: string;
let ledger: LedgerStore;
let caller: McpToolCaller;
let machine: ProductStateMachine;

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-mcp-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
  const versions = new VersionStore(ledger);
  machine = new ProductStateMachine(new EngineCore(ledger), versions, undefined);
  caller = createMcpServer({ ledger, versions, machine });
});

describe("MCP server tools (projection-only exit)", () => {
  it("rt.start opens a task and reports the phase", async () => {
    const result = await caller.call("rt.start", { task_id: "t1" });
    expect(result).toMatchObject({ task_id: "t1", phase: "chat" });
  });

  it("rt.status reports phase and ledger digest", async () => {
    await caller.call("rt.start", { task_id: "t1" });
    const status = await caller.call("rt.status", { task_id: "t1" });
    expect(status).toMatchObject({ task_id: "t1", phase: "chat" });
    expect((status as Record<string, unknown>).ledger_events).toBeTypeOf("number");
  });

  it("rt.correct routes through the same correction path (no privileged channel)", async () => {
    await caller.call("rt.start", { task_id: "t1" });
    const result = await caller.call("rt.correct", {
      task_id: "t1",
      kind: "preference-change",
      payload: { note: "prefer lightweight" },
    });
    expect(result).toMatchObject({ accepted: true, routed: "correction" });
  });

  it("rt.verdict returns report and verdict paths when committed", async () => {
    // walk to committed via the machine, then ask for the verdict
    const versions = new VersionStore(ledger);
    versions.openDraft("t1", {
      snapshot: { elements: null, claims: [], evidence_refs: [], report: { summary: "ok" }, deleted_nodes: [] },
      baseV: null,
    });
    machine.openTask("t1");
    machine.transition("t1", { event: "confirm" });
    confirmDecomposition(ledger, "t1", parseDecomposition({
      requirements: [{ text: "r", source: SOURCE }],
      constraints: [{ text: "c", source: SOURCE, hardness: "hard" }],
      background: [{ text: "b", source: SOURCE }],
      intents: [{ text: "i", source: SOURCE }],
      refusals: [],
      difficulties: [{ text: "d", source: SOURCE, kill_candidates: ["cp1"] }],
      claims_preview: [{ id: "cp1", text: "claim", kill_condition: "fails" }],
    }), { refusals: "none" }, { decomposition_id: "dc-mcp" });
    machine.attachDecomposition("t1", "dc-mcp");
    const { parseRunPlan } = await import("../src/state/run_plan.js");
    machine.attachRunPlan("t1", parseRunPlan({
      plan_id: "p", stages: [], budget: { capMs: 12 * 3600 * 1000 },
      yaw_checks: [{ slot: "plan-level", mode: "auto" }, { slot: "problem-level", mode: "human" }, { slot: "knowledge-level", mode: "auto" }],
    }));
    machine.transition("t1", { event: "sign" });
    machine.transition("t1", { event: "research-completed" });
    const committed = machine.freezeTask("t1", { verdict: "GO", summary: "mcp walk" });

    const verdict = await caller.call("rt.verdict", { task_id: "t1" });
    expect(verdict).toMatchObject({
      task_id: "t1", v: committed.v, verdict: "GO", commit_hash: committed.commit_hash,
    });
    expect(verdict.report_path).toContain("report");
    expect(verdict.verdict_path).toContain("verdict");
  });

  it("rejects unknown tools", async () => {
    await expect(caller.call("rt.self_destruct", {})).rejects.toThrow(/unknown tool/);
  });
});
