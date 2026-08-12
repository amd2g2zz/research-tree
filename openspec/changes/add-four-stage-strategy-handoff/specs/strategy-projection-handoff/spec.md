## ADDED Requirements

### Requirement: StrategyProjection is complete, immutable, and digest-bound

The system SHALL persist a versioned `StrategyProjection` containing the
current understanding, assumptions, decision targets, initial tracks and
method hypotheses, depth, evidence expectations, autonomy envelope,
replanning policy, success oracles, delivery contract, stop rule, exact parent
references, and a deterministic canonical digest.

#### Scenario: Complete projection round trips across hosts

- **WHEN** a coordinator persists a complete projection and Codex, Claude Code,
  and Hermes serialize it
- **THEN** every host produces the same semantic digest and the ledger retains
  the DecisionFrame, alignment-handoff, target, and evidence lineage

#### Scenario: Missing required field fails closed

- **WHEN** a caller omits an autonomy boundary, oracle, delivery contract, or
  stop rule
- **THEN** validation fails before an artifact or revision is appended

### Requirement: Four macro stages are monotonic and explicit

The coordinator SHALL expose alignment (stage 1), handoff_pending (stage 2),
autonomous research through delivery_pending (stage 3), and delivery/acceptance
(stage 4) as a pure projection of canonical lifecycle state. No legal transition
MAY skip stage 2 or enter stage 3 without a current projection.

#### Scenario: Alignment becomes handoff pending

- **WHEN** alignment readiness passes but no human confirmation exists
- **THEN** the run enters `handoff_pending`, exposes the projection digest, and
  cannot dispatch autonomous work

#### Scenario: Direct autonomous transition is rejected

- **WHEN** a host requests stage-3 dispatch from alignment or with no projection
- **THEN** the coordinator returns a stable guard error and leaves the state
  digest and revision unchanged

#### Scenario: Pause and resume preserve macro stage

- **WHEN** a stage-3 run pauses for an operational limit and later resumes
- **THEN** the resumed run remains stage 3 and cannot regress to alignment or
  handoff_pending

### Requirement: Confirmation accepts only the displayed current projection

The system SHALL bind confirmation to the exact current projection artifact
revision and digest. A generic acknowledgement, stale digest, incomplete
projection, or confirmation from an unauthorized actor MUST fail without
mutating canonical lifecycle state.

#### Scenario: Contextual confirmation authorizes stage 3

- **WHEN** a human explicitly accepts the displayed strategy, scope, oracles,
  autonomy envelope, and delivery contract with the current digest
- **THEN** one idempotent confirmation event is appended and the coordinator may
  transition from `handoff_pending` to `autonomous_research`

#### Scenario: Generic acknowledgement is non-authorizing

- **WHEN** the requester responds only with `okay`, `continue`, or `go ahead`
- **THEN** the run remains `handoff_pending` and no dispatch or confirmation
  event is written

#### Scenario: Stale confirmation is rejected

- **WHEN** a strategy revision or alignment correction changes the displayed
  projection before confirmation
- **THEN** the old digest is rejected with a stable stale error and the old
  projection remains historical only

### Requirement: Revisions and material corrections preserve lineage

The system SHALL distinguish same-round method/depth/evidence strategy
revisions from material target, authority, safety, outcome, or success changes.
Same-round revisions SHALL supersede the prior projection and invalidate its
confirmation candidate; material changes SHALL create a linked stage-1
successor run.

#### Scenario: Method revision stays in the same run

- **WHEN** a coordinator changes depth or method while the primary target and
  success definition remain unchanged
- **THEN** a new projection is appended with the prior projection as parent and
  the run remains in handoff_pending until the new digest is confirmed

#### Scenario: Target correction creates a successor

- **WHEN** requester feedback changes the primary outcome or success definition
- **THEN** the predecessor is superseded, a successor run is linked, and the
  successor re-enters alignment without mutating predecessor artifacts

### Requirement: Replay, migration, and host observations are safe

Projection writes, confirmation events, and v5 migration SHALL be idempotent,
revision-bound, replayable, and atomic under injected failure. Host adapters MAY
transport projection/confirmation observations but SHALL NOT become lifecycle
authority.

#### Scenario: Duplicate event replay is idempotent

- **WHEN** the same projection or confirmation idempotency key is submitted
  twice with the same payload
- **THEN** the original artifact is returned and the canonical revision does not
  advance twice

#### Scenario: Fault during projection batch rolls back

- **WHEN** a fault occurs after generic artifact staging but before the v5
  projection/event commit
- **THEN** neither partial projection nor lifecycle mutation is visible after
  reload

#### Scenario: Host capability is unavailable

- **WHEN** a host cannot run its native confirmation transport
- **THEN** the evaluator records `unavailable` for that host while the canonical
  projection digest and authority remain valid
