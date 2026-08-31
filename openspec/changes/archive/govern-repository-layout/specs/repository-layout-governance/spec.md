## MODIFIED Requirements

### Requirement: Repository Path Registry
The repository SHALL maintain a machine-readable registry for every tracked
checkout root and supported local root. Each entry SHALL declare owner, asset
class, mutability, tracked status, distribution status, cleanup safety,
canonical command, and non-empty lifecycle. Validation SHALL enumerate the
actual checkout rather than validating only a hand-written allowlist and SHALL
emit deterministic diagnostics for malformed, missing, duplicate, or
unregistered classifications.

#### Scenario: Unexpected top-level directory appears
- **WHEN** CI or a release check encounters an unregistered top-level path
- **THEN** validation fails with a stable diagnostic that requires
  classification or relocation and does not modify the path

#### Scenario: Path ownership is inspected
- **WHEN** a contributor inspects a registered path
- **THEN** they can determine whether it is source, generated, installed,
  runtime, evaluation, build, cache, or historical material and its lifecycle

#### Scenario: Registered local material is encountered
- **WHEN** the checker finds a registered untracked installed, runtime, raw, or
  evaluation path
- **THEN** it reports the path as protected and leaves it unchanged

The canonical registry SHALL remain at
`registries/repository-paths-v1.json` and SHALL conform to
`schemas/path-registry-v1.json`.

### Requirement: Source and Generated Package Boundary
Authoring sources and generated host packages MUST have non-overlapping
ownership, and every generated package file MUST be reproducible from
registered sources. The layout checker SHALL reject a registry that classifies
the package root as source, omits its rebuildable lifecycle, or fails to retain
the canonical package command.

#### Scenario: Host package source changes
- **WHEN** a shared or host-specific source changes
- **THEN** the build identifies every affected generated package and package
  validation fails until generated output is current

#### Scenario: Host formats differ
- **WHEN** Codex, Claude Code, and Hermes require different metadata or scripts
- **THEN** each remains in its registered package boundary without leaking
  files to another host

#### Scenario: Package boundary is checked
- **WHEN** the layout checker reads the path registry
- **THEN** it confirms that authoring input and generated package roots have
  distinct classes, mutability, and canonical commands

### Requirement: Installed Copy Boundary
Repository-local `.agents`, `.claude`, and `.codex` installations MUST be
classified separately from distributable packages, ignored by Git, and SHALL
NOT become package authoring sources. The checker SHALL diagnose a missing
installed-copy classification or ignore rule without reading, editing, moving,
or deleting the installed material.

#### Scenario: Local installation is performed
- **WHEN** a supported repository-local install command completes
- **THEN** installed files occupy registered ignored paths and a clean source
  status is preserved

#### Scenario: Installed copy is edited
- **WHEN** a developer edits a repository-local installed copy
- **THEN** build and contributor guidance do not treat that edit as a
  distributable source change

#### Scenario: Installed copy is present during validation
- **WHEN** the layout checker encounters a registered installed-copy root
- **THEN** it reports the root as protected local material and performs no
  filesystem mutation

### Requirement: Runtime and Build Artifact Policy
The repository SHALL assign durable runtime state, content-addressed artifacts,
sample research output, raw acquisition data, build products, package metadata,
and caches explicit non-overlapping tracked or ignored policies. Supported workflow probes
SHALL leave only registered and rebuildable output; the checker SHALL report
unexpected checkout roots and SHALL identify the expected class and canonical
command for registered ones.

#### Scenario: Supported workflows complete
- **WHEN** package build, tests, local installation, and a documented sample
  run execute from a clean checkout
- **THEN** `git status` contains no unexplained artifacts and the layout
  checker reports only registered roots

#### Scenario: Runtime output is written into source
- **WHEN** a workflow writes run state, raw acquisition output, or generated
  reports under a registered authoring-source path
- **THEN** the boundary check fails with the producing command and expected
  destination class

#### Scenario: Ignore policy is incomplete
- **WHEN** a registered untracked runtime, installed, raw, evaluation, build,
  or cache root lacks its exact ignore rule
- **THEN** the checker fails with a stable diagnostic and does not alter the
  checkout

### Requirement: Non-Destructive Layout Migration
Layout migration MUST inventory existing tracked and untracked material,
provide an explicit source-to-destination map, detect collisions, and require
operator confirmation before moving or deleting user-owned untracked data.
Contributor guidance SHALL describe the collision inspection and verification
sequence, and the layout checker SHALL be read-only.

#### Scenario: Existing untracked research run is discovered
- **WHEN** migration finds `research-runs`, raw material, installed host copies,
  or evaluation experience output
- **THEN** it reports the classification and proposed disposition and leaves
  the material unchanged without explicit operator action

#### Scenario: Required alpha1 fixture moves
- **WHEN** a tracked alpha1 fixture is relocated
- **THEN** its provenance, stable identifier, compatibility reference, and
  release-baseline usability are preserved

#### Scenario: Collision is found during a proposed migration
- **WHEN** a contributor identifies a destination that already exists
- **THEN** guidance requires a collision report and explicit confirmation before
  any manual operation and the checker performs no operation
