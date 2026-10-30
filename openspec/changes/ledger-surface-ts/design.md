# design — ledger-surface-ts

## Schema (v2, additive)

Same DDL shape as the superseded Python implementation: all six tables keyed
`(task_id, <id>)`, `task_id TEXT NOT NULL` plain column (FK to #548's tasks
table deferred — SQLite cannot ALTER-add constraints; integrity enforced at
the store API), JSON columns canonical, booleans 0/1 (better-sqlite3 binds no
booleans).

## Validation

Table-driven specs (`SURFACE_SPECS`): kind-checked fields (nonEmpty/string/
enum/probability/integer/boolean), composite rules (killEdgeList: non-empty
list, no duplicates, never self), optional mappings (review/stop_state),
preregistration required non-empty. Errors are `LedgerIntegrityError` (the
canonical ledger boundary error, now shared via `store/integrity.js`).

## Dual-write seam

`EngineCore.upsertClaim`: ledger row → `claim.upsert` (row state, no `stale`
— owned by belief propagation) → `claim.kill_edge` × edges. The graph's
pending-edge queue defers edges whose endpoints are not yet registered.

## rejected_designs

- FK to tasks now (arrives with #548; ALTER cannot add constraints).
- Physical DELETE for claims (soft delete keeps 产物删除 auditable).
- Coordinator passthroughs for all six tables (only the claim round-trip is
  required; satellites wire in with their consumer issues).
- Emitting `stale` from claim upserts (belief propagation owns that flag).
