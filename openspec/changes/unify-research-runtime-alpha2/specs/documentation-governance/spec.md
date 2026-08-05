## ADDED Requirements

### Requirement: Documentation Authority Registry

The repository SHALL maintain one discoverable registry that assigns every documentation class a canonical source, authority level, audience, owner, lifecycle status, update trigger, and validation rule.

#### Scenario: Contributor locates canonical edit source

- **WHEN** a contributor inspects a generated host-package reference
- **THEN** the registry identifies its authoring source and generation command
- **AND** the generated copy is not presented as independently authoritative

#### Scenario: Agent encounters conflicting documents

- **WHEN** an active normative document conflicts with a historical or generated document
- **THEN** the registry determines which document governs current behavior
- **AND** the conflict is reported rather than silently merged

The initial registry SHALL be stored at registries/documentation-authority-v1.json and its precedence list SHALL be validated before active documentation changes are accepted.

### Requirement: Documentation Lifecycle and Supersession

Every governed document SHALL be classified as normative, active-change, generated, historical, operational, or evaluation evidence and SHALL declare how it becomes superseded or archived.

#### Scenario: Legacy RT specification remains traceable

- **WHEN** an RT specification is replaced by a ratified alpha2 OpenSpec or ADR
- **THEN** the RT specification retains its decision history
- **AND** it carries a resolvable supersession reference and cannot override the active contract

#### Scenario: Active change becomes architecture record

- **WHEN** an OpenSpec change is accepted and archived
- **THEN** normative decisions are synchronized to the designated product specification or ADR surface
- **AND** the registry updates the active and historical lifecycle states

### Requirement: Generated Documentation Provenance

Generated host-package documentation MUST be reproducibly derived from canonical authoring sources and MUST carry mechanically verifiable provenance.

#### Scenario: Generated copy is stale

- **WHEN** a canonical reference changes without rebuilding affected host packages
- **THEN** validation fails with the source and stale generated paths

#### Scenario: Generated copy is edited directly

- **WHEN** a package document differs from its generation result without a corresponding source change
- **THEN** validation rejects the edit and identifies the canonical source

### Requirement: Documentation Integrity Gates

CI SHALL validate internal links, active terminology, required index membership, and generated-copy consistency.

#### Scenario: Active document uses retired delivery terminology

- **WHEN** an active normative or user-facing document uses a forbidden legacy contract name without a compatibility annotation
- **THEN** the documentation gate fails with the exact location

#### Scenario: Historical document uses legacy terminology

- **WHEN** a document classified as historical preserves an old term with explicit supersession metadata
- **THEN** the terminology gate permits it

The integrity command SHALL have a documented invocation and non-zero exit code for broken links, stale generated copies, missing registry membership, or active terminology violations.

### Requirement: Documentation Discoverability

README and contributor guidance SHALL describe the enforced documentation model and SHALL link to the authority registry, active product contract, architecture decisions, host installation guidance, and evaluation governance.

#### Scenario: New contributor starts from README

- **WHEN** a new contributor follows the repository documentation entry point
- **THEN** they can distinguish current product requirements, active changes, architecture decisions, generated packages, and historical records without inspecting source code
