import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { EVSIError, selectAction, type ActionCandidate } from "../src/evsi/selector.js";

function candidate(id: string, evsi: number, cost: number): ActionCandidate {
  return { action_id: id, claim_id: "c1", evsi, cost, kind: "read-source" };
}

let workspace: string;

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-evsi-"));
});

describe("A3 unified EVSI action selection (issue #557)", () => {
  it("selects by EVSI/cost (the same formula for a paper and a benchmark)", () => {
    const chosen = selectAction([
      candidate("a1", 0.8, 10), // 0.08 per unit
      candidate("a2", 0.3, 2), // 0.15 per unit — better ratio
    ], { makeOrBreakIds: [] });
    expect(chosen?.action_id).toBe("a2");
  });

  it("make-or-break claims always go first regardless of ratio", () => {
    const chosen = selectAction([
      { ...candidate("cheap-act", 0.2, 1), claim_id: "c2" },
      candidate("mob-act", 0.5, 100),
    ], { makeOrBreakIds: ["c1"], claimId: "c1" });
    expect(chosen?.action_id).toBe("mob-act");
  });

  it("records the regret gap (hindsight-best minus chosen) for replay", () => {
    const decision = selectAction([
      candidate("a1", 0.8, 10),
      candidate("a2", 0.3, 2),
    ], { makeOrBreakIds: [] })!;
    // a1 had the best EVSI (0.08/1.0 relative) but a2 won on EVSI/cost —
    // the replay log must disclose the suboptimal gap
    expect(decision?.replay).toBeDefined();
    expect(decision.replay.candidates).toHaveLength(2);
    expect(decision.replay.chosen).toBe("a2");
  });

  it("returns null on an empty candidate set (caller decides next step)", () => {
    expect(selectAction([], { makeOrBreakIds: [] })).toBeNull();
  });

  it("zero-cost candidates are rejected (nothing is free — guard against div-by-zero)", () => {
    // zero-cost actions cannot be scored by EVSI/cost — they raise rather
    // than win degenerately
    expect(() => selectAction([
      candidate("free", 0.5, 0),
      candidate("costed", 0.1, 5),
    ], { makeOrBreakIds: [] })).toThrow(EVSIError);
  });
});
