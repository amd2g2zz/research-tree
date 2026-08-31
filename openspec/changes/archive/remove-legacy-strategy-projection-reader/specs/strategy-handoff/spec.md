## MODIFIED Requirements

### Requirement: Strategy projection is complete, immutable, and content-bound
The runtime SHALL persist a versioned `StrategyProjection` containing current
understanding, provisional assumptions, decision targets, initial tracks and
method hypotheses, depth, evidence and validation expectations, autonomy and
safety envelope, replanning policy, success oracles, delivery contract, stop
rule, required project-preference influence lineage, revision, predecessor
lineage, and deterministic digest. Every material preference influence SHALL
name its source observation, profile revision, precedence, and reversal
condition, and MUST NOT override conflicting current explicit requester
intent. Construction and loading SHALL reject any payload that omits the
required current field set; the runtime SHALL not infer an empty influence
tuple or accept a legacy projection shape.

#### Scenario: Required strategy field is incomplete
- **WHEN** any required projection field, including
  `preference_influences`, is absent, empty where prohibited, or semantically
  invalid
- **THEN** persistence fails with field diagnostics and no projection revision
  is committed

#### Scenario: Equivalent hosts serialize a projection
- **WHEN** Codex, Claude Code, and Hermes project semantically equivalent
  strategy data including preference influence lineage
- **THEN** their canonical strategy payload and semantic digest are identical

#### Scenario: Current explicit request conflicts with the profile
- **WHEN** a profile entry conflicts with current explicit requester input
  during projection construction
- **THEN** the explicit input remains authoritative and the projection cannot
  claim profile precedence
