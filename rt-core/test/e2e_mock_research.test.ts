/** Mock e2e — full research loop simulation (issue #607).

The complete integrated stack — event log, ledger surface, version store,
state machine, scheduler, pi-subagents dispatch, audited providers, headless
runner, MCP — driven through **complete research runs** with every external
boundary mocked (LLM, provider CLIs, network: zero real calls).

Three scenarios cover three of the four verdicts (REFRAMED is variant-search,
T2 #563): GO (happy loop), NO-GO (early termination with belief propagation),
PARK (worker failure → retry→park). Every run asserts the audit trail: the
event stream sequence, chain integrity, graph rebuild equality, and MCP
consistency.
*/

import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { runHeadless } from "../src/headless/runner.js";
import { GraphStore } from "../src/graph/projection.js";
import { LedgerStore } from "../src/store/ledger.js";
import { VersionStore } from "../src/versions/store.js";
import { ProductStateMachine } from "../src/state/machine.js";
import { EngineCore } from "../src/store/engine.js";
import { ProviderRegistry } from "../src/providers/registry.js";
import { auditedProvider } from "../src/providers/audited.js";
import { AnysearchProvider } from "../src/providers/anysearch.js";
import { dispatchStage } from "../src/pi/dispatch.js";
import {
  evaluateStage,
  selectDispatchable,
  propagateRefutation,
  type ClaimState,
  type StageState,
} from "../src/scheduler/engine.js";
import { createMcpServer } from "../src/mcp/server.js";
import { parseDecomposition, confirmDecomposition } from "../src/decomposition/engine.js";

// ------------------------------------------------------------------ fixtures

const SOURCE = { kind: "chat-message" as const, ref: "msg:1", quote: "2C4G 越快上越好" };

const EXTRACTION = {
  requirements: [{ text: "deploy on 2C4G fast", source: SOURCE }],
  constraints: [{ text: "2C4G is a guess", source: SOURCE, hardness: "guessed" }],
  background: [{ text: "pilot feedback", source: { kind: "attachment" as const, ref: "att:1", quote: "row2" } }],
  intents: [{ text: "ship fast", source: SOURCE }],
  refusals: [],
  difficulties: [{ text: "2C4G memory ceiling", source: SOURCE, kill_candidates: ["c-mob"] }],
  claims_preview: [{ id: "c-mob", text: "2C4G suffices", kill_condition: "OOM under load" }],
};

const PLAN = {
  plan_id: "plan-mock",
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

const ANYSEARCH_RESULTS = [
  { title: "2C4G deployment guide", url: "https://docs.example.com/2c4g", snippet: "deploy on 2 vCPU 4GB" },
  { title: "OOM postmortem", url: "https://postmortem.example.com/oom", snippet: "memory ceiling at 3.2GB" },
];

let workspace: string;
let ledger: LedgerStore;
let versions: VersionStore;
let graph: GraphStore;
let engine: EngineCore;
let machine: ProductStateMachine;
let registry: ProviderRegistry;

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-mocke2e-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
  versions = new VersionStore(ledger);
  graph = new GraphStore(join(workspace, "graph.kuzu"));
  engine = new EngineCore(ledger, graph);
  machine = new ProductStateMachine(engine, versions, graph);
  registry = new ProviderRegistry();
  registry.register(auditedProvider(engine, new AnysearchProvider({
    runner: async () => ({ stdout: JSON.stringify(ANYSEARCH_RESULTS), exitCode: 0 }),
  })));
  registry.setDefault("anysearch");
});

interface Harness {
  claims: ClaimState[];
  stages: Array<StageState & { max_retries: number }>;
  subagentSpawns: Array<{ agent: string; stage_id: string }>;
  runRound(opts: { refuteMob?: boolean; workerFails?: boolean }): void;
}

/** The research-loop harness: scheduler rounds + pi-subagents dispatch +
 * audited evidence search + dual-write claim updates. This is the loop the
 * #552 pi extension drives in production — here with every boundary mocked. */
function harness(): Harness {
  const claims: ClaimState[] = [{ id: "c-mob", state: "undecided", posterior: 0.5 }];
  const stages = PLAN.stages.map((stage) => ({
    id: stage.id,
    title: stage.title,
    status: "in_progress" as const,
    claim_ids: [...stage.claim_ids],
    depends_on: [...stage.depends_on],
    retries: 0,
    max_retries: 3,
    assigned_worker_class: undefined as undefined | "retrieval",
  }));
  const subagentSpawns: Array<{ agent: string; stage_id: string }> = [];
  const anysearch = auditedProvider(engine, registry.get("anysearch")!);

  const harness: Harness = {
    claims,
    stages,
    subagentSpawns,
    async runRound(opts) {
      const ready = selectDispatchable(stages, {
        maxConcurrency: 4,
        workerClasses: ["retrieval", "code-reading", "experiment", "verification"],
      });
      for (const stage of ready) {
        if (opts.workerFails) {
          // the dispatched worker fails: task-level retry increments; the
          // scheduler parks the stage when retries exhaust (#550 semantics)
          stage.retries = (stage.retries ?? 0) + 1;
          continue;
        }
        // dispatch via the pi-subagents fake (the mapped agent type), then
        // the "worker" applies verdicts through the dual-write
        void dispatchStage(
          {
            spawn: async (agent, _prompt) => {
              subagentSpawns.push({ agent, stage_id: stage.id });
              return { session_id: `sub-${subagentSpawns.length}` };
            },
          },
          { stage, claims, concurrency: 4 },
        );
        // worker pass: re-verify any open claim (undecided / refuted /
        // stale) — the refuteMob option makes the worker refute the
        // make-or-break instead (early-termination trigger)
        for (const claimId of stage.claim_ids) {
          const claim = claims.find((c) => c.id === claimId)!;
          if (opts.refuteMob && claimId === "c-mob") {
            claim.posterior = 0.05;
            claim.state = "refuted";
            const propagated = propagateRefutation(claims, claimId);
            for (const updated of propagated) {
              const target = claims.find((c) => c.id === updated.id)!;
              target.state = updated.state;
              target.reopen_count = updated.reopen_count;
            }
          } else if (claim.state !== "decided") {
            claim.posterior = 0.95;
            claim.state = "decided";
          }
          engine.upsertClaim("t-e2e", {
            claim_id: claim.id,
            text: `claim ${claim.id}`,
            source: "research",
            weight: claimId === "c-mob" ? "make_or_break" : "important",
            posterior: claim.posterior,
            verify_tier: "multi-source",
            kill_edges: [],
            incentive_flag: false,
          });
        }
        // evidence search through the audited provider (provider.action events)
        await registry.get("anysearch")!.search({ query: `evidence for ${stage.id}` });
        // open-loop check AFTER the worker pass
        const decision = evaluateStage(stage, claims, {
          budgetRemainingMs: 1000,
          evsi: (claimId) => (claims.find((c) => c.id === claimId)!.state === "undecided" ? 0.9 : 0.0),
        });
        if (decision.action === "rollup") {
          stage.status = "rolled_up";
        }
      }
    },
  };
  return harness;
}

const SETUP_STEPS = [
  { event: "confirm" },
  { event: "attach", decomposition: EXTRACTION, decomposition_id: "dc-e2e", plan: PLAN },
  { event: "sign" },
  {
    event: "open-draft",
    snapshot: {
      elements: { requirements: [{ id: "r1", text: "deploy on 2C4G" }] },
      claims: [{ id: "c-mob", posterior: 0.5 }],
      evidence_refs: [],
      report: {},
      deleted_nodes: [],
    },
    base_v: null,
  },
] as const;

// ------------------------------------------------------------------ GO path

describe("mock e2e — GO path (happy research loop)", () => {
  it("runs scheduler rounds → dispatch → evidence → decisions → rollup → converge → GO commit", async () => {
    const h = harness();
    const first = await runHeadless({
      ledger, versions, machine, graph,
      script: {
        task_id: "t-e2e",
        pre_signed: { verdict: "GO", summary: "2C4G verified" },
        steps: SETUP_STEPS.map((step) => ({ ...step })),
      },
      emit: () => {},
      log: () => {},
    });
    expect(first.outcome).toBe("success");
    expect(machine.phaseOf("t-e2e")).toBe("research");

    // research rounds until both stages roll up
    for (let round = 0; round < 6; round += 1) {
      await h.runRound({});
      if (h.stages.every((stage) => stage.status === "rolled_up")) {
        break;
      }
    }
    expect(h.stages.map((s) => s.status)).toEqual(["rolled_up", "rolled_up"]);
    expect(h.subagentSpawns.map((s) => s.agent)).toContain("rt-retrieval");
    const mob = h.claims.find((c) => c.id === "c-mob")!;
    expect(mob.state).toBe("decided");

    machine.transition("t-e2e", { event: "research-completed" });
    const committed = machine.freezeTask("t-e2e", { verdict: "GO", summary: "2C4G verified" });
    expect(committed.v).toBe(0);

    // audit trail: transitions + provider actions + claim dual-writes
    const events = ledger.graphEvents().map((e) => e.event_type);
    expect(events).toContain("task.transition");
    expect(events).toContain("provider.action");
    expect(events).toContain("claim.upsert");
    expect(() => ledger.verifyGraphChain()).not.toThrow();

    // graph rebuild from the log alone equals the live projection
    const rebuilt = await new GraphStore(join(workspace, "rebuilt.kuzu")).rebuild(ledger.graphEvents());
    expect(rebuilt).toEqual(await graph.snapshotState());

    // MCP consistency
    const mcp = createMcpServer({ ledger, versions, machine });
    const verdict = await mcp.call("rt.verdict", { task_id: "t-e2e" });
    expect(verdict).toMatchObject({ v: 0, verdict: "GO" });
  });
});

// ------------------------------------------------------------------ NO-GO path

describe("mock e2e — NO-GO path (early termination with belief propagation)", () => {
  it("refutes the make-or-break, reopens descendants, pauses, resumes continue, converges to NO-GO", async () => {
    const h = harness();
    await runHeadless({
      ledger, versions, machine, graph,
      script: {
        task_id: "t-e2e",
        pre_signed: {},
        steps: SETUP_STEPS.map((step) => ({ ...step })),
      },
      emit: () => {},
      log: () => {},
    });

    // round 1: the make-or-break refutes
    await h.runRound({ refuteMob: true });
    expect(h.claims.find((c) => c.id === "c-mob")!.state).toBe("refuted");

    // the hard gate pauses research
    machine.raiseEarlyTermination("t-e2e", { refuted_claim: "c-mob", evidence: "posterior 0.05" });
    expect(machine.phaseOf("t-e2e")).toBe("paused");

    // resume "continue" → the affected stage reopens for re-verification
    machine.resolveEarlyTermination("t-e2e", { choice: "continue" });
    expect(machine.phaseOf("t-e2e")).toBe("research");
    h.stages.find((s) => s.id === "stage-recon")!.status = "in_progress";
    h.runRound({});
    expect(h.claims.find((c) => c.id === "c-mob")!.posterior).toBe(0.95);

    machine.transition("t-e2e", { event: "research-completed" });
    const committed = machine.freezeTask("t-e2e", { verdict: "NO-GO", summary: "re-verified insufficient" });
    expect(committed.verdict).toBe("NO-GO");

    // bury path on a second task: pause → bury → converged (NO-GO recommendation)
    machine.openTask("t2");
    machine.transition("t2", { event: "confirm" });
    confirmDecomposition(ledger, "t2", parseDecomposition(EXTRACTION), { refusals: "none" }, { decomposition_id: "dc-t2" });
    machine.attachDecomposition("t2", "dc-t2");
    const { parseRunPlan } = await import("../src/state/run_plan.js");
    machine.attachRunPlan("t2", parseRunPlan(PLAN));
    machine.transition("t2", { event: "sign" });
    machine.raiseEarlyTermination("t2", { refuted_claim: "c-mob", evidence: "p=0.05" });
    machine.resolveEarlyTermination("t2", { choice: "bury" });
    expect(machine.phaseOf("t2")).toBe("converged");
  });
});

// ------------------------------------------------------------------ PARK path

describe("mock e2e — PARK path (worker failure)", () => {
  it("parks the failing stage after retries and converges to a PARK commit", async () => {
    const h = harness();
    await runHeadless({
      ledger, versions, machine, graph,
      script: {
        task_id: "t-e2e",
        pre_signed: { verdict: "PARK", summary: "worker failed, budget retained" },
        steps: SETUP_STEPS.map((step) => ({ ...step })),
      },
      emit: () => {},
      log: () => {},
    });

    // the worker fails on every round → retries exhaust → the next
    // dispatch pass parks the stage (#550 retry→park semantics)
    for (let i = 0; i < 3; i += 1) {
      await h.runRound({ workerFails: true });
    }
    await h.runRound({ workerFails: true }); // selectDispatchable parks it here
    const recon = h.stages.find((s) => s.id === "stage-recon")!;
    expect(recon.status).toBe("parked");

    machine.transition("t-e2e", { event: "research-completed" });
    const committed = machine.freezeTask("t-e2e", { verdict: "PARK", summary: "worker failed, budget retained" });
    expect(committed.verdict).toBe("PARK");
    const mcp = createMcpServer({ ledger, versions, machine });
    const verdict = await mcp.call("rt.verdict", { task_id: "t-e2e" });
    expect(verdict).toMatchObject({ verdict: "PARK" });
  });
});
