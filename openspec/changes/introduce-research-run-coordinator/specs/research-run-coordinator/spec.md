## ADDED Requirements

### Requirement: Coordinator owns the lifecycle
Only `ResearchRunCoordinator` SHALL mutate canonical lifecycle state. Allowed
edges SHALL come from the lifecycle matrix and illegal transitions SHALL leave
the state digest unchanged while recording a rejection reason.

#### Scenario: Illegal transition
- **WHEN** a host requests an edge absent from the matrix
- **THEN** the coordinator returns `illegal_transition` and does not change state

### Requirement: Initialization is exact and idempotent
Initialization SHALL require same-round current `alignment-handoff` and
`blueprint-target` revisions with explicit parent lineage. Repeating the same
idempotency key SHALL return the original state without a duplicate transition.

#### Scenario: Stale handoff
- **WHEN** initialization references a superseded handoff
- **THEN** it is rejected before a run-state artifact is appended

### Requirement: Completion is a conjunction of obligations
The coordinator SHALL require current P0 closure tokens, non-blocking insight
state, readiness, technical and human delivery revisions, and exact user
acceptance. Worker, host, hook, report, and empty-frontier signals SHALL never
satisfy these requirements.

#### Scenario: Worker wave finishes early
- **WHEN** all host events are terminal but one obligation is missing
- **THEN** the run remains non-terminal and exposes the missing next action

### Requirement: Events and recovery are replayable
Host events SHALL be idempotent on `(run_id,event_id,payload_digest)`, stale
revisions SHALL be rejected, and recovery SHALL mark unfinished leases unknown
without treating them as success.

#### Scenario: Duplicate event
- **WHEN** an event with the same id and payload is ingested twice
- **THEN** the original artifact is returned and no second state transition occurs
