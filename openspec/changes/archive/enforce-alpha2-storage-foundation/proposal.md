## Why

Alpha1 writes canonical research state into several filesystem and host-owned
stores. A crash, retry, or concurrent worker can leave those stores disagreeing
about the current revision, parent lineage, or active attempt. Alpha2 needs a
single durable ledger before evidence, coordinator, and host event work can
rely on state transitions.

The original #53 scope combines a full SQLite ledger, content-addressed blob
store, filesystem importer, replay tooling, and migration. Its prior draft was
1,716 lines, which exceeds the repository's one-PR review limit. This change
therefore delivers the narrow, independently useful ledger foundation. CAS and
legacy import remain explicit follow-on work rather than hidden scope.

## What Changes

- Add a workspace-scoped SQLite `RunLedger` with immutable runs, artifact
  revisions, parent references, and append-only events.
- Apply SQLite foreign keys, WAL, full synchronous mode, busy timeout, and
  optimistic expected-revision checks to every canonical write.
- Support deterministic reconstruction and idempotent event append semantics.
- Define a minimal storage protocol so a later coordinator can own writes while
  workers submit candidate data.
- Add crash-boundary and concurrent-reader/writer tests for the core ledger.
- **BREAKING** Alpha2 callers use the ledger as the canonical store; existing
  `RunStore` remains a read-only legacy source until its separate importer lands.

## Capabilities

### New Capabilities

- `durable-research-runtime`: Transactional SQLite storage for canonical run
  lineage, immutable revisions, events, and reconstruction.

### Modified Capabilities

None.

## Impact

- Adds focused runtime modules under `src/research_tree/` and contract tests
  under `tests/`.
- Does not migrate existing filesystem data, persist large blobs, alter host
  packages, or assign completion authority in this change.
- Unblocks evidence (#54) and the coordinator path; follow-on issues will add
  CAS and legacy import without widening this PR.
