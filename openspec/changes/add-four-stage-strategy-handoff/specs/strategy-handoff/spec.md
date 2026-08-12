## ADDED Requirements

### Requirement: Strategy projection is complete, immutable, and content-bound
The runtime SHALL persist a versioned `StrategyProjection` containing current understanding, provisional assumptions, decision targets, initial tracks and method hypotheses, depth, evidence and validation expectations, autonomy and safety envelope, replanning policy, success oracles, delivery contract, stop rule, revision, predecessor lineage, and deterministic digest.

#### Scenario: Required strategy field is incomplete
- **WHEN** any required projection field is absent, empty, or semantically invalid
- **THEN** persistence fails with field diagnostics and no projection revision is committed

#### Scenario: Equivalent hosts serialize a projection
- **WHEN** Codex, Claude Code, and Hermes project semantically equivalent strategy data
- **THEN** their canonical strategy payload and semantic digest are identical

### Requirement: Exact displayed projection confirmation gates research
The coordinator SHALL enter autonomous research only after the current complete StrategyProjection was displayed and a requester explicitly confirms its exact revision and digest in context.

#### Scenario: Generic acknowledgement follows display
- **WHEN** the requester says only a generic acknowledgement such as okay, continue, or looks good
- **THEN** the run remains handoff_pending and dispatch is rejected

#### Scenario: Stale projection is confirmed
- **WHEN** confirmation references a predecessor or correction-invalidated projection digest
- **THEN** confirmation and dispatch fail without mutating lifecycle state

### Requirement: Strategy lineage distinguishes revisions and successors
The runtime SHALL append same-run revisions for method, track, depth, evidence, validation, replanning, delivery-detail, and stop-rule feedback, and SHALL create a stage-1 successor when outcome, target, scope, authority, safety, or success definition changes materially.

#### Scenario: Method changes during strategy review
- **WHEN** feedback changes only an initial method hypothesis
- **THEN** a successor StrategyProjection revision is appended in the same run and prior confirmation candidates are invalidated

#### Scenario: Success definition changes
- **WHEN** feedback materially changes the success oracle
- **THEN** the current run is superseded and a linked successor re-enters stage 1

### Requirement: Macro stage identity is monotonic and replayable
The runtime SHALL project detailed lifecycle states into four requester-visible macro stages and SHALL preserve the originating macro stage across pause, block, replay, and resume.

#### Scenario: Delivery pauses and resumes
- **WHEN** a stage-4 delivery is paused and later resumed
- **THEN** it remains stage 4 and cannot silently resume as stage-3 research

