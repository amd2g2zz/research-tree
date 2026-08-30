<!-- generated from openspec/changes/heterogeneous-install-plan:PR #357 (#328) at alpha3-batch2-fixup-sync -->

## ADDED Requirements

### Requirement: install produces a per-host plan first
A single request can express heterogeneous host requirements. The lifecycle produces a per-host capability and target plan before any partial write.

#### Scenario: mixed project scope with Hermes
- **WHEN** the request is `install --host all --scope project`
- **THEN** codex/claude get install actions; Hermes gets a skipped entry with the machine-readable external_dirs snippet (idempotent, path-correct, preserves unrelated keys); no exception is raised

#### Scenario: one-host conflict does not fail the plan
- **WHEN** one host's target conflicts with a user-owned file
- **THEN** that host is recorded as conflict; other hosts still get install/skip entries; aggregate_ready reflects partial readiness honestly

#### Scenario: status reports per host independently
- **WHEN** status is queried after planning
- **THEN** it returns one entry per host plus an aggregate that does not hide partial readiness

#### Scenario: rollback boundary per host
- **WHEN** a plan entry has action install or conflict
- **THEN** rollback_boundary equals the target path; skipped entries carry `n/a`
