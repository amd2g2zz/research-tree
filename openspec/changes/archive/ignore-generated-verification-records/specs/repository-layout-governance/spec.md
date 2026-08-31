## ADDED Requirements

### Requirement: Generated verification records remain outside source control

The repository SHALL keep locally generated command stdout, stderr, receipt
metadata, coverage reports, test reports, cache state, profiles, and editor or
index state outside tracked source paths. Verification generators SHALL write
such output only below the ignored `.research-tree/verification-runs/` boundary.

#### Scenario: receipt destination is local-only

- **WHEN** a task verification receipt is generated
- **THEN** its output path is below `.research-tree/verification-runs/` and a
  destination under `openspec/changes/**/evidence/` is rejected

#### Scenario: force-added verification output is rejected

- **WHEN** a pull request adds a generated verification output or receipt path
- **THEN** the delivery gate fails even if the file was force-added past
  `.gitignore`

### Requirement: Normative evidence remains trackable

The repository SHALL continue to track hand-authored specifications, schemas,
semantic fixtures, redacted evaluation evidence, and review artifacts.

#### Scenario: semantic fixture is not a generated record

- **WHEN** a versioned semantic fixture or schema is added below an OpenSpec or
  evaluation source path
- **THEN** the generated-record guard does not reject it solely by directory
  location
