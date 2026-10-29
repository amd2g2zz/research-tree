/** Object-graph projection over SQLite adjacency tables (issue #546, rt-core TS).

Implements the `GraphProjection` port. The write authority stays in the
ledger's hash-chained event log; this store is a **replayable projection**:
`rebuild(records)` reproduces an identical state from the log alone, and every
`applyEvent` is idempotent (state-carrying upserts + existence-checked edges).

Storage note (disclosed 2026-10-30): the roadmap names Kùzu for this layer,
but the kuzu npm 0.11.x binding segfaults with concurrent open databases and
hangs closing after heavy use (measured). Per the pre-agreed risk path, the
projection ships on SQLite adjacency tables behind the same port; the Kùzu
adapter returns when the binding is stable. Forward-referenced edges (an edge
event whose endpoint is not yet upserted) are held in a pending queue keyed by
endpoint and materialized when the endpoint arrives.
*/

import Database from "better-sqlite3";

import type { GraphEventType } from "../events/schema.js";
import { GraphEventError, validateGraphEvent } from "../events/schema.js";
import type { GraphProjection, Snapshot } from "../store/ports.js";

type Payload = Record<string, unknown>;
type Row = Record<string, unknown>;

export const NODE_TABLES = ["Claim", "Stage", "Evidence", "Artifact", "VersionNode"] as const;

interface NodeSpec {
  table: string;
  columns: readonly string[];
  booleans: readonly string[];
}

const NODE_SPECS: Record<string, NodeSpec> = {
  Claim: {
    table: "nodes_claim",
    columns: ["id", "text", "source", "weight", "posterior", "verify_tier", "stale", "updated_at"],
    booleans: ["stale"],
  },
  Stage: { table: "nodes_stage", columns: ["id", "title", "status", "updated_at"], booleans: [] },
  Evidence: { table: "nodes_evidence", columns: ["id", "digest", "origin", "updated_at"], booleans: [] },
  Artifact: {
    table: "nodes_artifact",
    columns: ["id", "kind", "digest", "deleted", "updated_at"],
    booleans: ["deleted"],
  },
  VersionNode: {
    table: "nodes_version",
    columns: ["id", "task_id", "v", "commit_hash", "verdict", "summary", "created_at"],
    booleans: [],
  },
};

const REL_ENDPOINTS: Record<string, readonly [string, string]> = {
  KILL_EDGE: ["Claim", "Claim"],
  STAGE_DEPENDS_ON: ["Stage", "Stage"],
  CONTAINS: ["Stage", "Claim"],
  EVIDENCE_FOR: ["Evidence", "Claim"],
  ARTIFACT_FOR: ["Artifact", "Claim"],
  FORKED_FROM: ["VersionNode", "VersionNode"],
};

const DDL = `
CREATE TABLE IF NOT EXISTS nodes_claim (
    id TEXT PRIMARY KEY, text TEXT NOT NULL, source TEXT NOT NULL, weight TEXT NOT NULL,
    posterior REAL NOT NULL, verify_tier TEXT NOT NULL, stale INTEGER NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS nodes_stage (
    id TEXT PRIMARY KEY, title TEXT NOT NULL, status TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS nodes_evidence (
    id TEXT PRIMARY KEY, digest TEXT NOT NULL, origin TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS nodes_artifact (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, digest TEXT NOT NULL,
    deleted INTEGER NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS nodes_version (
    id TEXT PRIMARY KEY, task_id TEXT NOT NULL, v INTEGER NOT NULL, commit_hash TEXT NOT NULL,
    verdict TEXT NOT NULL, summary TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS edges (
    rel TEXT NOT NULL, src TEXT NOT NULL, dst TEXT NOT NULL,
    PRIMARY KEY (rel, src, dst)
);
`;

interface PendingEdge {
  rel: string;
  sourceId: string;
  targetId: string;
}

export class GraphStore implements GraphProjection {
  private database: Database.Database | null = null;
  /** pending edges keyed by each missing endpoint: `${table}:${id}` → edges waiting on it */
  private pendingEdges = new Map<string, PendingEdge[]>();

  constructor(readonly databasePath: string) {}

  async close(): Promise<void> {
    this.database?.close();
    this.database = null;
  }

  async applyEvent(record: Row): Promise<void> {
    const eventType = record.event_type as string | undefined;
    const payload = validateGraphEvent(eventType, record.payload);
    const handler = HANDLERS[eventType as GraphEventType];
    await handler(this, payload, String(record.created_at ?? ""));
  }

  async rebuild(records: Iterable<Row>): Promise<Snapshot> {
    const db = this.connect();
    const wipe = db.transaction(() => {
      for (const spec of Object.values(NODE_SPECS)) {
        db.prepare(`DELETE FROM ${spec.table}`).run();
      }
      db.prepare("DELETE FROM edges").run();
    });
    wipe();
    this.pendingEdges.clear();
    for (const record of records) {
      await this.applyEvent(record);
    }
    return this.snapshotState();
  }

  async snapshotState(): Promise<Snapshot> {
    const state: Record<string, unknown> = {};
    for (const [table, spec] of Object.entries(NODE_SPECS)) {
      const rows = this.connect()
        .prepare(`SELECT * FROM ${spec.table} ORDER BY id`)
        .all() as Array<Record<string, unknown>>;
      state[table] = Object.fromEntries(
        rows.map((row) => [
          row.id,
          Object.fromEntries(
            Object.entries(row).map(([column, value]) => [
              column,
              spec.booleans.includes(column) ? Boolean(value) : value,
            ]),
          ),
        ]),
      );
    }
    const edges = this.connect()
      .prepare("SELECT rel, src, dst FROM edges ORDER BY rel, src, dst")
      .all() as Array<{ rel: string; src: string; dst: string }>;
    for (const rel of Object.keys(REL_ENDPOINTS)) {
      state[rel] = edges.filter((edge) => edge.rel === rel).map((edge) => [edge.src, edge.dst]);
    }
    return state;
  }

  async counts(): Promise<Record<string, number>> {
    const counts: Record<string, number> = {};
    for (const [table, spec] of Object.entries(NODE_SPECS)) {
      counts[table] =
        (this.connect().prepare(`SELECT count(*) AS n FROM ${spec.table}`).get() as { n: number }).n;
    }
    const edgeRows = this.connect()
      .prepare("SELECT rel, count(*) AS n FROM edges GROUP BY rel")
      .all() as Array<{ rel: string; n: number }>;
    const byRel = new Map(edgeRows.map((row) => [row.rel, row.n]));
    for (const rel of Object.keys(REL_ENDPOINTS)) {
      counts[rel] = byRel.get(rel) ?? 0;
    }
    return counts;
  }

  async forkParent(versionId: string): Promise<string | null> {
    // edges run child -> parent (FORKED_FROM): the parent sits in `dst`
    const row = this.connect()
      .prepare("SELECT dst FROM edges WHERE rel = 'FORKED_FROM' AND src = ?")
      .get(versionId) as { dst: string } | undefined;
    return row?.dst ?? null;
  }

  async forkChildren(versionId: string): Promise<string[]> {
    const rows = this.connect()
      .prepare("SELECT src FROM edges WHERE rel = 'FORKED_FROM' AND dst = ? ORDER BY src")
      .all(versionId) as Array<{ src: string }>;
    return rows.map((row) => row.src);
  }

  // ------------------------------------------------------- projection operations
  // The strategy registry below calls these; they are the projection's own grammar.

  upsertNode(table: string, columns: readonly string[], values: Row): void {
    const spec = NODE_SPECS[table];
    if (spec === undefined) {
      throw new GraphEventError(`unknown node table: ${table}`);
    }
    const assignments = columns
      .filter((column) => column !== "id")
      .map((column) => `${column} = excluded.${column}`)
      .join(", ");
    this.connect()
      .prepare(
        `INSERT INTO ${spec.table} (${columns.join(", ")}) VALUES (${columns.map(() => "?").join(", ")}) `
        + `ON CONFLICT(id) DO UPDATE SET ${assignments}`,
      )
      // better-sqlite3 binds numbers/strings/bigints/buffers/null — booleans go in as 0/1
      .run(...columns.map((column) => (typeof values[column] === "boolean" ? (values[column] ? 1 : 0) : values[column])));
    this.materializePending(`${table}:${String(values.id)}`);
  }

  ensureEdge(rel: string, sourceId: string, targetId: string): void {
    const [sourceTable, targetTable] = REL_ENDPOINTS[rel]!;
    const entry: PendingEdge = { rel, sourceId, targetId };
    let ready = true;
    if (!this.nodeExists(sourceTable, sourceId)) {
      this.enqueuePending(`${sourceTable}:${sourceId}`, entry);
      ready = false;
    }
    if (!this.nodeExists(targetTable, targetId)) {
      this.enqueuePending(`${targetTable}:${targetId}`, entry);
      ready = false;
    }
    if (ready) {
      this.createEdge(rel, sourceId, targetId);
    }
  }

  // ------------------------------------------------------------------ internal

  private enqueuePending(key: string, entry: PendingEdge): void {
    const bucket = this.pendingEdges.get(key) ?? [];
    if (!bucket.some((candidate) => sameEdge(candidate, entry))) {
      bucket.push(entry);
      this.pendingEdges.set(key, bucket);
    }
  }

  private materializePending(key: string): void {
    const bucket = this.pendingEdges.get(key);
    if (bucket === undefined) {
      return;
    }
    this.pendingEdges.delete(key);
    for (const entry of bucket) {
      // re-registers under the still-missing endpoint if the edge is not ready yet
      this.ensureEdge(entry.rel, entry.sourceId, entry.targetId);
    }
  }

  private createEdge(rel: string, sourceId: string, targetId: string): void {
    this.connect()
      .prepare("INSERT OR IGNORE INTO edges(rel, src, dst) VALUES(?, ?, ?)")
      .run(rel, sourceId, targetId);
  }

  private nodeExists(table: string, id: string): boolean {
    const spec = NODE_SPECS[table]!;
    return (
      (this.connect().prepare(`SELECT count(*) AS n FROM ${spec.table} WHERE id = ?`).get(id) as { n: number }).n > 0
    );
  }

  private connect(): Database.Database {
    if (this.database === null) {
      this.database = new Database(this.databasePath);
      this.database.pragma("journal_mode = WAL");
      this.database.exec(DDL);
    }
    return this.database;
  }
}

function sameEdge(a: PendingEdge, b: PendingEdge): boolean {
  return a.rel === b.rel && a.sourceId === b.sourceId && a.targetId === b.targetId;
}

type ProjectionHandler = (store: GraphStore, payload: Payload, createdAt: string) => void;

const node = (
  table: string,
  columns: readonly string[],
  pick: (payload: Payload) => Payload,
  stampKey = "updated_at",
): ProjectionHandler =>
  (store, payload, createdAt) => {
    store.upsertNode(table, columns, { ...pick(payload), [stampKey]: createdAt });
  };

const edge = (rel: string, sourceKey: string, targetKey: string): ProjectionHandler =>
  (store, payload) => {
    store.ensureEdge(rel, payload[sourceKey] as string, payload[targetKey] as string);
  };

/** Explicit strategy registry — compiler-enforced coverage of the vocabulary. */
const HANDLERS: Record<GraphEventType, ProjectionHandler> = {
  "claim.upsert": node("Claim", NODE_SPECS.Claim!.columns, (payload) => payload.claim as Payload),
  "claim.kill_edge": edge("KILL_EDGE", "claim_id", "kill_target_id"),
  "stage.upsert": node("Stage", NODE_SPECS.Stage!.columns, (payload) => payload.stage as Payload),
  "stage.depends_on": edge("STAGE_DEPENDS_ON", "stage_id", "depends_on_id"),
  "stage.contains": edge("CONTAINS", "stage_id", "claim_id"),
  "evidence.upsert": node("Evidence", NODE_SPECS.Evidence!.columns, (payload) => payload.evidence as Payload),
  "evidence.attach": edge("EVIDENCE_FOR", "evidence_id", "claim_id"),
  "artifact.upsert": node("Artifact", NODE_SPECS.Artifact!.columns, (payload) => payload.artifact as Payload),
  "artifact.link": edge("ARTIFACT_FOR", "artifact_id", "claim_id"),
  "version.commit": node(
    "VersionNode",
    NODE_SPECS.VersionNode!.columns,
    (payload) => {
      const version = { ...(payload.version as Payload) };
      // the version node's created_at comes from the event envelope stamp
      delete version.created_at;
      return version;
    },
    "created_at",
  ),
  "fork.edge": edge("FORKED_FROM", "child_version_id", "parent_version_id"),
};
