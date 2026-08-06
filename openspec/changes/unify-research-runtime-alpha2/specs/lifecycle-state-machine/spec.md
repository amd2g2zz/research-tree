## ADDED Requirements

### Requirement: Lifecycle states and transitions are published as a matrix

The runtime SHALL publish a machine-readable matrix for alignment, handoff_pending, autonomous_research, synthesis, readiness, delivery_pending, awaiting_acceptance, completed, paused, blocked, superseded, authority_blocked, and failed states. Each transition SHALL specify event, actor, host, guards, side effects, next actions, and failure code.

The checked-in matrix is `registries/lifecycle-matrix-v1.json`. Its `failure_code`
field may be null for a successful edge because guard failures use the registered
`illegal_transition` default; every edge still declares its guard and side effects.
Cancellation is represented by a `cancel_requested` event that moves the current run
to `superseded` with `termination_reason=cancelled` and a required operator or human
actor, so cancellation does not introduce a second lifecycle vocabulary.

#### Scenario: Illegal transition is attempted

- **WHEN** a host or CLI attempts a transition absent from the matrix
- **THEN** the coordinator returns illegal_transition, appends a rejected-transition trace, and leaves the state digest unchanged

#### Scenario: Research is ready but not accepted

- **WHEN** all research and readiness obligations pass but the user has not accepted exact delivery revisions
- **THEN** the run enters awaiting_acceptance, not completed

### Requirement: Research completion and delivery acceptance are separate milestones

The state machine SHALL represent research/readiness completion, delivery compilation, user acceptance, supersession, and terminal completion as separate auditable transitions.

#### Scenario: User requests deeper treatment

- **WHEN** the user rejects report depth or asks for material expansion
- **THEN** acceptance is not recorded as complete and the coordinator creates linked follow-up work or a successor round

### Requirement: Pause, resume, cancel, and authority blocking are reversible or explicit

Pause, resume, cancellation, provider outage, safety violation, infeasible objective, and human-authority boundary SHALL have distinct states and reason payloads. Only the documented actor may resume or override each state.

#### Scenario: Provider outage pauses a run

- **WHEN** all permitted providers fail while obligations remain
- **THEN** the run enters paused with retry/alternate-provider actions and cannot enter a successful terminal state

#### Scenario: Objective is infeasible

- **WHEN** evidence proves that a hard feasibility constraint cannot be met
- **THEN** the run enters authority_blocked with proof, alternatives, and the human decision required

### Requirement: Transition replay is deterministic

Replaying the append-only transition/event stream SHALL produce the same semantic state digest, unresolved-obligation set, and legal-next-action set on Windows and POSIX.

#### Scenario: Events arrive out of order

- **WHEN** an event references a future revision or an unstarted attempt
- **THEN** it is retained as pending/stale evidence and cannot mutate the projection until its causal predecessor is present
