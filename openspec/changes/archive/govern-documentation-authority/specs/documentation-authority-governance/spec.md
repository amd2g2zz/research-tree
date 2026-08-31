## ADDED Requirements

### Requirement: Documentation Authority Index
The repository SHALL maintain one discoverable registry that assigns each
governed documentation root a class, authority, canonical edit location,
audience, owner, lifecycle, update trigger, supersession rule, and validation
rule.

#### Scenario: Contributor finds a canonical edit source
- **WHEN** a contributor inspects a generated, historical, or normative document
- **THEN** the registry identifies its governing root and canonical edit source
- **AND** a generated copy is not treated as an authoring source

### Requirement: Lifecycle and Terminology Integrity
The documentation gate SHALL reject an active governed document that uses
retired delivery terminology without an explicit compatibility annotation and
shall allow historical or superseded records to preserve it.

#### Scenario: Historical RT record retains legacy wording
- **WHEN** a historical RT specification contains a retired delivery term
- **THEN** the gate permits it only when the registry supplies a resolvable
  supersession rule

### Requirement: Documentation Drift Gate
The documentation gate SHALL fail with deterministic path-specific diagnostics
for invalid registry data, missing governed-document membership, broken internal
links, generated package drift, and report/session-log classes outside their
registered roots.

#### Scenario: Generated package copy is stale
- **WHEN** canonical skill documentation changes without rebuilding packages
- **THEN** the gate fails and identifies the package provenance check

#### Scenario: Undocumented report is misplaced
- **WHEN** a tracked report or session log occurs outside its registered root
- **THEN** the gate fails and identifies the document path and governing rule

### Requirement: Documentation Discoverability
README and contributor guidance SHALL link to the authority index and explain
the relationship among product contracts, OpenSpec, ADRs, historical records,
authoring sources, generated packages, operations, and evaluation evidence.

#### Scenario: Contributor starts from README
- **WHEN** a contributor follows the repository entry point
- **THEN** they can locate the authority index and distinguish where current
  behavior is edited from generated or historical material
