/** 12h unattended overnight run (issue #569, charter H6, docs 02 硬帽).

The unattended reliability machinery around a research run. The research
rounds themselves are caller-supplied (the mock-e2e harness and the pi
extension drive the actual loop); this runner owns the product invariants:

- **12h hard cap forces convergence** — the run never hangs. When the cap is
  reached, one final round runs in `final` mode: if the info is sufficient
  the run converges (forced); otherwise it falls back to **PARK with revival
  conditions** (product red line: PARK 必须带复活条件).
- **Round limit fails closed** — a round executor that neither converges nor
  advances the wall clock parks the run instead of spinning forever.
- **Crash recovery** — `recoverFromCrash` verifies the hash-chained event log
  (tamper detection), rehydrates the state machine from `task.transition`
  events alone, and hands back a machine the caller can resume with: a
  mid-run crash resumes, it never restarts the ledger.
*/

import type { LedgerStore } from "../store/ledger.js";
import type { VersionStore } from "../versions/store.js";
import { ProductStateMachine } from "../state/machine.js";

export const DEFAULT_CAP_MS = 12 * 3600 * 1000;
export const DEFAULT_MAX_ROUNDS = 1000;

export interface OvernightClock {
  now(): number;
}

export interface OvernightRoundContext {
  round: number;
  /** true when this round is the forced final round (cap reached) */
  final: boolean;
}

export interface OvernightRoundResult {
  /** research converged naturally this round */
  done?: boolean;
  /** at forced convergence: is the info sufficient for a verdict? */
  info_sufficient?: boolean;
  /** required when info is insufficient (PARK 必须带复活条件) */
  revival_conditions?: string[];
}

export interface OvernightOptions {
  ledger: LedgerStore;
  machine: ProductStateMachine;
  taskId: string;
  clock: OvernightClock;
  capMs?: number;
  max_rounds?: number;
  round: (ctx: OvernightRoundContext) => Promise<OvernightRoundResult> | OvernightRoundResult;
  /** set when continuing a run recovered via recoverFromCrash */
  recovered?: boolean;
  emit?: (line: Record<string, unknown>) => void;
  log?: (line: string) => void;
}

export interface OvernightResult {
  outcome: "converged" | "parked";
  rounds: number;
  elapsedMs: number;
  /** true when convergence was forced by the hard cap */
  forced: boolean;
  revival_conditions?: string[];
  /** true when this run continued a recovered (crashed) run */
  recovered?: boolean;
}

export class OvernightError extends Error {}

export async function runOvernight(options: OvernightOptions): Promise<OvernightResult> {
  const capMs = options.capMs ?? DEFAULT_CAP_MS;
  const maxRounds = options.max_rounds ?? DEFAULT_MAX_ROUNDS;
  const log = options.log ?? (() => {});
  const emit = options.emit ?? (() => {});
  const start = options.clock.now();
  let rounds = 0;

  const park = (revivalConditions: string[], forced: boolean): OvernightResult => ({
    outcome: "parked",
    rounds,
    elapsedMs: options.clock.now() - start,
    forced,
    revival_conditions: revivalConditions,
    recovered: options.recovered,
  });

  while (rounds < maxRounds) {
    const elapsed = options.clock.now() - start;
    const final = elapsed >= capMs;
    rounds += 1;
    const result = await options.round({ round: rounds, final });
    if (final) {
      // hard cap: converge now, one way or the other — the run never hangs
      if (result.info_sufficient === true) {
        log(`[overnight] cap reached at round ${rounds}: info sufficient → forced convergence`);
        return { outcome: "converged", rounds, elapsedMs: options.clock.now() - start, forced: true, recovered: options.recovered };
      }
      const revival = result.revival_conditions ?? [];
      if (revival.length === 0) {
        throw new OvernightError("PARK requires revival conditions (PARK 必须带复活条件)");
      }
      log(`[overnight] cap reached at round ${rounds}: info insufficient → PARK`);
      return park(revival, true);
    }
    if (result.done === true) {
      return { outcome: "converged", rounds, elapsedMs: options.clock.now() - start, forced: false, recovered: options.recovered };
    }
  }

  // round limit: a round executor that never converges nor advances the clock parks
  return park(["round limit exceeded without convergence — revive with a larger round budget or a fix to the round executor"], false);
}

export interface CrashRecovery {
  chain_verified: true;
  phase: string | undefined;
  events: number;
  machine: ProductStateMachine;
}

/** Crash recovery protocol: verify the chain, rehydrate from the event log. */
export function recoverFromCrash(options: {
  ledger: LedgerStore;
  versions: VersionStore;
  taskId: string;
  graph?: import("../store/ports.js").GraphProjection | null;
}): CrashRecovery {
  options.ledger.verifyGraphChain(); // throws on tamper — a corrupt log is never resumed
  const events = options.ledger.graphEvents();
  const machine = ProductStateMachine.rehydrate(events as Array<Record<string, unknown>>, options.versions, options.graph ?? null);
  return {
    chain_verified: true,
    phase: machine.phaseOf(options.taskId),
    events: events.length,
    machine,
  };
}
