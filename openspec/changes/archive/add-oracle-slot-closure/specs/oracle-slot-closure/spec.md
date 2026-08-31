## ADDED Requirements

### Requirement: Oracle execution is revision-bound
The runtime SHALL persist `OracleSpec`, `OracleAttempt`, and `OracleRun` as
immutable artifacts. An OracleRun SHALL bind the exact specification, attempt,
inputs, method, environment, tool events, result artifacts, evaluator, verdict,
timing state, reproducibility state, and limitations.

#### Scenario: stale specification
- **WHEN** an OracleRun names a specification revision different from its attempt
- **THEN** the runtime rejects it before persistence

### Requirement: Worker validation prose is non-authoritative
The runtime SHALL retain legacy Finding Pack validation strings as history but
SHALL NOT treat them as executable validation or closure evidence.

#### Scenario: forged passed string
- **WHEN** a Finding Pack reports `passed` without a current passed OracleRun
- **THEN** an assessment cannot issue a closure token

### Requirement: Closure is evaluator-owned and conservative
Only the configured core evaluator SHALL issue a `SlotClosureAssessment`.
Selected or conditional P0 decisions SHALL require matching slot evidence,
independent provenance, counterevidence disposition, no active contradiction,
a passed OracleRun, fallback, and reversal condition.

#### Scenario: manual close attempt
- **WHEN** a non-core identity asks to close a slot
- **THEN** no passed assessment or closure token is persisted

#### Scenario: active contradiction
- **WHEN** the supplied evidence has an unresolved contradiction
- **THEN** the assessment is inconclusive and requests adversarial work

### Requirement: Failure retains obligations
Failed, blocked, or inconclusive OracleRuns SHALL produce typed validation,
method-switch, fallback, or residual-risk successor recommendations.

#### Scenario: timed out oracle
- **WHEN** an OracleRun times out
- **THEN** its assessment is inconclusive and includes a successor
