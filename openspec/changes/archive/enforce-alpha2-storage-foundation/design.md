## Context

`RunStore` serializes immutable artifacts and events into individual files;
`AlignmentGraphStore` separately uses SQLite. Neither is the canonical
cross-host run store. The existing domain types already validate identifiers,
timestamps, payloads, content hashes, and parent references. The ledger must
persist those semantics transactionally without changing their public JSON
representation.

## Goals / Non-Goals

**Goals:**

- One SQLite database per workspace at `.research-tree/run-ledger.sqlite3`.
- Immutable run, artifact, parent-edge, and event records.
- Atomic writes with expected run revision, event-id idempotency, durable
  SQLite settings, and reconstruction from the ledger alone.
- A narrow protocol that future coordinator code can depend on.

**Non-Goals:**

- CAS blobs, filesystem import, migration commands, leases, host events,
  evidence/oracle tables, or a coordinator lifecycle state machine.
- Replacing or deleting `RunStore` before a tested importer exists.
- Storing prompts, credentials, or provider diagnostics.

## Decisions

### Reuse existing domain values at the storage boundary

The public methods accept and return existing `RoundRecord`,
`ArtifactRevision`, `ArtifactRef`, and `LineageEvent` instances. SQLite stores
the canonical JSON payload and indexed identity fields. Reads reconstruct those
same values with their existing validators, so a corrupted payload, digest, or
lineage reference is rejected rather than normalized.

Alternative: define separate Alpha2 persistence models. Rejected because
parallel representations would make the legacy importer and future coordinator
conversion paths ambiguous.

### One transaction per canonical append

The ledger has `runs`, `artifacts`, `artifact_parents`, `events`, and
`schema_migrations`. Each canonical mutation begins `BEGIN IMMEDIATE`, verifies
the caller's expected run revision, inserts immutable rows, increments the run
revision, and commits. A failed write rolls back every row in the mutation.

`events` has a unique `(run_id, event_id)` key. Repeating the same event with
the same canonical payload returns the existing event; a payload mismatch is a
conflict. This permits at-least-once host delivery without accepting a forged
retry.

Alternative: append first and reconcile later. Rejected because a partial
append is an invalid canonical history.

### SQLite durability and concurrency settings are explicit

Every connection enables foreign keys, WAL journal mode, `synchronous=FULL`,
and a bounded busy timeout. Writes use `BEGIN IMMEDIATE`; readers use ordinary
read transactions. SQLite remains local and dependency-free while preserving
concurrent readers and one coordinated writer.

Alternative: a global database or graph database. Rejected because this is a
workspace-scoped transactional workload with no multi-machine requirement.

### Reconstruction validates, it does not merely query

`load_run` loads all artifacts and events in deterministic order, verifies
artifact content hashes through `ArtifactRevision.from_dict`, resolves every
parent reference, checks every event artifact reference, and returns a
`RoundSnapshot`. A dangling edge or corrupt row makes the run unreadable with a
storage-integrity error.

### Storage protocol is intentionally narrow

`RunLedgerProtocol` exposes create, append-artifact, append-event, and
load-run. It does not expose raw SQL or mutable rows. The coordinator is not
implemented here, but this boundary prevents workers from receiving general
database access later.

## Risks / Trade-offs

- [SQLite lock contention] -> bounded busy timeout plus deterministic
  `LedgerConflictError`; callers retry from a new snapshot.
- [Power failure during write] -> SQLite FULL synchronous transactions; tests
  inject failures before commit and assert prior committed state survives.
- [A legacy artifact contains unsupported data] -> retain `RunStore` unchanged
  and defer import disposition to the dedicated importer issue.
- [Schema evolution] -> record v1 in `schema_migrations`; reject unknown or
  partial schema states rather than applying implicit migrations.

## Migration Plan

1. Create an empty ledger lazily in a workspace without touching `RunStore`.
2. Add one new run through the ledger and verify reconstruction/replay tests.
3. Keep legacy filesystem state read-only until the import boundary is
   delivered in a follow-on issue.
4. Roll back by disabling the Alpha2 ledger entry point; committed databases
   remain audit evidence and are never silently deleted.

## Open Questions

The CAS locator schema and legacy closure disposition are deliberately deferred
to follow-on issues so this PR retains one persistence responsibility.
