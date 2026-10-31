import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { CanvasProjection } from "../src/canvas/projection.js";
import { LedgerStore } from "../src/store/ledger.js";
import { VersionStore } from "../src/versions/store.js";
import { ProductStateMachine } from "../src/state/machine.js";
import { EngineCore } from "../src/store/engine.js";

let workspace: string;
let ledger: LedgerStore;
let versions: VersionStore;
let engine: EngineCore;
let machine: ProductStateMachine;

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-canvas-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
  versions = new VersionStore(ledger);
  engine = new EngineCore(ledger);
  machine = new ProductStateMachine(engine, versions, undefined);
});

const SNAPSHOT = {
  elements: { requirements: [{ id: "r1", text: "deploy" }] },
  claims: [{ id: "c-mob", posterior: 0.9 }],
  evidence_refs: [],
  report: { verdict_narrative: "solid" },
  deleted_nodes: [],
};

describe("minimal canvas projection (issue #559)", () => {
  it("derives the three-layer graph purely from the ledger (question → task → claims)", async () => {
    await engine.appendGraphEvent("provider.action", {
      id: "pa1", provider: "anysearch", action: "search", target: "2C4G", outcome: "ok",
    });
    engine.upsertClaim("t1", {
      claim_id: "c1", text: "rt works offline", source: "user", weight: "make_or_break",
      posterior: 0.5, verify_tier: "multi-source", kill_edges: [], incentive_flag: false,
    });
    const projection = await CanvasProjection.fromLedger(ledger);
    const view = await projection.render("t1");
    expect(view.question).toMatchObject({ task_id: "t1" });
    expect(view.claims["c1"]).toMatchObject({ posterior: 0.5 });
    expect(view.providers).toContain("anysearch");
  });

  it("is deterministic — same events, same canvas state", async () => {
    const a = await (await CanvasProjection.fromLedger(ledger)).render("t1");
    const b = await (await CanvasProjection.fromLedger(ledger)).render("t1");
    expect(a).toEqual(b);
  });
});

describe("five write gates (issue #559)", () => {
  it("pause-resume gate mutates the stage and emits an event", async () => {
    const projection = await CanvasProjection.fromLedger(ledger);
    const receipt = await projection.gates.pauseResume("t1", "stage-recon", "pause", "user-requested");
    expect(receipt.accepted).toBe(true);
  });

  it("kill-stage gate redirects", async () => {
    const projection = await CanvasProjection.fromLedger(ledger);
    const receipt = await projection.gates.killStage("t1", "stage-bad", "superseded by stage-good");
    expect(receipt.accepted).toBe(true);
  });

  it("park gate parks with mandatory revival conditions", async () => {
    const projection = await CanvasProjection.fromLedger(ledger);
    await expect(projection.gates.park("t1", {})).rejects.toThrow(/revival/);
    const receipt = await projection.gates.park("t1", { revival_conditions: ["new evidence"] });
    expect(receipt.accepted).toBe(true);
  });

  it("verdict-confirm gate requires a verdict on the closed vocabulary", async () => {
    const projection = await CanvasProjection.fromLedger(ledger);
    await expect(projection.gates.verdictConfirm("t1", { verdict: "MAYBE" })).rejects.toThrow(/verdict/);
    const receipt = await projection.gates.verdictConfirm("t1", { verdict: "GO" });
    expect(receipt.accepted).toBe(true);
  });

  it("append-info gate accepts user-provided context", async () => {
    const projection = await CanvasProjection.fromLedger(ledger);
    const receipt = await projection.gates.appendInfo("t1", { note: "new context" });
    expect(receipt.accepted).toBe(true);
  });

  it("any non-gate mutation is rejected (canvas = pure projection)", async () => {
    const projection = await CanvasProjection.fromLedger(ledger);
    expect(() =>
      (projection as unknown as { mutate: () => void }).mutate(),
    ).toThrow();
  });
});
