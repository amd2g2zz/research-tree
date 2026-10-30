# version-fork-storage

## Why

Issue #548 (T0 row 3, docs 00 §2/§3 + 01 A7): git semantics for the research tree — 草稿可变提交不可变，分叉即继承. Version/fork is new (新旧映射: A7 快照/提交/fork_edge 新算法件).

## What changes

- `LedgerStore` migration **v3** (additive): versions (task_id+v PK, commit_hash UNIQUE per task, parent_v, verdict, summary, snapshot_json), fork_edges (from_task/from_v/to_task), drafts (task_id PK, working_set, base_v).
- `src/versions/store.ts`: VersionStore —
  - **drafts**: the only writable state (openDraft/mutateDraft/draftOf; no hash, never tracked);
  - **freeze()**: the ONLY draft→version channel (fail-closed) — hash = sha256(canonical(snapshot)) over the whole working set (要素集‖账本‖证据‖报告‖deleted_nodes — partial commits do not exist); identical content rejected (nothing to commit); verdict on the closed A6 vocabulary;
  - **append-only**: v per-task monotonic (insertVersion rejects skips); no update path; `verifyIntegrity` re-hashes all snapshots (raw-SQL tampering detected);
  - **fork(v) → new task**: v0 = shallow copy of the source snapshot (分叉即继承 — per-task hash uniqueness makes identical fork copies legal) + lineage edge; forkParent/forkChildren bidirectional;
  - copy-on-write: openDraftFromVersion seeds a draft from a committed snapshot; deleted_nodes ride the snapshot (产物删除 auditable).
- Graph lineage: fork.edge/version.commit events land with #551's state-machine wiring (documented seam).

## impact_scope

- `rt-core/src/versions/store.ts` (new), `rt-core/src/store/ledger.ts` (migration v3 + connection accessor)
- tests: `rt-core/test/versions.test.ts`
