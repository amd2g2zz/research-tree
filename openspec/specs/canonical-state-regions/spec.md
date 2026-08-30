<!-- generated from openspec/changes/canonical-state-regions:PR #364 (#324) at alpha3-batch2-fixup-sync -->

## ADDED Requirements

### Requirement: canonical state is orthogonal regions
A canonical state projection exposes five regions — cognitive, workflow, authority, epistemic, delivery — each carrying its own (value, revision). Lineage (affected forest/branch, blockers, authority waits, next action) is surfaced alongside.

#### Scenario: self_state surfaces five regions + lineage
- **WHEN** self_state(run_id) is queried
- **THEN** the result has keys for cognitive, workflow, authority, epistemic, delivery plus a lineage entry with revision, blockers, authority_waits, next_action

#### Scenario: cross-region combinations fail closed
- **WHEN** a transition event would set an invalid cross-region combination (research/running while authority says awaiting_requester)
- **THEN** the transition raises CoordinatorConflictError before any state change

#### Scenario: visible plan events do not advance canonical state
- **WHEN** a transition event of kind plan_completed / plan_displayed / plan_visible is sent
- **THEN** the transition raises CoordinatorConflictError (visible_plan_cannot_advance_canonical)

#### Scenario: branch lineage is independent of run revision
- **WHEN** self_state is queried twice without intervening state changes
- **THEN** the lineage revision is identical and the workflow region value is preserved
