## Context

`RunLedger` already stores immutable artifact revisions, `content_objects`,
`artifact_contents`, and lineage events, but callers currently append an
artifact, register content, and bind content through separate transactions.
The content-addressed store owns byte publication and integrity checks. This
issue adds the SQLite publication boundary; it does not introduce evidence
domain objects.

## Goals / Non-Goals

**Goals:**

- Publish one artifact revision, verified content metadata, exact binding,
  event, and run-revision increment atomically.
- Preserve content-addressed byte verification before SQLite state becomes
  authoritative.
- Make the exact committed artifact and its binding readable after restart.
- Preserve distinct artifact identity when two captures use identical bytes.

**Non-Goals:**

- Define `EvidenceArtifact`, `EvidenceAnchor`, selectors, or resolver logic.
- Change existing legacy registration/binding APIs or migrate prior rows.
- Make filesystem publication and SQLite commit one cross-filesystem
  transaction. Unbound CAS objects remain non-authoritative.

## Decisions

### Verify bytes before the ledger transaction

The new `append_artifact_with_content` operation receives both a
`ContentAddressedStore` and a `ContentObject`. It reads the object before
opening the SQLite write transaction so digest, byte-size, locator, and
availability failures are rejected before canonical rows are visible. SQLite
then atomically publishes metadata and binding.

An alternative that trusts only a caller-supplied digest was rejected because
it cannot prove the bytes are still present and untampered at publication.

### Reuse generic artifact and content tables

The operation writes the existing `artifacts`, `artifact_parents`,
`content_objects`, `artifact_contents`, `events`, and `runs` tables. Its event
is `artifact-content-appended` and references the exact new `ArtifactRef`.
No evidence-specific table or payload schema is introduced; a later issue can
use kind `evidence-artifact` through this generic primitive.

An evidence-specific API was rejected because it would couple the durable
storage primitive to a model that is intentionally owned by a later issue.

### Use optimistic revision checks for both run and artifact identity

The operation requires the current run revision. It also accepts an optional
expected artifact revision for callers that need to prevent replacement of a
specific artifact identity. Both checks occur inside the same immediate SQLite
transaction before any authoritative row is inserted.

### Add exact read helpers

`get_artifact` and `get_bound_content` load one exact revision and validate its
identity or binding. They are intentionally narrow: selector, provenance, and
evidence-policy validation remain outside this issue.

## Risks / Trade-offs

- [Risk] CAS bytes can remain after a failed SQLite transaction. -> They are
  unbound and therefore non-authoritative; existing orphan recovery owns their
  cleanup.
- [Risk] A commit fault could leave partial rows. -> Use SQLite transaction
  rollback and test the existing `_before_commit` fault-injection seam.
- [Risk] Existing callers may continue using separate APIs. -> Retain those
  APIs unchanged; future canonical evidence callers use the new primitive.

## Migration Plan

1. Add failing tests for successful publication, rollback, restart, duplicate
   bytes with separate artifact identities, and stale revisions.
2. Implement the generic transaction and exact read helpers.
3. Run focused ledger/content tests, OpenSpec validation, and the relevant
   regression suite.

Rollback removes use of the new API. It does not delete any already committed
immutable ledger or CAS rows.

## Open Questions

- None for this storage primitive. Evidence-specific status, provenance, and
  selector policies are explicitly deferred to dependent issues.
