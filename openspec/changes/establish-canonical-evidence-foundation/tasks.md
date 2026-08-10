## 1. Contract and red tests

- [x] 1.1 Add focused failing tests for atomic artifact-plus-content publication,
  exact binding reads after restart, equal digest with distinct artifact
  payloads, stale revisions, and injected pre-commit rollback.
- [x] 1.2 Add a failing test proving tampered or unavailable CAS content cannot
  create an artifact, content binding, event, or run-revision increment.

## 2. Atomic ledger primitive

- [x] 2.1 Refactor content registration into a transaction-local helper and add
  exact artifact and bound-content read helpers with integrity checks.
- [x] 2.2 Implement `append_artifact_with_content` with CAS verification,
  optimistic revision checks, artifact/parent/event writes, exact content
  binding, and one transaction boundary.
- [x] 2.3 Preserve the existing registration and binding APIs without changing
  their legacy behavior.

## 3. Canonical evidence identity

- [x] 3.1 Add red tests for canonical artifact serialization, exact
  `ArtifactRef` anchors, explicit legacy compatibility, restart, and equal
  bytes with distinct provenance.
- [x] 3.2 Add canonical `EvidenceArtifact`/`EvidenceAnchor` payloads and an
  `EvidenceRepository` using the atomic ledger primitive.
- [x] 3.3 Update the canonical anchor schema and example registry.

## 4. Verification and handoff

- [x] 4.1 Run focused ledger/content and canonical-evidence tests plus the
  relevant SQLite regression
  suite from this clean worktree.
- [x] 4.2 Run strict OpenSpec validation and the repository delivery workflow
  checks for issue #111.
- [x] 4.3 Commit the OpenSpec, tests, and implementation in small logical
  commits, then push only `feat/issue-111-ledger-binding` to origin.
