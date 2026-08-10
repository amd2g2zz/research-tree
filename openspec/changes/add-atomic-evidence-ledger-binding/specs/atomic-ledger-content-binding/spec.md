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
