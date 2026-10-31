/** Decomposition visualization (P3 card wall) + artifact management
 * (issue #561, docs 03 §六要素分解可视化).

Grouped card wall, six grids: 🎯 requirements / 📌 constraints (hard vs
guessed separated) / 📖 background (incl. attachment parses) / 💡 intents /
🚫 refusals / ⚠ difficulties→kill candidates.

- **溯源律 visible**: every card carries its provenance quote
  ("来自你的话：'…'" / "来自附件：…");
- **edit rights before confirm**: delete is a real mutation on the draft model;
- **insufficient elements show "待对齐" placeholders** — never demo content;
- **checklist gating**: confirm blocks on the pre-registration gap.

The UI rendering is host-side; this module is the projection the P3 page renders.
*/

import { checklistFor, type ParsedDecomposition } from "../decomposition/engine.js";
import { confirmDecomposition } from "../decomposition/engine.js";
import type { LedgerStore } from "../store/ledger.js";

export interface Card {
  text: string;
  provenance: string;
  source: Record<string, unknown>;
  kill_candidates?: string[];
  hardness?: string;
}

export type CardGroups = Record<string, Card[]>;

export class CardWallModel {
  private readonly parsed: ParsedDecomposition;

  constructor(parsed: ParsedDecomposition) {
    this.parsed = parsed;
  }

  cards(): CardGroups {
    // the six P3 classes only — claims_preview is the ledger preview, not a card wall group
    const classes = ["requirements", "constraints", "background", "intents", "refusals", "difficulties"];
    const groups: CardGroups = {};
    for (const cls of classes) {
      const elements = this.parsed.elements[cls as keyof typeof this.parsed.elements] as
        | Array<Record<string, unknown>>
        | undefined;
      groups[cls] = (elements ?? []).map((element) => this.toCard(element));
    }
    return groups;
  }

  deleteElement(cls: string, index: number): void {
    const elements = this.parsed.elements[cls] as Array<Record<string, unknown>> | undefined;
    if (elements === undefined) {
      throw new Error(`unknown class: ${cls}`);
    }
    if (index < 0 || index >= elements.length) {
      throw new Error(`index out of range: ${cls}[${index}]`);
    }
    elements.splice(index, 1);
  }

  placeholderFor(cls: string): string {
    return `待对齐 — ${cls}: 需要更多对话轮次来提取这一类要素（非演示脚手架）`;
  }

  /** Confirm via the #549 engine (checklist-gated). */
  confirm(
    ledger: LedgerStore,
    taskId: string,
    notes: { refusals?: string },
    identity: { decomposition_id: string },
  ): Record<string, unknown> {
    return confirmDecomposition(ledger, taskId, this.parsed, notes, identity);
  }

  checklist(): ReturnType<typeof checklistFor> {
    return checklistFor(this.parsed, {});
  }

  private toCard(element: Record<string, unknown>): Card {
    const source = element.source as { kind: string; ref: string; quote: string };
    const provenance =
      source.kind === "attachment"
        ? `来自附件：${source.ref}（"${source.quote}"）`
        : `来自你的话："${source.quote}"`;
    const card: Card = { text: String(element.text ?? ""), provenance, source: element };
    if (Array.isArray(element.kill_candidates)) {
      card.kill_candidates = element.kill_candidates as string[];
    }
    if (element.hardness !== undefined) {
      card.hardness = String(element.hardness);
    }
    return card;
  }
}

/** Render the card wall as text (the P3 page's data shape, host-side UI optional). */
export function renderCardWall(model: CardWallModel): string {
  const groups = model.cards();
  const lines: string[] = [];
  const icons: Record<string, string> = {
    requirements: "🎯", constraints: "📌", background: "📖",
    intents: "💡", refusals: "🚫", difficulties: "⚠",
  };
  for (const [cls, cards] of Object.entries(groups)) {
    lines.push(`${icons[cls] ?? "·"} ${cls} (${cards.length})`);
    for (const card of cards) {
      lines.push(`  - ${card.text} [${card.provenance}]`);
    }
    if (cards.length === 0) {
      lines.push(`  - ${model.placeholderFor(cls)}`);
    }
  }
  return lines.join("\n");
}
