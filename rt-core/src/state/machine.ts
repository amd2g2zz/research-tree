/** Product state machine v2.0 — the single phase authority (issue #551).

docs 02 引擎层新建核心件; answers the #530 finding (phase authority has no
writer) structurally: every phase transition is an **engine fact** — a
`task.transition` event in the log — consumable by headless (#579), the
canvas (#559) and hooks.

    CHAT →(confirm) DECOMPOSE →(sign) RESEARCH ⟲(EVSI→verify→early-term
    hard gate→yaw check) → CONVERGED (artifacts deletable, unfrozen)
    →(freeze) COMMITTED [vN hash+summary] → CHAT (inherit-and-realign)
    → RESEARCH[vN+1] …
    fork(v) = (new task, inherited v0 snapshot, fork edge)

Guards (fail-closed):
- **freeze gate**: COMMITTED is reachable only from CONVERGED through
  `freezeTask` — no bypass; the version comes from the #548 VersionStore.
- **sign gate**: RESEARCH requires a **confirmed decomposition** (the signed
  constitution, #549) and a parsed run plan.
- **early-termination hard gate** (run-plan fail-closed): a refuted
  make-or-break pauses research; continuation is blocked until the user
  resolves 埋了/继续挖 (T0 PAUSE primitive — variant search lands #563).
- **mid-chain re-entry**: research → chat keeps the ledger intact.

State is event-sourced: `rehydrate` rebuilds phases from `task.transition`
events alone.
*/

import { VERDICTS } from "../events/schema.js";
import type { GraphProjection, Snapshot } from "../store/ports.js";
import type { EngineCore } from "../store/engine.js";
import type { VersionStore } from "../versions/store.js";
import { LedgerIntegrityError } from "../store/integrity.js";
import type { RunPlan } from "./run_plan.js";

export type Phase = "chat" | "decompose" | "research" | "converged" | "committed" | "paused";

export type TransitionEvent =
  | "confirm"            // chat → decompose (user: 聊得差不多了)
  | "sign"               // decompose → research (decomposition confirmed + plan signed)
  | "research-completed" // research → converged
  | "user-recalled"      // research → chat (mid-chain decomposition re-entry)
  | "unfrozen-continue"  // converged → research (artifacts deletable, unfrozen continue)
  | "inherit"            // committed → chat (inherit-and-realign, version+1)
  | "pause"              // any active → paused (early-termination hard gate)
  | "resume-research"    // paused → research (user: 继续挖)
  | "resume-converge";   // paused → converged (user: 埋了 → NO-GO recommendation)

/** Legal transition matrix — the state machine's whole law. */
const TRANSITIONS: Record<Phase, Partial<Record<TransitionEvent, Phase>>> = {
  chat: { confirm: "decompose" },
  decompose: { sign: "research" },
  research: { "research-completed": "converged", "user-recalled": "chat", pause: "paused" },
  converged: { inherit: "chat", "unfrozen-continue": "research", pause: "paused" },
  committed: { inherit: "chat" },
  paused: { "resume-research": "research", "resume-converge": "converged" },
};

const ACTIVE_PHASES: Phase[] = ["chat", "decompose", "research", "converged"];

let transitionSeq = 0;

export class ProductStateMachine {
  private phases = new Map<string, Phase>();
  private decompositions = new Map<string, string>();
  private plans = new Map<string, RunPlan>();

  private engine: EngineCore;

  constructor(
    engine: EngineCore,
    private versions: VersionStore,
    private graph?: GraphProjection | null,
  ) {
    this.engine = engine;
  }

  /** Task birth: every task starts in chat (the hub is the entry). */
  openTask(taskId: string): void {
    if (this.phases.has(taskId)) {
      throw new LedgerIntegrityError(`task already open: ${taskId}`);
    }
    this.phases.set(taskId, "chat");
    this.emitTransition(taskId, undefined, "chat", "task birth");
  }

  // ------------------------------------------------------------------ queries

  phaseOf(taskId: string): Phase | undefined {
    return this.phases.get(taskId);
  }

  events() {
    return this.engine.graphEvents();
  }

  // ------------------------------------------------------------------ transitions

  transition(taskId: string, signal: { event: TransitionEvent; reason?: string }): void {
    const from = this.phases.get(taskId);
    if (from === undefined) {
      throw new LedgerIntegrityError(`unknown task: ${taskId}`);
    }
    // fail-closed guards ahead of the matrix
    if (signal.event === "sign") {
      this.guardSign(taskId);
    }
    if (signal.event === "pause") {
      if (!ACTIVE_PHASES.includes(from) || from === "chat") {
        throw new LedgerIntegrityError(`pause refused: phase ${from} is not an active research phase`);
      }
    }
    const to = TRANSITIONS[from]?.[signal.event];
    if (to === undefined) {
      throw new LedgerIntegrityError(
        `illegal transition: ${signal.event} is not valid from phase "${from}" (task ${taskId})`,
      );
    }
    this.phases.set(taskId, to);
    this.emitTransition(taskId, from, to, signal.reason);
  }

  /** DECOMPOSE prerequisite: the confirmed constitution (#549) is attached. */
  attachDecomposition(taskId: string, decompositionId: string): void {
    const row = this.engine.ledgerStore?.getDecomposition(taskId, decompositionId) ?? null;
    if (row === null || row.status !== "confirmed") {
      throw new LedgerIntegrityError(
        `sign gate: decomposition ${decompositionId} is not confirmed for ${taskId}`,
      );
    }
    this.decompositions.set(taskId, decompositionId);
  }

  /** DECOMPOSE prerequisite: the run plan is parsed and attached (plan = data). */
  attachRunPlan(taskId: string, plan: RunPlan): void {
    this.plans.set(taskId, plan);
  }

  private guardSign(taskId: string): void {
    const decompositionId = this.decompositions.get(taskId);
    if (decompositionId === undefined) {
      throw new LedgerIntegrityError(
        `sign gate: research requires a confirmed decomposition for ${taskId}`,
      );
    }
    const row = this.engine.ledgerStore?.getDecomposition(taskId, decompositionId) ?? null;
    if (row === null || row.status !== "confirmed") {
      throw new LedgerIntegrityError(
        `sign gate: decomposition ${decompositionId} is not confirmed for ${taskId}`,
      );
    }
    if (!this.plans.has(taskId)) {
      throw new LedgerIntegrityError(`sign gate: research requires a signed run plan for ${taskId}`);
    }
  }

  // ------------------------------------------------------------------ freeze gate

  /** The only converged→committed path: VersionStore.freeze (fail-closed,
   * whole-snapshot hash). No bypass exists on the machine. */
  freezeTask(taskId: string, commit: { verdict: string; summary: string }): Record<string, unknown> {
    const from = this.phases.get(taskId);
    if (from !== "converged") {
      throw new LedgerIntegrityError(
        `freeze gate: committed is reachable only from converged (task ${taskId} is "${from ?? "unknown"}")`,
      );
    }
    if (!(VERDICTS as readonly string[]).includes(commit.verdict)) {
      throw new LedgerIntegrityError(`field "verdict" must be one of ${JSON.stringify(VERDICTS)}`);
    }
    const committed = this.versions.freeze(taskId, commit);
    // commit is a transient fact — the machine lands in chat (inherit-and-realign)
    this.phases.set(taskId, "committed");
    this.emitTransition(taskId, "converged", "committed", `v${committed.v} ${committed.commit_hash.slice(0, 12)}`);
    this.phases.set(taskId, "chat");
    this.emitTransition(taskId, "committed", "chat", "inherit-and-realign");
    return committed as unknown as Record<string, unknown>;
  }

  // ------------------------------------------------------------------ early termination

  /** Early-termination hard gate (run-plan fail-closed): a refuted
   * make-or-break pauses research — the question is not the verdict. */
  raiseEarlyTermination(taskId: string, detail: { refuted_claim: string; evidence: string }): void {
    const from = this.phases.get(taskId);
    if (from !== "research") {
      throw new LedgerIntegrityError(
        `early termination refused: task ${taskId} is not in research ("${from ?? "unknown"}")`,
      );
    }
    this.phases.set(taskId, "paused");
    this.emitTransition(taskId, "research", "paused", `make-or-break refuted: ${detail.refuted_claim}`);
  }

  resolveEarlyTermination(taskId: string, choice: { choice: "continue" | "bury" }): void {
    if (this.phases.get(taskId) !== "paused") {
      throw new LedgerIntegrityError(`resolve refused: task ${taskId} is not paused`);
    }
    const to: Phase = choice.choice === "bury" ? "converged" : "research";
    this.phases.set(taskId, to);
    this.emitTransition(taskId, "paused", to, `user choice: ${choice.choice}`);
  }

  // ------------------------------------------------------------------ fork

  /** fork(v) → new task with an inherited v0 snapshot, chat phase (the user
   * realigns in chat), lineage edge recorded. */
  forkTask(fork: { fromTask: string; fromV: number; toTask: string }): Record<string, unknown> {
    const committed = this.versions.fork(fork);
    this.phases.set(fork.toTask, "chat");
    this.emitTransition(fork.toTask, undefined, "chat", `forked from ${fork.fromTask}@v${fork.fromV}`);
    return committed as unknown as Record<string, unknown>;
  }

  // ------------------------------------------------------------------ event sourcing

  /** Rebuild phases from `task.transition` events alone (state is engine fact). */
  static rehydrate(
    events: Array<Record<string, unknown>>,
    versions: VersionStore,
    graph?: GraphProjection | null,
  ): ProductStateMachine {
    const machine = Object.create(ProductStateMachine.prototype) as ProductStateMachine;
    machine.phases = new Map();
    machine.decompositions = new Map();
    machine.plans = new Map();
    machine.engine = undefined as unknown as EngineCore;
    machine.versions = versions;
    machine.graph = graph ?? null;
    for (const event of events) {
      if (event.event_type !== "task.transition") {
        continue;
      }
      const payload = event.payload as Record<string, unknown>;
      const taskId = String(payload.task_id);
      const to = payload.to as Phase | undefined;
      if (to === undefined) {
        continue;
      }
      if (payload.from === null && !machine.phases.has(taskId)) {
        machine.phases.set(taskId, "chat"); // task birth (fork)
      }
      machine.phases.set(taskId, to);
    }
    return machine;
  }

  // ------------------------------------------------------------------ internal

  private emitTransition(taskId: string, from: Phase | undefined, to: Phase, reason?: string): void {
    transitionSeq += 1;
    this.engine.appendGraphEvent("task.transition", {
      id: `task-transition-${transitionSeq}`,
      task_id: taskId,
      from: from ?? null,
      to,
      reason: reason ?? null,
    });
  }
}
