import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { CardWallModel, renderCardWall, type Card } from "../src/ux/card_wall.js";
import { LedgerStore } from "../src/store/ledger.js";
import { VersionStore } from "../src/versions/store.js";
import { ProductStateMachine } from "../src/state/machine.js";
import { EngineCore } from "../src/store/engine.js";
import { parseDecomposition, confirmDecomposition } from "../src/decomposition/engine.js";

const SOURCE = { kind: "chat-message" as const, ref: "msg:1", quote: "2C4G 越快上越好" };

const EXTRACTION = {
  requirements: [{ text: "deploy on 2C4G fast", source: SOURCE }],
  constraints: [{ text: "on-prem only", source: SOURCE, hardness: "hard" }],
  background: [{ text: "pilot feedback", source: { kind: "attachment" as const, ref: "att:1", quote: "row2" } }],
  intents: [{ text: "ship fast", source: SOURCE }],
  refusals: [],
  difficulties: [{ text: "2C4G memory ceiling", source: SOURCE, kill_candidates: ["c-mob"] }],
  claims_preview: [{ id: "c-mob", text: "2C4G suffices", kill_condition: "OOM under load" }],
};

let workspace: string;
let ledger: LedgerStore;
let versions: VersionStore;
let machine: ProductStateMachine;

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-cardwall-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
  versions = new VersionStore(ledger);
  machine = new ProductStateMachine(new EngineCore(ledger), versions, undefined);
});

describe("decomposition card wall (P3, issue #561)", () => {
  it("renders six provenance-visible card groups", () => {
    const parsed = parseDecomposition(EXTRACTION);
    const model = new CardWallModel(parsed);
    const cards = model.cards();
    expect(Object.keys(cards).sort()).toEqual([
      "background", "constraints", "difficulties", "intents", "refusals", "requirements",
    ]);
    expect((cards.requirements as Card[])[0]).toMatchObject({
      text: "deploy on 2C4G fast",
      provenance: "来自你的话：\"2C4G 越快上越好\"",
    });
  });

  it("supports delete before confirm (real button, mutation local to draft)", () => {
    const parsed = parseDecomposition(EXTRACTION);
    const model = new CardWallModel(parsed);
    model.deleteElement("requirements", 0);
    expect(model.cards().requirements).toHaveLength(0);
  });

  it("difficult-to-kill-candidate mapping is visible per difficulty card", () => {
    const parsed = parseDecomposition(EXTRACTION);
    const model = new CardWallModel(parsed);
    const difficulty = (model.cards().difficulties as Card[])[0]!;
    expect(difficulty.kill_candidates).toEqual(["c-mob"]);
  });

  it("empty refusals show the explicit-none placeholder (非演示脚手架)", () => {
    const parsed = parseDecomposition(EXTRACTION);
    const model = new CardWallModel(parsed);
    const refusalCards = model.cards().refusals;
    expect(refusalCards).toHaveLength(0);
    expect(model.placeholderFor("refusals")).toContain("待对齐");
  });

  it("checklist gates confirm: gaps block, complete set confirms", () => {
    const parsed = parseDecomposition(EXTRACTION);
    const model = new CardWallModel(parsed);
    const complete = model.confirm(ledger, "t1", { refusals: "none" }, { decomposition_id: "dc-1" });
    expect(complete.status).toBe("confirmed");
  });

  it("insufficient set blocks confirm with named gaps (insufficient saves as draft)", () => {
    const parsed = parseDecomposition({ requirements: EXTRACTION.requirements });
    const model = new CardWallModel(parsed);
    expect(() => model.confirm(ledger, "t1", { refusals: "none" }, { decomposition_id: "dc-gap" })).toThrow(
      /pre-registration gap/,
    );
  });
});

describe("artifact management & freeze-commit (post-convergence)", () => {
  it("delete nodes land in deleted_nodes and the freeze discloses them", async () => {
    versions.openDraft("t1", {
      snapshot: {
        elements: EXTRACTION, claims: [], evidence_refs: [],
        report: {}, deleted_nodes: ["node-sketch"],
      },
      baseV: null,
    });
    const machine = new ProductStateMachine(new EngineCore(ledger), versions, undefined);
    machine.openTask("t1");
    machine.transition("t1", { event: "confirm" });
    confirmDecomposition(ledger, "t1", parseDecomposition(EXTRACTION), { refusals: "none" }, { decomposition_id: "dc-1" });
    machine.attachDecomposition("t1", "dc-1");
    const { parseRunPlan } = await import("../src/state/run_plan.js");
    machine.attachRunPlan("t1", parseRunPlan(PLAN()));
    machine.transition("t1", { event: "sign" });
    machine.transition("t1", { event: "research-completed" });
    const committed = machine.freezeTask("t1", { verdict: "GO", summary: "v0 with deleted node" }) as unknown as { snapshot: { deleted_nodes: string[] } };
    expect(committed.snapshot.deleted_nodes).toEqual(["node-sketch"]);
  });
});

const PLAN = () => ({
  plan_id: "plan-dv",
  stages: [{ id: "s1", title: "cluster", claim_ids: [], depends_on: [] }],
  budget: { capMs: 12 * 3600 * 1000 },
  yaw_checks: [
    { slot: "plan-level", mode: "auto" },
    { slot: "problem-level", mode: "human" },
    { slot: "knowledge-level", mode: "auto" },
  ],
});
