/** A0 six-element decomposition engine (issue #549, docs 01 A0).

After the user confirms in chat, the conversation is decomposed into six
element classes; the confirmed set ships with v0 as the constitution of the
research. Extraction is model-side work; **schema / provenance / checklist
validation is engine-side** (two-layer contract, #501).

Mechanical rules (docs 01 A0):
1. **溯源律**: every element carries source = chat message id or attachment id
   + quote; unsourceable elements are hallucinations — **dropped before
   persist** (not rejected: the extractor's guesses are simply discarded).
2. **Sufficiency checklist**: all six classes ≥1 (refusals may be explicitly
   "none" via the confirmation note); a difficulty with no mapped kill-graph
   candidate is a pre-registration gap → blocks confirmation.
3. **Semantic classification, never user classification**: one utterance may
   split into several classes.
4. **Edit rights before confirmation**: confirmation persists the set
   (status confirmed); incomplete sets persist as draft.
5. Constraints separate hard (deployment facts) from guessed (the A1
   discrimination question relaxes guessed ones to intents).
*/

import type { LedgerStore } from "../store/ledger.js";
import { LedgerIntegrityError } from "../store/integrity.js";

export const ELEMENT_CLASSES = [
  "requirements",
  "constraints",
  "background",
  "intents",
  "refusals",
  "difficulties",
] as const;

export type ElementClass = (typeof ELEMENT_CLASSES)[number];

export interface ElementSource {
  kind: "chat-message" | "attachment";
  ref: string;
  quote: string;
}

export interface DecompositionElements {
  requirements?: Array<Record<string, unknown>>;
  constraints?: Array<Record<string, unknown>>;
  background?: Array<Record<string, unknown>>;
  intents?: Array<Record<string, unknown>>;
  refusals?: Array<Record<string, unknown>>;
  difficulties?: Array<Record<string, unknown>>;
  claims_preview?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

export interface ParsedDecomposition {
  elements: Required<DecompositionElements>;
  dropped: number;
}

export interface ChecklistState {
  complete: boolean;
  gaps: string[];
  refusals_note: string | null;
}

function hasProvenance(element: Record<string, unknown>): boolean {
  const source = element.source as Record<string, unknown> | undefined;
  return (
    isMapping(source) &&
    (source.kind === "chat-message" || source.kind === "attachment") &&
    typeof source.ref === "string" &&
    source.ref !== "" &&
    typeof source.quote === "string" &&
    source.quote !== ""
  );
}

function isMapping(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

/** 溯源律 enforcement: unsourceable elements are dropped before persist. */
function filterByProvenance(elements: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(elements)) {
    return [];
  }
  return elements.filter((element) => isMapping(element) && hasProvenance(element));
}

/** Parse a raw model-side extraction: provenance-filtered, six-class keyed. */
export function parseDecomposition(raw: DecompositionElements): ParsedDecomposition {
  if (!isMapping(raw)) {
    throw new LedgerIntegrityError("decomposition payload must be a mapping");
  }
  let dropped = 0;
  const elements = {} as Required<DecompositionElements>;
  for (const cls of ELEMENT_CLASSES) {
    const before = Array.isArray(raw[cls]) ? (raw[cls] as unknown[]).length : 0;
    const kept = filterByProvenance(raw[cls]);
    dropped += before - kept.length;
    elements[cls] = kept as Required<DecompositionElements>[ElementClass];
  }
  const preview = raw.claims_preview;
  elements.claims_preview = Array.isArray(preview)
    ? (preview.filter((entry) => isMapping(entry)) as Array<Record<string, unknown>>)
    : [];
  return { elements, dropped };
}

/** Sufficiency checklist — mechanical, computed (never LLM-judged). */
export function checklistFor(
  parsed: ParsedDecomposition,
  notes: { refusals?: string },
): ChecklistState {
  const gaps: string[] = [];
  for (const cls of ELEMENT_CLASSES) {
    const count = (parsed.elements[cls] as Array<unknown>).length;
    if (count === 0) {
      if (cls === "refusals" && notes.refusals === "none") {
        continue; // explicit "no refusals" confirmation is a valid state
      }
      gaps.push(cls);
    }
  }
  for (const difficulty of parsed.elements.difficulties as Array<Record<string, unknown>>) {
    const candidates = difficulty.kill_candidates;
    if (!Array.isArray(candidates) || candidates.length === 0) {
      gaps.push(`difficulties:${String(difficulty.text ?? "<unnamed>")}`);
    }
  }
  return { complete: gaps.length === 0, gaps, refusals_note: notes.refusals ?? null };
}

/** Persist an INCOMPLETE decomposition as a working draft (保存草稿). */
export function saveDraftDecomposition(
  ledger: LedgerStore,
  taskId: string,
  parsed: ParsedDecomposition,
  notes: { refusals?: string },
  identity: { decomposition_id: string },
): Record<string, unknown> {
  const checklist = checklistFor(parsed, notes);
  return ledger.upsertDecomposition(taskId, {
    decomposition_id: identity.decomposition_id,
    elements: parsed.elements as unknown as Record<string, unknown>,
    checklist_state: { ...checklist, dropped: parsed.dropped, notes },
    status: "draft",
  });
}

/** Confirm a decomposition: the 确认 action is gated on the sufficiency
 * checklist — gaps block (pre-registration gap). Confirmed sets are the
 * constitution; post-confirmation change is a major pivot (re-sign). */
export function confirmDecomposition(
  ledger: LedgerStore,
  taskId: string,
  parsed: ParsedDecomposition,
  notes: { refusals?: string },
  identity: { decomposition_id: string },
): Record<string, unknown> {
  const checklist = checklistFor(parsed, notes);
  if (!checklist.complete) {
    throw new LedgerIntegrityError(
      `pre-registration gap: confirmation blocked by ${JSON.stringify(checklist.gaps)}`,
    );
  }
  const existing = ledger.getDecomposition(taskId, identity.decomposition_id);
  if (existing !== null && existing.status === "confirmed") {
    throw new LedgerIntegrityError(
      `decomposition ${identity.decomposition_id} is already confirmed; post-confirmation change is a major pivot (re-sign)`,
    );
  }
  return ledger.upsertDecomposition(taskId, {
    decomposition_id: identity.decomposition_id,
    elements: parsed.elements as unknown as Record<string, unknown>,
    checklist_state: { ...checklist, dropped: parsed.dropped, notes },
    status: "confirmed",
  });
}
