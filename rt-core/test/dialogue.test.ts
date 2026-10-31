import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { DialogueController } from "../src/dialogue/controller.js";
import { LedgerStore } from "../src/store/ledger.js";

let ledger: LedgerStore;

beforeEach(() => {
  ledger = new LedgerStore(mkdtempSync(join(tmpdir(), "rt-a1-")));
  ledger.initialize();
});

describe("four-way routing (per-utterance, no privileged channel)", () => {
  it("routes preferences/intents to slots (authority domain — followed)", () => {
    const controller = new DialogueController(ledger);
    const receipt = controller.ingest({
      kind: "preference",
      text: "must run offline",
      source: { kind: "chat-message", ref: "msg:1", quote: "must run offline" },
    });
    expect(receipt.routed).toBe("slot");
    expect(controller.slots.get("must run offline")).toMatchObject({ value: "must run offline", origin: "msg:1" });
  });

  it("routes factual claims to the claim ledger (verify — neither trust nor rebut)", () => {
    const controller = new DialogueController(ledger);
    const receipt = controller.ingest({
      kind: "claim",
      text: "2C4G suffices for the pilot",
      source: { kind: "chat-message", ref: "msg:2", quote: "2C4G suffices" },
    });
    expect(receipt.routed).toBe("claim-ledger");
    expect(receipt.claim_id).toBeTypeOf("string");
    // the dual-write landed the row + claim.upsert event
    expect(ledger.getClaim("t-default", receipt.claim_id!)).not.toBeNull();
  });

  it("routes solution guesses to the hypothesis ledger (admitted, tried — same footing as alternatives)", () => {
    const controller = new DialogueController(ledger);
    const receipt = controller.ingest({
      kind: "guess",
      text: "maybe 2M memory is enough",
      source: { kind: "chat-message", ref: "msg:3", quote: "2M memory" },
    });
    expect(receipt.routed).toBe("hypothesis-ledger");
    expect(receipt.hypothesis_id !== undefined && (ledger.getHypothesis("t-default", receipt.hypothesis_id) ?? { status: null }).status).toBe("open");
  });

  it("routes branches to the parking lot (contained, not punished)", () => {
    const controller = new DialogueController(ledger);
    const receipt = controller.ingest({
      kind: "branch",
      text: "later we could also add multi-tenant",
      source: { kind: "chat-message", ref: "msg:4", quote: "multi-tenant" },
    });
    expect(receipt.routed).toBe("parking-lot");
    expect(controller.parkingLot()).toContain("later we could also add multi-tenant");
  });
});

describe("constraint provenance (guesses relax to intents on discrimination)", () => {
  it("registers guessed constraints with their discrimination question", () => {
    const controller = new DialogueController(ledger);
    controller.ingest({
      kind: "constraint",
      text: "must fit 2M memory",
      source: { kind: "chat-message", ref: "msg:5", quote: "2M memory" },
      hardness: "guessed",
    });
    expect(controller.guessedConstraints()).toHaveLength(1);
    expect(controller.guessedConstraints()[0]!.discrimination).toContain("deployment fact");
  });

  it("relaxes a guessed constraint to an intent on the spot when discriminated as estimate", () => {
    const controller = new DialogueController(ledger);
    controller.ingest({
      kind: "constraint",
      text: "must fit 2M memory",
      source: { kind: "chat-message", ref: "msg:5", quote: "2M memory" },
      hardness: "guessed",
    });
    const receipt = controller.discriminate("must fit 2M memory", "estimate");
    expect(receipt.routed).toBe("slot"); // relaxed to intent
    expect(controller.guessedConstraints()).toHaveLength(0);
    expect(controller.slots.get("must fit 2M memory")).toBeDefined();
  });

  it("keeps hard constraints when discriminated as deployment facts", () => {
    const controller = new DialogueController(ledger);
    controller.ingest({
      kind: "constraint",
      text: "must run on-prem",
      source: { kind: "chat-message", ref: "msg:6", quote: "on-prem only" },
      hardness: "guessed",
    });
    const receipt = controller.discriminate("must run on-prem", "deployment-fact");
    expect(receipt.routed).toBe("constraint");
    expect(controller.hardConstraints()).toContain("must run on-prem");
  });
});

describe("corrections route the same way (no privileged channel)", () => {
  it("preference change → comply + consequence map", () => {
    const controller = new DialogueController(ledger);
    const receipt = controller.correct({
      kind: "preference-change",
      text: "actually, cloud is fine",
      source: { kind: "chat-message", ref: "msg:7", quote: "cloud is fine" },
      consequence_map: ["offline requirement superseded"],
    });
    expect(receipt.routed).toBe("slot");
    expect(receipt.consequences).toEqual(["offline requirement superseded"]);
  });

  it("private fact → ledger + elicitation", () => {
    const controller = new DialogueController(ledger);
    const receipt = controller.correct({
      kind: "private-fact",
      text: "our prod runs on 1GB",
      source: { kind: "chat-message", ref: "msg:8", quote: "1GB" },
    });
    expect(receipt.routed).toBe("claim-ledger");
  });

  it("guess restated → hypothesis ledger re-review", () => {
    const controller = new DialogueController(ledger);
    const first = controller.ingest({ kind: "guess", text: "2M is enough", source: { kind: "chat-message", ref: "m1", quote: "2M" } });
    const receipt = controller.correct({
      kind: "guess-restated",
      text: "2M is enough",
      source: { kind: "chat-message", ref: "m2", quote: "2M" },
      hypothesis_id: first.hypothesis_id!,
    });
    expect(receipt.routed).toBe("hypothesis-ledger");
    expect(receipt.re_reviewed).toBe(true);
  });
});

describe("echo confirmation (only for deconstructions that change signed things)", () => {
  it("triggers for kill-condition changes", () => {
    const controller = new DialogueController(ledger);
    const receipt = controller.deconstruct({
      changes_kill_conditions: true,
      changes_feasibility_menu: false,
      changes_verdict_structure: false,
    });
    expect(receipt.echo_required).toBe(true);
  });

  it("triggers for feasibility-menu or verdict-structure changes", () => {
    const controller = new DialogueController(ledger);
    expect(controller.deconstruct({ changes_kill_conditions: false, changes_feasibility_menu: true, changes_verdict_structure: false }).echo_required).toBe(true);
    expect(controller.deconstruct({ changes_kill_conditions: false, changes_feasibility_menu: false, changes_verdict_structure: true }).echo_required).toBe(true);
  });

  it("does not trigger for ordinary deconstructions", () => {
    const controller = new DialogueController(ledger);
    expect(controller.deconstruct({ changes_kill_conditions: false, changes_feasibility_menu: false, changes_verdict_structure: false }).echo_required).toBe(false);
  });
});

describe("convergence (computed, never felt)", () => {
  function controllerWith(inputs: Array<{ kind: string; text: string }>): DialogueController {
    const controller = new DialogueController(ledger);
    for (const input of inputs) {
      controller.ingest({ ...input, source: { kind: "chat-message", ref: `m-${input.text}`, quote: input.text } } as never);
    }
    return controller;
  }

  it("requires C1 problem-shaped + C2 key slots + C3 make-or-break", () => {
    const shaped = controllerWith([
      { kind: "preference", text: "must run offline" },
      { kind: "claim", text: "2C4G suffices" },
    ]);
    shaped.setProblemShape({ decidable: true, scoped: true, decisionLinked: true });
    shaped.setMakeOrBreak("c1");
    expect(shaped.convergenceCheck().converged).toBe(false); // C2/C3 partial

    shaped.ingest({ kind: "preference", text: "response under 200ms", source: { kind: "chat-message", ref: "m9", quote: "200ms" } });
    shaped.ingest({ kind: "preference", text: "runs on-prem", source: { kind: "chat-message", ref: "m10", quote: "on-prem" } });
    const check = shaped.convergenceCheck();
    expect(check.converged).toBe(true);
    expect(check.C1).toBe(true);
    expect(check.C2).toBe(true);
    expect(check.C3).toBe(true);
  });

  it("soft signals C4 (new-claim-rate decay) and C5 (restatement uncorrected) shape the pace", () => {
    const controller = controllerWith([{ kind: "claim", text: "claim one" }]);
    controller.recordTurn({ newClaims: 3, restatementCorrected: false });
    controller.recordTurn({ newClaims: 2, restatementCorrected: false });
    const check = controller.convergenceCheck();
    expect(check.C4).toBe(true); // decay: 2 < 3
    controller.recordTurn({ newClaims: 0, restatementCorrected: true });
    expect(controller.convergenceCheck().C5).toBe(false); // restatement corrected → not converging
  });
});

describe("divergence (branches > claims two consecutive rounds → terrain proposal)", () => {
  it("proposes an upstream terrain check on sustained divergence", () => {
    const controller = new DialogueController(ledger);
    for (const text of ["branch a", "branch b", "branch c"]) {
      controller.ingest({ kind: "branch", text, source: { kind: "chat-message", ref: text, quote: text } });
    }
    controller.ingest({ kind: "claim", text: "one claim", source: { kind: "chat-message", ref: "mc", quote: "one claim" } });
    const diagnosis = controller.divergenceCheck();
    expect(diagnosis.diverging).toBe(true);
    expect(diagnosis.proposal).toContain("upstream");
  });

  it("stays quiet when claims outpace branches", () => {
    const controller = new DialogueController(ledger);
    for (const text of ["claim a", "claim b", "claim c"]) {
      controller.ingest({ kind: "claim", text, source: { kind: "chat-message", ref: text, quote: text } });
    }
    expect(controller.divergenceCheck().diverging).toBe(false);
  });
});

describe("intent model is a visible versioned artifact", () => {
  it("versions on every preference change with diff access", () => {
    const controller = new DialogueController(ledger);
    controller.ingest({ kind: "preference", text: "must run offline", source: { kind: "chat-message", ref: "m1", quote: "offline" } });
    const v1 = controller.intentModel().version;
    controller.correct({ kind: "preference-change", text: "cloud is fine", source: { kind: "chat-message", ref: "m2", quote: "cloud" }, consequence_map: [] });
    const model = controller.intentModel();
    expect(model.version).toBeGreaterThan(v1);
    expect(model.history.length).toBeGreaterThanOrEqual(2);
  });
});
