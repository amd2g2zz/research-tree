## Why

Content registration, immutable artifact append, content binding, and lineage
event recording are currently separate operations. A failure between them can
leave an artifact that appears committed but has no authoritative content
binding. Alpha2 evidence persistence needs one durable primitive before a
later issue introduces typed evidence models or resolvers.

## What Changes

- Add one generic `RunLedger` operation that verifies a content-addressed
  object, appends an immutable artifact revision, binds that exact revision to
  the content object, records its lineage event, and advances the run revision
  in one SQLite transaction.
- Add exact artifact and content-binding read helpers needed to prove the
  committed state after a fresh ledger instance is opened.
- Preserve the existing separate registration and binding APIs for historical
  callers; this change does not migrate or reinterpret those rows.
- Add focused rollback, restart, stale-revision, and equal-bytes/different-
  artifact tests.

## Capabilities

### New Capabilities

- `atomic-ledger-content-binding`: atomically publishes one immutable artifact
  revision, its verified content metadata, exact binding, and event lineage.

### Modified Capabilities

- None.

## Impact

- `src/research_tree/run_ledger.py` gains a generic atomic publication API and
  exact read helpers.
- A focused SQLite ledger test module proves transaction boundaries and restart
  durability.
- No EvidenceAnchor, resolver, Finding Pack, delivery, readiness, registry, or
  legacy-data behavior changes in this issue.
