## ADDED Requirements

### Requirement: Canonical Evaluation Namespace

The repository SHALL define exactly one canonical namespace for versioned evaluation source assets and SHALL assign distinct governed paths to cases, schemas, harnesses, fixtures, oracle interfaces, baselines, scored results, expert reviews, raw transcripts, and disposable output.

#### Scenario: Two ambiguous evaluation roots exist

- **WHEN** repository validation finds multiple roots without non-overlapping registered roles
- **THEN** validation fails and reports the conflicting roots

The initial path contract SHALL be stored at registries/evaluation-paths-v1.json. evaluation/ is the tracked source root, .research-tree/evaluation-runs/ is disposable output, and evals/ has no active role.

#### Scenario: Evaluation asset is introduced

- **WHEN** a new evaluation file is added
- **THEN** its path determines a registered asset class, owner, tracked status, and lifecycle

### Requirement: Versioned Case and Oracle Separation

Every versioned public case MUST declare a stable identifier, schema version, permitted source, immutable baseline, environment, public inputs, and opaque oracle reference, while hidden oracle bodies MUST remain outside worker-visible and public fixture inputs.

#### Scenario: Public case contains hidden oracle material

- **WHEN** a case or worker request contains a reference patch, hidden test body, private answer, or oracle payload
- **THEN** schema or request validation rejects it

#### Scenario: Existing v1 case is retained

- **WHEN** `evaluation/cases/v1.json` is migrated or retained
- **THEN** its stable identifiers and provenance remain resolvable
- **AND** compatibility and schema validation are documented

### Requirement: Evaluation Result Provenance

Every retained baseline, scored run, or expert review SHALL bind its case version, repository revision, package identity, host, command, environment, evaluator, timestamps, artifact references, and known limitations.

#### Scenario: Result lacks implementation identity

- **WHEN** a result cannot identify the exact source and host package revision under test
- **THEN** it is classified as anecdotal material and cannot satisfy a release gate

#### Scenario: Expert review is retained

- **WHEN** a human or simulated professional review is used as evidence
- **THEN** the reviewed artifacts, rubric version, reviewer role, conflicts, and limitations are recorded

### Requirement: Evaluation Retention and Redaction

The evaluation asset model MUST define tracked versus ignored policy, retention, redaction, size limits, and safe diagnostics for raw transcripts and provider output.

#### Scenario: Oversized raw session is added to source assets

- **WHEN** an uncompressed transcript or generated run exceeds the governed threshold in a tracked source path
- **THEN** validation rejects it and directs it to the governed output or external artifact location

#### Scenario: Transcript contains restricted details

- **WHEN** retained evaluation evidence contains secrets, raw provider diagnostics, private prompts, or hidden-oracle content
- **THEN** publication validation fails until the material is redacted or excluded

### Requirement: Reproducible Evaluation Entry Points

The repository SHALL provide deterministic commands for unit, integration, black-box, cross-host, and expert-review evaluation classes and SHALL state which outputs are release evidence.

#### Scenario: Public alpha1 baseline is reproduced

- **WHEN** an evaluator starts from a clean checkout and follows the documented public baseline command
- **THEN** the same case manifest and registered evaluation configuration are selected
- **AND** any unavailable hidden component is reported as unavailable rather than passed

#### Scenario: Release gate consumes a private convention

- **WHEN** #55 or #64 references an unregistered local path or undocumented result format
- **THEN** release validation rejects that evidence

The commands, result schema, and release-gate mapping SHALL be checked in under evaluation/harness/ and SHALL be referenced by the frozen release manifest.
