## Why

Content registration, immutable artifact append, content binding, and lineage
event recording were separate operations. A failure between them could leave
an artifact that appeared committed but had no authoritative content binding.
The old evidence model also identifies an anchor only by digest and revision,
which cannot distinguish equal bytes captured from different sources. Alpha2
needs one durable, typed evidence foundation before later resolver policy can
enforce strict closure.

## What Changes

- Add one generic `RunLedger` operation that verifies a content-addressed
  object, appends an immutable artifact revision, binds that exact revision to
  the content object, records its lineage event, and advances the run revision
  in one SQLite transaction.
- Add exact artifact and content-binding read helpers needed to prove the
  committed state after a fresh ledger instance is opened.
- Define canonical `EvidenceArtifact` serialization and a typed
  `EvidenceAnchor` carrying an exact `ArtifactRef`.
- Add an `EvidenceRepository` that publishes canonical evidence through the
  atomic ledger primitive and rejects implicit classes or CAS metadata drift.
- Preserve generic anchors only as explicit `legacy_unverified` compatibility
  data; they are never silently upgraded to canonical evidence.
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
- `src/research_tree/evidence.py` gains canonical evidence/anchor
  serialization and repository publication, but no resolution policy.
- A focused ledger test module and canonical-evidence test module prove
  transaction boundaries, restart durability, and provenance separation.
- Resolver, Finding Pack, Decision/Readiness, delivery, and registry behavior
  remain deferred.
