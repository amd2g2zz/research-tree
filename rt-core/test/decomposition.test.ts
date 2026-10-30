import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import {
  checklistFor,
  confirmDecomposition,
  parseDecomposition,
  saveDraftDecomposition,
} from "../src/decomposition/engine.js";
import { LedgerStore } from "../src/store/ledger.js";

const SOURCE = { kind: "chat-message" as const, ref: "msg:12", quote: "2C4G 越快上越好" };

let ledger: LedgerStore;

beforeEach(() => {
  ledger = new LedgerStore(mkdtempSync(join(tmpdir(), "rt-a0-")));
  ledger.initialize();
});

function rawWith(elements: Record<string, unknown[]>): Record<string, unknown> {
  return {
    requirements: [],
    constraints: [],
    background: [],
    intents: [],
    refusals: [],
    difficulties: [],
    claims_preview: [],
    ...elements,
  };
}

describe("provenance law (溯源律)", () => {
  it("drops unsourceable elements before persist", () => {
    const parsed = parseDecomposition(
      rawWith({
        requirements: [
          { text: "sourced requirement", source: SOURCE },
          { text: "hallucinated requirement" }, // no source — hallucination
          { text: "partial source", source: { kind: "chat-message", ref: "msg:1" } }, // no quote
        ],
      }),
    );
    expect(parsed.elements.requirements).toHaveLength(1);
    expect(parsed.elements.requirements[0]).toMatchObject({ text: "sourced requirement" });
  });

  it("keeps attachment provenance with quotes", () => {
    const parsed = parseDecomposition(
      rawWith({
        background: [
          { text: "from attachment", source: { kind: "attachment", ref: "att:xxx.xlsx", quote: "sheet1 row3" } },
        ],
      }),
    );
    expect(parsed.elements.background[0]!.source).toMatchObject({ kind: "attachment", ref: "att:xxx.xlsx" });
  });

  it("supports one utterance splitting into several classes", () => {
    const parsed = parseDecomposition(
      rawWith({
        constraints: [{ text: "2C4G 越快上越好", source: SOURCE, hardness: "guessed" }],
        intents: [{ text: "2C4G 越快上越好", source: SOURCE }],
      }),
    );
    expect(parsed.elements.constraints).toHaveLength(1);
    expect(parsed.elements.intents).toHaveLength(1);
  });

  it("separates hard constraints from guessed ones", () => {
    const parsed = parseDecomposition(
      rawWith({
        constraints: [
          { text: "must run offline", source: SOURCE, hardness: "hard" },
          { text: "prefer lightweight", source: SOURCE, hardness: "guessed" },
        ],
      }),
    );
    expect(parsed.elements.constraints.map((c) => (c as { hardness: string }).hardness)).toEqual(["hard", "guessed"]);
  });
});

describe("sufficiency checklist (充分性)", () => {
  it("requires all six classes (refusals may be explicit none)", () => {
    const complete = parseDecomposition(
      rawWith({
        requirements: [{ text: "r", source: SOURCE }],
        constraints: [{ text: "c", source: SOURCE, hardness: "hard" }],
        background: [{ text: "b", source: SOURCE }],
        intents: [{ text: "i", source: SOURCE }],
        refusals: [],
        difficulties: [{ text: "d", source: SOURCE, kill_candidates: ["cp1"] }],
        claims_preview: [{ id: "cp1", text: "claim", kill_condition: "fails" }],
      }),
    );
    const checklist = checklistFor(complete, { refusals: "none" });
    expect(checklist.complete).toBe(true);
    expect(checklist.gaps).toEqual([]);
  });

  it("names empty classes as gaps (except explicitly-confirmed-none refusals)", () => {
    const parsed = parseDecomposition(
      rawWith({
        requirements: [{ text: "r", source: SOURCE }],
        intents: [{ text: "i", source: SOURCE }],
        difficulties: [{ text: "d", source: SOURCE, kill_candidates: ["cp1"] }],
      }),
    );
    const checklist = checklistFor(parsed, {});
    expect(checklist.complete).toBe(false);
    expect(checklist.gaps).toContain("constraints");
    expect(checklist.gaps).toContain("background");
    expect(checklist.gaps).toContain("refusals");
  });

  it("treats a difficulty without kill-candidate mapping as a pre-registration gap", () => {
    const parsed = parseDecomposition(
      rawWith({
        requirements: [{ text: "r", source: SOURCE }],
        constraints: [{ text: "c", source: SOURCE, hardness: "hard" }],
        background: [{ text: "b", source: SOURCE }],
        intents: [{ text: "i", source: SOURCE }],
        refusals: [],
        difficulties: [{ text: "unmapped difficulty", source: SOURCE, kill_candidates: [] }],
      }),
    );
    const checklist = checklistFor(parsed, { refusals: "none" });
    expect(checklist.complete).toBe(false);
    expect(checklist.gaps).toContain("difficulties:unmapped difficulty");
  });

  it("blocks confirmation while gaps remain (draft save still allowed)", () => {
    const parsed = parseDecomposition(
      rawWith({ requirements: [{ text: "r", source: SOURCE }] }),
    );
    expect(() =>
      confirmDecomposition(ledger, "t1", parsed, { refusals: "none" }, { decomposition_id: "dc1" }),
    ).toThrow(/pre-registration gap/);
    const draft = saveDraftDecomposition(ledger, "t1", parsed, { refusals: "none" }, { decomposition_id: "dc-draft" });
    expect(draft.status).toBe("draft");
  });
});

describe("persistence", () => {
  it("stores a confirmed decomposition with checklist state", () => {
    const parsed = parseDecomposition(
      rawWith({
        requirements: [{ text: "r", source: SOURCE }],
        constraints: [{ text: "c", source: SOURCE, hardness: "hard" }],
        background: [{ text: "b", source: SOURCE }],
        intents: [{ text: "i", source: SOURCE }],
        refusals: [],
        difficulties: [{ text: "d", source: SOURCE, kill_candidates: ["cp1"] }],
        claims_preview: [{ id: "cp1", text: "claim", kill_condition: "fails" }],
      }),
    );
    const row = confirmDecomposition(ledger, "t1", parsed, { refusals: "none" }, { decomposition_id: "dc1" });
    expect(row.status).toBe("confirmed");
    expect(ledger.getDecomposition("t1", "dc1")?.status).toBe("confirmed");
    const stored = ledger.getDecomposition("t1", "dc1")!;
    expect((stored.elements as Record<string, unknown>).refusals).toEqual([]);
    expect((stored.checklist_state as Record<string, unknown>).complete).toBe(true);
  });

  it("persists drafted (incomplete) decompositions with draft status", () => {
    const parsed = parseDecomposition(rawWith({ requirements: [{ text: "r", source: SOURCE }] }));
    const row = saveDraftDecomposition(ledger, "t1", parsed, {}, { decomposition_id: "dc-draft" });
    expect(row.status).toBe("draft");
  });
});
