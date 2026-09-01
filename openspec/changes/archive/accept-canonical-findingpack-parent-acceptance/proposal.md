## Why

Issues #180 and #181 independently migrated the retained Finding Pack test
consumers and recorded source-bound verification receipts. Parent issue #171
needs a small composition receipt proving both completed child receipts remain
reachable from the current baseline before it can close.

## What Changes

- Add parent-only group 81 for #171, depending only on verified groups 79 and
  80.
- Add a focused acceptance test that proves each child receipt revision is
  reachable and records the parent ownership mapping.
- Register a source-bound group-81 receipt after the parent acceptance command
  succeeds.

## Capabilities

### New Capabilities

- `canonical-findingpack-parent-acceptance`: Parent-only evidence that the
  completed canonical Finding Pack consumer migrations remain current.

### Modified Capabilities

- None.

## Impact

- Affects only issue-local OpenSpec metadata, Alpha2 registries, and focused
  governance tests.
- Consumes the already-merged group-79 and group-80 receipts without changing
  either child definition, source revision, fixture, or runtime implementation.
- Does not delete the retired compiler or add a runtime adapter, bridge,
  fallback parser, alias, dual store, or exported compatibility helper.
