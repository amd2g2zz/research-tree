/** Engine core: dual-write mediator between the event log (authority) and the graph projection.

Depends only on the `EventLog` / `GraphProjection` ports (dependency inversion):
implementations are swappable and tests can substitute fakes. The state machine
(issue #551) grows on top of this class. Projection failure is fail-closed —
the log keeps the event and `resyncGraph()` rebuilds the projection from the
log alone.
*/

import type { GraphProjection, Snapshot } from "./ports.js";
import type { EventLog, EventPayload } from "./ports.js";
import type { GraphEventRecord, LedgerStore } from "./ledger.js";

export class GraphProjectionError extends Error {}

export class EngineCore {
  private readonly projection: GraphProjection | null;

  constructor(
    readonly log: EventLog,
    projection?: GraphProjection | null,
  ) {
    if (projection !== undefined && projection !== null && !isGraphProjection(projection)) {
      throw new Error("projection must implement GraphProjection");
    }
    this.projection = projection ?? null;
  }

  async appendGraphEvent(
    eventType: string,
    payload: EventPayload,
    options: { runId?: string | null } = {},
  ): Promise<GraphEventRecord> {
    const record = this.log.appendGraphEvent(eventType, payload, options);
    if (this.projection !== null) {
      try {
        await this.projection.applyEvent(record);
      } catch (error: unknown) {
        // the log (authority) keeps the event; the caller learns the projection diverged
        throw new GraphProjectionError(
          `graph projection diverged from the event log; resyncGraph() required: ${String(error)}`,
        );
      }
    }
    return record;
  }

  graphEvents(sinceSeq = 0): GraphEventRecord[] {
    return this.log.graphEvents(sinceSeq);
  }

  /** Claim ledger round-trip: ledger row write + graph events.
   * Emits one `claim.upsert` (row state; the node's `stale` flag is owned by
   * belief-propagation events) plus one `claim.kill_edge` per kill edge —
   * CRUD never bypasses the dual-write seam.
   */
  upsertClaim(taskId: string, payload: Record<string, unknown>): Record<string, unknown> {
    const surface = this.log as LedgerStore;
    const row = surface.upsertClaim(taskId, payload);
    this.appendGraphEvent("claim.upsert", {
      claim: {
        id: row.claim_id,
        text: row.text,
        source: row.source,
        weight: row.weight,
        posterior: row.posterior,
        verify_tier: row.verify_tier,
      },
    });
    for (const killTarget of row.kill_edges as string[]) {
      this.appendGraphEvent("claim.kill_edge", {
        claim_id: row.claim_id,
        kill_target_id: killTarget,
      });
    }
    return row;
  }

  async resyncGraph(): Promise<Snapshot> {
    if (this.projection === null) {
      throw new Error("no graph projection attached to this engine");
    }
    return this.projection.rebuild(this.log.graphEvents());
  }
}

function isGraphProjection(value: unknown): value is GraphProjection {
  return (
    value !== null &&
    typeof value === "object" &&
    typeof (value as GraphProjection).applyEvent === "function" &&
    typeof (value as GraphProjection).rebuild === "function" &&
    typeof (value as GraphProjection).snapshotState === "function"
  );
}
