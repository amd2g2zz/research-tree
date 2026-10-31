/** Workspace SQLite ledger — the sole write authority (issue #546, rt-core TS).

Schema evolution runs through a versioned migration registry (`MIGRATIONS`):
`initialize()` applies pending migrations in order and records the version.
Schema v1 carries the hash-chained `graph_events` table (parity with the
superseded Python implementation's v8). The v2 ledger tables land with
issue #547 (schema v2 entry).
*/

import { mkdirSync } from "node:fs";
import { join } from "node:path";

import Database from "better-sqlite3";
import { createHash } from "node:crypto";

import { canonicalJsonBytes } from "../events/canonical.js";
import { GENESIS_HASH, validateGraphEvent } from "../events/schema.js";
import { SURFACE_SPECS, validateSurfacePayload } from "../ledger/schema.js";
import { LedgerIntegrityError } from "./integrity.js";
import type { EventLog, EventPayload } from "./ports.js";

export interface GraphEventRecord {
  seq: number;
  run_id: string | null;
  event_type: string;
  payload: EventPayload;
  prev_hash: string;
  content_hash: string;
  created_at: string;
  [key: string]: unknown;
}

export { LedgerIntegrityError } from "./integrity.js";
export { LedgerStore as LedgerStoreClass };

interface Migration {
  readonly version: number;
  readonly statements: string;
}

const MIGRATIONS: readonly Migration[] = [
  {
    version: 1,
    statements: `
      CREATE TABLE IF NOT EXISTS graph_events (
          seq INTEGER PRIMARY KEY AUTOINCREMENT,
          run_id TEXT,
          event_type TEXT NOT NULL,
          payload_json BLOB NOT NULL,
          prev_hash TEXT NOT NULL,
          content_hash TEXT NOT NULL,
          created_at TEXT NOT NULL
      );
    `,
  },
  {
    version: 2,
    statements: `
      CREATE TABLE IF NOT EXISTS claims (
          task_id TEXT NOT NULL,
          claim_id TEXT NOT NULL,
          text TEXT NOT NULL,
          source TEXT NOT NULL,
          weight TEXT NOT NULL,
          posterior REAL NOT NULL,
          verify_tier TEXT NOT NULL,
          kill_edges TEXT NOT NULL,
          incentive_flag INTEGER NOT NULL CHECK (incentive_flag IN (0, 1)),
          deleted_at TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          PRIMARY KEY (task_id, claim_id)
      );
      CREATE TABLE IF NOT EXISTS sources (
          task_id TEXT NOT NULL,
          source_id TEXT NOT NULL,
          origin TEXT NOT NULL,
          kind TEXT NOT NULL,
          reliability REAL NOT NULL,
          incentive_vector TEXT NOT NULL,
          astroturf_flag INTEGER NOT NULL CHECK (astroturf_flag IN (0, 1)),
          provenance TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          PRIMARY KEY (task_id, source_id)
      );
      CREATE TABLE IF NOT EXISTS hypotheses (
          task_id TEXT NOT NULL,
          hypothesis_id TEXT NOT NULL,
          text TEXT NOT NULL,
          status TEXT NOT NULL,
          review TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          PRIMARY KEY (task_id, hypothesis_id)
      );
      CREATE TABLE IF NOT EXISTS directions (
          task_id TEXT NOT NULL,
          direction_id TEXT NOT NULL,
          round INTEGER NOT NULL CHECK (round >= 0),
          value_posterior REAL NOT NULL,
          budget_allocation REAL NOT NULL,
          history TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          PRIMARY KEY (task_id, direction_id)
      );
      CREATE TABLE IF NOT EXISTS experiments (
          task_id TEXT NOT NULL,
          experiment_id TEXT NOT NULL,
          status TEXT NOT NULL,
          preregistration TEXT NOT NULL,
          stop_state TEXT,
          cost REAL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          PRIMARY KEY (task_id, experiment_id)
      );
      CREATE TABLE IF NOT EXISTS decompositions (
          task_id TEXT NOT NULL,
          decomposition_id TEXT NOT NULL,
          elements TEXT NOT NULL,
          checklist_state TEXT NOT NULL,
          status TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          PRIMARY KEY (task_id, decomposition_id)
      );
    `,
  },
  {
    version: 3,
    statements: `
      CREATE TABLE IF NOT EXISTS versions (
          task_id TEXT NOT NULL,
          v INTEGER NOT NULL CHECK (v >= 0),
          commit_hash TEXT NOT NULL,
          parent_v INTEGER,
          verdict TEXT NOT NULL,
          summary TEXT NOT NULL,
          snapshot_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY (task_id, v),
          UNIQUE (task_id, commit_hash)
      );
      CREATE TABLE IF NOT EXISTS fork_edges (
          from_task TEXT NOT NULL,
          from_v INTEGER NOT NULL,
          to_task TEXT NOT NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY (from_task, from_v, to_task)
      );
      CREATE TABLE IF NOT EXISTS drafts (
          task_id TEXT PRIMARY KEY,
          working_set_json TEXT NOT NULL,
          base_v INTEGER,
          updated_at TEXT NOT NULL
      );
    `,
  },
  {
    version: 4,
    statements: `
      CREATE TABLE IF NOT EXISTS parallel_stages (
          stage_id TEXT PRIMARY KEY,
          title TEXT NOT NULL,
          status TEXT NOT NULL,
          claim_ids TEXT NOT NULL,
          depends_on TEXT NOT NULL,
          assigned_worker_class TEXT NOT NULL,
          retries INTEGER NOT NULL,
          max_retries INTEGER NOT NULL,
          outputs TEXT NOT NULL
      );
    `,
  },
  {
    version: 5,
    statements: `
      CREATE TABLE IF NOT EXISTS projects (
          project_id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          description TEXT NOT NULL,
          status TEXT NOT NULL CHECK (status IN ('active', 'archived')),
          attachments TEXT NOT NULL,
          created_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS project_tasks (
          task_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          role TEXT NOT NULL CHECK (role IN ('main', 'fork')),
          created_at TEXT NOT NULL
      );
    `,
  },
  {
    version: 6,
    statements: `
      CREATE TABLE IF NOT EXISTS archive_entries (
          task_id TEXT NOT NULL,
          v INTEGER NOT NULL,
          verdict TEXT NOT NULL,
          entry_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY (task_id, v)
      );
    `,
  },
];

function chainHash(record: Record<string, unknown>): string {
  return createHash("sha256").update(canonicalJsonBytes(record as never)).digest("hex");
}

export class LedgerStore implements EventLog {
  readonly databasePath: string;
  private database: Database.Database | null = null;

  constructor(workspace: string) {
    this.databasePath = join(workspace, ".research-tree", "rt-core.sqlite3");
  }

  initialize(): void {
    mkdirSync(join(this.databasePath, ".."), { recursive: true });
    const db = this.connect();
    const applied = new Set(
      (db.prepare("SELECT version FROM schema_migrations").all() as Array<{ version: number }>).map(
        (row) => row.version,
      ),
    );
    for (const migration of MIGRATIONS) {
      if (applied.has(migration.version)) {
        continue;
      }
      db.transaction(() => {
        db.exec(migration.statements);
        db.prepare("INSERT INTO schema_migrations(version, applied_at) VALUES(?, datetime('now'))").run(
          migration.version,
        );
      })();
    }
  }

  appendGraphEvent(
    eventType: string,
    payload: EventPayload,
    options: { runId?: string | null } = {},
  ): GraphEventRecord {
    this.initialize();
    const normalized = validateGraphEvent(eventType, payload);
    const runId = options.runId ?? null;
    const createdAt = new Date().toISOString();
    const append = this.connect().transaction((): GraphEventRecord => {
      const tail = this.connect()
        .prepare("SELECT content_hash FROM graph_events ORDER BY seq DESC LIMIT 1")
        .get() as { content_hash: string } | undefined;
      const prevHash = tail?.content_hash ?? GENESIS_HASH;
      const chainRecord = {
        run_id: runId,
        event_type: eventType,
        payload: normalized,
        prev_hash: prevHash,
        created_at: createdAt,
      };
      const contentHash = chainHash(chainRecord);
      const info = this.connect()
        .prepare(
          "INSERT INTO graph_events(run_id, event_type, payload_json, prev_hash, content_hash, created_at) "
          + "VALUES(?, ?, ?, ?, ?, ?)",
        )
        .run(runId, eventType, canonicalJsonBytes(normalized as never), prevHash, contentHash, createdAt);
      return { seq: Number(info.lastInsertRowid), ...chainRecord, content_hash: contentHash };
    });
    return append();
  }

  graphEvents(sinceSeq = 0): GraphEventRecord[] {
    this.initialize();
    const rows = this.connect()
      .prepare(
        "SELECT seq, run_id, event_type, payload_json, prev_hash, content_hash, created_at "
        + "FROM graph_events WHERE seq > ? ORDER BY seq",
      )
      .all(sinceSeq) as Array<Record<string, unknown>>;
    return rows.map((row) => ({
      seq: Number(row.seq),
      run_id: (row.run_id as string | null) ?? null,
      event_type: row.event_type as string,
      payload: JSON.parse(String(row.payload_json)) as EventPayload,
      prev_hash: row.prev_hash as string,
      content_hash: row.content_hash as string,
      created_at: row.created_at as string,
    }));
  }

  verifyGraphChain(): void {
    this.initialize();
    const rows = this.connect()
      .prepare(
        "SELECT seq, run_id, event_type, payload_json, prev_hash, content_hash, created_at "
        + "FROM graph_events ORDER BY seq",
      )
      .all() as Array<Record<string, unknown>>;
    let previous = GENESIS_HASH;
    let expectedSeq = 1;
    for (const row of rows) {
      const seq = Number(row.seq);
      if (seq !== expectedSeq) {
        throw new LedgerIntegrityError(`graph event seq gap: expected ${expectedSeq}, found ${seq}`);
      }
      const record = {
        run_id: (row.run_id as string | null) ?? null,
        event_type: row.event_type,
        payload: JSON.parse(String(row.payload_json)),
        prev_hash: row.prev_hash,
        created_at: row.created_at,
      };
      if (row.prev_hash !== previous) {
        throw new LedgerIntegrityError(`graph event chain break at seq ${seq}`);
      }
      if (chainHash(record) !== row.content_hash) {
        throw new LedgerIntegrityError(`graph event hash mismatch at seq ${seq}`);
      }
      previous = row.content_hash as string;
      expectedSeq = seq + 1;
    }
  }

  // ------------------------------------------------- v2 ledger surface (issue #547)
  // Full-row state upserts (created_at stable, updated_at refreshes); claims
  // delete is soft — 产物删除 must stay auditable and land in version snapshots.

  upsertClaim(taskId: string, payload: Record<string, unknown>): Record<string, unknown> {
    return this.surfaceWrite("claims", taskId, payload);
  }

  getClaim(taskId: string, claimId: string): Record<string, unknown> | null {
    return this.surfaceGet("claims", taskId, claimId);
  }

  listClaims(taskId: string): Array<Record<string, unknown>> {
    return this.surfaceList("claims", taskId);
  }

  deleteClaim(taskId: string, claimId: string, deletedAt: string): Record<string, unknown> {
    this.initialize();
    const now = new Date().toISOString();
    const info = this.connect()
      .prepare("UPDATE claims SET deleted_at = ?, updated_at = ? WHERE task_id = ? AND claim_id = ?")
      .run(deletedAt, now, taskId, claimId);
    if (info.changes !== 1) {
      throw new LedgerIntegrityError(`claim does not exist: ${taskId}/${claimId}`);
    }
    return this.surfaceGet("claims", taskId, claimId)!;
  }

  upsertSource(taskId: string, payload: Record<string, unknown>): Record<string, unknown> {
    return this.surfaceWrite("sources", taskId, payload);
  }

  getSource(taskId: string, sourceId: string): Record<string, unknown> | null {
    return this.surfaceGet("sources", taskId, sourceId);
  }

  listSources(taskId: string): Array<Record<string, unknown>> {
    return this.surfaceList("sources", taskId);
  }

  upsertHypothesis(taskId: string, payload: Record<string, unknown>): Record<string, unknown> {
    return this.surfaceWrite("hypotheses", taskId, payload);
  }

  getHypothesis(taskId: string, hypothesisId: string): Record<string, unknown> | null {
    return this.surfaceGet("hypotheses", taskId, hypothesisId);
  }

  listHypotheses(taskId: string): Array<Record<string, unknown>> {
    return this.surfaceList("hypotheses", taskId);
  }

  upsertDirection(taskId: string, payload: Record<string, unknown>): Record<string, unknown> {
    return this.surfaceWrite("directions", taskId, payload);
  }

  getDirection(taskId: string, directionId: string): Record<string, unknown> | null {
    return this.surfaceGet("directions", taskId, directionId);
  }

  listDirections(taskId: string): Array<Record<string, unknown>> {
    return this.surfaceList("directions", taskId);
  }

  upsertExperiment(taskId: string, payload: Record<string, unknown>): Record<string, unknown> {
    return this.surfaceWrite("experiments", taskId, payload);
  }

  getExperiment(taskId: string, experimentId: string): Record<string, unknown> | null {
    return this.surfaceGet("experiments", taskId, experimentId);
  }

  listExperiments(taskId: string): Array<Record<string, unknown>> {
    return this.surfaceList("experiments", taskId);
  }

  upsertDecomposition(taskId: string, payload: Record<string, unknown>): Record<string, unknown> {
    return this.surfaceWrite("decompositions", taskId, payload);
  }

  getDecomposition(taskId: string, decompositionId: string): Record<string, unknown> | null {
    return this.surfaceGet("decompositions", taskId, decompositionId);
  }

  listDecompositions(taskId: string): Array<Record<string, unknown>> {
    return this.surfaceList("decompositions", taskId);
  }

  private surfaceWrite(
    table: string,
    taskId: string,
    payload: Record<string, unknown>,
  ): Record<string, unknown> {
    this.initialize();
    const spec = SURFACE_SPECS[table]!;
    const values = validateSurfacePayload(table, payload);
    const now = new Date().toISOString();
    const columns = ["task_id", ...Object.keys(values), "created_at", "updated_at"];
    const updateColumns = [...Object.keys(values), "updated_at"];
    const sql =
      `INSERT INTO ${table} (${columns.join(", ")}) VALUES (${columns.map(() => "?").join(", ")}) ` +
      `ON CONFLICT(task_id, ${spec.idColumn}) DO UPDATE SET ` +
      updateColumns.map((column) => `${column} = excluded.${column}`).join(", ");
    const jsonColumns = new Set(spec.json);
    const rowValues = [
      taskId,
      ...Object.keys(values).map((column) =>
        jsonColumns.has(column) && values[column] !== null
          ? canonicalJsonBytes(values[column] as never)
          : typeof values[column] === "boolean"
            ? values[column]
              ? 1
              : 0
            : values[column],
      ),
      now,
      now,
    ];
    const write = this.connect().transaction(() => {
      this.connect().prepare(sql).run(...rowValues);
    });
    try {
      write();
    } catch (error: unknown) {
      throw new LedgerIntegrityError(`${table} write violated a ledger constraint: ${String(error)}`);
    }
    return this.surfaceGet(table, taskId, String(values[spec.idColumn]))!;
  }

  private surfaceGet(table: string, taskId: string, rowId: string): Record<string, unknown> | null {
    const spec = SURFACE_SPECS[table]!;
    const row = this.connect()
      .prepare(`SELECT * FROM ${table} WHERE task_id = ? AND ${spec.idColumn} = ?`)
      .get(taskId, rowId) as Record<string, unknown> | undefined;
    if (row === undefined) {
      return null;
    }
    const record: Record<string, unknown> = { ...row };
    for (const column of spec.json) {
      if (record[column] !== null && record[column] !== undefined) {
        record[column] = JSON.parse(String(record[column]));
      }
    }
    for (const column of spec.booleans) {
      record[column] = Boolean(record[column]);
    }
    return record;
  }

  private surfaceList(table: string, taskId: string): Array<Record<string, unknown>> {
    const spec = SURFACE_SPECS[table]!;
    const rows = this.connect()
      .prepare(`SELECT * FROM ${table} WHERE task_id = ? ORDER BY ${spec.idColumn}`)
      .all(taskId) as Array<Record<string, unknown>>;
    return rows.map((row) => {
      const record: Record<string, unknown> = { ...row };
      for (const column of spec.json) {
        if (record[column] !== null && record[column] !== undefined) {
          record[column] = JSON.parse(String(record[column]));
        }
      }
      for (const column of spec.booleans) {
        record[column] = Boolean(record[column]);
      }
      return record;
    });
  }

  get connection(): Database.Database {
    this.connect();
    return this.database!;
  }

  private connect(): Database.Database {
    if (this.database === null) {
      this.database = new Database(this.databasePath);
      this.database.pragma("journal_mode = WAL");
      this.database.pragma("synchronous = FULL");
      this.database.pragma("foreign_keys = ON");
      this.database.exec(
        "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)",
      );
    }
    return this.database;
  }
}
