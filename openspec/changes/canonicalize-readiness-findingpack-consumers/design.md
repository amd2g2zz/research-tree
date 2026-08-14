## Context

`CanonicalReadinessVerifier` already requires a `RunLedger`, matching
`EvidenceResolver`, and explicit revision on every write. #180 supplies
canonical Finding Pack and delivery fixture seams. The remaining consumers
must construct their prerequisite graph directly rather than migrate legacy
state into a second storage plane.

## Decisions

### Direct readiness fixture

Readiness tests will build delivery artifacts from the canonical fixture and
invoke `CanonicalReadinessVerifier` with the matching resolver and current
ledger revision. Helpers retain their existing return shape where external
tests consume them.

### Direct strict-evidence negative fixture

The strict-evidence test will append the one required legacy-unverified
artifact directly to a canonical ledger. It will preserve the explicit
negative check that `FindingPackCompiler(..., strict_evidence=True)` is
rejected, without importing a legacy fixture or copying a `RunStore` graph.

### Explicit retained legacy boundary

`tests/legacy_runstore_fixture.py` remains solely for assurance and exporter
coverage. This change neither changes that fixture nor declares that coverage
canonical.

## Risks and Mitigations

- Readiness helpers have broad test fan-out. Preserve their public test return
  shape, run focused tests first, then the full suite.
- Direct graph construction can drift. Reuse #180 canonical fixture helpers,
  explicit revisions, and static lineage checks.

## Migration

This is test-only. Revert the issue commit if necessary; do not restore a
RunStore-to-ledger bridge, runtime compatibility path, or weakened assertion.
