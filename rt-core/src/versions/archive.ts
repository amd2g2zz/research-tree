/** Four-state archival (issue #573, charter §3, docs 01 A6).

All four verdicts are successes, attached to **versions**:
- **GO** → 底稿 handoff (deliverable pointer from the frozen report);
- **NO-GO** → graveyard: why it was abandoned + revival conditions, browsable;
  **revival = fork from the graveyard version** (分叉即继承);
- **PARK** → frozen brief + **mandatory revival conditions** — a PARK without
  revival conditions is a defect (product red line, pinned rejection);
- **REFRAMED** → the new task **inherits the ledger** (fork semantics via the
  state machine, lineage edge recorded) with a user-confirmed delta report.

Entries persist in the v6 `archive_entries` table, keyed (task_id, v).
*/

import type { LedgerStore } from "../store/ledger.js";
import type { VersionStore, CommittedVersion } from "./store.js";
import type { ProductStateMachine } from "../state/machine.js";

export type ArchiveDisposition =
  | { kind: "deliverable"; report: Record<string, unknown> }
  | { kind: "graveyard"; reason: string; revival_conditions: string[] }
  | { kind: "frozen-brief"; brief: string; revival_conditions: string[] }
  | { kind: "inherited"; delta_report: string; inherited_to: string };

export interface ArchiveEntry {
  task_id: string;
  v: number;
  verdict: string;
  disposition: ArchiveDisposition;
  revived_to?: string;
  created_at: string;
}

export class ArchiveError extends Error {}

export interface ArchivePayload {
  reason?: string;
  revival_conditions?: string[];
  brief?: string;
  delta_report?: string;
  new_task_id?: string;
}

interface ArchiveRow {
  task_id: string;
  v: number;
  verdict: string;
  entry_json: string;
  created_at: string;
}

export class FourStateArchive {
  constructor(
    private readonly ledger: LedgerStore,
    private readonly versions: VersionStore,
    private readonly machine: ProductStateMachine,
  ) {}

  /** Archive a committed version by its verdict. Disposition payloads are
   * validated per state — NO-GO/PARK revival conditions are mandatory. */
  archive(
    taskId: string,
    v: number,
    payload: ArchivePayload = {},
  ): ArchiveEntry {
    const committed = this.versions.getVersion(taskId, v);
    if (committed === null) {
      throw new ArchiveError(`nothing to archive: ${taskId}@v${v} is not a committed version`);
    }
    const disposition = this.dispositionFor(committed, payload);
    const entry: ArchiveEntry = {
      task_id: taskId,
      v,
      verdict: committed.verdict,
      disposition,
      created_at: new Date().toISOString(),
    };
    this.ledger.connection
      .prepare(
        "INSERT OR REPLACE INTO archive_entries (task_id, v, verdict, entry_json, created_at) VALUES (?, ?, ?, ?, ?)",
      )
      .run(taskId, v, committed.verdict, JSON.stringify({ disposition, revived_to: entry.revived_to ?? null }), entry.created_at);
    return entry;
  }

  /** Graveyard: browsable NO-GO entries (why abandoned + revival conditions). */
  graveyard(): Array<ArchiveEntry & { disposition: { kind: "graveyard"; reason: string; revival_conditions: string[] } }> {
    return this.list().filter(
      (entry): entry is ArchiveEntry & { disposition: { kind: "graveyard"; reason: string; revival_conditions: string[] } } =>
        entry.disposition.kind === "graveyard",
    );
  }

  entry(taskId: string, v: number): ArchiveEntry | null {
    const row = this.ledger.connection
      .prepare("SELECT * FROM archive_entries WHERE task_id = ? AND v = ? LIMIT 1")
      .get(taskId, v) as ArchiveRow | undefined;
    return row !== undefined ? this.toEntry(row) : null;
  }

  list(): ArchiveEntry[] {
    const rows = this.ledger.connection
      .prepare("SELECT * FROM archive_entries ORDER BY created_at")
      .all() as ArchiveRow[];
    return rows.map((row) => this.toEntry(row));
  }

  /** Revival = fork from the graveyard version (分叉即继承): the new task
   * inherits the snapshot and the graveyard entry records the revival. */
  revive(taskId: string, v: number, newTaskId: string): CommittedVersion {
    const entry = this.entry(taskId, v);
    if (entry === null || entry.disposition.kind !== "graveyard") {
      throw new ArchiveError(`revival requires a graveyard entry: ${taskId}@v${v}`);
    }
    const committed = this.machine.forkTask({ fromTask: taskId, fromV: v, toTask: newTaskId }) as unknown as CommittedVersion;
    this.ledger.connection
      .prepare("UPDATE archive_entries SET entry_json = ? WHERE task_id = ? AND v = ?")
      .run(JSON.stringify({ disposition: entry.disposition, revived_to: newTaskId }), taskId, v);
    return committed;
  }

  private dispositionFor(committed: CommittedVersion, payload: ArchivePayload): ArchiveDisposition {
    const revival = payload.revival_conditions ?? [];
    const requireRevival = (): string[] => {
      if (revival.length === 0) {
        throw new ArchiveError(`${committed.verdict} requires non-empty revival conditions (PARK/NO-GO 必须带复活条件)`);
      }
      return revival;
    };
    switch (committed.verdict) {
      case "GO":
        return { kind: "deliverable", report: committed.snapshot.report ?? {} };
      case "NO-GO":
        return { kind: "graveyard", reason: payload.reason ?? committed.summary, revival_conditions: requireRevival() };
      case "PARK":
        if (payload.brief === undefined || payload.brief.length === 0) {
          throw new ArchiveError("PARK requires a frozen brief");
        }
        return { kind: "frozen-brief", brief: payload.brief, revival_conditions: requireRevival() };
      case "REFRAMED": {
        if (payload.new_task_id === undefined || payload.new_task_id.length === 0) {
          throw new ArchiveError("REFRAMED requires the inheriting task id");
        }
        if (payload.delta_report === undefined || payload.delta_report.length === 0) {
          throw new ArchiveError("REFRAMED requires a user-confirmed delta report");
        }
        this.machine.forkTask({ fromTask: committed.task_id, fromV: committed.v, toTask: payload.new_task_id });
        return { kind: "inherited", delta_report: payload.delta_report, inherited_to: payload.new_task_id };
      }
      default:
        throw new ArchiveError(`unknown verdict: ${committed.verdict}`);
    }
  }

  private toEntry(row: ArchiveRow): ArchiveEntry {
    const parsed = JSON.parse(row.entry_json) as { disposition: ArchiveDisposition; revived_to: string | null };
    return {
      task_id: row.task_id,
      v: row.v,
      verdict: row.verdict,
      disposition: parsed.disposition,
      revived_to: parsed.revived_to ?? undefined,
      created_at: row.created_at,
    };
  }
}
