## Why

The intent-derived SearchPortfolio behavior is now delivered through three
reviewable child slices, but group 27 still points at a retired change, an
incomplete one-file command, an unreachable group-74 source revision, and a
legacy rollback promise. The parent issue needs one current-baseline acceptance
that proves the child behavior composes without restoring retired direct-query
or acquisition compatibility paths.

## What Changes

- Add a parent-only aggregate acceptance for issue #83 and group 27, depending
  on the delivered planning, execution, and canonical-lineage groups 74, 75,
  and 77.
- Rebind group 74's existing exact verification command to reachable squash
  merge `34d1c2b`; do not change the delivered planner implementation.
- Publish a deterministic, explicitly limited historical direct-query baseline
  comparison that measures rediscovery, coverage, depth, and closure deltas
  without loading or reintroducing a legacy runtime.
- Correct group-27 registry and delivery-matrix metadata to the current public
  Python surfaces, source modules, receipt contract, and current-only rollback.
- Mark the umbrella #83 tasks complete only after the aggregate command and
  source-bound group-27 receipt succeed.

## Capabilities

### New Capabilities

- `search-portfolio-aggregate-acceptance`: Parent-only, current-baseline
  verification that composes the delivered SearchPortfolio slices and retains
  an honest non-live historical comparison.

### Modified Capabilities

- None.

## Impact

- Affects only OpenSpec governance/registry records, a focused parent
  acceptance test, and its controlled comparison fixture.
- Depends on verified groups 74, 75, and 77 and their merged `origin/dev`
  behavior.
- Does not alter `SearchPortfolio` execution semantics, coordinator authority,
  source-capture persistence, public CLI routing, generated packages, or the
  retained release manifest.
