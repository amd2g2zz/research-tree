## ADDED Requirements

### Requirement: Every capability maps to implementation and verification surfaces

The change SHALL publish a delivery matrix mapping each requirement to source modules, public API or CLI surface, migration impact, unit/integration/black-box tests, expected evidence artifact, and owning GitHub issue. A task is not complete when only prose or a passing structural test exists.

#### Scenario: Requirement has no executable owner

- **WHEN** release review finds a requirement without a source owner, test, or evidence path
- **THEN** the requirement is marked incomplete and the milestone cannot close

#### Scenario: A generated package is changed

- **WHEN** a host package differs from its registered source output
- **THEN** the delivery matrix identifies the source change and package regeneration evidence required for acceptance

### Requirement: Public runtime and host package contracts are installable

The implementation SHALL define supported Python versions, dependency lock behavior, entry points, configuration precedence, workspace path rules, package manifests, and Codex/Claude Code/Hermes installation and smoke-test commands. A clean checkout SHALL be sufficient to execute the documented first successful path.

The source-checkout contract SHALL provide one supported launcher that resolves the `src/` package without an ambient `PYTHONPATH` (the default is `uv run research-tree ...`), and SHALL separately document direct-interpreter behavior, installed-wheel behavior, and the expected failure when dependencies or package installation are missing. Each host package SHALL declare its own skill format, setup command, runtime module/resource roots, generated-file provenance, and compatibility version; no host may import another host's package directory as its runtime.

#### Scenario: A host is installed from source checkout

- **WHEN** a user follows the host installation contract on Windows or POSIX
- **THEN** the correct isolated package is installed, its native metadata is valid, and a status or no-op smoke command succeeds

#### Scenario: A host package is missing a required resource

- **WHEN** package validation or installation resolves a referenced resource that is absent or belongs to another host
- **THEN** the operation fails before installation and identifies the source/package mismatch

### Requirement: Migration is dry-run, idempotent, and reversible

The migration tool SHALL expose inventory, dry-run, apply, verify, rollback, and status operations; record source digests, destination mappings, schema dispositions, collisions, and operator confirmation; and never delete untracked user data implicitly.

#### Scenario: Migration is run twice

- **WHEN** the same legacy input is imported twice
- **THEN** the second run reports `already_imported` by source digest and creates no duplicate canonical artifacts

#### Scenario: Migration verification fails

- **WHEN** a required lineage, digest, or compatibility check fails after apply
- **THEN** rollback restores the prior canonical pointer while preserving imported artifacts as quarantined evidence

### Requirement: Release evidence is a signed, reproducible manifest

Every release candidate SHALL produce a machine-readable manifest containing source revision, package hashes for all hosts, schema versions, test commands and results, evaluation corpus and baseline identifiers, migration result, documentation/layout checks, known failures, and verifier identity. The manifest SHALL be immutable after publication.

#### Scenario: Release notes claim a passing gate

- **WHEN** a release claim has no matching command result and artifact reference in the manifest
- **THEN** release validation rejects the claim

#### Scenario: Environment differs from the recorded run

- **WHEN** a verifier reruns a gate under a different Python, OS, package, or container identity
- **THEN** the result is recorded as a distinct environment and cannot overwrite the original evidence

### Requirement: Quality gates have pre-registered decision rules

The evaluation manifest SHALL freeze case versions, baselines, metrics, aggregation, missing-data handling, expert rubric, and release thresholds before candidate runs. Post-hoc source count, token count, heading count, URL count, or report length SHALL not alter a pass decision.

#### Scenario: A metric is unavailable

- **WHEN** a case cannot exercise an implementation or recovery dimension
- **THEN** the evaluator records `not_applicable` with a reason and does not count it as a pass

#### Scenario: Alpha2 improves one metric but regresses safety

- **WHEN** quality improves while false completion, evidence resolution, or recovery loss violates an absolute gate
- **THEN** the release fails despite aggregate improvement

### Requirement: Definition of Done requires observable evidence

Each implementation task SHALL close only after code, focused tests, full regression results, documentation updates, migration notes, and a linked evidence manifest are present where applicable. "Implemented" or "tests pass" without artifact references is insufficient.

#### Scenario: Feature passes unit tests but lacks black-box proof

- **WHEN** a P0 behavior has only unit-test evidence
- **THEN** the task remains incomplete until the required integration or black-box oracle evidence is attached

#### Scenario: A known limitation remains

- **WHEN** a capability cannot be fully supported on one host or environment
- **THEN** the release records the limitation, fallback, affected scenarios, and explicit non-claim instead of silently marking it complete

### Requirement: Rollout has an explicit compatibility and rollback window

The release plan SHALL define alpha1 import compatibility, package versioning, schema migration order, feature flags, observability period, rollback trigger, and final removal criteria for every replaced authority.

#### Scenario: Host parity fails after cutover

- **WHEN** a host produces a divergent semantic digest during the observation window
- **THEN** rollout is halted or rolled back according to the manifest and legacy state remains read-only and recoverable
