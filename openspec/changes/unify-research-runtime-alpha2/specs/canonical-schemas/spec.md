## ADDED Requirements

### Requirement: A checked-in contract registry is the schema source

The change SHALL contain a checked-in contract registry under schemas/ (or a ratified equivalent) for all canonical entities and SHALL validate it in CI before any runtime implementation is accepted.

#### Scenario: A new entity is introduced

- **WHEN** an implementation adds a persisted or host-facing entity
- **THEN** it adds a versioned schema, valid example, invalid example, owner, and migration note
- **AND** contract validation fails if any of those artifacts is missing

#### Scenario: Runtime and schema disagree

- **WHEN** a serialized runtime object does not validate against its registered schema
- **THEN** the object is rejected before persistence or host emission

### Requirement: Canonical entity fields and references are exact

The registry SHALL define required fields, optional fields, enum values, uniqueness constraints, reference cardinality, and digest rules for InputRecord, PermissionProfile, AlignmentMessage, AlignmentHandoff, FeedbackEvent, ResearchRun, BlueprintTarget, DecisionSlot, ResearchAction, WorkItem, AttemptLease, EvidenceArtifact, EvidenceAnchor, OracleSpec, OracleRun, SlotClosureAssessment, InsightDigest, ReadinessRecord, HostEvent, DeliveryManifest, DeliveryAcceptance, and ReleaseManifest.

`AlignmentHandoff` SHALL bind the exact Alignment Graph, Working Brief, and
Intent Model refs to the objective, execution context, alignment digest,
strategy digest, and explicit confirmation record. The confirmation record
contains the human actor id, response digest, displayed strategy digest, and
UTC confirmation time. `BlueprintTarget` SHALL carry exact refs to the same
Working Brief and Intent Model and to that handoff; its artifact parent set
must resolve to those three revisions.

#### Scenario: Evidence anchor is submitted

- **WHEN** an anchor is validated
- **THEN** it contains artifact_digest, artifact_revision, selector_type, selector_value, extractor_version, applicability, confidence, and limitations
- **AND** the selector type determines the required selector shape

#### Scenario: Reference cardinality is violated

- **WHEN** a P0 Slot has no required oracle reference or a delivery claim has no evidence reference
- **THEN** validation fails with a field-level error and cannot be marked complete

#### Scenario: Handoff confirmation is not bound to the displayed strategy

- **WHEN** the confirmation's displayed digest differs from the handoff's
  strategy digest
- **THEN** contract validation fails before coordinator initialization

### Requirement: Schema versions have a compatibility matrix

Every schema version SHALL declare supported readers, writers, lossless migration functions, deprecation date, and rejection behavior. Protocol, package, template, and database versions SHALL be cross-referenced in one compatibility matrix.

#### Scenario: Older artifact is read

- **WHEN** an alpha1 artifact is loaded by alpha2
- **THEN** it is imported through a named migration disposition and the original bytes/digest remain retrievable

#### Scenario: Unsupported future artifact is read

- **WHEN** a future version has no registered reader
- **THEN** loading fails explicitly and does not downgrade the version or infer fields

### Requirement: Examples exercise positive and negative paths

Each schema SHALL have canonical examples covering the smallest valid object, a complete P0 object, and at least one invalid object for missing reference, stale revision, contradictory evidence, and illegal terminal transition.

#### Scenario: Contract tests are generated

- **WHEN** CI runs contract validation
- **THEN** examples are parsed, normalized, hashed, and checked against the same validators used by runtime ingestion
