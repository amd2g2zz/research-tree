## Why

`LegacyRunStoreImporter` still makes retired filesystem `RunStore` payloads a
source of canonical SQLite lineage. The current-only product policy removes
that compatibility authority instead of preserving imports, receipts, aliases,
or a migration path.

## What Changes

- **BREAKING**: Remove `LegacyRunStoreImporter`, its result and receipt types,
  and `src/research_tree/legacy_import.py`.
- **BREAKING**: Remove the `legacy_imports` SQLite DDL and the
  `RunLedger.record_import_receipt` and `RunLedger.get_import_receipt` APIs.
- Remove importer tests, root-package exports, active Alpha2 registry rows, and
  active umbrella documents that advertise legacy RunStore import, read,
  projection, or migration as a capability.
- Retire the obsolete group 13 / issue #65 migration slice, whose acceptance
  command names the deleted `tests/test_migration.py`.
- Register Alpha2 group 55 / issue #167 as a planned retirement slice with a
  source-bound acceptance command.

## Capabilities

### New Capabilities

- `legacy-runstore-import-removal`: Retire all published legacy RunStore import
  authority without a compatibility, migration, or replay path.

### Modified Capabilities

- `durable-research-runtime`: New SQLite ledgers no longer create legacy import
  receipt storage or expose receipt APIs.

## Impact

This affects `legacy_import.py`, `run_ledger.py`, the root package surface, the
dedicated importer tests, and active Alpha2 execution, verification, issue-map,
delivery, schema, task, design, and capability-spec artifacts. It does not
inspect, migrate, drop, or otherwise mutate user-owned filesystem or SQLite
data. Current canonical SQLite run, artifact, event, and content behavior stays
unchanged.
