/** Ports & adapters: the engine core depends on these interfaces only.

`LedgerStore` adapts `EventLog` (SQLite authority); `GraphStore` adapts
`GraphProjection` (Kùzu fold). Tests substitute in-memory fakes; later waves
add implementations (replay-synced projection, queue-backed log) without
touching the mediator.
*/

import type { GraphEventRecord } from "./ledger.js";

export type EventPayload = Record<string, unknown>;

export interface EventLog {
  appendGraphEvent(
    eventType: string,
    payload: EventPayload,
    options: { runId?: string | null },
  ): GraphEventRecord;
  graphEvents(sinceSeq?: number): GraphEventRecord[];
  verifyGraphChain(): void;
}

export type Snapshot = Record<string, unknown>;

export interface GraphProjection {
  applyEvent(record: Record<string, unknown>): Promise<void>;
  rebuild(records: Iterable<Record<string, unknown>>): Promise<Snapshot>;
  snapshotState(): Promise<Snapshot>;
}
