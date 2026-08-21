## ADDED Requirements

### Requirement: Material corrections are typed and revision-bound
The system SHALL accept a material correction/reopen only as a strict event containing run/event/actor/reason/relation, separate source and successor task/domain identities, and exact revision/digest bindings for Intent Model, Working Brief, Decision Map, strategy, and handoff.

#### Scenario: Correction omits an affected revision
- **WHEN** a required binding is missing or its digest differs from the exact revision
- **THEN** the event is rejected without artifact or lifecycle mutation

#### Scenario: Parallel latest artifact is submitted
- **WHEN** a binding is latest for its id but is not the state's exact active role, or source task/domain differs from the state
- **THEN** the correction is rejected atomically

#### Scenario: Task and domain identity remain distinct
- **WHEN** the diagnostic domain is not the research task target
- **THEN** successor state changes only explicitly named task/domain identities

### Requirement: Correction application is atomic and append-only
The coordinator SHALL preserve the predecessor and atomically append correction, stale quarantine, and successor alignment state linked by `supersedes` or `reopens`.

#### Scenario: Material correction commits successfully
- **WHEN** a correction uses exact active bindings and matching source identity
- **THEN** all three records commit and every predecessor remains unchanged

#### Scenario: Unrelated dependent kind exists
- **WHEN** a latest dependent-kind artifact is unreachable from affected authority or predecessor state
- **THEN** it remains usable and absent from quarantine

#### Scenario: Correction transaction fails before commit
- **WHEN** validation, revision comparison, or injected storage failure occurs
- **THEN** no batch artifact is visible and the predecessor remains current

#### Scenario: Correction event id is replayed
- **WHEN** the same id and payload replay
- **THEN** the existing successor returns; changed reuse conflicts

### Requirement: Stale state is quarantined before later control actions
After correction, dispatch, handoff confirmation, delivery compilation/acceptance, and completion MUST use exact current non-quarantined decision-map, strategy, and handoff bindings.

#### Scenario: Old strategy is dispatched after correction
- **WHEN** dispatch references a quarantined strategy or handoff
- **THEN** `stale_digest` is returned without lease or lifecycle mutation

#### Scenario: Old handoff is confirmed after correction
- **WHEN** confirmation references the previous displayed alignment/handoff digest
- **THEN** stale state is reported and the run stays in alignment

#### Scenario: Delivery or completion uses stale authority
- **WHEN** compilation, acceptance, or completion references quarantined authority
- **THEN** no obligation is satisfied and lifecycle does not advance

#### Scenario: Fresh successor authority is supplied
- **WHEN** bindings equal current revisions in state-owned successor streams
- **THEN** ordinary guards run; a parallel latest child set is rejected first

### Requirement: Requester decisions cannot be inferred from agent evidence
The protocol SHALL accept responses only for the pending action and SHALL NOT let agent evidence resolve a human-only Decision Slot.

#### Scenario: Response targets another action
- **WHEN** action or attempt differs from the active pending action
- **THEN** pending state, readiness, and lifecycle remain unchanged

#### Scenario: Agent evidence targets a requester-only slot
- **WHEN** agent belief/evidence claims to resolve a human-only field
- **THEN** it is rejected or non-resolving and requester input remains missing

### Requirement: Regression trace proves stale-plan quarantine
The project SHALL retain a deterministic wrong-subject fixture covering old strategy use, wrong pending response, and agent closure of requester-only state.

#### Scenario: Stale-plan contamination sequence is replayed
- **WHEN** the fixture runs on a fresh ledger
- **THEN** history remains, stale actions fail, identities stay distinct, and only canonical successor authority proceeds
