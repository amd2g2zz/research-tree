## ADDED Requirements

### Requirement: Material corrections are typed and revision-bound
The system SHALL accept a material requester correction or reopen only as a
strict typed event that identifies its run, event identity, actor, reason,
relation, separate task and domain identities, and exact affected Intent Model,
Working Brief, Decision Map, strategy, and handoff artifact revisions and
digests.

#### Scenario: Correction omits an affected revision
- **WHEN** a material correction lacks any required affected artifact binding or supplies a digest that does not match the exact revision
- **THEN** the system rejects the event without appending an artifact or changing lifecycle state

#### Scenario: Task and domain identity remain distinct
- **WHEN** a correction says that a diagnostic domain subject is not the research task target
- **THEN** the successor state records separate task and domain ids and changes only identities explicitly named by the event

### Requirement: Correction application is atomic and append-only
The coordinator SHALL apply a valid correction as one ledger transaction that
preserves the predecessor state, records the correction and stale-state
quarantine, creates a successor alignment-state revision, and links the old and
new state through an explicit `supersedes` or `reopens` relation.

#### Scenario: Material correction commits successfully
- **WHEN** the requester corrects current state using exact active bindings
- **THEN** the correction, quarantine, and successor state all commit together and every predecessor artifact remains readable and unchanged

#### Scenario: Correction transaction fails before commit
- **WHEN** validation, revision comparison, or injected storage failure prevents the transaction
- **THEN** none of the correction, quarantine, or successor artifacts is visible and the predecessor remains current

#### Scenario: Correction event id is replayed
- **WHEN** the same correction event id and payload are replayed
- **THEN** the existing successor is returned idempotently, while changed reuse of that id is rejected as an event conflict

### Requirement: Stale state is quarantined before later control actions
After a material correction, the coordinator MUST reject dispatch, handoff
confirmation, delivery compilation, delivery acceptance, and completion unless
the action is bound to current non-quarantined alignment, strategy, and handoff
revisions and digests.

#### Scenario: Old strategy is dispatched after correction
- **WHEN** a dispatch references a strategy or handoff revision quarantined by the latest correction
- **THEN** the dispatch is rejected with a machine-readable `stale_digest` reason and no lease or lifecycle mutation occurs

#### Scenario: Old handoff is confirmed after correction
- **WHEN** handoff confirmation references the previously displayed alignment or handoff digest
- **THEN** confirmation is rejected with a machine-readable stale-state reason and the run remains in alignment

#### Scenario: Delivery or completion uses stale authority
- **WHEN** delivery compilation, acceptance, or completion references a quarantined binding
- **THEN** the operation is rejected without satisfying an obligation or advancing lifecycle state

#### Scenario: Fresh successor authority is supplied
- **WHEN** all required action bindings name current successor artifacts with exact matching digests
- **THEN** the coordinator evaluates the ordinary lifecycle and evidence guards without treating the predecessor as current

### Requirement: Requester decisions cannot be inferred from agent evidence
The alignment protocol SHALL accept a response only for its active pending
action and SHALL NOT allow an agent-authored belief or evidence record to resolve
a human-only Decision Slot.

#### Scenario: Response targets another action
- **WHEN** a record operation names an action or attempt other than the active pending action
- **THEN** it is rejected without changing the pending attempt, belief readiness, or lifecycle state

#### Scenario: Agent evidence targets a requester-only slot
- **WHEN** an agent-authored belief or evidence record is marked as resolving a human-only field
- **THEN** it is rejected or remains non-resolving and readiness continues to report the requester decision as missing

### Requirement: Regression trace proves stale-plan quarantine
The project SHALL retain a deterministic regression fixture that models a
wrong-subject correction followed by attempts to use the old strategy, answer
the wrong pending question, and close a requester-only slot with agent evidence.

#### Scenario: Stale-plan contamination sequence is replayed
- **WHEN** the fixture is executed against a fresh ledger
- **THEN** the predecessor remains historical, stale and unauthorized actions are rejected, task/domain identity stays distinct, and only a fresh successor-bound action can proceed
