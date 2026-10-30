/** rt-core pi extension (issue #552 — the pi-host end-to-end acceptance).

pi 是家: this module mounts rt-core into a **real pi host session**. On load
it (1) registers the `rt_research` tool for LLM-driven sessions, and
(2) runs the **fake-research end-to-end walk** once at startup — the full
#551 state-machine chain (chat→decompose→research→[mid-chain re-entry]→
early-termination PAUSE→bury→NO-GO commit) driven through the #579 headless
runner against the #547/#548 ledger and version stores, entirely inside the
pi host process. The walk result is written to
`.research-tree/e2e-marker.json` — the acceptance artifact.

Cross-extension integration: if the pi-subagents extension is installed, its
`subagents:ready` broadcast is captured via the pi event bus and recorded in
the marker (both extensions live in the same host session).
*/

import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { runHeadless } from "../src/headless/runner.js";
import { EngineCore } from "../src/store/engine.js";
import { LedgerStore } from "../src/store/ledger.js";
import { VersionStore } from "../src/versions/store.js";
import { ProductStateMachine } from "../src/state/machine.js";
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

const SOURCE = { kind: "chat-message" as const, ref: "msg:1", quote: "2C4G 越快上越好" };

const EXTRACTION = {
  requirements: [{ text: "deploy on 2C4G fast", source: SOURCE }],
  constraints: [{ text: "2C4G is a guess", source: SOURCE, hardness: "guessed" }],
  background: [{ text: "pilot feedback", source: { kind: "attachment" as const, ref: "att:1", quote: "row2" } }],
  intents: [{ text: "ship fast", source: SOURCE }],
  refusals: [],
  difficulties: [{ text: "2C4G memory ceiling", source: SOURCE, kill_candidates: ["cp-mob"] }],
  claims_preview: [{ id: "cp-mob", text: "2C4G suffices", kill_condition: "OOM under load" }],
};

const SNAPSHOT = {
  elements: { requirements: [{ id: "r1", text: "deploy on 2C4G", source: SOURCE }] },
  claims: [{ id: "c-mob", posterior: 0.9, state: "decided" }],
  evidence_refs: ["sha256:" + "a".repeat(64)],
  report: { verdict_narrative: "2C4G deployment is viable" },
  deleted_nodes: ["node-early-sketch"],
};

const PLAN = {
  plan_id: "plan-e2e",
  stages: [
    { id: "stage-recon", title: "recon cluster", claim_ids: ["c-mob"], depends_on: [] },
    { id: "stage-verify", title: "verify cluster", claim_ids: [], depends_on: ["stage-recon"] },
  ],
  budget: { capMs: 12 * 3600 * 1000 },
  yaw_checks: [
    { slot: "plan-level", mode: "auto" },
    { slot: "problem-level", mode: "human" },
    { slot: "knowledge-level", mode: "auto" },
  ],
};

/** The fake-research walk: full #551 chain with mid-chain re-entry and an
 * early-termination PAUSE→bury. Deterministic — no LLM calls (假研究). */
async function fakeResearchWalk(
  ledger: LedgerStore,
  versions: VersionStore,
  machine: ProductStateMachine,
): Promise<Record<string, unknown>> {
  const transitions: Array<Record<string, unknown>> = [];
  const mirror = (): void => {
    const events = ledger.graphEvents();
    const last = events[events.length - 1];
    if (last !== undefined && last.event_type === "task.transition") {
      transitions.push({ from: last.payload.from, to: last.payload.to });
    }
  };

  // phase 1: chat → decompose → sign → research
  const first = await runHeadless({
    ledger, versions, machine,
    script: {
      task_id: "t-e2e",
      pre_signed: {},
      steps: [
        { event: "confirm" },
        { event: "attach", decomposition: EXTRACTION as never, decomposition_id: "dc-e2e-1", plan: PLAN },
        { event: "sign" },
        { event: "open-draft", snapshot: SNAPSHOT as never, base_v: null },
      ],
    },
    emit: () => {},
    log: (line) => console.error(`[rt-e2e] ${line}`),
  });

  // mid-chain decomposition re-entry: research → chat → new confirmed set → research
  machine.transition("t-e2e", { event: "user-recalled" });
  const mid = await runHeadless({
    ledger, versions, machine,
    script: {
      task_id: "t-e2e",
      pre_signed: {},
      steps: [
        { event: "confirm" },
        { event: "attach", decomposition: EXTRACTION as never, decomposition_id: "dc-e2e-2", plan: PLAN },
        { event: "sign" },
      ],
    },
    emit: () => {},
    log: (line) => console.error(`[rt-e2e] ${line}`),
  });
  mirror();

  // early termination: make-or-break dies → PAUSE → user buries → converge → freeze
  machine.raiseEarlyTermination("t-e2e", { refuted_claim: "c-mob", evidence: "posterior 0.05" });
  const paused = await runHeadless({
    ledger, versions, machine,
    script: { task_id: "t-e2e", pre_signed: {}, steps: [] },
    emit: () => {},
    log: (line) => console.error(`[rt-e2e] ${line}`),
  });
  const bury = await runHeadless({
    ledger, versions, machine,
    script: {
      task_id: "t-e2e",
      pre_signed: { early_termination: "bury", verdict: "NO-GO", summary: "2C4G ceiling buried the plan" },
      steps: [],
    },
    emit: () => {},
    log: (line) => console.error(`[rt-e2e] ${line}`),
  });
  mirror();

  const committed = versions.latestVersion("t-e2e");
  return {
    first: first.outcome,
    mid: mid.outcome,
    paused: paused.outcome,
    bury: bury.outcome,
    transitions,
    committed: committed === null
      ? null
      : { v: committed.v, verdict: committed.verdict, commit_hash: committed.commit_hash, deleted_nodes: committed.snapshot.deleted_nodes },
  };
}

export default async function (pi: ExtensionAPI): Promise<void> {
  const workspace = process.cwd();
  let subagentsReady = false;
  try {
    // the pi-subagents extension broadcasts ready on session start — same bus
    (pi as unknown as { events: { on: (name: string, handler: () => void) => void } }).events.on(
      "subagents:ready",
      () => {
        subagentsReady = true;
      },
    );
  } catch {
    // event bus unavailable in this host version — the marker records it
  }

  // ---- the fake-research e2e walk, inside the real pi host process
  let walk: Record<string, unknown>;
  let walkError: string | null = null;
  try {
    const ledger = new LedgerStore(workspace);
    ledger.initialize();
    const versions = new VersionStore(ledger);
    const machine = new ProductStateMachine(new EngineCore(ledger), versions, undefined);
    walk = await fakeResearchWalk(ledger, versions, machine);
  } catch (error: unknown) {
    walkError = String(error);
    walk = { first: "fail-closed", mid: "fail-closed", paused: "fail-closed", bury: "fail-closed", transitions: [], committed: null };
  }

  const root = join(workspace, ".research-tree");
  if (!existsSync(root)) {
    mkdirSync(root, { recursive: true });
  }
  const marker = {
    extension: "rt-core/pi-extension",
    host: "pi",
    outcome: walkError === null ? "success" : "fail-closed",
    walk,
    walk_error: walkError,
    subagents_ready: subagentsReady,
  };
  writeFileSync(join(root, "e2e-marker.json"), JSON.stringify(marker, null, 2));
  // the subagents broadcast fires on session_start (after factories) — rewrite
  // the marker when it arrives so the final on-disk state records coexistence
  try {
    (pi as unknown as {
      events: { on: (name: string, handler: (data: unknown) => void) => void };
    }).events.on("subagents:ready", () => {
      marker.subagents_ready = true;
      writeFileSync(join(root, "e2e-marker.json"), JSON.stringify(marker, null, 2));
    });
  } catch {
    // bus unavailable — marker keeps the factory-time state
  }

  // ---- the tool real LLM sessions use
  pi.registerTool({
    name: "rt_research",
    label: "rt research",
    description: "Drive a research-tree run: transitions the product state machine and returns engine facts",
    parameters: {
      type: "object",
      properties: {
        action: { type: "string", description: "confirm | sign | research-completed | user-recalled" },
        task_id: { type: "string", description: "task id" },
      },
      required: ["action", "task_id"],
    },
    async execute(_toolCallId: string, params: { action: string; task_id: string }) {
      const ledger = new LedgerStore(workspace);
      ledger.initialize();
      const machine = new ProductStateMachine(new EngineCore(ledger), new VersionStore(ledger), undefined);
      machine.openTask(params.task_id);
      machine.transition(params.task_id, { event: params.action as never });
      return {
        content: [{ type: "text", text: `task ${params.task_id} → ${machine.phaseOf(params.task_id)}` }],
        details: {},
      };
    },
  });
}
