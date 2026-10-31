import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { recoverFromCrash, runOvernight, OvernightError } from "../src/headless/overnight.js";
import { LedgerStore } from "../src/store/ledger.js";
import { VersionStore } from "../src/versions/store.js";
import { EngineCore } from "../src/store/engine.js";
import { ProductStateMachine } from "../src/state/machine.js";

let workspace: string;
let ledger: LedgerStore;
let versions: VersionStore;
let engine: EngineCore;
let machine: ProductStateMachine;

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-overnight-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
  versions = new VersionStore(ledger);
  engine = new EngineCore(ledger);
  machine = new ProductStateMachine(engine, versions);
});

/** mock wall clock the round executor advances (1h per round) */
function mockClock(start = 0) {
  const state = { t: start };
  return {
    now: () => state.t,
    advance: (hours: number) => {
      state.t += hours * 3600 * 1000;
    },
  };
}

const HOUR = 3600 * 1000;
const CAP_12H = 12 * HOUR;

describe("12h unattended overnight run (issue #569)", () => {
  it("completes naturally when research converges within the cap", async () => {
    const clock = mockClock();
    const result = await runOvernight({
      ledger,
      machine,
      taskId: "t1",
      clock,
      capMs: CAP_12H,
      round: async () => {
        clock.advance(1);
        return { done: true };
      },
    });
    expect(result.outcome).toBe("converged");
    expect(result.rounds).toBe(1);
    expect(result.forced).toBe(false);
  });

  it("hard cap forces convergence — the run never hangs", async () => {
    const clock = mockClock();
    let rounds = 0;
    const result = await runOvernight({
      ledger,
      machine,
      taskId: "t1",
      clock,
      capMs: 4 * HOUR,
      round: async ({ final }) => {
        rounds += 1;
        clock.advance(1);
        if (final) {
          return { info_sufficient: true };
        }
        return {};
      },
    });
    expect(result.outcome).toBe("converged");
    expect(result.forced).toBe(true);
    expect(result.rounds).toBe(rounds);
    expect(rounds).toBe(5); // 4 productive rounds reach the cap, the 5th is the forced final round
  });

  it("PARK fallback with revival conditions when info is insufficient at the cap", async () => {
    const clock = mockClock();
    const result = await runOvernight({
      ledger,
      machine,
      taskId: "t1",
      clock,
      capMs: 2 * HOUR,
      round: async ({ final }) => {
        clock.advance(1);
        if (final) {
          return { info_sufficient: false, revival_conditions: ["budget for the 2h benchmark on c-mob"] };
        }
        return {};
      },
    });
    expect(result.outcome).toBe("parked");
    expect(result.revival_conditions).toEqual(["budget for the 2h benchmark on c-mob"]);
  });

  it("PARK without revival conditions is rejected (product red line)", async () => {
    const clock = mockClock();
    await expect(
      runOvernight({
        ledger,
        machine,
        taskId: "t1",
        clock,
        capMs: 1 * HOUR,
        round: async ({ final }) => {
          clock.advance(1);
          if (final) {
            return { info_sufficient: false, revival_conditions: [] };
          }
          return {};
        },
      }),
    ).rejects.toThrow(/revival/);
  });

  it("round limit fails closed to PARK with a revival condition", async () => {
    const clock = mockClock();
    const result = await runOvernight({
      ledger,
      machine,
      taskId: "t1",
      clock,
      capMs: CAP_12H,
      max_rounds: 3,
      round: async () => {
        clock.advance(1);
        return {};
      },
    });
    expect(result.outcome).toBe("parked");
    expect(result.revival_conditions?.join(" ")).toContain("round limit");
  });

  it("mid-run crash resumes from the event log without ledger corruption", async () => {
    // pre-crash: task walks to research phase and 2 overnight rounds happen
    machine.openTask("t1");
    const clock = mockClock();
    const crashedRound = async ({ final }: { final: boolean }) => {
      clock.advance(1);
      if (final) {
        return { info_sufficient: false, revival_conditions: ["more budget"] };
      }
      return {};
    };
    await runOvernight({ ledger, machine, taskId: "t1", clock, capMs: CAP_12H, max_rounds: 2, round: crashedRound });

    const phaseBefore = machine.phaseOf("t1");
    const eventsBefore = ledger.graphEvents().length;
    expect(eventsBefore).toBeGreaterThan(0);

    // crash recovery protocol: chain verification + rehydrate from task.transition events
    const recovered = recoverFromCrash({ ledger, versions, taskId: "t1" });
    expect(recovered.chain_verified).toBe(true);
    expect(recovered.phase).toBe(phaseBefore);
    expect(recovered.events).toBe(eventsBefore);

    // the resumed run continues (does not restart the ledger) and converges
    const result = await runOvernight({
      ledger,
      machine: recovered.machine,
      taskId: "t1",
      clock,
      capMs: CAP_12H,
      recovered: true,
      round: async () => {
        clock.advance(1);
        return { done: true };
      },
    });
    expect(result.outcome).toBe("converged");
    expect(result.recovered).toBe(true);
    expect(() => ledger.verifyGraphChain()).not.toThrow(); // no corruption after resume
  });
});
