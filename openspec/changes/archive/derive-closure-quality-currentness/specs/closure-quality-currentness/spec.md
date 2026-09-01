## ADDED Requirements

### Requirement: Closure quality is derived from exact current graph evidence

The closure assessor SHALL derive usable method/provider independence from the
current exact Finding graph. It SHALL resolve each qualifying Finding through
strict evidence, receipt, and capture lineage, and independence SHALL require
at least two distinct usable `(method_id, provider_id)` boundaries. Caller
provided provenance groups, counterevidence dispositions, and contradiction
flags SHALL NOT be accepted by the API, persisted, migrated, or included in a
closure token.

#### Scenario: Removed caller quality keyword is rejected

- **WHEN** a caller invokes `assess()` with a prior provenance,
  counterevidence, or contradiction keyword
- **THEN** the API rejects the invocation instead of accepting or ignoring the
  legacy claim

#### Scenario: Canonical graph has independent capture boundaries

- **WHEN** qualifying Findings resolve to at least two distinct usable capture
  method/provider boundaries and all other derived checks pass
- **THEN** the derived independence check is satisfied without caller claims

### Requirement: Selected-option contradictions require an exact Oracle witness

The closure assessor SHALL treat a contradiction as a current direct Finding
parent whose effect contradicts the decision's selected option. Such a Finding
SHALL remain unresolved unless an exact current passed candidate OracleRun
includes the Finding reference in its input lineage. Contradictions for an
unselected option SHALL NOT create this selected-option obligation. The
assessor SHALL NOT claim global semantic adjudication or detect omitted Oracle
runs beyond the exact supplied candidate set.

#### Scenario: Selected option contradiction lacks an Oracle witness

- **WHEN** a complete direct Finding set contradicts the selected option and no
  current passed candidate OracleRun binds that Finding as an input
- **THEN** the assessment is inconclusive and emits an `adversarial` successor

#### Scenario: Exact Oracle witness covers a selected option contradiction

- **WHEN** a current passed candidate OracleRun includes the exact
  contradictory Finding reference and all other derived checks pass
- **THEN** the contradiction check is satisfied without trusting a caller flag

### Requirement: Current assessments bind deterministic derived inputs

A passed version-two `slot-closure-assessment` SHALL persist evaluator identity,
exact parent references, derived checks and diagnostics, successor obligations,
assessor version, and a deterministic token digest. The token envelope SHALL
exclude caller quality arguments. Version-one assessments SHALL be unsupported:
the runtime SHALL NOT provide a schema, parser, migration, or replay path for
them.

#### Scenario: Same graph is assessed twice

- **WHEN** the core evaluator assesses identical canonical graph inputs twice
- **THEN** the derived payload and token digest are identical

#### Scenario: Derived quality is insufficient

- **WHEN** independence or selected-option contradiction coverage is false
- **THEN** the assessment is inconclusive, has no closure token, and contains
  deterministic successor obligations

### Requirement: Currentness replays exact version-two closure state

The closure assessor SHALL expose deterministic currentness validation for an
exact persisted version-two `slot-closure-assessment`. It SHALL reparse the
typed payload, resolve every exact Finding/evidence/receipt/capture/origin and
OracleRun/spec/attempt/input/result/event lineage as current and in the
assessment run, recompute the derived envelope and token, and return false
unless the stored result is reproduced exactly. A raw, structurally incomplete,
stale, or tampered assessment or token SHALL NOT pass merely by carrying
current-looking references.

#### Scenario: Superseding graph input invalidates a token

- **WHEN** an assessment input or exact Oracle lineage input is superseded
  after a token was issued
- **THEN** currentness validation returns false and does not issue a replacement

#### Scenario: Raw assessment is non-replayable

- **WHEN** a generic ledger append creates an incomplete assessment or
  incomplete OracleRun with a passed status and current-looking references
- **THEN** currentness validation returns false

#### Scenario: Stored payload is tampered

- **WHEN** a persisted token, derived check, successor list, or diagnostic
  differs from the replayed canonical result
- **THEN** currentness validation returns false deterministically

### Requirement: Quality and currentness retain downstream authority boundaries

The quality/currentness child SHALL retain durable-content admission from #160
and SHALL NOT register completion inputs, alter coordinator completion,
propagate corrections, expose a new CLI command, or mark parent group 39
verified. Byte-identical generic-writer authority SHALL remain a #156 and #158
boundary.

#### Scenario: Replay rejects an unsupported or non-authoritative assessment

- **WHEN** currentness validation receives a version-one, malformed, stale,
  tampered, or non-replayable payload
- **THEN** it rejects the payload without a compatibility or migration path,
  and completion registration remains the responsibility of #156 and #158
