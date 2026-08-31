# Goal Wiring Specification

## ADDED Requirements

### Requirement: Decision Slots carry a required serves link to the confirmed projection

Each Decision Slot payload MUST carry `serves: {target_id, oracle_ids}` referencing the
`decision_targets` and `success_oracles` ids of the run's current confirmed StrategyProjection.
`CanonicalWorkItemCompiler` MUST reject the whole work item when a slot's serves references do
not resolve against that projection.

#### Scenario: Unknown serves target is rejected

- **WHEN** a work item is compiled for a slot whose `serves.target_id` is absent from the
  confirmed projection's `decision_targets`
- **THEN** compilation fails with
  `serves.target_id not in confirmed strategy-projection decision_targets: <id>`
- **AND** no work item artifact is appended.

#### Scenario: Unknown serves oracle is rejected

- **WHEN** a work item is compiled for a slot whose `serves.oracle_ids` contains an id absent
  from the confirmed projection's `success_oracles`
- **THEN** compilation fails with
  `serves.oracle_id not in confirmed strategy-projection success_oracles: <id>`

#### Scenario: P0 slot without oracle coverage is rejected

- **WHEN** a P0 slot carries an empty `serves.oracle_ids`
- **THEN** compilation fails with `P0 slot requires non-empty serves.oracle_ids: <slot_id>`

#### Scenario: Happy path compiles with the serves link

- **WHEN** a work item is compiled for a slot whose serves references resolve against the
  confirmed projection
- **THEN** the work item payload carries `serves: {target_id, oracle_ids}` and the goal→slot
  decomposition contains the mapping.

### Requirement: Slot whitelist requires the serves shape

The Decision Slot whitelist MUST require `serves` with exactly `target_id` (identifier) and
`oracle_ids` (identifier sequence).

#### Scenario: Blueprint target compile rejects a slot without serves

- **WHEN** a Blueprint Target is compiled with a slot lacking `serves`
- **THEN** compilation fails naming the missing `serves` field.

### Requirement: Work item compilation fails closed without a confirmed projection

Work item compilation MUST use the run's current confirmed projection as the serves basis. A
projection that was never confirmed MUST NOT authorize compilation.

#### Scenario: Unconfirmed projection is rejected

- **WHEN** the run has no confirmed projection (draft or displayed only)
- **THEN** work item compilation fails requiring a confirmed strategy-projection
- **AND** no work item artifact is appended.

### Requirement: Confirmation MUST be the authoritative handoff_confirmed lifecycle event

The confirmed projection SHALL be the projection revision named (and digest-matched) by the
run's latest `handoff_confirmed` lifecycle event, queried via
`strategy_projection.latest_confirmed`. Projections that are draft, displayed, or superseded
MUST NOT be treated as confirmed.

#### Scenario: Displayed projection without confirmation is not a basis

- **WHEN** a projection has been displayed but not confirmed
- **THEN** `latest_confirmed` returns no confirmed projection for the run.

#### Scenario: A late unresolvable confirmation fails closed instead of re-arming the old one

- **WHEN** a `handoff_confirmed` event that cannot be resolved to the projection revision it
  names (unparseable reference, unknown revision, digest mismatch) is newer than the last
  resolvable confirmation
- **THEN** `latest_confirmed` returns no confirmed projection for the run
- **AND** work item compilation fails requiring a confirmed strategy-projection.

#### Scenario: A superseded confirmation is no longer a basis

- **WHEN** a later revision of the confirmed projection exists in the run
- **THEN** `latest_confirmed` returns no confirmed projection until the newer revision is
  itself confirmed.

### Requirement: The projection lifecycle is drivable through the CLI with human authority

The stable CLI MUST expose `strategy propose`, `strategy display`, and `strategy confirm`.
Propose persists a reviewed projection draft through
`coordinator.persist_strategy_projection`; display performs the falsifiability review, commits
the displayed projection revision, and drives `coordinator.display_strategy`; confirm keeps
`actor="human"`, enforces the digest-in-confirmation check, and MUST reject generic
acknowledgements.

#### Scenario: CLI drives propose, display, confirm, and the tree bridge

- **WHEN** an operator proposes a projection draft, displays it, and confirms it with a
  contextual authorization containing the displayed digest
- **THEN** the run advances through alignment → handoff_pending → autonomous_research
- **AND** the confirmation bridges to `initialize_research_from_alignment` so the research
  tree artifact exists.

#### Scenario: Generic confirmation is rejected

- **WHEN** the confirm verb receives a generic acknowledgement such as `okay`
- **THEN** the command fails with `generic_confirmation` and the run state is unchanged.

#### Scenario: Serve validation fails closed before confirmation

- **WHEN** work items are compiled after display but before confirmation
- **THEN** compilation fails requiring a confirmed strategy-projection.

### Requirement: Displayed projections are falsifiable

`display_strategy` MUST reject a projection whose success oracles are not evidence-bound —
every success oracle entry must carry non-empty `evidence_standard_ids`, and every
decision-target `oracle_ids` reference must resolve inside `success_oracles`. The review is
enforced at the coordinator authority layer; `strategy display` pre-flights the same rules
before committing the displayed revision so a rejected display appends no artifact. Rejected
displays MUST NOT mutate run state.

#### Scenario: Oracle without evidence standards is rejected at display

- **WHEN** a success oracle entry carries empty `evidence_standard_ids`
- **THEN** the display fails naming `evidence_standard_ids` and the run state is unchanged.

#### Scenario: Dangling decision-target oracle reference is rejected at display

- **WHEN** a decision target references an oracle id absent from `success_oracles`
- **THEN** the display fails naming the dangling reference and the run state is unchanged.

#### Scenario: Authority layer rejects an unfalsifiable projection without the CLI

- **WHEN** a projection with string success oracles is persisted directly through the
  coordinator API with a hand-forged `displayed` status and `display_strategy` is called
- **THEN** `display_strategy` rejects it naming `evidence_standard_ids`
- **AND** the run state, run revision, and lifecycle-event count are unchanged.

### Requirement: Handoff payloads project the goal decomposition

Alignment-handoff payload assembly MUST record `confirmed: true` and the
`goal_decomposition` mapping (`[{slot_id, target_id, oracle_ids, priority}]`, ordered by
priority then slot id) derived from Decision Slots' serves links, and strategy display output
MUST include the same mapping.

#### Scenario: Handoff decomposition orders slots by priority then slot id

- **WHEN** the alignment handoff is compiled for a run whose blueprint target carries slots
  with serves links at mixed priorities
- **THEN** the handoff payload's `goal_decomposition` lists every serving slot with its
  target, oracle ids, and priority in priority→slot_id order.
