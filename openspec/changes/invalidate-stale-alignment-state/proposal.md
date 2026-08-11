## Why

Requester corrections currently can be acknowledged while obsolete alignment,
strategy, and handoff state remains executable. This lets an old task framing or
diagnostic subject survive a material correction and influence later questions,
dispatch, confirmation, delivery, or completion.

## What Changes

- Add a strict typed correction/reopen event bound to exact predecessor Intent
  Model, Working Brief, Decision Map, strategy, and handoff revisions/digests.
- Apply correction as one transaction that preserves immutable history, creates
  explicit successor/supersession lineage, and quarantines dependent stale state.
- Require answers to match the active pending question and keep typed evidence
  separate from requester answers.
- Enforce Decision Slot resolution authority so agent-only evidence cannot close
  a requester-only slot.
- Reject dispatch, confirmation, delivery, acceptance, and completion from stale
  alignment/strategy/handoff references with machine-readable reasons.
- Preserve separate task and domain identities through correction and successor
  state; changing one never implicitly changes the other.

## Capabilities

### New Capabilities

- `transactional-correction-invalidation`: Typed correction/reopen events,
  immutable supersession, stale-state quarantine, exact digest guards, pending
  question binding, evidence authority, and task/domain identity separation.

### Modified Capabilities

None.

## Impact

The change is confined to the alignment/feedback and coordinator boundaries in
`src/research_tree/`, their public exports, focused tests, and group 23 OpenSpec
evidence. It adds no provider dependency, host UI behavior, scheduler authority,
or generated package source.
