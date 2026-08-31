## Why

Correction handling currently selects dependent work from a static kind list.
That permits descendants behind unknown or newly introduced artifacts to remain
authoritative after their upstream decision has changed.

## What Changes

- Replace kind-list correction invalidation with conservative transitive graph
  traversal over canonical artifact parents.
- Classify dependency-bearing canonical artifacts and fail closed for unknown
  descendants on a corrected path.
- Persist deterministic stale-path diagnostics used by dispatch, ingress, and
  completion checks across restart.

## Capabilities

### New Capabilities

- `transitive-correction-invalidation`: Conservative correction quarantine over
  canonical artifact lineage.

### Modified Capabilities

- None.

## Impact

The change affects `ResearchRunCoordinator`, ledger lineage traversal, focused
correction/host-event tests, and Alpha2 group 40 governance evidence. It adds
no CLI surface and does not delete immutable history.
