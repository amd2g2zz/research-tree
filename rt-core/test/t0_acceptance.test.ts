/** T0 exit acceptance (issue #554): the engine-level integration test —
 * the manual-ledger FULL CHAIN driven headless, with one mid-chain
 * decomposition and one early termination, plus external MCP calls.
 *
 * This is the walk the roadmap defines as T0's exit criterion:
 * 对话→计划→两阶段递归→裁决→渲染, driven through the #579 headless runner
 * (which doubles as the log-coverage acceptance), with every engine
 * algorithm unit-pinned by the suites that precede this file.
 */

import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { runHeadless, type HeadlessScript } from "../src/headless/runner.js";
import { GraphStore } from "../src/graph/projection.js";
import { LedgerStore } from "../src/store/ledger.js";
import { VersionStore } from "../src/versions/store.js";
import { ProductStateMachine } from "../src/state/machine.js";
import { EngineCore } from "../src/store/engine.js";
import { createMcpServer } from "../src/mcp/server.js";
import { ProviderRegistry } from "../src/providers/registry.js";
import { AnysearchProvider } from "../src/providers/anysearch.js";
import { AgentBrowserProvider } from "../src/providers/agent_browser.js";
import { WebFetchProvider } from "../src/providers/web_fetch.js";
import { auditedProvider } from "../src/providers/audited.js";

const SOURCE = { kind: "chat-message" as const, ref: "msg:1", quote: "2C4G 越快上越好" };

const SNAPSHOT = {
  elements: {
    requirements: [{ id: "r1", text: "deploy on 2C4G", source: SOURCE }],
    constraints: [],
    background: [],
    intents: [],
    refusals: [],
    difficulties: [],
  },
  claims: [{ id: "c-mob", posterior: 0.9, state: "decided" }],
  evidence_refs: ["sha256:" + "a".repeat(64)],
  report: { verdict_narrative: "2C4G deployment is viable" },
  deleted_nodes: ["node-early-sketch"],
};

const EXTRACTION = {
  requirements: [{ text: "deploy on 2C4G fast", source: SOURCE }],
  constraints: [{ text: "2C4G is a guess", source: SOURCE, hardness: "guessed" }],
  background: [{ text: "pilot feedback", source: { kind: "attachment" as const, ref: "att:1", quote: "row2" } }],
  intents: [{ text: "ship fast", source: SOURCE }],
  refusals: [],
  difficulties: [{ text: "2C4G memory ceiling", source: SOURCE, kill_candidates: ["cp-mob"] }],
  claims_preview: [{ id: "cp-mob", text: "2C4G suffices", kill_condition: "OOM under load" }],
};

const PLAN = {
  plan_id: "plan-accept",
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

let workspace: string;
let ledger: LedgerStore;
let versions: VersionStore;
let graph: GraphStore;
let machine: ProductStateMachine;
let registry: ProviderRegistry;

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-accept-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
  versions = new VersionStore(ledger);
  graph = new GraphStore(join(workspace, "graph.kuzu"));
  machine = new ProductStateMachine(new EngineCore(ledger), versions, graph);
  registry = new ProviderRegistry();
  registry.register(new AnysearchProvider({ runner: async () => ({ stdout: "[]", exitCode: 0 }) }));
  registry.register(new AgentBrowserProvider({ runner: async () => ({ stdout: "content", exitCode: 0 }) }));
  registry.register(new WebFetchProvider({
    workspace,
    fetchFn: async () => new Response("ok", { status: 200, headers: { "content-type": "text/plain" } }),
    markitdownRunner: async () => ({ stdout: "# md", exitCode: 0 }),
  }));
});

const FIRST_RUN: HeadlessScript = {
  task_id: "t-accept",
  pre_signed: {},
  steps: [
    { event: "confirm" },
    { event: "attach", decomposition: EXTRACTION, decomposition_id: "dc-accept-1", plan: PLAN },
    { event: "sign" },
    { event: "open-draft", snapshot: SNAPSHOT, base_v: null },
  ],
};

describe("T0 exit: manual-ledger full chain, headless-driven", () => {
  it("walks 对话→计划→研究→裁决→提交 with one mid-chain decomposition and one early termination", async () => {
    // phase 1: chat → decompose → sign → research
    const first = await runHeadless({
      ledger, versions, machine, graph,
      script: FIRST_RUN,
      emit: () => {},
      log: () => {},
    });
    expect(first.outcome).toBe("success");
    expect(machine.phaseOf("t-accept")).toBe("research");

    // mid-chain decomposition: research → chat → a NEW confirmed decomposition → research
    machine.transition("t-accept", { event: "user-recalled" });
    expect(machine.phaseOf("t-accept")).toBe("chat");
    const recalled = await runHeadless({
      ledger, versions, machine, graph,
      script: {
        task_id: "t-accept",
        pre_signed: {},
        steps: [
          { event: "confirm" },
          { event: "attach", decomposition: EXTRACTION, decomposition_id: "dc-accept-2", plan: PLAN },
          { event: "sign" },
        ],
      },
      emit: () => {},
      log: () => {},
    });
    expect(recalled.outcome).toBe("success");
    expect(machine.phaseOf("t-accept")).toBe("research");

    // early termination: the make-or-break dies — PAUSE (no pre-signed choice)
    machine.raiseEarlyTermination("t-accept", { refuted_claim: "c-mob", evidence: "posterior 0.05" });
    expect(machine.phaseOf("t-accept")).toBe("paused");
    const paused = await runHeadless({
      ledger, versions, machine, graph,
      script: { task_id: "t-accept", pre_signed: {}, steps: [] },
      emit: () => {},
      log: () => {},
    });
    expect(paused.outcome).toBe("paused-pending-decision");
    expect(paused.resume_token).toBeTypeOf("string");

    // the user chooses 埋了 → converge → freeze commits with the disclosed deleted node
    const bury = await runHeadless({
      ledger, versions, machine, graph,
      script: { task_id: "t-accept", pre_signed: { early_termination: "bury", verdict: "NO-GO", summary: "2C4G ceiling buried the plan" }, steps: [] },
      emit: () => {},
      log: () => {},
    });
    expect(bury.outcome).toBe("success");
    expect(machine.phaseOf("t-accept")).toBe("chat");

    // the committed version discloses deleted_nodes and carries the verdict
    const committed = versions.latestVersion("t-accept")!;
    expect(committed.verdict).toBe("NO-GO");
    expect(committed.snapshot.deleted_nodes).toEqual(["node-early-sketch"]);
  });

  it("leaves a complete audit trail: transitions, provider actions, frozen version", async () => {
    // an audited retrieval action (anysearch, the default) lands in the stream
    const audited = auditedProvider(new EngineCore(ledger), registry.get("anysearch")!);
    await audited.search({ query: "2C4G deployment" });
    // the claim dual-write (row + claim.upsert + kill_edge events) via EngineCore
    new EngineCore(ledger).upsertClaim("t-accept", {
      claim_id: "c-mob", text: "2C4G suffices", source: "research", weight: "make_or_break",
      posterior: 0.9, verify_tier: "rederive", kill_edges: [], incentive_flag: false,
    });
    await runHeadless({
      ledger, versions, machine, graph,
      script: FIRST_RUN,
      emit: () => {},
      log: () => {},
    });
    const events = ledger.graphEvents().map((e) => e.event_type);
    expect(events).toContain("task.transition");
    expect(events).toContain("provider.action"); // audited retrieval actions
    expect(events).toContain("claim.upsert");
    expect(() => ledger.verifyGraphChain()).not.toThrow();
    await expect(graph.rebuild(ledger.graphEvents())).resolves.toBeDefined();
  });
});

describe("T0 exit: external MCP call completes a minimal flow", () => {
  it("serves rt.start/status/correct/verdict over the tool interface", async () => {
    const mcp = createMcpServer({ ledger, versions, machine });
    await mcp.call("rt.start", { task_id: "t-mcp" });
    const status = await mcp.call("rt.status", { task_id: "t-mcp" });
    expect(status).toMatchObject({ task_id: "t-mcp", phase: "chat" });
    await mcp.call("rt.correct", { task_id: "t-mcp", kind: "preference-change", payload: {} });
    // walk to committed so verdict has content
    versions.openDraft("t-mcp", { snapshot: SNAPSHOT, baseV: null });
    machine.transition("t-mcp", { event: "confirm" });
    const { parseDecomposition, confirmDecomposition } = await import("../src/decomposition/engine.js");
    confirmDecomposition(ledger, "t-mcp", parseDecomposition({
      requirements: [{ text: "r", source: SOURCE }],
      constraints: [{ text: "c", source: SOURCE, hardness: "hard" }],
      background: [{ text: "b", source: SOURCE }],
      intents: [{ text: "i", source: SOURCE }],
      refusals: [],
      difficulties: [{ text: "d", source: SOURCE, kill_candidates: ["cp1"] }],
      claims_preview: [{ id: "cp1", text: "claim", kill_condition: "fails" }],
    }), { refusals: "none" }, { decomposition_id: "dc-mcp" });
    machine.attachDecomposition("t-mcp", "dc-mcp");
    const { parseRunPlan } = await import("../src/state/run_plan.js");
    machine.attachRunPlan("t-mcp", parseRunPlan(PLAN));
    machine.transition("t-mcp", { event: "sign" });
    machine.transition("t-mcp", { event: "research-completed" });
    machine.freezeTask("t-mcp", { verdict: "GO", summary: "mcp flow" });
    const verdict = await mcp.call("rt.verdict", { task_id: "t-mcp" });
    expect(verdict).toMatchObject({ task_id: "t-mcp", verdict: "GO" });
    expect(verdict.report_path).toContain("report");
  });
});

describe("T0 exit: provider surface is live (bundled adapters)", () => {
  it("registers all three bundled providers with correct capabilities", () => {
    const manifests = registry.manifests();
    expect(manifests.map((m) => m.name).sort()).toEqual(["agent-browser", "anysearch", "web_fetch"]);
    expect(manifests.find((m) => m.name === "anysearch")!.capabilities.search).toBe(true);
    expect(manifests.find((m) => m.name === "agent-browser")!.capabilities.fetch).toBe(true);
    expect(manifests.find((m) => m.name === "web_fetch")!.kinds).toContain("office-doc");
  });
});
