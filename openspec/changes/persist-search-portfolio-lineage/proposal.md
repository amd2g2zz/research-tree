## Why

The settled SearchPortfolio planner and executor currently produce pure values,
while the canonical runtime cannot prove how a portfolio's intent, methods,
captures, findings, assessment, and next decision relate to one worker
attempt.  That gap lets a worker finish without an auditable portfolio lineage
and prevents safe autonomous replanning from its assessment.

## What Changes

- Persist an immutable SearchPortfolio lineage projection through the existing
  coordinator and ledger, with exact references to captures, receipts,
  checkpoints, and findings.
- Require a worker-finished HostEvent to reference the persisted lineage and
  verify it belongs to the event's run and attempt.
- Route an in-authority pivot through the authorized CorrectionEvent and
  `apply_correction()` stale-state-quarantine path; block requester-controlled
  changes for an explicit pending human decision reopening.
- Register issue #187 as group 77, depending on verified groups 23, 25, 61,
  and 75, with source-bound verification evidence.

## Capabilities

### New Capabilities

- `canonical-search-portfolio-lineage`: Coordinator-owned persistence and
  validation of SearchPortfolio execution lineage and its bounded next action.

### Modified Capabilities

- None.

## Impact

Affected code is limited to the canonical coordinator/HostEvent boundary, a
focused lineage projection, and the SearchPortfolio, worker orchestration, and
coordinator tests.  This introduces no CLI route, legacy reader, acquisition
fallback, contract rewrite, execution-semantic change, or parent #83 closure.
