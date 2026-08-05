## ADDED Requirements

### Requirement: Canonical run state is stored transactionally in SQLite
The system SHALL persist all runs in one workspace-scoped SQLite RunLedger at `.research-tree/run-ledger.sqlite3`; every canonical row is keyed by `run_id`. The ledger SHALL enforce foreign keys, WAL, full synchronization, busy timeout, and expected-revision checks. Artifact append SHALL advance the run revision and emit one canonical `artifact_appended` event in the same transaction.

#### Scenario: Concurrent host events target the same revision
- **WHEN** two events attempt to advance the same run revision
- **THEN** exactly one transaction commits and the stale event is rejected or idempotently recognized

#### Scenario: Stored lineage references a missing parent
- **WHEN** an artifact revision is submitted with an unresolved parent reference
- **THEN** the transaction is rejected without partially appending the artifact or event

### Requirement: Large artifacts use tamper-evident content-addressed storage
The system SHALL store large documents, source snapshots, binaries, images, and experiment outputs in a SHA-256 content-addressed store and SHALL bind ledger metadata to the exact digest, media type, size, and locator. CAS ingestion SHALL reject source paths outside the workspace and persist bounded metadata alongside each blob.

#### Scenario: Content changes after ingestion
- **WHEN** a stored artifact no longer matches its recorded digest
- **THEN** integrity verification fails and all dependent unclosed work is reopened or blocked

### Requirement: One coordinator owns lifecycle transitions
The system SHALL allow only `ResearchRunCoordinator` to transition canonical lifecycle state, close Decision Slots, register readiness, request delivery acceptance, supersede a round, or complete a run.

#### Scenario: Host adapter reports all tasks finished
- **WHEN** a host emits worker-finished events for every dispatched action
- **THEN** the coordinator ingests the events but does not complete the run unless all canonical closure and delivery requirements pass

#### Scenario: A report file exists without canonical decisions
- **WHEN** technical and human Markdown files are present but no closed Decision Ledger supports them
- **THEN** the coordinator rejects delivery registration and the run remains non-complete

### Requirement: Recovery is exact, replayable, and idempotent
The system SHALL reconstruct the latest committed state, mark uncertain in-flight attempts explicitly, replay unconsumed artifacts once, and produce the same state digest after repeated recovery.

#### Scenario: Process crashes after artifact persistence but before state projection
- **WHEN** restart finds a committed Finding Pack absent from the latest consumed set
- **THEN** recovery ingests it exactly once and appends the next deterministic state revision

#### Scenario: Process crashes during an external worker attempt
- **WHEN** no authoritative completion event exists for the active attempt
- **THEN** recovery marks the attempt unknown and requires reconciliation or a new attempt identity

### Requirement: Operational limits create checkpoints, not successful completion
The system SHALL treat provider, token, concurrency, wall-clock, and local execution limits as resumable pause or method-switch conditions and SHALL NOT use monetary cost as a research completion criterion.

#### Scenario: Host context is exhausted with open P0 obligations
- **WHEN** an operational limit is reached while a P0 Decision Slot remains unclosed
- **THEN** the system persists a resumable checkpoint and does not emit completion

### Requirement: Legacy state is imported without inheriting trust
The system SHALL import alpha1 filesystem rounds, alignment databases, native checkpoints, and Hermes checkpoints idempotently while marking legacy findings, validation, closure, and delivery claims with explicit verification dispositions.

#### Scenario: Legacy run claims completion using a structural report gate
- **WHEN** migration imports an alpha1 run whose reports passed only byte and heading checks
- **THEN** the reports remain historical artifacts and the alpha2 run cannot complete until current closure and readiness requirements pass

### Requirement: SQLite scope, migration, and CAS consistency are fixed

Alpha2 SHALL use the workspace database and CAS layout defined by the design, with schema_migrations, foreign keys, unique event and digest constraints, staged CAS writes, orphan quarantine, and explicit WAL/locking behavior on Windows and POSIX.

#### Scenario: Import encounters a conflicting legacy id

- **WHEN** two legacy stores map to one canonical id with different bytes or lineage
- **THEN** migration records conflict and quarantines both candidates until an operator disposition is persisted

#### Scenario: CAS write succeeds but database commit fails

- **WHEN** a staged blob is not referenced by a committed ledger transaction
- **THEN** it remains quarantined and cannot influence evidence, and a later GC may remove it only after the retention window

### Requirement: Migration has verifiable operations

Migration SHALL expose inventory, dry-run, apply, verify, rollback, and status operations and SHALL report source digest, destination refs, disposition (imported, legacy_unverified, quarantined, conflict, or already_imported), and operator confirmation.

#### Scenario: Migration is repeated

- **WHEN** the same source digest is imported again
- **THEN** the operation is idempotent and reports already_imported without duplicate canonical revisions
