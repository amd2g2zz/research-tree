## Why

Issue #178 removed the public RunStore scheduler surface, leaving its
unreachable implementation and an obsolete public contract behind. Retaining
them makes an already-retired writer appear available to future callers.

## What Changes

- **BREAKING**: Delete `src/research_tree/scheduler.py` with no replacement,
  alias, bridge, adapter, migration, fallback, or user-data operation.
- **BREAKING**: Delete the obsolete `RT-010` public scheduler contract and
  replace the #178 transitional source-presence assertion with a deletion
  regression.
- Prove no runtime import, active contract, test, or generated package
  reference can resolve the retired scheduler boundary.

## Capabilities

### New Capabilities

- `unreachable-runstore-scheduler-source-removal`: The retired RunStore
  scheduler has no physical source or current reference.

### Modified Capabilities

None.

## Impact

`src/research_tree/scheduler.py`, `docs/specs/RT-010.md`, and the focused
retirement regression change. Group 76 records this child receipt without
changing group 62 or closing parent #175.
