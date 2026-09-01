## ADDED Requirements

### Requirement: Canonical host events are the only append path

The runtime SHALL reject the former generic event-ingestion arguments and
shall persist host observations only after `HostEvent.from_value()` and the
coordinator's canonical lease/revision checks.

#### Scenario: Arbitrary payload bypass is attempted

- **WHEN** a caller supplies `run_id`, `event_id`, `attempt_id`, arbitrary
  `payload`, and `expected_revision` without a complete HostEvent
- **THEN** the call returns `host_event_envelope_required` and changes no
  ledger revision or artifact

### Requirement: Lease, revision, and causal lineage are current

An accepted event SHALL reference the current active, unexpired attempt lease,
the current ledger revision, and the next attempt sequence. Every sequence
after one SHALL name its immediately preceding event in `causation_id`.

#### Scenario: Lease or causal lineage is stale

- **WHEN** an event uses an inactive/expired lease, a stale revision, or a
  missing/mismatched predecessor
- **THEN** the coordinator rejects it with a stable reason and performs no
  partial write

### Requirement: Worker completion proves durable evidence

`checkpoint_persisted` and `worker_finished` SHALL resolve exact current
artifact revisions. `worker_finished` SHALL require committed same-run,
same-attempt SourceCapture, successful AcquisitionReceipt, AnalysisCheckpoint,
Finding Pack, and produced-artifact references; path existence or local adapter
state is not evidence.

#### Scenario: Completion arrives before durable evidence

- **WHEN** a worker-finished event omits or misbinds a capture, receipt,
  checkpoint, finding, or produced artifact
- **THEN** the event is rejected before mutation with a capture/receipt/
  checkpoint/finding reference disposition

### Requirement: Accepted events remain atomic and replayable

The event and non-authoritative projection SHALL be appended in one ledger
transaction. Exact duplicate events SHALL replay idempotently; changed semantic
reuse SHALL conflict; a crash before commit SHALL expose neither half.

#### Scenario: Append crashes before commit

- **WHEN** fault injection interrupts the event/projection batch
- **THEN** recovery sees no partially accepted event and can retry the same
  envelope
