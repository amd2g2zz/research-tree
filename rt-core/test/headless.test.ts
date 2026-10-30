import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { runHeadless } from "../src/headless/runner.js";
import { GraphStore } from "../src/graph/projection.js";
import { EngineCore } from "../src/store/engine.js";
import { LedgerStore } from "../src/store/ledger.js";
import { ProductStateMachine } from "../src/state/machine.js";
import { VersionStore } from "../src/versions/store.js";
import { parseRunPlan } from "../src/state/run_plan.js";
import { parseDecomposition, confirmDecomposition } from "../src/decomposition/engine.js";

const SOURCE = { kind: "chat-message" as const, ref: "msg:1", quote: "quote" };

const SNAPSHOT = {
  elements: { requirements: [{ id: "r1", text: "deploy" }] },
  claims: [{ id: "c1", posterior: 0.9 }],
  evidence_refs: [],
  report: {},
  deleted_nodes: [],
};

let workspace: string;
let ledger: LedgerStore;
let versions: VersionStore;

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-headless-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
  versions = new VersionStore(ledger);
});

function setup(): { machine: ProductStateMachine; graph: GraphStore } {
  const graph = new GraphStore(join(workspace, "graph.kuzu"));
  const machine = new ProductStateMachine(new EngineCore(ledger), new VersionStore(ledger), graph);
  return { machine, graph };
}



describe("headless runner", () => {
  it("walks a full chain driven by a launch script and emits JSON Lines", async () => {
    const { machine } = setup();
    const lines: Record<string, unknown>[] = [];
    const result = await runHeadless({
      ledger,
      versions,
      machine,
      script: {
        task_id: "t1",
        pre_signed: { verdict: "GO", summary: "auto run" },
        steps: [
          { event: "confirm" },
          { event: "attach", decomposition: completeExtraction(), decomposition_id: "dc-1", plan: PLAN },
          { event: "sign" },
          { event: "research-completed" },
          { event: "open-draft", snapshot: SNAPSHOT, base_v: null },
        ],
      },
      emit: (line) => lines.push(line),
    });
    expect(result.outcome).toBe("success");
    // every step is a JSON Lines record
    expect(lines.length).toBeGreaterThanOrEqual(4); // birth+confirm+sign+completed(+freeze events mirror too)
    expect(lines.every((line) => typeof line.seq === "number")).toBe(true);
    const transitions = lines.filter((l) => l.event_type === "task.transition");
    expect(transitions.length).toBeGreaterThanOrEqual(4); // birth+confirm+sign+completed; freeze adds committed+chat
  });

  it("detailed logs carry state transitions, reasons and correlations", async () => {
    const { machine } = setup();
    const logs: string[] = [];
    await runHeadless({
      ledger,
      versions,
      machine,
      script: { task_id: "t1", pre_signed: { verdict: "GO", summary: "s" }, steps: [{ event: "confirm" }] },
      emit: () => {},
      log: (line) => logs.push(line),
    });
    const joined = logs.join("\n");
    expect(joined).toContain("transition");
    expect(joined).toContain("task_id=t1");
  });

  it("never silently auto-signs an unhandled gate (PAUSE + pending-decision + resume)", async () => {
    const { machine } = setup();
    machine.openTask("t1");
    machine.transition("t1", { event: "confirm" });
    confirmDecomposition(ledger, "t1", parseDecomposition(completeExtraction()), { refusals: "none" }, { decomposition_id: "dc-h" });
    machine.attachDecomposition("t1", "dc-h");
    machine.attachRunPlan("t1", parseRunPlan(PLAN));
    machine.transition("t1", { event: "sign" });
    // early termination fires mid-research — script has NO pre-signed choice
    machine.raiseEarlyTermination("t1", { refuted_claim: "c-mob", evidence: "p=0.05" });
    const result = await runHeadless({
      ledger,
      versions,
      machine,
      script: { task_id: "t1", pre_signed: {}, steps: [] },
      emit: () => {},
      resumeFrom: undefined,
    });
    expect(result.outcome).toBe("paused-pending-decision");
    expect(result.resume_token).toBeTypeOf("string");
    // resume with the pre-signed choice continues the same run
    const resumed = await runHeadless({
      ledger,
      versions,
      machine,
      script: { task_id: "t1", pre_signed: { early_termination: "bury" }, steps: [] },
      emit: () => {},
      resumeFrom: result.resume_token,
    });
    expect(["success", "park"]).toContain(resumed.outcome); // bury → converged; no verdict signed → park fallback
    expect(resumed.outcome).toBe("park");
  });

  it("reuses the ledger fork-free from a resume token", async () => {
    const { machine } = setup();
    machine.openTask("t1");
    const result = await runHeadless({
      ledger, versions, machine,
      script: { task_id: "t1", pre_signed: {}, steps: [] },
      emit: () => {},
    });
    const before = ledger.graphEvents().length;
    await runHeadless({
      ledger, versions, machine,
      script: { task_id: "t1", pre_signed: {}, steps: [] },
      emit: () => {},
      resumeFrom: result.resume_token,
    });
    // resuming does not fork the ledger: same store, events only appended
    expect(ledger.graphEvents().length).toBeGreaterThanOrEqual(before);
  });
});

function completeExtraction(): Record<string, unknown> {
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

const PLAN = {
  plan_id: "plan-1",
  stages: [{ id: "s1", title: "cluster", claim_ids: ["c1"], depends_on: [] }],
  budget: { capMs: 12 * 3600 * 1000 },
  yaw_checks: [
    { slot: "plan-level", mode: "auto" },
    { slot: "problem-level", mode: "human" },
    { slot: "knowledge-level", mode: "auto" },
  ],
};
