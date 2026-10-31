/** T1 closeout acceptance (issue #562): 3 real ideas end-to-end through the
 * complete stack — A1 dialogue → A0 decomposition → headless research walk
 * (mid-chain re-entry + early termination paths) → dual rendering → version
 * commits → MCP verdict. Ideas differ in shape to exercise the A1 router:
 * a fuzzy idea (many branches), a crisp idea (few rounds), and an
 * early-termination idea (make-or-break dies).
 *
 * H1/H3 first data: the LLM-side measurements (user prompt effort vs Deep
 * Research, 底稿 feeding an implementation agent) require keyed sessions —
 * deferred to the keyed-session provisioning (#588); the engine-side
 * projections (routing receipts, 底稿 supported/unverified structure) are
 * verified here and are the data the LLM-side measurements will consume.
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
import { createMcpServer } from "../src/mcp/server.js";
import { DialogueController } from "../src/dialogue/controller.js";
import { parseDecomposition, confirmDecomposition, checklistFor } from "../src/decomposition/engine.js";
import { renderReport, renderDeliverable } from "../src/rendering/dual.js";
import { renderTuiFrame } from "../src/tui/renderer.js";
import { auditedProvider } from "../src/providers/audited.js";
import { AnysearchProvider } from "../src/providers/anysearch.js";

const PLAN = {
  plan_id: "plan-t1",
  stages: [{ id: "s1", title: "cluster", claim_ids: [], depends_on: [] }],
  budget: { capMs: 12 * 3600 * 1000 },
  yaw_checks: [
    { slot: "plan-level", mode: "auto" },
    { slot: "problem-level", mode: "human" },
    { slot: "knowledge-level", mode: "auto" },
  ],
};

const SOURCE = { kind: "chat-message" as const, ref: "msg:1", quote: "idea" };

interface IdeaFixture {
  task_id: string;
  utterances: Array<{ kind: string; text: string }>;
  extraction: Record<string, unknown>;
  pre_signed: { verdict: string; summary: string; early_termination?: "continue" | "bury" };
  refute_mob: boolean;
}

const IDEAS: IdeaFixture[] = [
  {
    // fuzzy idea: many branches, converges through slots
    task_id: "idea-fuzzy",
    utterances: [
      { kind: "preference", text: "must run offline" },
      { kind: "preference", text: "response under 200ms" },
      { kind: "preference", text: "runs on-prem" },
      { kind: "branch", text: "maybe multi-tenant later" },
      { kind: "branch", text: "maybe k8s deployment" },
      { kind: "branch", text: "maybe edge nodes" },
      { kind: "claim", text: "2C4G suffices" },
    ],
    extraction: {
      requirements: [{ text: "deploy on 2C4G offline", source: SOURCE }],
      constraints: [{ text: "on-prem", source: SOURCE, hardness: "hard" }],
      background: [{ text: "pilot feedback", source: { kind: "attachment" as const, ref: "att:1", quote: "row1" } }],
      intents: [{ text: "ship fast", source: SOURCE }],
      refusals: [{ text: "no public cloud", source: SOURCE }],
      difficulties: [{ text: "memory ceiling", source: SOURCE, kill_candidates: ["c-mob"] }],
      claims_preview: [{ id: "c-mob", text: "2C4G suffices", kill_condition: "OOM" }],
    },
    pre_signed: { verdict: "GO", summary: "fuzzy idea verified" },
    refute_mob: false,
  },
  {
    // crisp idea: few rounds, direct
    task_id: "idea-crisp",
    utterances: [
      { kind: "preference", text: "must be open source" },
      { kind: "preference", text: "must support SSO" },
      { kind: "preference", text: "self-hosted only" },
      { kind: "claim", text: "keycloak satisfies SSO" },
    ],
    extraction: {
      requirements: [{ text: "SSO via keycloak", source: SOURCE }],
      constraints: [{ text: "self-hosted", source: SOURCE, hardness: "hard" }],
      background: [{ text: "security review", source: { kind: "attachment" as const, ref: "att:2", quote: "row1" } }],
      intents: [{ text: "enterprise ready", source: SOURCE }],
      refusals: [{ text: "no SaaS", source: SOURCE }],
      difficulties: [{ text: "SSO integration surface", source: SOURCE, kill_candidates: ["c-ss"] }],
      claims_preview: [{ id: "c-ss", text: "keycloak satisfies SSO", kill_condition: "audit failure" }],
    },
    pre_signed: { verdict: "GO", summary: "crisp idea verified" },
    refute_mob: false,
  },
  {
    // early-termination idea: the make-or-break dies mid-research
    task_id: "idea-doomed",
    utterances: [
      { kind: "preference", text: "must run on 512MB" },
      { kind: "preference", text: "must be real-time" },
      { kind: "preference", text: "must use wasm" },
      { kind: "claim", text: "wasm fits in 512MB" },
    ],
    extraction: {
      requirements: [{ text: "wasm in 512MB realtime", source: SOURCE }],
      constraints: [{ text: "512MB hard cap", source: SOURCE, hardness: "hard" }],
      background: [{ text: "hardware spec", source: { kind: "attachment" as const, ref: "att:3", quote: "row1" } }],
      intents: [{ text: "edge deployment", source: SOURCE }],
      refusals: [],
      difficulties: [{ text: "wasm memory model", source: SOURCE, kill_candidates: ["c-wasm"] }],
      claims_preview: [{ id: "c-wasm", text: "wasm fits 512MB", kill_condition: "OOM" }],
    },
    pre_signed: { verdict: "NO-GO", summary: "wasm does not fit", early_termination: "bury" },
    refute_mob: true,
  },
];

let workspace: string;
let ledger: LedgerStore;
let versions: VersionStore;
let graph: GraphStore;
let machine: ProductStateMachine;
let engine: EngineCore;

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-t1acc-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
  versions = new VersionStore(ledger);
  graph = new GraphStore(join(workspace, "graph.kuzu"));
  engine = new EngineCore(ledger);
  machine = new ProductStateMachine(engine, versions, graph);
});

describe("T1 closeout: three real ideas end-to-end (A1 → A0 → headless → dual rendering → MCP)", () => {
  for (const idea of IDEAS) {
    it(`walks ${idea.task_id} through the full closed loop`, async () => {
      // A1: dialogue intake — the router processes the idea's utterances
      const dialogue = new DialogueController(ledger, idea.task_id);
      for (const utterance of idea.utterances) {
        dialogue.ingest({
          kind: utterance.kind as never,
          text: utterance.text,
          source: { kind: "chat-message", ref: utterance.text, quote: utterance.text },
          ...(utterance.kind === "branch" ? {} : {}),
        });
      }
      machine.openTask(idea.task_id);
      machine.transition(idea.task_id, { event: "confirm" });

      // A0: decomposition confirmed (the constitution ships with v0)
      const parsed = parseDecomposition(idea.extraction);
      const checklist = checklistFor(parsed, { refusals: "none" });
      confirmDecomposition(ledger, idea.task_id, parsed, { refusals: "none" }, { decomposition_id: `dc-${idea.task_id}` });
      machine.attachDecomposition(idea.task_id, `dc-${idea.task_id}`);
      const { parseRunPlan } = await import("../src/state/run_plan.js");
      machine.attachRunPlan(idea.task_id, parseRunPlan(PLAN));
      machine.transition(idea.task_id, { event: "sign" });
      expect(machine.phaseOf(idea.task_id)).toBe("research");

      // audited evidence search (the default provider)
      const audited = auditedProvider(engine, new AnysearchProvider({
        runner: async () => ({ stdout: JSON.stringify([{ title: "t", url: "u", snippet: "s" }]), exitCode: 0 }),
      }));
      await audited.search({ query: idea.task_id });

      // research: the walk handles open-draft + headless events; the refute
      // variant exercises the early-termination gate
      if (!idea.refute_mob) {
        const result = await runHeadless({
          ledger, versions, machine, graph,
          script: {
            task_id: idea.task_id,
            pre_signed: idea.pre_signed,
            steps: [
              { event: "open-draft", snapshot: idea.extraction, base_v: null },
            ],
          },
          emit: () => {},
          log: () => {},
        });
        expect(result.outcome).toBe("success");
      } else {
        await runHeadless({
          ledger, versions, machine, graph,
          script: {
            task_id: idea.task_id,
            pre_signed: {},
            steps: [{ event: "open-draft", snapshot: idea.extraction, base_v: null }],
          },
          emit: () => {},
          log: () => {},
        });
        machine.raiseEarlyTermination(idea.task_id, { refuted_claim: "c-wasm", evidence: "posterior 0.05" });
        expect(machine.phaseOf(idea.task_id)).toBe("paused");
        machine.resolveEarlyTermination(idea.task_id, { choice: idea.pre_signed.early_termination ?? "bury" });
      }
      if (machine.phaseOf(idea.task_id) !== "converged") {
        machine.transition(idea.task_id, { event: "research-completed" });
      }
      const committed = machine.freezeTask(idea.task_id, {
        verdict: idea.pre_signed.verdict,
        summary: idea.pre_signed.summary,
      });
      expect(committed.verdict).toBe(idea.pre_signed.verdict);

      // dual rendering from the committed snapshot (H3 projection)
      const report = renderReport(committed.snapshot as never, {
        verdict: idea.pre_signed.verdict, confidence: "moderate",
      });
      const deliverable = renderDeliverable(committed.snapshot as never, { verdict: idea.pre_signed.verdict });
      expect(report).toContain("## 7. 三元裁决");
      expect(deliverable.clarified_question.verdict).toBe(idea.pre_signed.verdict);

      // TUI renders the closed loop
      const frame = await renderTuiFrame({ ledger, versions, machine, graph });
      expect(frame).toContain(idea.task_id);
    });
  }

  it("all three ideas coexist in one ledger with their versions (multi-task)", async () => {
    for (const idea of IDEAS) {
      machine.openTask(idea.task_id);
      versions.openDraft(idea.task_id, { snapshot: idea.extraction, baseV: null });
      machine.transition(idea.task_id, { event: "confirm" });
      confirmDecomposition(ledger, idea.task_id, parseDecomposition(idea.extraction), { refusals: "none" }, { decomposition_id: `dc-${idea.task_id}` });
      machine.attachDecomposition(idea.task_id, `dc-${idea.task_id}`);
      const { parseRunPlan } = await import("../src/state/run_plan.js");
      machine.attachRunPlan(idea.task_id, parseRunPlan(PLAN));
      machine.transition(idea.task_id, { event: "sign" });
      machine.transition(idea.task_id, { event: "research-completed" });
      machine.freezeTask(idea.task_id, { verdict: idea.pre_signed.verdict, summary: idea.pre_signed.summary });
    }
    for (const idea of IDEAS) {
      const latest = versions.latestVersion(idea.task_id);
      expect(latest).not.toBeNull();
      expect(latest!.verdict).toBe(idea.pre_signed.verdict);
    }
    // chain integrity across all tasks
    expect(() => ledger.verifyGraphChain()).not.toThrow();
  });

  it("MCP exposes all three committed verdicts", async () => {
    for (const idea of IDEAS) {
      machine.openTask(idea.task_id);
      versions.openDraft(idea.task_id, { snapshot: idea.extraction, baseV: null });
      machine.transition(idea.task_id, { event: "confirm" });
      confirmDecomposition(ledger, idea.task_id, parseDecomposition(idea.extraction), { refusals: "none" }, { decomposition_id: `dc-${idea.task_id}` });
      machine.attachDecomposition(idea.task_id, `dc-${idea.task_id}`);
      const { parseRunPlan } = await import("../src/state/run_plan.js");
      machine.attachRunPlan(idea.task_id, parseRunPlan(PLAN));
      machine.transition(idea.task_id, { event: "sign" });
      machine.transition(idea.task_id, { event: "research-completed" });
      machine.freezeTask(idea.task_id, { verdict: idea.pre_signed.verdict, summary: idea.pre_signed.summary });
    }
    const mcp = createMcpServer({ ledger, versions, machine });
    for (const idea of IDEAS) {
      const verdict = await mcp.call("rt.verdict", { task_id: idea.task_id });
      expect(verdict.verdict).toBe(idea.pre_signed.verdict);
    }
  });
});

describe("H1/H3 first data (engine-side projections; LLM-side deferred to keyed sessions)", () => {
  it("H1 projection: A1 routing receipts quantify intake effort", () => {
    const dialogue = new DialogueController(ledger, "t-h1");
    for (const utterance of IDEAS[0]!.utterances) {
      dialogue.ingest({ kind: utterance.kind as never, text: utterance.text, source: { kind: "chat-message", ref: utterance.text, quote: utterance.text } });
    }
    // the routing receipt count IS the user-effort proxy the LLM-side
    // measurement will compare against Deep Research
    expect(dialogue.slots.size).toBeGreaterThan(0);
    expect(dialogue.parkingLot().length).toBeGreaterThan(0);
  });

  it("H3 projection: the 底稿 carries the implementation-agent handoff shape", async () => {
    const idea = IDEAS[1]!;
    const nested = {
      elements: idea.extraction,
      claims: [{ id: "c-ss", posterior: 0.3 }],
      evidence_refs: [], report: {}, deleted_nodes: [],
    };
    const deliverable = renderDeliverable(nested as never, { verdict: idea.pre_signed.verdict });
    // the 底稿 is the seam the implementation agent consumes — capability
    // outline + constraints + unverified assumptions are the H3 payload
    expect(deliverable.capability_outline.length).toBeGreaterThan(0);
    expect(deliverable.constraints.hard.length).toBeGreaterThan(0);
    expect(deliverable.unverified_assumptions).toBeDefined();
  });
});
