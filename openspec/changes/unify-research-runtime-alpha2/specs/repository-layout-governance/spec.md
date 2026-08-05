## ADDED Requirements

### Requirement: Repository Path Registry

The repository SHALL maintain a machine-readable registry for every allowed top-level path and governed subtree, including owner, asset class, mutability, tracked status, distribution status, cleanup safety, and canonical generation or execution command.

#### Scenario: Unexpected top-level directory appears

- **WHEN** CI or a release check encounters an unregistered top-level path
- **THEN** validation fails and requires classification or relocation

#### Scenario: Path ownership is inspected

- **WHEN** a contributor inspects a registered path
- **THEN** they can determine whether it is source, generated, installed, runtime, evaluation, build, cache, or historical material

The initial path registry SHALL be stored at registries/repository-paths-v1.json and validation SHALL enumerate the actual checkout rather than validating only a hand-written allowlist.

### Requirement: Source and Generated Package Boundary

Authoring sources and generated host packages MUST have non-overlapping ownership, and every generated package file MUST be reproducible from registered sources.

#### Scenario: Host package source changes

- **WHEN** a shared or host-specific source changes
- **THEN** the build identifies every affected generated package
- **AND** package validation fails until generated output is current

#### Scenario: Host formats differ

- **WHEN** Codex, Claude Code, and Hermes require different metadata or scripts
- **THEN** each remains in its registered package boundary without leaking files to another host

### Requirement: Installed Copy Boundary

Repository-local `.agents`, `.claude`, and `.codex` installations MUST be classified separately from distributable packages and SHALL NOT become package authoring sources.

#### Scenario: Local installation is performed

- **WHEN** a supported repository-local install command completes
- **THEN** installed files occupy registered ignored paths
- **AND** a clean source status is preserved

#### Scenario: Installed copy is edited

- **WHEN** a developer edits a repository-local installed copy
- **THEN** build and contributor guidance do not treat that edit as a distributable source change

### Requirement: Runtime and Build Artifact Policy

Durable runtime state, content-addressed artifacts, sample research output, raw acquisition data, build products, package metadata, and caches SHALL have explicit non-overlapping tracked or ignored policies.

#### Scenario: Supported workflows complete

- **WHEN** package build, tests, local installation, and a documented sample run execute from a clean checkout
- **THEN** `git status` contains no unexplained artifacts

#### Scenario: Runtime output is written into source

- **WHEN** a workflow writes run state, raw acquisition output, or generated reports under a registered authoring-source path
- **THEN** the boundary check fails with the producing command and expected destination class

### Requirement: Non-Destructive Layout Migration

Layout migration MUST inventory existing tracked and untracked material, provide an explicit source-to-destination map, detect collisions, and require operator confirmation before moving or deleting user-owned untracked data.

#### Scenario: Existing untracked research run is discovered

- **WHEN** migration finds `research-runs`, raw material, installed host copies, or evaluation experience output
- **THEN** it reports the classification and proposed disposition
- **AND** leaves the material unchanged without explicit operator action

The migration tool SHALL emit a collision report and confirmation token before any operator-migrated path is moved, and SHALL preserve source and destination digests in the audit manifest.

#### Scenario: Required alpha1 fixture moves

- **WHEN** a tracked alpha1 fixture is relocated
- **THEN** its provenance, stable identifier, compatibility reference, and release-baseline usability are preserved
