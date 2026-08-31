## Why

The Alpha2 Readiness boundary can now prove that a Finding Pack and Decision
belong to the canonical research graph, but `DeliveryCompiler` still accepts
the legacy `RunStore` path and derives output parents without an explicit
strict evidence resolver or run-revision check. A stale or foreign evidence
subgraph could therefore be rendered as a technical package and human report.
Issue #110 closes this last delivery boundary before the integrated receipt in
#112 is attempted.

## What Changes

- Add an issue-scoped strict delivery entry point that requires the canonical
  `RunLedger`, a ledger-backed `EvidenceResolver`, and the caller's expected
  run revision while retaining the existing readiness projection input.
- Resolve every consequential evidence anchor and exact artifact revision
  before either delivery artifact is appended.
- Carry the exact resolved `ArtifactRef` values into both output parent
  lineages without changing the legacy delivery payload schemas.
- Make stale, missing, foreign, or unverifiable evidence fail before any
  technical package or human report append; preserve the legacy compiler path
  for non-Alpha2 callers.
- Add focused TDD coverage for successful round trips, stale/missing lineage,
  revision conflicts, and the no-partial-write invariant.

## Capabilities

### New Capabilities

- `strict-delivery-lineage`: Atomically compile Alpha2 deliveries from a
  canonical strict evidence/decision graph with exact artifact provenance.

### Modified Capabilities

- None. The existing legacy delivery contract remains compatible; this issue
  adds the strict Alpha2 entry point as a separate boundary.

## Impact

- `src/research_tree/delivery.py` and package exports receive the strict
  delivery facade and preflight validation.
- Canonical ledger/evidence types are consumed, but their schemas are not
  changed.
- New focused tests and an issue-scoped OpenSpec change are added.
- No new dependency, host integration, OracleRun work, or #112 registry work
  is included.
