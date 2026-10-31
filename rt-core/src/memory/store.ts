/** Simple auto memory (L5-adjacent, user request 2026-10-31).

Research compounds only if what a task learned survives the task. This is a
deliberately SMALL memory: the system writes typed entries automatically
during research (harvest), recalls them bounded and deterministically, and
never physically deletes — append-only like the rest of the ledger.

Product red lines honored mechanically:
- **溯源律** — every memory carries provenance (task/claim/quote/digest); an
  entry without provenance is a hallucination and is rejected.
- **永不按用户画像改变任何行为** — the kind set is closed
  (preference/lesson/source-baseline/outcome); a user-profile kind cannot
  exist. Memories are semantic facts, not persona models.
- **prior-only (L5)** — memory feeds alignment priors and source baselines,
  never policy; the closed kind set is the gate.
- **KV-cache-friendly** — recall is deterministic (same query → same order,
  same volume), bounded (limit + char budget), and lazy: the index carries
  text only, provenance detail loads on demand (#589 惰性披露 pattern).

Every write lands a provider.action audit event in the hash-chained log.
*/

import { createHash } from "node:crypto";

import type { LedgerStore } from "../store/ledger.js";
import type { VersionStore } from "../versions/store.js";

export const MEMORY_KINDS = ["preference", "lesson", "source-baseline", "outcome"] as const;
export type MemoryKind = (typeof MEMORY_KINDS)[number];

export type MemoryScope = "user" | `project:${string}` | `task:${string}`;

export interface MemoryProvenance {
  task_id?: string;
  claim_id?: string;
  quote?: string;
  digest?: string;
  [key: string]: unknown;
}

export interface RememberInput {
  memory_id?: string;
  scope: MemoryScope;
  kind: MemoryKind;
  text: string;
  provenance: MemoryProvenance;
}

export interface MemoryEntry {
  memory_id: string;
  scope: MemoryScope;
  kind: MemoryKind;
  text: string;
  status: "active" | "superseded";
  created_at: string;
  updated_at: string;
  /** present only via load() (lazy detail) */
  provenance?: MemoryProvenance;
  superseded_by?: string | null;
}

export interface RecallQuery {
  scope: MemoryScope;
  kinds?: MemoryKind[];
  limit?: number;
  /** caps the summed text length of the returned index */
  char_budget?: number;
}

export interface RecallResult {
  index: Array<{ memory_id: string; scope: MemoryScope; kind: MemoryKind; text: string; updated_at: string }>;
  total: number;
}

interface MemoryRow {
  memory_id: string;
  scope: string;
  kind: string;
  text: string;
  provenance_json: string;
  content_hash: string;
  status: string;
  superseded_by: string | null;
  created_at: string;
  updated_at: string;
}

export class MemoryError extends Error {}

function validScope(scope: string): boolean {
  return scope === "user" || /^project:.+$/.test(scope) || /^task:.+$/.test(scope);
}

/** user-scope memories apply everywhere; anything else matches exactly. */
function scopeMatches(rowScope: string, queryScope: string): boolean {
  return rowScope === queryScope || rowScope === "user";
}

export class AutoMemory {
  constructor(
    private readonly ledger: LedgerStore,
    private readonly versions: VersionStore,
  ) {}

  remember(input: RememberInput): MemoryEntry {
    if (!MEMORY_KINDS.includes(input.kind)) {
      throw new MemoryError(
        `memory kind must be one of the closed set (${MEMORY_KINDS.join(", ")}); user-profile kinds are excluded by product red line`,
      );
    }
    if (!validScope(input.scope)) {
      throw new MemoryError(`memory scope must be "user", "project:<id>" or "task:<id>": ${input.scope}`);
    }
    if (!input.provenance || Object.keys(input.provenance).length === 0) {
      // 溯源律: a memory without provenance is a hallucination
      throw new MemoryError("memory requires non-empty provenance (溯源律)");
    }
    const contentHash = createHash("sha256")
      .update(`${input.scope}|${input.kind}|${input.text.trim()}`)
      .digest("hex");
    const now = new Date().toISOString();
    const db = this.ledger.connection;

    const existing = db
      .prepare("SELECT memory_id FROM memories WHERE scope = ? AND kind = ? AND content_hash = ? AND status = 'active' LIMIT 1")
      .get(input.scope, input.kind, contentHash) as { memory_id: string } | undefined;
    if (existing !== undefined) {
      // idempotent: same content bumps recency in place, never duplicates
      db.prepare("UPDATE memories SET updated_at = ? WHERE memory_id = ?").run(now, existing.memory_id);
      return this.load(existing.memory_id)!;
    }

    const memoryId = input.memory_id ?? `mem-${contentHash.slice(0, 12)}`;
    const idCollision = db.prepare("SELECT status FROM memories WHERE memory_id = ? LIMIT 1").get(memoryId) as
      | { status: string }
      | undefined;
    if (idCollision !== undefined) {
      throw new MemoryError(`memory id already exists: ${memoryId}`);
    }
    db.prepare(
      "INSERT INTO memories (memory_id, scope, kind, text, provenance_json, content_hash, status, superseded_by, created_at, updated_at) "
        + "VALUES (?, ?, ?, ?, ?, ?, 'active', NULL, ?, ?)",
    ).run(memoryId, input.scope, input.kind, input.text, JSON.stringify(input.provenance), contentHash, now, now);
    this.audit("remember", `${memoryId} [${input.scope}/${input.kind}]`);
    return this.load(memoryId)!;
  }

  /** Bounded, deterministic recall: exact scope + the global user layer,
   * active entries only, newest first with id tiebreak, limit + char budget. */
  recall(query: RecallQuery): RecallResult {
    if (!validScope(query.scope)) {
      throw new MemoryError(`memory scope must be "user", "project:<id>" or "task:<id>": ${query.scope}`);
    }
    const kinds = query.kinds ?? [];
    const rows = (
      this.ledger.connection.prepare("SELECT * FROM memories WHERE status = 'active' ORDER BY updated_at DESC, memory_id").all() as MemoryRow[]
    ).filter((row) => scopeMatches(row.scope, query.scope) && (kinds.length === 0 || kinds.includes(row.kind as MemoryKind)));
    const limit = query.limit ?? 10;
    const index: RecallResult["index"] = [];
    let used = 0;
    for (const row of rows) {
      if (index.length >= limit) {
        break;
      }
      if (query.char_budget !== undefined && used + row.text.length > query.char_budget) {
        continue;
      }
      used += row.text.length;
      index.push({
        memory_id: row.memory_id,
        scope: row.scope as MemoryScope,
        kind: row.kind as MemoryKind,
        text: row.text,
        updated_at: row.updated_at,
      });
    }
    return { index, total: rows.length };
  }

  /** Lazy detail: provenance loads only here. */
  load(memoryId: string): MemoryEntry | null {
    const row = this.ledger.connection.prepare("SELECT * FROM memories WHERE memory_id = ? LIMIT 1").get(memoryId) as
      | MemoryRow
      | undefined;
    if (row === undefined) {
      return null;
    }
    return {
      memory_id: row.memory_id,
      scope: row.scope as MemoryScope,
      kind: row.kind as MemoryKind,
      text: row.text,
      status: row.status as "active" | "superseded",
      provenance: JSON.parse(row.provenance_json) as MemoryProvenance,
      superseded_by: row.superseded_by,
      created_at: row.created_at,
      updated_at: row.updated_at,
    };
  }

  /** Append-only: supersede, never delete. The reason goes to the audit. */
  forget(memoryId: string, reason: string): void {
    const row = this.ledger.connection.prepare("SELECT status FROM memories WHERE memory_id = ? LIMIT 1").get(memoryId) as
      | { status: string }
      | undefined;
    if (row === undefined) {
      throw new MemoryError(`unknown memory: ${memoryId}`);
    }
    this.ledger.connection
      .prepare("UPDATE memories SET status = 'superseded', updated_at = ? WHERE memory_id = ?")
      .run(new Date().toISOString(), memoryId);
    this.audit("forget", `${memoryId}: ${reason}`);
  }

  /** Mechanical auto-write from a finished task: refuted claims become
   * lessons, the committed verdict becomes an outcome. Idempotent via
   * content-hash dedupe — harvest twice, write once. */
  harvest(taskId: string, options: { project_scope?: string } = {}): void {
    const scope = (options.project_scope ?? `task:${taskId}`) as MemoryScope;
    for (const claim of this.ledger.listClaims(taskId)) {
      const posterior = Number(claim.posterior ?? 1);
      if (posterior <= 0.1) {
        this.remember({
          scope,
          kind: "lesson",
          text: String(claim.text),
          provenance: { task_id: taskId, claim_id: String(claim.claim_id), posterior },
        });
      }
    }
    const latest = this.versions.listVersions(taskId).slice().sort((a, b) => b.v - a.v)[0];
    if (latest !== undefined) {
      this.remember({
        scope,
        kind: "outcome",
        text: `${taskId}@v${latest.v} → ${latest.verdict} (${latest.summary})`,
        provenance: { task_id: taskId, v: latest.v, verdict: latest.verdict, commit_hash: latest.commit_hash },
      });
    }
  }

  private audit(action: string, target: string): void {
    this.ledger.appendGraphEvent("provider.action", {
      id: `memory-${action}-${Date.now()}`,
      provider: "auto-memory",
      action: "report",
      target: `memory:${action}:${target}`,
      outcome: "ok",
    });
  }
}
