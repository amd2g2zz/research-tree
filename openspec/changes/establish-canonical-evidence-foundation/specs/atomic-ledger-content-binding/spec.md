## ADDED Requirements

### Requirement: Atomic content-bound artifact publication

The system SHALL provide a `RunLedger` operation that verifies a supplied
content-addressed object, appends one immutable artifact revision, registers
its canonical content metadata, binds that exact revision to the content
digest, records an immutable lineage event, and increments the run revision in
one SQLite transaction. The operation MUST require an expected run revision
and MUST reject an optional stale expected artifact revision before any
authoritative row is committed.

#### Scenario: A verified capture is atomically published

- **WHEN** a caller supplies available, digest-valid CAS content and the
  current run revision
- **THEN** the ledger SHALL expose the artifact, its exact content binding, its
  lineage event, and the incremented run revision together after commit

#### Scenario: A stale writer attempts atomic publication

- **WHEN** the supplied expected run or artifact revision is stale
- **THEN** the operation SHALL reject the write and preserve the prior run
  revision, artifacts, bindings, and events unchanged

### Requirement: Interrupted atomic publication has no authoritative partial state

The system SHALL make the artifact, content metadata, binding, event, and run
revision visible only after the enclosing SQLite transaction commits. A failed
content verification or injected pre-commit failure MUST leave no newly
authoritative artifact, binding, event, or run revision.

#### Scenario: Commit fails after transaction writes begin

- **WHEN** a fault is injected before commit after an atomic publication has
  begun
- **THEN** reopening the ledger SHALL return exactly the snapshot and run
  revision that existed before the operation

### Requirement: Exact bindings survive restart without collapsing provenance

The system SHALL read an artifact and its bound content by exact
`ArtifactRef` after reopening a workspace. Two distinct artifact revisions MAY
bind the same digest, and the ledger MUST preserve both artifact identities and
their distinct payload/provenance metadata.

#### Scenario: Equal bytes are captured under two artifact identities

- **WHEN** two successful publications bind the same verified digest to
  different artifact identifiers or payload metadata
- **THEN** each exact artifact reference SHALL resolve after restart and both
  bindings SHALL retain the shared digest without replacing either artifact

### Requirement: Canonical evidence identity is an immutable ledger artifact

The system SHALL serialize an authoritative `EvidenceArtifact` inside one
immutable `evidence-artifact` ledger revision. A canonical `EvidenceAnchor`
MUST carry the exact resulting `ArtifactRef`, digest, and revision. The
repository SHALL reject evidence whose declared content digest, byte size, or
media type does not match the supplied verified CAS object.

#### Scenario: A canonical capture is published and reopened

- **WHEN** a caller provides an explicit evidence class and matching CAS
  content to the evidence repository
- **THEN** reopening the ledger SHALL reconstruct the same artifact metadata
  from the anchor's exact `ArtifactRef`

#### Scenario: Equal bytes arrive from distinct sources

- **WHEN** two canonical evidence artifacts bind the same digest with distinct
  locators or provenance groups
- **THEN** their exact artifact references and serialized provenance SHALL
  remain distinct

### Requirement: Generic legacy anchors remain explicitly non-authoritative

The system SHALL encode a non-canonical anchor as `legacy_unverified` and
MUST require an explicit compatibility-reader opt-in to deserialize it. The
system MUST NOT implicitly convert a generic legacy anchor into a canonical
`ArtifactRef` anchor.

#### Scenario: A caller reads imported generic evidence

- **WHEN** the caller requests legacy compatibility explicitly
- **THEN** the anchor SHALL remain marked `legacy_unverified` and contain no
  authoritative artifact reference
