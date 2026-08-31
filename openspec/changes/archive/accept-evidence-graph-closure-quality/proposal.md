## Why

Issue #152 is a parent acceptance boundary. Its two bounded children, #160
and #161, now supply durable evidence/Finding admission and replayable closure
quality tokens respectively, but the parent group must prove both receipts are
reachable from one current integration revision before it can close.

## What Changes

- Add a parent-only acceptance contract for the evidence-graph closure-quality
  capability.
- Register group 39 as a source-bound aggregation of the already-merged group
  46 and group 47 receipts.
- Add deterministic governance coverage that rejects a missing, unverified, or
  unreachable child receipt.
- **BREAKING:** none. This slice adds no runtime parser, adapter, fallback, or
  compatibility surface.

## Capabilities

### New Capabilities

- `evidence-graph-closure-quality-acceptance`: Parent acceptance of the
  content-bound and current-token closure children.

### Modified Capabilities

- None.

## Impact

The change affects Alpha2 OpenSpec task registries, parent acceptance tests,
and #152 governance evidence. It does not modify runtime code or public APIs.
