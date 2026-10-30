# ledger-surface-ts

## Why

Issue #547 (T0 row 2), rt-core TypeScript implementation. The claim ledger is the heart of rt (一切裁决由机械规则在账本上计算); v2 promotes it to product surface. Spec source: the superseded Python W2 implementation (schema, field sets, error naming carried verbatim; issue #547 amendment records the language ruling).

## What changes

- `LedgerStore` migration **v2** (additive): six tables keyed `(task_id, <id>)` — claims (posterior/verify_tier/kill_edges/incentive_flag/deleted_at soft delete), sources, hypotheses, directions, experiments, decompositions.
- Table-driven surface specs (`src/ledger/schema.ts`, the EVENT_SPECS pattern): declarative field contracts, generic validation engine, every violation named by field; closed vocabularies (statuses/tiers/weights) shared with the event stream.
- CRUD on `LedgerStore` (upsert/get/list per table + claims soft delete; created_at stable, updated_at refreshes; JSON columns canonical).
- `EngineCore.upsertClaim` dual-write: ledger row + `claim.upsert` event + one `claim.kill_edge` per edge (CRUD never bypasses the #546 seam). Forward-referenced kill edges stay deferred by the projection's pending queue (#546 semantics).

## impact_scope

- `rt-core/src/ledger/schema.ts` (new), `rt-core/src/store/ledger.ts` (migration v2 + CRUD), `rt-core/src/store/engine.ts` (upsertClaim), `rt-core/src/store/integrity.ts` (new shared error module)
- tests: `rt-core/test/{ledger,claims}.test.ts`
- openspec change files
