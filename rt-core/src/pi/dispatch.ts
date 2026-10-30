/** pi-subagents dispatch substrate (issue #552, docs 02 执行层).

pi is home — the subagent extension (**pi-subagents**, official pi.dev
catalog) is the dispatch substrate: isolated sessions, parallel execution,
custom agent types. rt-core does NOT build session/fleet management; it maps
the 4 worker classes onto custom agent types (each agent definition carries
the class's contract) and expresses the engine's dispatch policy (≤4
concurrency per stage, fresh-context blind verification) as extension
invocations.

The `PiSubagentsApi` is the structural port the extension satisfies; tests
inject fakes.
*/

import type { ClaimState, StageState, WorkerClass } from "../scheduler/engine.js";

export interface WorkerAgentType {
  name: string;
  description: string;
  workerClass: WorkerClass;
}

/** One custom agent type per worker class — the compiler-checked mapping. */
export const WORKER_AGENT_TYPES: readonly WorkerAgentType[] = [
  {
    name: "rt-retrieval",
    description: "rt: retrieval worker — evidence search through DataSourceProviders",
    workerClass: "retrieval",
  },
  {
    name: "rt-code-reading",
    description: "rt: code-reading worker — mechanism extraction from source",
    workerClass: "code-reading",
  },
  {
    name: "rt-experiment",
    description: "rt: experiment worker — pre-registered discriminating runs",
    workerClass: "experiment",
  },
  {
    name: "rt-verification",
    description: "rt: verification worker — fresh-context blind re-derivation",
    workerClass: "verification",
  },
];

export interface AgentDefinition {
  name: string;
  description: string;
  systemPrompt: string;
}

/** Agent definitions carry each class's contract (the two-layer contract:
 * the prompt side carries the open-ended behavior strategy). */
export function buildAgentDefinitions(): AgentDefinition[] {
  return WORKER_AGENT_TYPES.map((agentType) => ({
    name: agentType.name,
    description: agentType.description,
    systemPrompt: AGENT_PROMPTS[agentType.workerClass],
  }));
}

const AGENT_PROMPTS: Record<WorkerClass, string> = {
  retrieval:
    "You are the rt retrieval worker. Search through the DataSourceProvider adapters (anysearch default, agent-browser for rendered pages, web_fetch for direct fetch). Every source lands with provenance. Report findings as claim-relevant evidence with verbatim anchors.",
  "code-reading":
    "You are the rt code-reading worker. Extract mechanisms from real source: what it does, how it implements it, evidence beyond README-level claims. Cite file paths and line ranges.",
  experiment:
    "You are the rt experiment worker. Run pre-registered discriminating experiments only (hypothesis, criterion, minimum sample, cost cap registered first). Designer ≠ executor; sequential stop when the posterior passes the threshold.",
  verification:
    "You are the rt verification worker. Fresh-context BLIND re-derivation: you receive the claim and its evidence, never the original derivation. Re-derive independently; report supported/refuted with your own reasoning. You have no stake in the outcome.",
};

// ------------------------------------------------------------------ dispatch

export interface PiSubagentsSpawnResult {
  session_id: string;
}

/** Structural port satisfied by the pi-subagents extension. */
export interface PiSubagentsApi {
  spawn(agentName: string, prompt: string): Promise<PiSubagentsSpawnResult>;
}

export interface DispatchInput {
  stage: StageState;
  claims: ClaimState[];
  concurrency: number;
}

export interface DispatchResult {
  dispatched: Array<{ agent: string; stage_id: string; session_id: string }>;
}

function claimContext(claims: ClaimState[], stage: StageState): string {
  const relevant = claims.filter((claim) => stage.claim_ids.includes(claim.id));
  return relevant
    .map((claim) => {
      const premises = claim.depends_on_claims?.length
        ? ` (stands on: ${claim.depends_on_claims.join(", ")})`
        : "";
      return `claim ${claim.id} [${claim.state}, posterior ${claim.posterior}]${premises}`;
    })
    .join("; ");
}

/** Dispatch one stage's work onto its mapped agent type. The engine's policy
 * (≤4 concurrency — the scheduler cuts the ready set; blind verification) is
 * expressed here, as extension invocations. */
export async function dispatchStage(subagents: PiSubagentsApi, input: DispatchInput): Promise<DispatchResult> {
  const { stage, claims, concurrency } = input;
  if (stage.assigned_worker_class === undefined) {
    return { dispatched: [] }; // the scheduler's ready-set cut decides who runs
  }
  if (concurrency <= 0) {
    return { dispatched: [] };
  }
  const agentType = WORKER_AGENT_TYPES.find((t) => t.workerClass === stage.assigned_worker_class);
  if (agentType === undefined) {
    return { dispatched: [] };
  }
  const prompt = [
    `Stage ${stage.id} (${stage.title}).`,
    `Claims: ${claimContext(claims, stage) || "none registered"}.`,
    "Work the stage claims mechanically; every artifact lands with provenance.",
  ].join(" ");
  const spawned = await subagents.spawn(agentType.name, prompt);
  return { dispatched: [{ agent: agentType.name, stage_id: stage.id, session_id: spawned.session_id }] };
}
