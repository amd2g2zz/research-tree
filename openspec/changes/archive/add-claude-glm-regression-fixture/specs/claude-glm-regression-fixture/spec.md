## ADDED Requirements

### Requirement: Public fixture is synthetic and non-historical

The repository SHALL retain Issue #72 as a versioned public synthetic fixture.
It MUST identify itself as non-historical, include only labelled synthetic
turns and an opaque evaluator identifier, and MUST NOT claim to reproduce a
source conversation or expose hidden oracle material.

#### Scenario: A source session is unavailable

- **WHEN** no authoritative source session is retained
- **THEN** the public fixture SHALL remain synthetic and non-historical rather
  than reconstructing exact user turns

### Requirement: Deterministic controls preserve behavioral boundaries

The fixture runner SHALL reject a trace that quotes a reference before
activation, asks more than one open alignment question, continues invalidated
strategy state, changes task identity, stops before recursive
decision-specific closure, omits either evidence-bound delivery, or presents
unsupported causal attribution.

#### Scenario: A correction leaves a stale strategy executable

- **WHEN** research continues with an invalidated strategy after a correction
- **THEN** the runner SHALL fail the correction-invalidation control

### Requirement: Runtime unavailability remains non-passing evidence

The fixture SHALL record an unavailable required runtime with a named blocker
and unresolved attribution. It MUST NOT count the unavailable result as parity
success, historical reproduction, or model/host causal evidence.

#### Scenario: GLM5.2 is not configured

- **WHEN** the controlled GLM5.2 runtime cannot be executed
- **THEN** the runner SHALL return `unavailable`, retain the blocker id, and
  return a non-passing result

### Requirement: Evaluation outputs remain locally ignored

Raw fixture output and source-bound receipt material SHALL stay under
`.research-tree/evaluation-runs/issue-72/` and SHALL NOT be committed as raw
transcripts or raw provider results.

#### Scenario: The acceptance command is recorded

- **WHEN** group 24 verification runs
- **THEN** its raw output reference SHALL resolve inside the ignored evaluation
  run root while the tracked registry contains only digests and references
