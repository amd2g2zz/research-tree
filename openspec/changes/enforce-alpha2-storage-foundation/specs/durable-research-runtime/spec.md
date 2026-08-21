## ADDED Requirements

### Requirement: Workspace-scoped durable ledger
The system SHALL create a SQLite v1 ledger at the workspace-scoped Alpha2 path.
It MUST enable foreign keys, WAL, full synchronous durability, and a bounded
busy timeout on every connection. Schema creation MUST be idempotent and record
the applied schema version.

#### Scenario: A fresh workspace creates a ledger
- **WHEN** a caller opens a ledger for an empty workspace
- **THEN** the SQLite schema SHALL be created once with the required durability
  settings and migration record

### Requirement: Immutable lineage writes use optimistic concurrency
The ledger SHALL persist runs, immutable artifact revisions, parent references,
and events in a single transaction. A write MUST include the expected run
revision and SHALL fail without partial rows when the revision is stale.

#### Scenario: A stale writer appends an artifact
- **WHEN** the run revision has advanced after the writer's snapshot
- **THEN** the append SHALL reject with a conflict and preserve the committed
  artifact/event history unchanged

### Requirement: Event delivery is idempotent but not mutable
The ledger SHALL use the pair of run id and event id as an idempotency key.
Repeating an equivalent event SHALL return the stored event; reusing that key
with different canonical content SHALL be rejected.

#### Scenario: An event delivery is retried
- **WHEN** a caller appends the same event twice to one run
- **THEN** the ledger SHALL retain one immutable event and report a successful
  idempotent result

### Requirement: Reconstructed state validates all lineage
The ledger SHALL reconstruct a run as the existing domain snapshot and validate
artifact hashes, artifact parent references, and event artifact references.
It MUST reject corrupt or dangling persisted lineage instead of returning a
partial snapshot.

#### Scenario: A persisted parent reference is dangling
- **WHEN** a stored artifact parent points to a missing revision
- **THEN** loading the run SHALL fail with a storage-integrity error

### Requirement: Interrupted writes preserve the last committed history
The ledger SHALL make a write visible only after its transaction commits. A
failure before commit MUST leave the prior run revision and snapshot
reconstructable.

#### Scenario: An append fails before transaction commit
- **WHEN** a storage fault is injected after beginning an append transaction
- **THEN** reopening the ledger SHALL return the exact prior committed snapshot
