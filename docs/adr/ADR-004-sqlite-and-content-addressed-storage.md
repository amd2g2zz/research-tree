# ADR-004: SQLite and Content-Addressed Storage

Status: Accepted

## Context

Filesystem and host-specific state can diverge after concurrent writes or
interruption. Large source snapshots, binaries, images, and experiment output
should not lengthen SQLite transactions.

## Decision

Use one workspace-scoped SQLite RunLedger with foreign keys, WAL, full
synchronization, busy timeout, immutable revisions, canonical events, and
expected-revision checks. Store large bytes in SHA-256 content-addressed
storage and bind digest, size, media type, locator, and availability metadata
in SQLite.

## Consequences

Canonical rows are transactional and restartable. Content is staged, fsynced,
digest-verified, and quarantined when it has no ledger registration; an orphan
cannot become evidence merely because bytes exist on disk.

## Rejected Alternatives

- Filesystem JSON as final authority: cross-file atomicity is not reliable.
- Store large blobs in SQLite: lock duration and database churn increase.
- A graph database: local artifact-centric transactions do not require one.

## Migration

Alpha1 RunStore rounds are imported idempotently as `legacy_unverified` history.
Compatibility readers remain available until recovery and rollback gates pass.
