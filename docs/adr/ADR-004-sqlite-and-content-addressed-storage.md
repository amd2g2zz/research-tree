# ADR-004: SQLite and Content-Addressed Storage

Status: Accepted

## Context

Filesystem and host-specific stores can disagree after concurrent writes or interruption.
Large source snapshots and binaries should not lengthen SQLite write transactions.

## Decision

Use one workspace-scoped SQLite RunLedger with foreign keys, WAL, full synchronization,
busy timeout, immutable revisions, canonical events, and expected-revision checks. Store
large bytes in a SHA-256 CAS and bind digest, size, media type, locator, and metadata in
SQLite.

## Consequences

Canonical writes are transactional and restartable. CAS staging and quarantine prevent an
uncommitted blob from becoming evidence. SQLite remains local rather than a graph service.

## Rejected Alternatives

- Filesystem JSON as final authority: cross-file atomicity is not reliable.
- Store large blobs in SQLite: lock duration and database churn increase.
- Dedicated graph database: local artifact-centric transactions do not require it.

## Migration

Alpha1 RunStore rounds are imported idempotently as unverified history. Compatibility reads
remain available until clean-checkout, recovery, and rollback gates pass.
