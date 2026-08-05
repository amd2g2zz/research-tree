# ADR-001: Run-Scoped Filesystem Runtime

Status: Superseded by [ADR-004](ADR-004-sqlite-and-content-addressed-storage.md)

## Context

The alpha1 runtime needed isolated, inspectable research rounds before the product's
cross-host and long-horizon coordination requirements were understood.

## Decision

Alpha1 used Python 3.11+, an explicit filesystem `RunStore`, versioned JSON artifact
envelopes, append-only lineage events, and a locked `uv` test environment.

## Consequences

The format remains readable for migration and audit. It is not a writable authority for
alpha2 lifecycle, closure, delivery, or completion state.

## Rejected Alternatives

- A global mutable state file could not isolate concurrent rounds.
- A server-first runtime added operations before the local product contract was stable.

## Migration

`LegacyRunStoreImporter` imports alpha1 artifacts as `legacy_unverified`. Alpha2 writes
canonical state only through the SQLite RunLedger selected by ADR-004.
