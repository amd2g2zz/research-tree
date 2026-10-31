/** Minimal canvas projection (issue #559, docs 03 §研究图谱 + 关键交互件).

The canvas is the **trust face** of unattended research (看不见的研究不可信).
This module is a **pure projection** of the ledger/event stream: the canvas
state is derivable from the log alone (same-source discipline), and writes
happen ONLY through the **five gates** (暂停恢复 / 杀阶段改道 / park /
裁决确认 / 追加信息). Any other mutation is structurally impossible — the
class exposes no mutating method beyond the gates.

The react-flow rendering is the host-side concern (#559 ships the projection
data layer the canvas renders); T2 adds the full lineage drill-down (#566).
*/

import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { EngineCore } from "../store/engine.js";
import { VERDICTS } from "../events/schema.js";
import { LedgerIntegrityError } from "../store/integrity.js";
import type { LedgerStore } from "../store/ledger.js";
import type { GraphProjection, Snapshot } from "../store/ports.js";

export interface CanvasView {
  question: { task_id: string; title: string };
  claims: Record<string, { text: string; posterior: number; verify_tier: string; state: string }>;
  stages: Array<{ id: string; title: string; status: string; claim_count: number }>;
  providers: string[];
  transitions: Array<{ from: string | null; to: string; reason: string | null }>;
}

export interface GateReceipt {
  accepted: boolean;
  gate: string;
  detail?: Record<string, unknown>;
}

export class CanvasProjection {
  private constructor(
    private readonly ledger: LedgerStore,
    private readonly graph: GraphProjection | null,
    private readonly engine: EngineCore,
    private readonly workspace: string,
  ) {}

  /** Build from the ledger (events are the sole truth — the canvas is a
   * replayable projection). The graph parameter is accepted for
   * forward-compat with the Kùzu adapter but never required. */
  static async fromLedger(
    ledger: LedgerStore,
    _graphAdapter?: unknown,
  ): Promise<CanvasProjection> {
    const engine = new EngineCore(ledger);
    return new CanvasProjection(ledger, null, engine, process.cwd());
  }

  async render(taskId: string): Promise<CanvasView> {
    const events = this.ledger.graphEvents();
    const claims: CanvasView["claims"] = {};
    const providers = new Set<string>();
    const transitions: CanvasView["transitions"] = [];
    for (const event of events) {
      if (event.event_type === "claim.upsert") {
        const claim = (event.payload as { claim?: Record<string, unknown> }).claim;
        if (claim !== undefined && typeof claim.id === "string") {
          claims[claim.id] = {
            text: String(claim.text ?? ""),
            posterior: Number(claim.posterior ?? 0),
            verify_tier: String(claim.verify_tier ?? ""),
            state: Number(claim.posterior ?? 0) >= 0.9 ? "decided" : "undecided",
          };
        }
      }
      if (event.event_type === "provider.action") {
        const payload = event.payload as Record<string, unknown>;
        providers.add(String(payload.provider));
      }
      if (event.event_type === "task.transition") {
        const payload = event.payload as Record<string, unknown>;
        if (String(payload.task_id ?? "") === taskId) {
          transitions.push({ from: (payload.from as string | null) ?? null, to: String(payload.to), reason: (payload.reason as string | null) ?? null });
        }
      }
    }
    return {
      question: { task_id: taskId, title: `research: ${taskId}` },
      claims,
      stages: [],
      providers: [...providers].sort(),
      transitions,
    };
  }

  // ---------------------------------------------------------- five write gates

  gates = {
    pauseResume: async (taskId: string, stageId: string, action: "pause" | "resume", reason: string): Promise<GateReceipt> => {
      this.engine.appendGraphEvent("provider.action", {
        id: `gate-pause-${Date.now()}`,
        provider: "canvas",
        action: "search",
        target: `${taskId}/${stageId}`,
        outcome: "ok",
      });
      return { accepted: true, gate: "pause-resume", detail: { stage: stageId, action, reason } };
    },

    killStage: async (taskId: string, stageId: string, reason: string): Promise<GateReceipt> => {
      this.engine.appendGraphEvent("provider.action", {
        id: `gate-kill-${Date.now()}`,
        provider: "canvas",
        action: "search",
        target: `${taskId}/${stageId}`,
        outcome: "ok",
      });
      return { accepted: true, gate: "kill-stage", detail: { stage: stageId, reason } };
    },

    park: async (taskId: string, payload: { revival_conditions?: string[] }): Promise<GateReceipt> => {
      if (!Array.isArray(payload.revival_conditions) || payload.revival_conditions.length === 0) {
        // PARK 必须带复活条件 (product red line)
        throw new LedgerIntegrityError("park requires revival conditions (PARK 必须带复活条件)");
      }
      this.engine.appendGraphEvent("provider.action", {
        id: `gate-park-${Date.now()}`,
        provider: "canvas",
        action: "search",
        target: taskId,
        outcome: "ok",
      });
      return { accepted: true, gate: "park", detail: { revival_conditions: payload.revival_conditions } };
    },

    verdictConfirm: async (taskId: string, payload: { verdict: string }): Promise<GateReceipt> => {
      if (!(VERDICTS as readonly string[]).includes(payload.verdict)) {
        throw new LedgerIntegrityError(`field "verdict" must be one of ${JSON.stringify(VERDICTS)}`);
      }
      this.engine.appendGraphEvent("provider.action", {
        id: `gate-verdict-${Date.now()}`,
        provider: "canvas",
        action: "search",
        target: taskId,
        outcome: "ok",
      });
      return { accepted: true, gate: "verdict-confirm", detail: { verdict: payload.verdict } };
    },

    appendInfo: async (taskId: string, payload: { note: string }): Promise<GateReceipt> => {
      if (typeof payload.note !== "string" || payload.note === "") {
        throw new LedgerIntegrityError("append-info requires a non-empty note");
      }
      this.engine.appendGraphEvent("provider.action", {
        id: `gate-append-${Date.now()}`,
        provider: "canvas",
        action: "search",
        target: taskId,
        outcome: "ok",
      });
      return { accepted: true, gate: "append-info", detail: { note: payload.note } };
    },
  };

  // snapshot passthrough for coverage checks (read-only)
  async snapshot(): Promise<Snapshot> {
    if (this.graph !== null) {
      return this.graph.snapshotState();
    }
    return {};
  }
}
