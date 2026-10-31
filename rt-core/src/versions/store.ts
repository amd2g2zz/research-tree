/** Version/fork/draft storage — git semantics for the research tree (issue #548).

docs/product/00 §2 step 3 + 01 A7: 草稿可变，提交不可变；分叉即继承.

- **Drafts** are the only writable working state (no hash, never tracked).
- **`freeze` is the only draft→version channel** (fail-closed): it snapshots
  the whole draft working set — hash = sha256(canonical(snapshot)), partial
  commits do not exist — and appends a version row. Identical content
  (identical hash) is rejected: nothing to commit.
- **Versions are append-only**: v is per-task monotonic; committed rows carry
  no update path, and `verifyIntegrity` re-hashes every snapshot so raw-SQL
  tampering is detected (research history is never silently rewritten).
- **fork(v) → new task**: the child's v0 is a shallow copy of the source
  snapshot plus a fork edge; lineage is queryable in both directions
  (also materialized in the graph via `fork.edge` events — engine wiring).
- **deleted_nodes ride the snapshot** and are disclosed by reports
  (产物删除 is auditable, never silent).
*/

import { createHash } from "node:crypto";

import type { LedgerStore } from "../store/ledger.js";
import { LedgerIntegrityError } from "../store/integrity.js";
import { canonicalJsonBytes } from "../events/canonical.js";
import { VERDICTS } from "../events/schema.js";

export interface VersionSnapshot {
  elements?: Record<string, unknown> | null;
  claims?: Array<Record<string, unknown>>;
  evidence_refs?: string[];
  report?: Record<string, unknown> | null;
  deleted_nodes?: string[];
  [key: string]: unknown;
}

export interface CommittedVersion {
  task_id: string;
  v: number;
  commit_hash: string;
  parent_v: number | null;
  verdict: string;
  summary: string;
  snapshot: VersionSnapshot;
  created_at: string;
}

export interface DraftState {
  task_id: string;
  snapshot: VersionSnapshot;
  base_v: number | null;
  updated_at: string;
}

const DDL = `
CREATE TABLE IF NOT EXISTS versions (
    task_id TEXT NOT NULL,
    v INTEGER NOT NULL CHECK (v >= 0),
    commit_hash TEXT NOT NULL UNIQUE,
    parent_v INTEGER,
    verdict TEXT NOT NULL,
    summary TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (task_id, v)
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
`;

function snapshotHash(snapshot: VersionSnapshot): string {
  return createHash("sha256").update(canonicalJsonBytes(snapshot as never)).digest("hex");
}

export class VersionStore {
  constructor(private readonly ledger: LedgerStore) {}

  // ------------------------------------------------------------ drafts (mutable)

  openDraft(taskId: string, init: { snapshot: VersionSnapshot; baseV: number | null }): void {
    const db = this.connect();
    const now = new Date().toISOString();
    const write = db.transaction(() => {
      db.prepare(
        "INSERT INTO drafts(task_id, working_set_json, base_v, updated_at) VALUES(?, ?, ?, ?) "
        + "ON CONFLICT(task_id) DO UPDATE SET working_set_json = excluded.working_set_json, "
        + "base_v = excluded.base_v, updated_at = excluded.updated_at",
      ).run(taskId, canonicalJsonBytes(init.snapshot as never), init.baseV, now);
    });
    write();
  }

  /** Copy-on-write: a new draft seeded from a committed snapshot. */
  openDraftFromVersion(taskId: string, v: number): void {
    const version = this.getVersion(taskId, v);
    if (version === null) {
      throw new LedgerIntegrityError(`cannot open draft: version does not exist: ${taskId}@v${v}`);
    }
    this.openDraft(taskId, { snapshot: version.snapshot, baseV: v });
  }

  mutateDraft(taskId: string, mutate: (draft: DraftState) => void): void {
    const draft = this.draftOf(taskId);
    if (draft === null) {
      throw new LedgerIntegrityError(`no draft to mutate: ${taskId}`);
    }
    mutate(draft);
    const db = this.connect();
    db.prepare("UPDATE drafts SET working_set_json = ?, updated_at = ? WHERE task_id = ?").run(
      canonicalJsonBytes(draft.snapshot as never),
      new Date().toISOString(),
      taskId,
    );
  }

  draftOf(taskId: string): DraftState | null {
    const row = this.connect()
      .prepare("SELECT task_id, working_set_json, base_v, updated_at FROM drafts WHERE task_id = ?")
      .get(taskId) as { task_id: string; working_set_json: string; base_v: number | null; updated_at: string } | undefined;
    if (row === undefined) {
      return null;
    }
    return {
      task_id: row.task_id,
      snapshot: JSON.parse(String(row.working_set_json)) as VersionSnapshot,
      base_v: row.base_v,
      updated_at: row.updated_at,
    };
  }

  // ------------------------------------------------------------ freeze (sole channel)

  /** The ONLY draft→version channel (fail-closed). Hash covers the whole
   * snapshot — partial commits do not exist; identical content is rejected. */
  freeze(taskId: string, commit: { verdict: string; summary: string }): CommittedVersion {
    const draft = this.draftOf(taskId);
    if (draft === null) {
      throw new LedgerIntegrityError(`freeze refused: no draft for ${taskId}`);
    }
    if (!(VERDICTS as readonly string[]).includes(commit.verdict)) {
      throw new LedgerIntegrityError(`field "verdict" must be one of ${JSON.stringify(VERDICTS)}`);
    }
    if (typeof commit.summary !== "string" || commit.summary === "") {
      throw new LedgerIntegrityError('field "summary" must be a non-empty string');
    }
    const commitHash = snapshotHash(draft.snapshot);
    if (this.findByHash(taskId, commitHash)) {
      throw new LedgerIntegrityError(`duplicate commit: identical snapshot already committed for ${taskId}`);
    }
    const committed = this.appendVersion(taskId, {
      v: this.nextV(taskId),
      snapshot: draft.snapshot,
      verdict: commit.verdict,
      summary: commit.summary,
      parentV: draft.base_v,
    });
    // freeze consumes the draft (草稿不可跟踪): the committed version is the
    // only remaining trackable state — no stale unfrozen row lingers.
    this.connect().prepare("DELETE FROM drafts WHERE task_id = ?").run(taskId);
    return committed;
  }

  /** Direct version insertion — the state machine's commit path (also the
   * only other writer; still append-only and hash-covered). */
  insertVersion(
    taskId: string,
    insert: { v: number; snapshot: VersionSnapshot; verdict: string; summary: string; parentV?: number | null },
  ): CommittedVersion {
    const latest = this.latestVersion(taskId);
    const expected = latest === null ? 0 : latest.v + 1;
    if (insert.v !== expected) {
      throw new LedgerIntegrityError(
        `append-only violation: expected v${expected} for ${taskId}, got v${insert.v}`,
      );
    }
    return this.appendVersion(taskId, {
      v: insert.v,
      snapshot: insert.snapshot,
      verdict: insert.verdict,
      summary: insert.summary,
      parentV: insert.parentV ?? null,
    });
  }

  // ------------------------------------------------------------ fork

  /** fork(v) → new task whose v0 is a shallow copy of the source snapshot,
   * with the lineage edge recorded. */
  fork(fork: { fromTask: string; fromV: number; toTask: string }): CommittedVersion {
    const source = this.getVersion(fork.fromTask, fork.fromV);
    if (source === null) {
      throw new LedgerIntegrityError(`fork refused: source version does not exist: ${fork.fromTask}@v${fork.fromV}`);
    }
    // fork v0 intentionally commits an identical snapshot under a new task
    // (分叉即继承) — the duplicate guard is per-task, not global.
    const committed = this.appendVersion(fork.toTask, {
      v: 0,
      snapshot: source.snapshot,
      verdict: source.verdict,
      summary: source.summary,
      parentV: null,
    });
    this.connect()
      .prepare("INSERT INTO fork_edges(from_task, from_v, to_task, created_at) VALUES(?, ?, ?, ?)")
      .run(fork.fromTask, fork.fromV, fork.toTask, new Date().toISOString());
    return committed;
  }

  forkParent(taskId: string): { task_id: string; v: number } | null {
    const row = this.connect()
      .prepare("SELECT from_task, from_v FROM fork_edges WHERE to_task = ?")
      .get(taskId) as { from_task: string; from_v: number } | undefined;
    return row ? { task_id: row.from_task, v: row.from_v } : null;
  }

  forkChildren(taskId: string, v: number): Array<{ task_id: string; v: number }> {
    const rows = this.connect()
      .prepare("SELECT to_task FROM fork_edges WHERE from_task = ? AND from_v = ? ORDER BY to_task")
      .all(taskId, v) as Array<{ to_task: string }>;
    return rows.map((row) => ({ task_id: row.to_task, v: 0 }));
  }

  // ------------------------------------------------------------ reads

  getVersion(taskId: string, v: number): CommittedVersion | null {
    const row = this.connect()
      .prepare("SELECT * FROM versions WHERE task_id = ? AND v = ?")
      .get(taskId, v) as Record<string, unknown> | undefined;
    return row === undefined ? null : this.rowToVersion(row);
  }

  latestVersion(taskId: string): CommittedVersion | null {
    const row = this.connect()
      .prepare("SELECT * FROM versions WHERE task_id = ? ORDER BY v DESC LIMIT 1")
      .get(taskId) as Record<string, unknown> | undefined;
    return row === undefined ? null : this.rowToVersion(row);
  }

  listVersions(taskId: string): CommittedVersion[] {
    const rows = this.connect()
      .prepare("SELECT * FROM versions WHERE task_id = ? ORDER BY v")
      .all(taskId) as Array<Record<string, unknown>>;
    return rows.map((row) => this.rowToVersion(row));
  }

  /** Tamper evidence: every committed snapshot must re-hash to its stored
   * commit_hash (raw-SQL edits are detected). */
  verifyIntegrity(): void {
    const rows = this.connect()
      .prepare("SELECT task_id, v, snapshot_json, commit_hash FROM versions ORDER BY task_id, v")
      .all() as Array<Record<string, unknown>>;
    for (const row of rows) {
      const snapshot = JSON.parse(String(row.snapshot_json)) as VersionSnapshot;
      if (snapshotHash(snapshot) !== row.commit_hash) {
        throw new LedgerIntegrityError(
          `version hash mismatch: ${row.task_id}@v${row.v} — committed history was modified`,
        );
      }
    }
  }

  // ------------------------------------------------------------ internal

  private appendVersion(
    taskId: string,
    insert: { v: number; snapshot: VersionSnapshot; verdict: string; summary: string; parentV: number | null },
  ): CommittedVersion {
    const commitHash = snapshotHash(insert.snapshot);
    const createdAt = new Date().toISOString();
    const db = this.connect();
    const write = db.transaction((): CommittedVersion => {
      db.prepare(
        "INSERT INTO versions(task_id, v, commit_hash, parent_v, verdict, summary, snapshot_json, created_at) "
        + "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
      ).run(
        taskId,
        insert.v,
        commitHash,
        insert.parentV,
        insert.verdict,
        insert.summary,
        canonicalJsonBytes(insert.snapshot as never),
        createdAt,
      );
      return {
        task_id: taskId,
        v: insert.v,
        commit_hash: commitHash,
        parent_v: insert.parentV,
        verdict: insert.verdict,
        summary: insert.summary,
        snapshot: insert.snapshot,
        created_at: createdAt,
      };
    });
    try {
      return write();
    } catch (error: unknown) {
      throw new LedgerIntegrityError(`version append violated a constraint: ${String(error)}`);
    }
  }

  private findByHash(taskId: string, commitHash: string): boolean {
    const row = this.connect()
      .prepare("SELECT 1 FROM versions WHERE task_id = ? AND commit_hash = ?")
      .get(taskId, commitHash);
    return row !== undefined;
  }

  private nextV(taskId: string): number {
    const latest = this.latestVersion(taskId);
    return latest === null ? 0 : latest.v + 1;
  }

  private rowToVersion(row: Record<string, unknown>): CommittedVersion {
    return {
      task_id: row.task_id as string,
      v: Number(row.v),
      commit_hash: row.commit_hash as string,
      parent_v: (row.parent_v as number | null) ?? null,
      verdict: row.verdict as string,
      summary: row.summary as string,
      snapshot: JSON.parse(String(row.snapshot_json)) as VersionSnapshot,
      created_at: row.created_at as string,
    };
  }

  private connect() {
    return this.ledger.connection;
  }
}
