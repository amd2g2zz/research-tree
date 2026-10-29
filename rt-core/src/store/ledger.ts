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

export class LedgerIntegrityError extends Error {}

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
