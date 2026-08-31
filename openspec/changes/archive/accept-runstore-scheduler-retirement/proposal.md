## Why

Issues #178 and #179 have separately retired the public RunStore scheduler
surface and purged its unreachable source. Their source-bound receipts are now
reachable from `dev`, but parent issue #175 has no composition receipt proving
that the completed deletion remains current-only.

## What Changes

- Add parent-only group 78 for #175, depending only on verified groups 62 and
  76.
- Add a focused acceptance test that proves both child receipt revisions are
  reachable, records the parent ownership mapping, and rechecks that the
  retired source and public contract remain absent.
- Register a source-bound group-78 receipt after the parent acceptance command
  succeeds.

## Capabilities

### New Capabilities

- `runstore-scheduler-retirement-acceptance`: Parent-only evidence that the
  completed scheduler retirement remains unreachable and contains no
  compatibility or user-data operation.

### Modified Capabilities

- None.

## Impact

- Affects only issue-local OpenSpec metadata, Alpha2 registries, and focused
  governance tests.
- Consumes the already-merged group-62 and group-76 receipts without changing
  either child definition, source revision, or implementation.
- Does not recreate, modify, import, read, move, or delete scheduler runtime
  behavior or user-owned data.
