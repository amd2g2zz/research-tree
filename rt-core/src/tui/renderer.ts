/** TUI renderer — same-source research projection in the terminal
 * (issue #580, docs 03 page logic + red lines).

The TUI is a **rendering surface, not a second behavior implementation**: the
frame derives entirely from the ledger/event stream (same source as the web
canvas #559 and the headless runner #579). Red lines carried over: status
never color-only (text state always present), draft nodes labeled
"未冻结·不可跟踪", committed versions never imply modifiability
("继续研究=版本+1").

This module renders the frame; the TUI toolkit (interactive scrolling,
keybindings) is host-side (#552 pi extension / standalone binary).
*/

import type { LedgerStore } from "../store/ledger.js";
import type { VersionStore } from "../versions/store.js";
import type { ProductStateMachine } from "../state/machine.js";

export interface TuiFrameOptions {
  ledger: LedgerStore;
  versions: VersionStore;
  machine: ProductStateMachine;
  graph?: unknown;
}

export async function renderTuiFrame(options: TuiFrameOptions): Promise<string> {
  const { ledger, versions, machine } = options;
  const lines: string[] = [];

  // SIDEBAR: task tree with draft/version nodes
  lines.push("=== SIDEBAR ===");
  const taskIds = collectTaskIds(ledger);
  for (const taskId of taskIds) {
    const latest = versions.latestVersion(taskId);
    // a task with no committed version is entirely untracked working state
    if (latest === null) {
      lines.push(`  ${taskId} [未冻结·不可跟踪]`);
      continue;
    }
    const draft = versions.draftOf(taskId);
    const suffix = draft !== null ? " + [未冻结·不可跟踪 draft]" : "";
    lines.push(`  ${taskId} [v${latest.v}·${latest.verdict}]${suffix}`);
  }

  // PHASE: machine phase per open task
  lines.push("=== PHASE ===");
  for (const taskId of taskIds) {
    lines.push(`  ${taskId} phase: ${machine.phaseOf(taskId) ?? "unknown"}`);
  }

  // CLAIMS: ledger rows with posterior
  lines.push("=== CLAIMS ===");
  for (const row of ledger.listClaims(taskIds[0] ?? "")) {
    lines.push(`  ${row.claim_id} ${row.text} [posterior ${Number(row.posterior).toFixed(2)}] [${row.verify_tier}] [${row.weight}]`);
  }

  // CONSOLE: last transition events (terminal tail)
  lines.push("=== CONSOLE ===");
  const events = ledger.graphEvents();
  for (const event of events.slice(-5)) {
    if (event.event_type === "task.transition") {
      const payload = event.payload as Record<string, unknown>;
      lines.push(`  [${event.seq}] ${payload.task_id}: ${payload.from ?? "birth"} -> ${payload.to}`);
    }
  }

  // FROZEN banner for committed versions
  for (const taskId of taskIds) {
    const latest = versions.latestVersion(taskId);
    if (latest !== null) {
      lines.push(`=== FROZEN ${taskId} v${latest.v}·${latest.verdict}·${latest.commit_hash.slice(0, 12)} (继续研究=版本+1) ===`);
    }
  }

  return lines.join("\n");
}

function collectTaskIds(ledger: LedgerStore): string[] {
  const seen = new Set<string>();
  for (const event of ledger.graphEvents()) {
    const payload = event.payload as Record<string, unknown> | undefined;
    const taskId = payload?.task_id;
    if (typeof taskId === "string" && taskId !== "") {
      seen.add(taskId);
    }
  }
  return [...seen].sort();
}
