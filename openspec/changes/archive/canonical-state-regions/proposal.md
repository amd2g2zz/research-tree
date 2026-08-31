# Proposal: canonical-state-regions

## Why

issue #324: canonical state is one overloaded `state` string on the run record,
which conflates cognitive/workflow/authority/epistemic/delivery phases.  Other
surfaces (alignment_graph, recursive_tree_state, host_visible output) all
duplicate or shadow this single field — the Agent cannot answer "what phase am
I in / who am I waiting for" reliably.

## What Changes

1. `ResearchRunCoordinator.STATE_REGIONS = ("cognitive", "workflow", "authority", "epistemic", "delivery")`.
2. `self_state(run_id)` projects the current state into 5 orthogonal regions
   + a `lineage` dict (run id, revision, affected forest/branch, authority,
   blockers, authority_waits, next_action, expected transition oracle,
   experiments).  Legacy single-string state is mapped via
   `_legacy_to_regions()` so byte-identical behavior for callers that don't
   touch the new surface.
3. `transition()` rejects forbidden cross-region payloads at the entry gate:
   `event == "research/running"` → `cross_region_research_running_not_permitted`;
   `event in {"plan_completed", "plan_displayed", "plan_visible"}` →
   `visible_plan_cannot_advance_canonical` (issue acceptance: "visible plan
   completion cannot advance canonical execution, epistemic, or delivery state").

## Impact

- src/research_tree/coordinator.py: STATE_REGIONS + self_state + helper + 2 transition guards
- All existing callers of transition() unaffected (guards precede legacy logic; new events are forbidden names)
- No behavior change for any caller that doesn't call self_state

## Non-building
- Full region transition table (wiring of all region transitions to events) — follow-up
- Compaction / crash-restore semantics — covered by self_state idempotence; full machine deferred
- Coordinator split — explicit NOT Building (batch-3 ledgers decision)
