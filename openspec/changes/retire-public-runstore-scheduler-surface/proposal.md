## Why

`AdaptivePortfolioScheduler` remains a public, RunStore-backed API even though
the current-only cutover has no supported caller for it. Issue #178 removes its
published surface now, leaving the isolated source file unreachable for the
separate #179 deletion slice.

## What Changes

- **BREAKING**: Remove the root-package scheduler exports and every current
  caller or public contract that advertises them.
- **BREAKING**: Delete `tests/test_scheduler.py` and replace it with a small
  regression proving the retired root symbols are absent.
- Remove active Alpha2 registry, contract, and documentation references to the
  RunStore scheduler and persisted `work-portfolio` boundary.
- Keep `src/research_tree/scheduler.py` as an unreachable private source file
  only; #179 owns its physical deletion.
- Register group 62 / issue #178 as a planned current-only deletion slice.

## Capabilities

### New Capabilities

- `public-runstore-scheduler-surface-removal`: Retire the published RunStore
  scheduler surface without an alias, bridge, replacement, migration, fallback,
  or user-data operation.

### Modified Capabilities

- `adaptive-research-execution`: Current execution no longer publishes or
  documents the retired RunStore scheduler boundary.
- `worker-orchestration`: Current orchestration contracts no longer list the
  retired RunStore scheduler as an authority or dependency.

## Impact

This changes the root package API, the dedicated scheduler test suite, active
Alpha2 contracts and registries, and active documentation. It intentionally
does not import, read, move, rewrite, or delete user-owned RunStore or
portfolio data, and it does not add a substitute scheduler.
