## ADDED Requirements

### Requirement: One canonical evaluation namespace
The repository SHALL use `evaluation/` for versioned source assets and SHALL
reject `evals/` or generated run trees as tracked evaluation sources.

#### Scenario: Ambiguous root is present
- **WHEN** a tracked asset is placed below `evals/`
- **THEN** evaluation governance fails with a stable misplaced-path diagnostic

### Requirement: Non-overlapping lifecycle classes
The repository MUST place cases, schemas, harnesses, fixtures, baselines,
results, reviews, and disposable runs in registry-defined non-overlapping paths
with explicit tracking, mutability, retention, and size rules.

#### Scenario: Raw transcript is mixed with a result
- **WHEN** raw provider transcript material appears in a tracked result path
- **THEN** validation rejects the asset without modifying it

### Requirement: Versioned identity and provenance
Every governed baseline, result, and review SHALL have a stable identifier,
schema version, source or case references, environment/producer identity, and
content digest sufficient to audit its origin.

#### Scenario: Provenance reference is missing
- **WHEN** an asset references an unknown case or baseline identifier
- **THEN** validation fails with the asset path and dangling reference

### Requirement: Hidden oracle isolation
Public and worker-visible evaluation assets MUST contain only opaque
evaluator-owned oracle references and MUST NOT expose oracle bodies, expected
patches, credentials, private prompts, or confidential provider logs.

#### Scenario: Oracle body leaks into a public case
- **WHEN** a public case contains an embedded hidden-oracle body
- **THEN** governance rejects the case before any evaluation command runs

### Requirement: Deterministic public evaluation entrypoint
A clean checkout SHALL provide a deterministic command that validates and runs
the public Alpha1 baseline without writing generated output into tracked source
directories.

#### Scenario: Public baseline is reproduced
- **WHEN** the documented baseline command runs twice on the same revision
- **THEN** its semantic result is identical and disposable output stays outside
  tracked evaluation paths

### Requirement: Non-destructive legacy inventory
The governance tooling MUST treat local experience reports and transcripts as
user-owned migration candidates and MUST NOT read bodies, move, delete, or stage
them automatically.

#### Scenario: Legacy experience directory exists
- **WHEN** `evaluation/experiences/` exists with untracked content
- **THEN** validation reports its lifecycle class without changing any file
