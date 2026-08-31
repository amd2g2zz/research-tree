## Why

Acquired source material and bounded worker progress currently have no canonical
artifact contract, so a crash can force a successor to reacquire evidence or
accept a completion event without durable analysis state. Issue #80 adds the
smallest runtime boundary needed to make captures, receipts, checkpoints, and
completion ordering resumable and auditable.

## What Changes

- Add immutable SourceCapture and AcquisitionReceipt records bound to a run,
  attempt, CAS digest, acquisition method, provider, and provenance.
- Add bounded AnalysisCheckpoint records that reference committed captures and
  reject secrets, prompts, and private reasoning.
- Add a service that atomically persists CAS content before capture metadata and
  exposes deterministic resume/quarantine decisions.
- Require worker-finished payloads to carry the same-run checkpoint and capture
  references after durable persistence.

## Capabilities

### New Capabilities

- `durable-source-capture`: Source captures, acquisition receipts, bounded
  checkpoints, recovery, redaction, and completion ordering.

### Modified Capabilities

- `worker-orchestration`: Worker completion payloads require durable capture and
  checkpoint references from the same run and attempt.

## Impact

Adds a runtime module and exports, focused tests, and issue-local OpenSpec
evidence. Existing CAS and ledger rows remain compatible; rollback disables the
completion assertion while retaining historical immutable records.
