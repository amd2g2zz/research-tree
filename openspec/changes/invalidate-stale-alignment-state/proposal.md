## Why

Requester corrections can leave obsolete alignment, strategy, and handoff state executable, allowing an old task framing to influence later work.

## What Changes

- Add strict correction/reopen events bound to the current five-role authority chain and predecessor task/domain identity.
- Atomically preserve history, record supersession, and quarantine only lineage descendants of corrected state.
- Derive post-correction authority from state-owned streams; reject parallel or stale bindings for dispatch, confirmation, delivery, acceptance, completion.
- Retain pending-question and human-only Decision Slot protections.

## Capabilities

### New Capabilities

- `transactional-correction-invalidation`: typed corrections, immutable supersession, exact authority, lineage quarantine, identity separation, and requester-only decisions.

### Modified Capabilities

None.

## Impact

Scoped to feedback/coordinator code, tests, schema, fixture, and group 23 evidence; no provider, scheduler, UI, or generated-package changes.
