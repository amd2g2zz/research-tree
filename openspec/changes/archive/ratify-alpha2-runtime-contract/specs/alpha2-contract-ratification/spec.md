## ADDED Requirements

### Requirement: Alpha2 architecture decisions are explicitly ratified
The system SHALL publish ADR-002 through ADR-005 covering the sole completion
authority, separate graph boundaries, SQLite plus content-addressed storage,
and host adapters as event translators. Each ADR SHALL state context, decision,
consequences, rejected alternatives, and migration disposition.

#### Scenario: A contributor reviews completion authority
- **WHEN** the contributor reads the Alpha2 ADR index
- **THEN** ADR-002 identifies `ResearchRunCoordinator` as the only canonical
  lifecycle and completion authority and rejects host, worker, hook, and report
  completion claims

#### Scenario: A contributor reviews storage or host boundaries
- **WHEN** the contributor reads ADR-004 or ADR-005
- **THEN** the documents distinguish SQLite/CAS canonical storage from host
  projections and require host activity to enter canonical state as events

### Requirement: Ratification references remain executable
The repository SHALL validate that the four ADRs, Alpha2 lifecycle matrix,
capability specifications, delivery matrix, and issue #66 group mapping exist
and expose the required architectural boundaries.

#### Scenario: A required ADR is removed or incomplete
- **WHEN** a required ADR file or mandatory decision section is absent
- **THEN** the contract-ratification test fails before the issue can be closed

#### Scenario: An issue mapping drifts
- **WHEN** issue #66 no longer maps to task group 14 and its named OpenSpec
  change
- **THEN** the contract-ratification test fails with the mismatched mapping
