/** Version timeline + fork (issue #574, docs 03 P5 + 快照视图, docs 01 A7).

The P5 version page over the #548 version store:

- **Timeline**: vN / hash / verdict / summary, newest first; a draft row when
  one exists (草稿永远明确标注"未冻结·不可跟踪"); fork markers (⑂ 已分叉 →
  支线) from the fork_edges queries.
- **Main branch** = the task without a fork parent; the default projection is
  always the main line's latest version — switching branches/versions is an
  explicit (task_id, v) addressing action, never implicit.
- **Actions**: 继续研究 (version+1 draft from the latest committed version —
  resuming an existing draft takes precedence, never clobbers live work);
  从此分叉 → new task via the state machine (分叉即继承) → chat.
- **Read-only snapshot view**: frozen banner (vN · hash · verdict — committed
  versions never hint at modifiability; continue = version+1) + the frozen
  report projection. Immutability is mechanical: append-only rows + duplicate
  content rejected at freeze.
- **H7 telemetry**: version-continue / fork operations land as provider.action
  events (version-as-compounding hypothesis, charter §7).
*/

import type { LedgerStore } from "../store/ledger.js";
import type { VersionStore, CommittedVersion, VersionSnapshot } from "./store.js";
import type { ProductStateMachine } from "../state/machine.js";

export interface TimelineVersion {
  v: number;
  commit_hash: string;
  verdict: string;
  summary: string;
  forked: boolean;
  created_at: string;
}

export interface TimelineView {
  task_id: string;
  is_main_branch: boolean;
  versions: TimelineVersion[];
  /** draft row — 未冻结·不可跟踪 (unfrozen work is untrackable) */
  draft: { base_v: number | null; updated_at: string } | null;
  fork_parent: { task_id: string; v: number } | null;
}

export interface SnapshotView {
  banner: { v: number; commit_hash: string; verdict: string; summary: string };
  report: Record<string, unknown>;
  snapshot: VersionSnapshot;
}

export class VersionTimelineError extends Error {}

export class VersionTimeline {
  constructor(
    private readonly ledger: LedgerStore,
    private readonly versions: VersionStore,
    private readonly machine: ProductStateMachine,
  ) {}

  timeline(taskId: string): TimelineView {
    this.requireTask(taskId);
    const committed = this.versions.listVersions(taskId);
    return {
      task_id: taskId,
      is_main_branch: this.isMainBranch(taskId),
      versions: committed
        .slice()
        .sort((a, b) => b.v - a.v)
        .map((version) => ({
          v: version.v,
          commit_hash: version.commit_hash,
          verdict: version.verdict,
          summary: version.summary,
          forked: this.versions.forkChildren(taskId, version.v).length > 0,
          created_at: version.created_at,
        })),
      draft: this.draftRow(taskId),
      fork_parent: this.versions.forkParent(taskId),
    };
  }

  isMainBranch(taskId: string): boolean {
    return this.versions.forkParent(taskId) === null;
  }

  /** Default projection = the main line's latest version (A7 rule 5). An
   * explicit call — switching is always an explicit user action. */
  defaultProjection(fromTaskId: string): { task_id: string; v: number; verdict: string; commit_hash: string; summary: string } {
    this.requireTask(fromTaskId);
    let root = fromTaskId;
    for (;;) {
      const parent = this.versions.forkParent(root);
      if (parent === null) {
        break;
      }
      root = parent.task_id;
    }
    const latest = this.versions.listVersions(root).slice().sort((a, b) => b.v - a.v)[0];
    if (latest === undefined) {
      throw new VersionTimelineError(`main branch has no committed version: ${root}`);
    }
    return { task_id: root, v: latest.v, verdict: latest.verdict, commit_hash: latest.commit_hash, summary: latest.summary };
  }

  /** 继续研究 (version+1): open a copy-on-write draft from the latest
   * committed version. A live draft takes precedence — resuming never
   * clobbers unfrozen work (回研究草稿 over a mistaken +1). */
  continueResearch(taskId: string): void {
    this.requireTask(taskId);
    const existing = this.versions.draftOf(taskId);
    if (existing !== null) {
      this.telemetry("version-continue", `${taskId} (resumed draft @base v${existing.base_v ?? "null"})`);
      return;
    }
    const latest = this.versions.listVersions(taskId).slice().sort((a, b) => b.v - a.v)[0];
    if (latest === undefined) {
      throw new VersionTimelineError(`nothing to continue: no committed version for ${taskId}`);
    }
    this.versions.openDraftFromVersion(taskId, latest.v);
    this.telemetry("version-continue", `${taskId} opened draft from v${latest.v}`);
  }

  /** 从此分叉: new task inherits the snapshot (分叉即继承), lands in chat. */
  fork(taskId: string, v: number, newTaskId: string): CommittedVersion {
    this.requireTask(taskId);
    const committed = this.machine.forkTask({ fromTask: taskId, fromV: v, toTask: newTaskId }) as unknown as CommittedVersion;
    this.telemetry("fork", `${taskId}@v${v} → ${newTaskId}`);
    return committed;
  }

  /** Read-only snapshot view: frozen banner + full report projection. */
  snapshotView(taskId: string, v: number): SnapshotView {
    const version = this.versions.getVersion(taskId, v);
    if (version === null) {
      throw new VersionTimelineError(`no committed version: ${taskId}@v${v}`);
    }
    return {
      banner: { v: version.v, commit_hash: version.commit_hash, verdict: version.verdict, summary: version.summary },
      report: version.snapshot.report ?? {},
      snapshot: version.snapshot,
    };
  }

  private draftRow(taskId: string): TimelineView["draft"] {
    const draft = this.versions.draftOf(taskId);
    return draft !== null ? { base_v: draft.base_v, updated_at: draft.updated_at } : null;
  }

  /** H7 telemetry (charter §7): version-continue / fork operation events. */
  private telemetry(action: string, target: string): void {
    this.ledger.appendGraphEvent("provider.action", {
      id: `h7-${action}-${Date.now()}`,
      provider: "telemetry",
      action: "report",
      target: `${action}:${target}`,
      outcome: "ok",
    });
  }

  private requireTask(taskId: string): void {
    const born = this.ledger
      .graphEvents()
      .some(
        (event) => event.event_type === "task.transition" && (event.payload as Record<string, unknown>).task_id === taskId,
      );
    const hasVersions = this.versions.listVersions(taskId).length > 0;
    if (!born && !hasVersions) {
      throw new VersionTimelineError(`unknown task: ${taskId}`);
    }
  }
}
