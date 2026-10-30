import { describe, expect, it } from "vitest";

import {
  WORKER_AGENT_TYPES,
  buildAgentDefinitions,
  dispatchStage,
  type PiSubagentsApi,
} from "../src/pi/dispatch.js";

describe("pi-subagents worker mapping (issue #552)", () => {
  it("declares one custom agent type per worker class", () => {
    expect(WORKER_AGENT_TYPES.map((t) => t.name)).toEqual([
      "rt-retrieval",
      "rt-code-reading",
      "rt-experiment",
      "rt-verification",
    ]);
    for (const agentType of WORKER_AGENT_TYPES) {
      expect(agentType.description).toContain("rt:");
    }
  });

  it("builds agent definitions carrying each class's contract", () => {
    const definitions = buildAgentDefinitions();
    const verification = definitions.find((d) => d.name === "rt-verification")!;
    expect(verification.systemPrompt).toContain("Fresh-context");
    expect(verification.systemPrompt).toContain("BLIND");
    const retrieval = definitions.find((d) => d.name === "rt-retrieval")!;
    expect(retrieval.systemPrompt).toContain("DataSourceProvider");
  });
});

describe("dispatch onto pi-subagents (≤4 concurrency, round-robin, retry→park)", () => {
  const api = (): PiSubagentsApi & { spawned: Array<{ agent: string; prompt: string }> } => {
    const spawned: Array<{ agent: string; prompt: string }> = [];
    return {
      spawned,
      spawn: async (agent: string, prompt: string) => {
        spawned.push({ agent, prompt });
        return { session_id: `sub-${spawned.length}` };
      },
    };
  };

  it("dispatches ready stages onto mapped agent types within the concurrency cap", async () => {
    const subagents = api();
    const result = await dispatchStage(subagents, {
      stage: { id: "s1", title: "cluster", status: "in_progress", claim_ids: ["c1"], depends_on: [], assigned_worker_class: "retrieval" },
      claims: [{ id: "c1", state: "undecided", posterior: 0.5 }],
      concurrency: 4,
    });
    expect(subagents.spawned).toHaveLength(1);
    expect(subagents.spawned[0]!.agent).toBe("rt-retrieval");
    expect(subagents.spawned[0]!.prompt).toContain("s1");
    expect(result.dispatched).toHaveLength(1);
  });

  it("passes the claim context in the dispatch prompt (the worker knows what it stands on)", async () => {
    const subagents = api();
    await dispatchStage(subagents, {
      stage: { id: "s1", title: "cluster", status: "in_progress", claim_ids: ["c1"], depends_on: [], assigned_worker_class: "verification" },
      claims: [{ id: "c1", state: "undecided", posterior: 0.5, depends_on_claims: ["premise"] }],
      concurrency: 4,
    });
    expect(subagents.spawned[0]!.prompt).toContain("c1");
    expect(subagents.spawned[0]!.prompt).toContain("premise");
  });
});
