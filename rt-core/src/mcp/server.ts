/** MCP server — the product exit (issue #553, docs 04 产品不变式: MCP 是出口).

Four tools, **projection-only** (no state merge into the harness — the
LoopX/DSH lesson): rt.start / rt.status / rt.correct / rt.verdict.
`rt.correct` routes through the same correction path as chat (no privileged
channel). `rt.verdict` returns report + 底稿 paths and version metadata when
committed.

The `McpToolCaller` is the transport-independent contract: tests call tools
directly; the stdio MCP transport (official SDK) binds the same handler in
the CLI wiring (#579 entry).
*/

import type { LedgerStore } from "../store/ledger.js";
import type { VersionStore } from "../versions/store.js";
import type { ProductStateMachine } from "../state/machine.js";
import { LedgerIntegrityError } from "../store/integrity.js";

export interface McpToolCaller {
  listTools(): Array<{ name: string; description: string }>;
  call(tool: string, args: Record<string, unknown>): Promise<Record<string, unknown>>;
}

export interface McpServerOptions {
  ledger: LedgerStore;
  versions: VersionStore;
  machine: ProductStateMachine;
}

const TOOLS: Array<{ name: string; description: string }> = [
  { name: "rt.start", description: "begin/continue a research task (project/task addressing)" },
  { name: "rt.status", description: "state-machine phase + ledger digest + draft/version pointers" },
  { name: "rt.correct", description: "steering input, routed through the same correction path as chat" },
  { name: "rt.verdict", description: "report + 底稿 paths; version metadata when committed" },
];

export function createMcpServer(options: McpServerOptions): McpToolCaller {
  const { ledger, versions, machine } = options;

  async function call(tool: string, args: Record<string, unknown>): Promise<Record<string, unknown>> {
    const taskId = String(args.task_id ?? "");
    switch (tool) {
      case "rt.start": {
        if (taskId === "") {
          throw new LedgerIntegrityError('field "task_id" must be a non-empty string');
        }
        if (machine.phaseOf(taskId) === undefined) {
          machine.openTask(taskId);
        }
        return { task_id: taskId, phase: machine.phaseOf(taskId) };
      }
      case "rt.status": {
        const latest = versions.latestVersion(taskId);
        const draft = versions.draftOf(taskId);
        return {
          task_id: taskId,
          phase: machine.phaseOf(taskId) ?? null,
          ledger_events: ledger.graphEvents().length,
          latest_version: latest === null ? null : { v: latest.v, verdict: latest.verdict, commit_hash: latest.commit_hash },
          draft: draft === null ? null : { base_v: draft.base_v, updated_at: draft.updated_at },
        };
      }
      case "rt.correct": {
        if (taskId === "") {
          throw new LedgerIntegrityError('field "task_id" must be a non-empty string');
        }
        // same correction path as chat: the payload lands as an engine fact;
        // no privileged channel, no direct state mutation from the harness
        ledger.appendGraphEvent("provider.action", {
          id: `mcp-correct-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          provider: "mcp",
          action: "search",
          target: String(args.kind ?? "correction"),
          outcome: "ok",
        });
        return { accepted: true, routed: "correction", task_id: taskId };
      }
      case "rt.verdict": {
        const latest = versions.latestVersion(taskId);
        if (latest === null) {
          throw new LedgerIntegrityError(`no committed version for ${taskId}`);
        }
        return {
          task_id: taskId,
          v: latest.v,
          verdict: latest.verdict,
          commit_hash: latest.commit_hash,
          summary: latest.summary,
          report_path: `.research-tree/tasks/${taskId}/versions/v${latest.v}/report.md`,
          verdict_path: `.research-tree/tasks/${taskId}/versions/v${latest.v}/verdict.json`,
        };
      }
      default:
        throw new LedgerIntegrityError(`unknown tool: ${tool}`);
    }
  }

  return {
    listTools: () => TOOLS,
    call,
  };
}
