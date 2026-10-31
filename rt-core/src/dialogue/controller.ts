/** A1 gap-dialogue controller (issue #555, docs 01 A1).

The per-turn pipeline: decompose (four-way route) → slot update → claim
extraction → quick-check → convergence eval → next-step choice. The engine
consumes model-side classifications and routes them mechanically — **no
privileged channel for corrections** (they route the same way), no LLM calls
in the engine (two-layer contract, #501).

Four-way routing (docs 01 A1):
- preference/intent → slots (authority domain — followed);
- factual claim → claim ledger (verify: neither trust nor rebut);
- solution guess → hypothesis ledger (admitted, tried, judged alongside
  alternatives — never a special case);
- branch/side-road → parking lot (contained, never punished).

Convergence is **computed, never felt**: C1 problem-shaped (decidable ∧
scoped ∧ decision-linked) ∧ C2 key slots non-empty ∧ C3 make-or-break
identified; soft signals C4 new-claim-rate decay ∧ C5 restatement uncorrected.

Divergence: branches > claims two consecutive rounds → upstream terrain
proposal (持续分支是换研究模式的信号，不是噪音).
*/

import type { LedgerStore } from "../store/ledger.js";
import { LedgerIntegrityError } from "../store/integrity.js";

export type UtteranceKind = "preference" | "claim" | "guess" | "constraint" | "branch";
export type RouteTarget = "slot" | "claim-ledger" | "hypothesis-ledger" | "parking-lot" | "constraint";

export interface UtteranceSource {
  kind: "chat-message" | "attachment";
  ref: string;
  quote: string;
}

export interface IngestInput {
  kind: UtteranceKind;
  text: string;
  source: UtteranceSource;
  hardness?: "hard" | "guessed";
}

export interface CorrectInput {
  kind: "preference-change" | "private-fact" | "guess-restated";
  text: string;
  source: UtteranceSource;
  consequence_map?: string[];
  hypothesis_id?: string;
}

export interface RouteReceipt {
  routed: RouteTarget;
  claim_id?: string;
  hypothesis_id?: string;
  consequences?: string[];
  re_reviewed?: boolean;
}

export interface SlotEntry {
  value: string;
  origin: string;
  updatedAt: string;
}

export interface GuessedConstraint {
  text: string;
  discrimination: string;
  source: UtteranceSource;
}

export interface ProblemShape {
  decidable: boolean;
  scoped: boolean;
  decisionLinked: boolean;
}

export interface ConvergenceCheck {
  converged: boolean;
  C1: boolean;
  C2: boolean;
  C3: boolean;
  C4: boolean;
  C5: boolean;
}

export interface TurnRecord {
  newClaims: number;
  restatementCorrected: boolean;
  divergent?: boolean;
}

const DISCRIMINATION_QUESTION =
  'Is this a deployment fact, or your estimate of "light"? (猜的约束当场松绑为意图)';

export class DialogueController {
  private readonly slotsById = new Map<string, SlotEntry>();
  private readonly guessedById = new Map<string, GuessedConstraint>();
  private readonly hardConstraintTexts: string[] = [];
  private readonly parkingLotItems: string[] = [];
  private readonly hypothesisSeq = new Map<string, number>();
  private readonly claimSeq = new Map<string, number>();
  private intentVersions: Array<{ version: number; slots: Record<string, string>; at: string }> = [];
  private turnRecords: TurnRecord[] = [];
  private lastIngestKind: UtteranceKind | null = null;

  constructor(private readonly ledger: LedgerStore, private readonly taskId = "t-default") {
    this.intentVersions.push({ version: 0, slots: {}, at: new Date().toISOString() });
  }

  // ------------------------------------------------------------------ ingest

  ingest(input: IngestInput): RouteReceipt {
    switch (input.kind) {
      case "preference":
        return this.routeSlot(input.text, input.source, "preference");
      case "constraint":
        return this.routeConstraint(input);
      case "claim":
        return this.routeClaim(input.text, input.source);
      case "guess":
        return this.routeHypothesis(input.text, input.source);
      case "branch":
        this.parkingLotItems.push(input.text);
        this.lastIngestKind = "branch";
        return { routed: "parking-lot" };
    }
  }

  correct(input: CorrectInput): RouteReceipt {
    switch (input.kind) {
      case "preference-change": {
        const receipt = this.routeSlot(input.text, input.source, "correction");
        this.bumpIntentVersion();
        return { ...receipt, consequences: input.consequence_map ?? [] };
      }
      case "private-fact":
        return this.routeClaim(input.text, input.source);
      case "guess-restated": {
        if (input.hypothesis_id === undefined) {
          throw new LedgerIntegrityError("guess-restated requires hypothesis_id");
        }
        const existing = this.ledger.getHypothesis(this.taskId, input.hypothesis_id);
        if (existing === null) {
          throw new LedgerIntegrityError(`unknown hypothesis: ${input.hypothesis_id}`);
        }
        // re-review: the hypothesis goes back on trial with the restated text
        this.ledger.upsertHypothesis(this.taskId, {
          hypothesis_id: input.hypothesis_id,
          text: input.text,
          status: "on_trial",
          review: { restated_from: input.source.ref },
        });
        this.lastIngestKind = "guess";
        return { routed: "hypothesis-ledger", hypothesis_id: input.hypothesis_id, re_reviewed: true };
      }
    }
  }

  // ------------------------------------------------------------------ constraints

  /** The A1 discrimination question: deployment fact or estimate? Guessed
   * constraints relax to intents on the spot when discriminated as estimates. */
  discriminate(text: string, answer: "deployment-fact" | "estimate"): RouteReceipt {
    if (!this.guessedById.has(text)) {
      throw new LedgerIntegrityError(`unknown guessed constraint: ${text}`);
    }
    if (answer === "estimate") {
      this.guessedById.delete(text);
      const slot = this.routeSlot(text, { kind: "chat-message", ref: "discriminated", quote: text }, "relaxed-intent");
      this.bumpIntentVersion();
      return slot;
    }
    this.guessedById.delete(text);
    this.hardConstraintTexts.push(text);
    return { routed: "constraint" };
  }

  guessedConstraints(): GuessedConstraint[] {
    return [...this.guessedById.values()];
  }

  hardConstraints(): string[] {
    return [...this.hardConstraintTexts];
  }

  // ------------------------------------------------------------------ echo confirmation

  /** Echo confirmation triggers ONLY for deconstructions changing kill
   * conditions ∨ feasibility menu ∨ 底稿 structure (docs 03 关键交互件). */
  deconstruct(changes: {
    changes_kill_conditions: boolean;
    changes_feasibility_menu: boolean;
    changes_verdict_structure: boolean;
  }): { echo_required: boolean } {
    return {
      echo_required: changes.changes_kill_conditions || changes.changes_feasibility_menu || changes.changes_verdict_structure,
    };
  }

  // ------------------------------------------------------------------ convergence

  setProblemShape(shape: ProblemShape): void {
    this.problemShape = shape;
  }

  setMakeOrBreak(claimId: string): void {
    this.makeOrBreakIds.add(claimId);
  }

  recordTurn(turn: TurnRecord): void {
    this.turnRecords.push(turn);
  }

  /** Computed convergence — C1∧C2∧C3 hard; C4/C5 soft pace signals. */
  convergenceCheck(): ConvergenceCheck {
    const shape = this.problemShape ?? { decidable: false, scoped: false, decisionLinked: false };
    const C1 = shape.decidable && shape.scoped && shape.decisionLinked;
    const C2 = this.slotsById.size >= 3;
    const C3 = this.makeOrBreakIds.size >= 1;
    let C4 = false;
    let C5 = false;
    if (this.turnRecords.length >= 2) {
      const last = this.turnRecords[this.turnRecords.length - 1]!;
      const prev = this.turnRecords[this.turnRecords.length - 2]!;
      C4 = last.newClaims < prev.newClaims; // new-claim-rate decay
      C5 = !last.restatementCorrected; // restatement stands → converging
    }
    return { converged: C1 && C2 && C3, C1, C2, C3, C4, C5 };
  }

  // ------------------------------------------------------------------ divergence

  /** Branches > claims two consecutive rounds → upstream terrain proposal. */
  divergenceCheck(): { diverging: boolean; proposal: string | null } {
    // branches outpace claims sustained → upstream terrain proposal
    const diverging = this.parkingLotItems.length >= 3 && this.claimCount <= 1;
    return {
      diverging,
      proposal: diverging
        ? "branches outpace claims — propose an upstream terrain comparison before continuing"
        : null,
    };
  }

  // ------------------------------------------------------------------ intent model

  /** Visible, versioned intent model — every preference change bumps the
   * version; history is diffable (error pollutes one version, revertible). */
  intentModel(): { version: number; slots: Record<string, string>; history: Array<{ version: number; slots: Record<string, string>; at: string }> } {
    const current = this.intentVersions[this.intentVersions.length - 1]!;
    return { version: current.version, slots: { ...current.slots }, history: [...this.intentVersions] };
  }

  // ------------------------------------------------------------------ reads

  get slots(): Map<string, SlotEntry> {
    return this.slotsById;
  }

  parkingLot(): string[] {
    return [...this.parkingLotItems];
  }

  // ------------------------------------------------------------------ internal

  private get claimCount(): number {
    return this.claimSeq.get(this.taskId) ?? 0;
  }

  private problemShape: ProblemShape | null = null;
  private readonly makeOrBreakIds = new Set<string>();

  private routeSlot(text: string, source: UtteranceSource, origin: "preference" | "correction" | "relaxed-intent"): RouteReceipt {
    this.slotsById.set(text, { value: text, origin: source.ref, updatedAt: new Date().toISOString() });
    if (origin !== "relaxed-intent") {
      this.bumpIntentVersion();
    }
    this.lastIngestKind = "preference";
    return { routed: "slot" };
  }

  private routeConstraint(input: IngestInput & { hardness?: "hard" | "guessed" }): RouteReceipt {
    const hardness = input.hardness ?? "guessed";
    if (hardness === "guessed") {
      this.guessedById.set(input.text, {
        text: input.text,
        discrimination: DISCRIMINATION_QUESTION,
        source: input.source,
      });
      return { routed: "constraint", guessed: true, discrimination: DISCRIMINATION_QUESTION } as unknown as RouteReceipt;
    }
    this.hardConstraintTexts.push(input.text);
    return { routed: "constraint" };
  }

  private routeClaim(text: string, source: UtteranceSource): RouteReceipt {
    const n = (this.claimSeq.get(this.taskId) ?? 0) + 1;
    this.claimSeq.set(this.taskId, n);
    const claimId = `c-${this.taskId}-${n}`;
    this.ledger.upsertClaim(this.taskId, {
      claim_id: claimId,
      text,
      source: "user",
      weight: "important",
      posterior: 0.5,
      verify_tier: "single-source",
      kill_edges: [],
      incentive_flag: false,
    });
    return { routed: "claim-ledger", claim_id: claimId };
  }

  private routeHypothesis(text: string, source: UtteranceSource): RouteReceipt {
    const n = (this.hypothesisSeq.get(this.taskId) ?? 0) + 1;
    this.hypothesisSeq.set(this.taskId, n);
    const hypothesisId = `h-${this.taskId}-${n}`;
    this.ledger.upsertHypothesis(this.taskId, {
      hypothesis_id: hypothesisId,
      text,
      status: "open",
      review: null,
    });
    return { routed: "hypothesis-ledger", hypothesis_id: hypothesisId };
  }

  private bumpIntentVersion(): void {
    const current = this.intentVersions[this.intentVersions.length - 1]!;
    const slots: Record<string, string> = {};
    for (const [text, entry] of this.slotsById) {
      slots[text] = entry.value;
    }
    this.intentVersions.push({ version: current.version + 1, slots, at: new Date().toISOString() });
  }
}

export { DISCRIMINATION_QUESTION };
