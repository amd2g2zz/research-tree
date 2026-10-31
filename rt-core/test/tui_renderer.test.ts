import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { renderTuiFrame } from "../src/tui/renderer.js";
import { EngineCore } from "../src/store/engine.js";
import { LedgerStore } from "../src/store/ledger.js";
import { VersionStore } from "../src/versions/store.js";
import { ProductStateMachine } from "../src/state/machine.js";

import { GraphStore } from "../src/graph/projection.js";
import { parseDecomposition, confirmDecomposition } from "../src/decomposition/engine.js";

let workspace: string;
let ledger: LedgerStore;
let versions: VersionStore;
let graph: GraphStore;
let engine: EngineCore;
let machine: ProductStateMachine;

const SNAPSHOT = {
  elements: { requirements: [{ id: "r1", text: "deploy" }] },
  claims: [{ id: "c-mob", posterior: 0.9 }],
  evidence_refs: [],
  report: {},
  deleted_nodes: [],
};

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-tui-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
  versions = new VersionStore(ledger);
  graph = new GraphStore(join(workspace, "graph.kuzu"));
  engine = new EngineCore(ledger);
  machine = new ProductStateMachine(engine, versions, graph);
});

describe("TUI frame (issue #580, same-source over the event stream)", () => {
  it("renders a frame with sidebar, phase, claims and console sections", async () => {
    machine.openTask("t1");
    const frame = await renderTuiFrame({ ledger, versions, machine, graph });
    expect(frame).toContain("SIDEBAR");
    expect(frame).toContain("PHASE");
    expect(frame).toContain("CLAIMS");
    expect(frame).toContain("CONSOLE");
  });

  it("shows the claim row with posterior after a commit", async () => {
    machine.openTask("t1");
    engine.upsertClaim("t1", {
      claim_id: "c1", text: "rt works offline", source: "user", weight: "make_or_break",
      posterior: 0.5, verify_tier: "multi-source", kill_edges: [], incentive_flag: false,
    });
    const frame = await renderTuiFrame({ ledger, versions, machine, graph });
    expect(frame).toContain("c1");
    expect(frame).toContain("0.50");
  });

  it("status never rides color alone (text state always present)", async () => {
    machine.openTask("t1");
    const frame = await renderTuiFrame({ ledger, versions, machine, graph });
    // the red-line check: state words appear as text next to any status marker
    expect(frame).toContain("phase:");
    expect(frame).toMatch(/phase: \w+/);
  });

  it("draft rows are labeled 未冻结·不可跟踪 (red line)", async () => {
    machine.openTask("t1");
    const frame = await renderTuiFrame({ ledger, versions, machine, graph });
    expect(frame).toContain("未冻结·不可跟踪");
  });

  it("committed versions show the frozen banner (vN·hash·verdict)", async () => {
    machine.openTask("t1");
    versions.openDraft("t1", { snapshot: SNAPSHOT, baseV: null });
    machine.transition("t1", { event: "confirm" });
    confirmDecomposition(ledger, "t1", parseDecomposition(completeExtraction()), { refusals: "none" }, { decomposition_id: "dc-1" });
    machine.attachDecomposition("t1", "dc-1");
    const { parseRunPlan } = await import("../src/state/run_plan.js");
    machine.attachRunPlan("t1", parseRunPlan(PLAN()));
    machine.transition("t1", { event: "sign" });
    machine.transition("t1", { event: "research-completed" });
    machine.freezeTask("t1", { verdict: "GO", summary: "first" });
    const frame = await renderTuiFrame({ ledger, versions, machine, graph });
    expect(frame).toContain("v0");
    expect(frame).toContain("GO");
    expect(frame).toMatch(/[0-9a-f]{12}/); // truncated commit hash
  });
});

function completeExtraction(): Record<string, unknown> {
  const SOURCE = { kind: "chat-message" as const, ref: "msg:1", quote: "quote" };
  return {
    requirements: [{ text: "r", source: SOURCE }],
    constraints: [{ text: "c", source: SOURCE, hardness: "hard" }],
    background: [{ text: "b", source: SOURCE }],
    intents: [{ text: "i", source: SOURCE }],
    refusals: [],
    difficulties: [{ text: "d", source: SOURCE, kill_candidates: ["cp1"] }],
    claims_preview: [{ id: "cp1", text: "claim", kill_condition: "fails" }],
  };
}

const PLAN = () => ({
  plan_id: "plan-tui",
  stages: [{ id: "s1", title: "cluster", claim_ids: [], depends_on: [] }],
  budget: { capMs: 12 * 3600 * 1000 },
  yaw_checks: [
    { slot: "plan-level", mode: "auto" },
    { slot: "problem-level", mode: "human" },
    { slot: "knowledge-level", mode: "auto" },
  ],
});
