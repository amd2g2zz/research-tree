/** Headless runner (issue #579, docs 02 产品层 CLI headless --json).

One headless entry driving the product state machine from a **launch script**
(declarative steps + pre-signed policy). Two output disciplines:
- **JSON Lines events → emit callback** (the stdout stream in CLI wiring) —
  every appended graph event, in seq order;
- **detailed human-readable log → log callback** (stderr/--log-file in CLI
  wiring) — transitions with reasons, correlations by task_id.

**Consent model (fail-closed)**: human-sign gates (verdict, early-termination
choices) never silently auto-sign. Signs live in the script's `pre_signed`
policy; an unhandled mid-run gate PAUSEs the run and exits with a
machine-readable pending-decision code + **resume token** (same ledger, no
fork). Exit codes: success / paused-pending-decision / fail-closed / park.
*/

import { createHash } from "node:crypto";

import type { EngineCore } from "../store/engine.js";
import type { ProductStateMachine } from "../state/machine.js";
import { parseDecomposition, confirmDecomposition } from "../decomposition/engine.js";

export type HeadlessOutcome =
  | "success"
  | "paused-pending-decision"
  | "fail-closed"
  | "park";

export interface HeadlessScript {
  task_id: string;
  /** pre-signed policy: signs captured at launch — never mid-run silently */
  pre_signed: {
    verdict?: string;
    summary?: string;
    early_termination?: "continue" | "bury";
  };
  steps: Array<
    | { event: "confirm" | "sign" | "research-completed" | "user-recalled" }
    | { event: "attach"; decomposition: Record<string, unknown>; decomposition_id: string; plan: unknown }
    | { event: "open-draft"; snapshot: Record<string, unknown>; base_v: number | null }
  >;
}

export interface HeadlessResult {
  outcome: HeadlessOutcome;
  resume_token?: string;
  detail?: string;
}

export interface RunHeadlessOptions {
  ledger: import("../store/ledger.js").LedgerStore;
  machine: ProductStateMachine;
  versions: import("../versions/store.js").VersionStore;
  script: HeadlessScript;
  /** JSON Lines sink (stdout in CLI wiring) */
  emit: (line: Record<string, unknown>) => void;
  /** detailed human-readable log (stderr/--log-file in CLI wiring) */
  log?: (line: string) => void;
  resumeFrom?: string;
}

function resumeTokenFor(taskId: string, phase: string): string {
  return createHash("sha256").update(`${taskId}:${phase}:${new Date().toISOString()}`).digest("hex").slice(0, 16);
}

export async function runHeadless(options: RunHeadlessOptions): Promise<HeadlessResult> {
  const { ledger, machine, versions, script, emit, log = () => {}, resumeFrom } = options;
  const taskId = script.task_id;

  const mirror = (event: Record<string, unknown> | undefined): void => {
    if (event !== undefined) {
      emit({ seq: ledger.graphEvents().length, ...event });
    }
  };
  const detail = (line: string): void => log(`[headless] task_id=${taskId} ${line}`);

  if (resumeFrom !== undefined) {
    detail(`resume from token ${resumeFrom}`);
  } else if (machine.phaseOf(taskId) === undefined) {
    machine.openTask(taskId);
    detail("task birth → chat");
  }

  const pendingPause = (): boolean =>
    machine.phaseOf(taskId) === "paused";

  for (const step of script.steps) {
    if (pendingPause()) {
      break; // fail-closed: a paused run consumes no further steps
    }
    if (step.event === "open-draft") {
      versions.openDraft(taskId, { snapshot: step.snapshot as never, baseV: step.base_v });
      detail("open draft");
      continue;
    }
    if (step.event === "attach") {
      confirmDecompositionVia(ledger, taskId, step.decomposition, step.decomposition_id);
      machine.attachDecomposition(taskId, step.decomposition_id);
      machine.attachRunPlan(taskId, step.plan as never);
      detail(`attach decomposition=${step.decomposition_id} plan ok`);
      continue;
    }
    machine.transition(taskId, { event: step.event });
    detail(`transition → ${machine.phaseOf(taskId)}`);
    mirror(lastEvent(ledger));
  }

  if (pendingPause()) {
    // early-termination gate is unhandled: no pre-signed choice exists
    if (script.pre_signed.early_termination === undefined) {
      const token = resumeTokenFor(taskId, "paused");
      detail(`PAUSE pending-decision token=${token}`);
      return { outcome: "paused-pending-decision", resume_token: token, detail: "early-termination unhandled" };
    }
    machine.resolveEarlyTermination(taskId, { choice: script.pre_signed.early_termination });
    detail(`early termination resolved: ${script.pre_signed.early_termination}`);
    mirror(lastEvent(ledger));
  }

  if (machine.phaseOf(taskId) === "converged" && script.pre_signed.verdict !== undefined) {
    const committed = machine.freezeTask(taskId, {
      verdict: script.pre_signed.verdict,
      summary: script.pre_signed.summary ?? "headless commit",
    });
    detail(`freeze → committed v${committed.v} hash=${String(committed.commit_hash).slice(0, 12)}`);
    mirror(lastEvent(ledger));
  }

  const phase = machine.phaseOf(taskId);
  if (phase === "paused") {
    const token = resumeTokenFor(taskId, "paused");
    return { outcome: "paused-pending-decision", resume_token: token, detail: "paused mid-run" };
  }
  if (phase === "converged" && script.pre_signed.verdict === undefined) {
    // converged but no verdict signed: PARK fallback per the budget matrix
    detail("no verdict signed — park fallback");
    return { outcome: "park", detail: "converged without pre-signed verdict" };
  }
  return { outcome: "success", detail: `phase=${phase}` };
}

// ------------------------------------------------------------------ internals

function lastEvent(ledger: import("../store/ledger.js").LedgerStore): Record<string, unknown> | undefined {
  const events = ledger.graphEvents();
  const last = events[events.length - 1];
  return last === undefined
    ? undefined
    : { event_type: last.event_type, payload: last.payload, seq: last.seq, created_at: last.created_at };
}

function confirmDecompositionVia(
  ledger: import("../store/ledger.js").LedgerStore,
  taskId: string,
  extraction: Record<string, unknown>,
  decompositionId: string,
): void {
  confirmDecomposition(ledger, taskId, parseDecomposition(extraction as never), { refusals: "none" }, { decomposition_id: decompositionId });
}
