import { describe, expect, it } from "vitest";

import {
  checkGlobalCap,
  evaluateStage,
  propagateRefutation,
  selectDispatchable,
  type ClaimState,
  type StageState,
} from "../src/scheduler/engine.js";

function claim(id: string, overrides: Partial<ClaimState> = {}): ClaimState {
  return { id, state: "undecided", posterior: 0.5, ...overrides };
}

function stage(id: string, overrides: Partial<StageState> = {}): StageState {
  return {
    id,
    title: `stage ${id}`,
    status: "in_progress",
    claim_ids: [],
    depends_on: [],
    retries: 0,
    ...overrides,
  };
}

describe("open-loop condition (docs 01: 已决 ∥ EVSI 饱和 ∥ 预算尽 → ROLLUP)", () => {
  it("rolls up when every claim in the stage is decided", () => {
    const decision = evaluateStage(
      stage("s1", { claim_ids: ["c1", "c2"] }),
      [claim("c1", { state: "decided" }), claim("c2", { state: "decided" })],
      { budgetRemainingMs: 1000, evsi: () => 0.8 },
    );
    expect(decision).toMatchObject({ action: "rollup", reason: "all-decided" });
  });

  it("rolls up when EVSI is saturated (placeholder scorer below threshold)", () => {
    const decision = evaluateStage(
      stage("s1", { claim_ids: ["c1"] }),
      [claim("c1", { state: "undecided" })],
      { budgetRemainingMs: 1000, evsi: () => 0.01 },
    );
    expect(decision).toMatchObject({ action: "rollup", reason: "evsi-saturated" });
  });

  it("rolls up when the stage budget is exhausted", () => {
    const decision = evaluateStage(
      stage("s1", { claim_ids: ["c1"] }),
      [claim("c1")],
      { budgetRemainingMs: 0, evsi: () => 0.9 },
    );
    expect(decision).toMatchObject({ action: "rollup", reason: "budget-exhausted" });
  });

  it("keeps drilling while claims are open and EVSI has signal", () => {
    const decision = evaluateStage(
      stage("s1", { claim_ids: ["c1"] }),
      [claim("c1")],
      { budgetRemainingMs: 1000, evsi: () => 0.9 },
    );
    expect(decision.action).toBe("drill-down");
  });
});

describe("belief propagation (append-only reopen)", () => {
  it("reopens descendants of a refuted premise without deleting them", () => {
    const claims = [
      claim("premise", { state: "refuted" }),
      claim("child", { state: "decided", depends_on_claims: ["premise"] }),
      claim("grandchild", { state: "decided", depends_on_claims: ["child"] }),
      claim("unrelated", { state: "decided" }),
    ];
    const propagated = propagateRefutation(claims, "premise");
    const child = propagated.find((c) => c.id === "child")!;
    const grandchild = propagated.find((c) => c.id === "grandchild")!;
    const unrelated = propagated.find((c) => c.id === "unrelated")!;
    expect(child.state).toBe("stale");
    expect(child.reopen_count).toBe(1); // append-only: reopened, not deleted
    expect(grandchild.state).toBe("stale");
    expect(unrelated.state).toBe("decided"); // untouched
  });
});

describe("12h hard cap", () => {
  it("forces convergence with PARK fallback when the cap hits", () => {
    expect(checkGlobalCap({ elapsedMs: 12 * 3600 * 1000 + 1, capMs: 12 * 3600 * 1000 })).toMatchObject({
      forced: true,
      fallback_verdict: "PARK",
    });
    expect(checkGlobalCap({ elapsedMs: 11 * 3600 * 1000, capMs: 12 * 3600 * 1000 }).forced).toBe(false);
  });
});

describe("dispatch (dependency-aware, inverts the #531 greedy cut)", () => {
  it("never dispatches a stage whose dependency is not closed", () => {
    const stages = [
      stage("upstream", { status: "in_progress" }),
      stage("downstream", { depends_on: ["upstream"] }),
    ];
    const ready = selectDispatchable(stages, { maxConcurrency: 4, workerClasses: ["retrieval", "code-reading", "experiment", "verification"] });
    expect(ready.map((s) => s.id)).toEqual(["upstream"]);
  });

  it("dispatches a stage in the same pass once its dependency closes", () => {
    const stages = [
      stage("upstream", { status: "rolled_up" }),
      stage("downstream", { depends_on: ["upstream"] }),
    ];
    const ready = selectDispatchable(stages, { maxConcurrency: 4, workerClasses: ["retrieval"] });
    expect(ready.map((s) => s.id)).toEqual(["downstream"]);
  });

  it("caps concurrent dispatch at 4", () => {
    const stages = ["s1", "s2", "s3", "s4", "s5", "s6"].map((id) => stage(id));
    const ready = selectDispatchable(stages, { maxConcurrency: 4, workerClasses: ["retrieval"] });
    expect(ready).toHaveLength(4);
  });

  it("assigns worker classes round-robin", () => {
    const stages = ["s1", "s2", "s3"].map((id) => stage(id));
    const ready = selectDispatchable(stages, {
      maxConcurrency: 4,
      workerClasses: ["retrieval", "code-reading", "experiment", "verification"],
    });
    expect(ready.map((s) => s.assigned_worker_class)).toEqual(["retrieval", "code-reading", "experiment"]);
  });

  it("parks a stage after repeated failures instead of blocking the critical path", () => {
    const stages = [stage("flaky", { status: "in_progress", retries: 3, max_retries: 3 })];
    const ready = selectDispatchable(stages, { maxConcurrency: 4, workerClasses: ["retrieval"] });
    expect(ready).toHaveLength(0);
    expect(stages[0]!.status).toBe("parked");
  });
});

describe("EVSI placeholder signature (TODO(issue-557))", () => {
  it("exposes the A3-shaped scorer (EVSI/cost) for later replacement", () => {
    const decision = evaluateStage(stage("s1", { claim_ids: ["c1"] }), [claim("c1")], {
      budgetRemainingMs: 1000,
      evsi: (claimId) => (claimId === "c1" ? 0.5 / 10 : 0), // EVSI/cost shape
    });
    expect(decision.action).toBe("drill-down");
  });
});
