## ADDED Requirements

### Requirement: Durable source captures and receipts

Every successful acquisition SHALL persist verified CAS bytes before an
immutable SourceCapture and AcquisitionReceipt, preserving locator, digest,
media type, selector, license/access note, parser version, and provenance.

#### Scenario: Duplicate bytes retain distinct provenance
- **WHEN** two attempts acquire identical bytes
- **THEN** CAS stores one object while both capture and receipt records retain
  distinct attempt and method provenance.

#### Scenario: Capture is interrupted before ledger commit
- **WHEN** staged bytes exist without a committed capture
- **THEN** recovery classifies the attempt as `capture_incomplete` and does not
  expose the bytes as accepted evidence.

### Requirement: Bounded analysis checkpoints

An AnalysisCheckpoint SHALL reference only committed or explicitly unavailable
captures and SHALL contain scope, facts, hypotheses, contradictions,
unresolved questions, method outcomes, and next actions without prompts,
credentials, secrets, or private reasoning.

#### Scenario: Checkpoint resumes after a crash
- **WHEN** a worker crashes after checkpoint persistence and before Finding Pack
- **THEN** a successor can resolve the checkpoint and its capture refs without
  blind reacquisition.

#### Scenario: Sensitive checkpoint content is supplied
- **WHEN** a checkpoint contains a prompt, credential, or private reasoning key
- **THEN** validation rejects it before persistence.

### Requirement: Completion ordering and same-run binding

`worker_finished` SHALL be accepted only when its capture and checkpoint refs
belong to the same run and attempt and all referenced records are committed.
Incomplete or mismatched attempts SHALL receive a durable `capture_incomplete`
disposition and a next action.

#### Scenario: Completion arrives before checkpoint
- **WHEN** a worker-finished event has no committed checkpoint
- **THEN** the event is rejected/quarantined and cannot mark the worker complete.

#### Scenario: Completed attempt is rehydrated
- **WHEN** the process restarts with committed capture, receipt, and checkpoint
- **THEN** the exact records and digests are returned idempotently for resume.
