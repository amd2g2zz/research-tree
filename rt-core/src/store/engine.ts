/** Engine core: dual-write mediator between the event log (authority) and the graph projection.

Depends only on the `EventLog` / `GraphProjection` ports (dependency inversion):
implementations are swappable and tests can substitute fakes. The state machine
(issue #551) grows on top of this class. Projection failure is fail-closed —
the log keeps the event and `resyncGraph()` rebuilds the projection from the
log alone.
*/

import type { GraphProjection, Snapshot } from "./ports.js";
import type { EventLog, EventPayload } from "./ports.js";
import type { GraphEventRecord } from "./ledger.js";

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
