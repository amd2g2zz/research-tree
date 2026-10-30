import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { parseRunPlan, validateRunPlan } from "../src/state/run_plan.js";
import { ProductStateMachine } from "../src/state/machine.js";
import { confirmDecomposition, parseDecomposition } from "../src/decomposition/engine.js";
import { GraphStore } from "../src/graph/projection.js";
import { EngineCore } from "../src/store/engine.js";
import { LedgerStore } from "../src/store/ledger.js";
import { VersionStore } from "../src/versions/store.js";

const SNAPSHOT = {
  elements: { requirements: [{ id: "r1", text: "deploy" }] },
  claims: [{ id: "c1", posterior: 0.9 }],
  evidence_refs: [],
  report: {},
  deleted_nodes: [],
};

const PLAN = (): import("../src/state/run_plan.js").RunPlan => ({
  plan_id: "plan-1",
  stages: [{ id: "s1", title: "factor cluster", claim_ids: ["c1"], depends_on: [] }],
  budget: { capMs: 12 * 3600 * 1000 },
  yaw_checks: [
    { slot: "plan-level", mode: "auto" },
    { slot: "problem-level", mode: "human" },
    { slot: "knowledge-level", mode: "auto" },
  ],
});

let workspace: string;
let ledger: LedgerStore;
let versions: VersionStore;
let store: GraphStore;
let machine: ProductStateMachine;

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-state-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
  versions = new VersionStore(ledger);
  store = new GraphStore(join(workspace, "graph.kuzu"));
  machine = new ProductStateMachine(new EngineCore(ledger), versions, store);
});

const SOURCE = { kind: "chat-message" as const, ref: "msg:1", quote: "quote" };

/** A complete six-element extraction (checklist-satisfying). */
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

/** Walk a task from chat to a first committed version. */
function walkToCommitted(machine: ProductStateMachine, taskId: string, ledger: LedgerStore): void {
  machine.openTask(taskId);
  machine.transition(taskId, { event: "confirm" });           // chat → decompose
  confirmDecomposition(ledger, taskId, parseDecomposition(completeExtraction()), { refusals: "none" }, { decomposition_id: `dc-${taskId}-1` });
  machine.attachDecomposition(taskId, `dc-${taskId}-1`);        // decompose prerequisite
  machine.attachRunPlan(taskId, PLAN());                        // decompose prerequisite (sign)
  machine.transition(taskId, { event: "sign" });               // decompose → research
  machine.transition(taskId, { event: "research-completed" }); // research → converged
  machine.freezeTask(taskId, { verdict: "GO", summary: "first" }); // converged → committed
}

describe("legal transition walk (对话→计划→研究→裁决→提交→继承)", () => {
  it("walks the full chain and commits v0 through the freeze gate", () => {
    versions.openDraft("t1", { snapshot: SNAPSHOT, baseV: null });
    walkToCommitted(machine, "t1", ledger);
    expect(machine.phaseOf("t1")).toBe("chat"); // inherit-and-realign
    const committed = versions.latestVersion("t1")!;
    expect(committed.v).toBe(0);
    expect(committed.verdict).toBe("GO");
    // every transition is an engine fact in the event stream
    const transitions = machine
      .events()
      .filter((e) => e.event_type === "task.transition")
      .map((e) => e.payload as Record<string, unknown>);
    expect(transitions.map((t) => t.to)).toEqual([
      "chat", "decompose", "research", "converged", "committed", "chat",
    ]);
  });

  it("continues research as version+1 after inherit-and-realign", () => {
    versions.openDraft("t1", { snapshot: SNAPSHOT, baseV: null });
    walkToCommitted(machine, "t1", ledger);
    machine.transition("t1", { event: "confirm" });
    confirmDecomposition(ledger, "t1", parseDecomposition(completeExtraction()), { refusals: "none" }, { decomposition_id: "dc-t1-2" });
    machine.attachDecomposition("t1", "dc-t1-2");
    machine.attachRunPlan("t1", PLAN());
    machine.transition("t1", { event: "sign" });
    machine.transition("t1", { event: "research-completed" });
    versions.mutateDraft("t1", (draft) => {
      (draft.snapshot.claims as Array<Record<string, unknown>>).push({ id: "c2", posterior: 0.4 });
    });
    machine.freezeTask("t1", { verdict: "PARK", summary: "second" });
    expect(versions.latestVersion("t1")!.v).toBe(1);
  });
});

describe("illegal transitions fail closed", () => {
  it("rejects every off-matrix transition without mutating state", () => {
    versions.openDraft("t1", { snapshot: SNAPSHOT, baseV: null });
    machine.openTask("t1");
    machine.transition("t1", { event: "confirm" }); // → decompose
    // decompose → converged is off-matrix
    expect(() => machine.transition("t1", { event: "research-completed" })).toThrow(/illegal transition/);
    expect(machine.phaseOf("t1")).toBe("decompose"); // unchanged
  });

  it("rejects research without a confirmed decomposition (unsigned plan)", () => {
    versions.openDraft("t1", { snapshot: SNAPSHOT, baseV: null });
    machine.openTask("t1");
    machine.transition("t1", { event: "confirm" }); // → decompose
    // no decomposition attached, no plan
    expect(() => machine.transition("t1", { event: "sign" })).toThrow(/confirmed decomposition/);
    expect(machine.phaseOf("t1")).toBe("decompose");
  });

  it("rejects freeze outside converged (the freeze gate has no bypass)", () => {
    versions.openDraft("t1", { snapshot: SNAPSHOT, baseV: null });
    expect(() => machine.freezeTask("t1", { verdict: "GO", summary: "s" })).toThrow(/freeze gate/);
    machine.openTask("t1");
    machine.transition("t1", { event: "confirm" });
    expect(() => machine.freezeTask("t1", { verdict: "GO", summary: "s" })).toThrow(/freeze gate/);
    expect(versions.latestVersion("t1")).toBeNull();
  });
});

describe("mid-chain decomposition re-entry", () => {
  it("returns research → chat without losing ledger state, then re-enters research", () => {
    versions.openDraft("t1", { snapshot: SNAPSHOT, baseV: null });
    walkToResearch(machine, "t1", ledger);
    ledger.upsertClaim("t1", {
      claim_id: "c-live", text: "in-research claim", source: "research", weight: "important",
      posterior: 0.6, verify_tier: "multi-source", kill_edges: [], incentive_flag: false,
    });
    machine.transition("t1", { event: "user-recalled" }); // research → chat (re-entry)
    expect(machine.phaseOf("t1")).toBe("chat");
    expect(ledger.getClaim("t1", "c-live")).not.toBeNull(); // ledger intact
    machine.transition("t1", { event: "confirm" });
    confirmDecomposition(ledger, "t1", parseDecomposition(completeExtraction()), { refusals: "none" }, { decomposition_id: "dc-t1-re" });
    machine.attachDecomposition("t1", "dc-t1-re");
    machine.attachRunPlan("t1", PLAN());
    machine.transition("t1", { event: "sign" });
    expect(machine.phaseOf("t1")).toBe("research");
  });
});

describe("early-termination hard gate (fail-closed) + PAUSE primitive", () => {
  it("pauses research on a refuted make-or-break and blocks continuation until the user chooses", () => {
    versions.openDraft("t1", { snapshot: SNAPSHOT, baseV: null });
    walkToResearch(machine, "t1", ledger);
    machine.raiseEarlyTermination("t1", { refuted_claim: "c-mob", evidence: "posterior 0.05" });
    expect(machine.phaseOf("t1")).toBe("paused");
    // research cannot continue while paused
    expect(() => machine.transition("t1", { event: "research-completed" })).toThrow(/paused/);
    machine.resolveEarlyTermination("t1", { choice: "continue" });
    expect(machine.phaseOf("t1")).toBe("research");
  });

  it("burying converges with a NO-GO recommendation (the question is not the verdict)", () => {
    versions.openDraft("t1", { snapshot: SNAPSHOT, baseV: null });
    walkToResearch(machine, "t1", ledger);
    machine.raiseEarlyTermination("t1", { refuted_claim: "c-mob", evidence: "posterior 0.05" });
    machine.resolveEarlyTermination("t1", { choice: "bury" });
    expect(machine.phaseOf("t1")).toBe("converged");
  });
});

describe("fork transition", () => {
  it("produces a new task with inherited v0 snapshot and chat phase", () => {
    versions.openDraft("t1", { snapshot: SNAPSHOT, baseV: null });
    walkToCommitted(machine, "t1", ledger);
    const forked = machine.forkTask({ fromTask: "t1", fromV: 0, toTask: "t2" });
    expect(forked.task_id).toBe("t2");
    expect(forked.snapshot).toEqual(SNAPSHOT);
    expect(machine.phaseOf("t2")).toBe("chat");
    expect(versions.forkParent("t2")).toEqual({ task_id: "t1", v: 0 });
  });
});

describe("state is event-sourced", () => {
  it("rehydrates phases from the transition events alone", () => {
    versions.openDraft("t1", { snapshot: SNAPSHOT, baseV: null });
    walkToCommitted(machine, "t1", ledger);
    const reborn = ProductStateMachine.rehydrate(
      machine.events(),
      versions,
      new GraphStore(join(workspace, "reborn.kuzu")),
    );
    expect(reborn.phaseOf("t1")).toBe("chat");
    expect(reborn.phaseOf("t2")).toBeUndefined();
  });
});

describe("run-plan interpreter", () => {
  it("validates the plan shape (stages, 12h budget cap, yaw-check slots)", () => {
    const plan = parseRunPlan(PLAN());
    expect(validateRunPlan(plan)).toEqual([]);
  });

  it("rejects plans with unknown yaw modes or over-cap budgets", () => {
    expect(() =>
      parseRunPlan({
        plan_id: "p",
        stages: [],
        budget: { capMs: 99 * 3600 * 1000 },
        yaw_checks: [{ slot: "plan-level", mode: "auto" }],
      }),
    ).toThrow(/12h product cap/);
    expect(() =>
      parseRunPlan({
        plan_id: "p",
        stages: [],
        budget: { capMs: 12 * 3600 * 1000 },
        yaw_checks: [{ slot: "plan-level", mode: "vibes" }],
      }),
    ).toThrow(/mode/);
    // yaw-slot coverage is validateRunPlan's job (parseRunPlan enforces the cap)
    const sparse = parseRunPlan({
      plan_id: "p", stages: [], budget: { capMs: 12 * 3600 * 1000 }, yaw_checks: [],
    });
    expect(validateRunPlan(sparse)).toContain("yaw-slot:plan-level");
  });

  it("tracks step advancement mechanically", async () => {
    const { parseRunPlan, RunPlanInterpreter } = await import("../src/state/run_plan.js");
    const plan = parseRunPlan(PLAN());
    const interpreter = new RunPlanInterpreter(plan);
    interpreter.advance("s1");
    expect(interpreter.stepStatus("s1")).toBe("advanced");
    interpreter.complete("s1");
    expect(interpreter.stepStatus("s1")).toBe("complete");
  });
});

/** research-phase helper: chat → decompose → (sign) → research */
let reentrySeq = 0;

function walkToResearch(machine: ProductStateMachine, taskId: string, ledger: LedgerStore): void {
  reentrySeq += 1;
  machine.openTask(taskId);
  machine.transition(taskId, { event: "confirm" });
  confirmDecomposition(ledger, taskId, parseDecomposition(completeExtraction()), { refusals: "none" }, { decomposition_id: `dc-${taskId}-${reentrySeq}` });
  machine.attachDecomposition(taskId, `dc-${taskId}-${reentrySeq}`);
  machine.attachRunPlan(taskId, PLAN());
  machine.transition(taskId, { event: "sign" });
}
