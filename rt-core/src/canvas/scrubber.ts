/** Timeline scrubber (issue #572, charter §6 时间轴回放).

The ledger is append-only, so **the canvas at any t is a pure projection of
events ≤ t** — the scrubber drags to any beat and the graph and console stay
in sync because both derive from the same event prefix. Deterministic by
construction: projection(t) reproduces from the event stream alone (#546
replay property), independent of when or where it is scrubbed.

Extends the #559 replay bar into full-run replay: "研究怎么走到今天" is
scrubable beat by beat (beat = one appended graph event).
*/

import { GraphStore } from "../graph/projection.js";
import type { LedgerStore } from "../store/ledger.js";

export interface Beat {
  seq: number;
  event_type: string;
  created_at: string;
  summary: string;
}

export interface CanvasAtBeat {
  snapshot: Record<string, unknown>;
  console: string[];
}

function summarize(event: Record<string, unknown>): string {
  const type = String(event.event_type);
  const payload = event.payload as Record<string, unknown> | undefined;
  if (type === "claim.upsert" && payload?.claim !== undefined) {
    const claim = payload.claim as Record<string, unknown>;
    return `claim ${String(claim.id)} posterior=${String(claim.posterior)} [${String(claim.weight)}]`;
  }
  if (type === "claim.kill_edge" && payload?.from !== undefined) {
    return `kill_edge ${String(payload.from)} → ${String(payload.to ?? "")}`;
  }
  if (type === "provider.action") {
    const results = payload?.result_count;
    return `${String(payload?.provider ?? "provider")} ${String(payload?.action ?? "")} ${String(payload?.target ?? "")} → ${String(payload?.outcome ?? "")}${results !== undefined ? ` (${String(results)} results)` : ""}`;
  }
  if (type === "task.transition") {
    return `task ${String(payload?.task_id ?? "")} → ${String(payload?.to ?? "")}`;
  }
  return type;
}

export class TimelineScrubber {
  private readonly store: GraphStore;

  constructor(
    private readonly ledger: LedgerStore,
    databasePath: string,
  ) {
    this.store = new GraphStore(databasePath);
  }

  async close(): Promise<void> {
    await this.store.close();
  }

  beatCount(): number {
    return this.ledger.graphEvents().length;
  }

  /** The full-run beat list the drag bar scrubs across. */
  beats(): Beat[] {
    return this.ledger.graphEvents().map((event) => ({
      seq: event.seq,
      event_type: event.event_type,
      created_at: event.created_at,
      summary: summarize(event as unknown as Record<string, unknown>),
    }));
  }

  /** The canvas at beat t: graph snapshot + console lines from events ≤ t. */
  async projectionAt(t: number): Promise<CanvasAtBeat> {
    const all = this.ledger.graphEvents();
    const clamped = Math.max(0, Math.min(t, all.length));
    const prefix = all.slice(0, clamped);
    const snapshot = await this.store.rebuild(prefix as unknown as Array<Record<string, unknown>>);
    return {
      snapshot: snapshot as unknown as Record<string, unknown>,
      console: prefix.map((event) => summarize(event as unknown as Record<string, unknown>)),
    };
  }
}
