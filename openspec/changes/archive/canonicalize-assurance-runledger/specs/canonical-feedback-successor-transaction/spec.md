## ADDED Requirements

### Requirement: Feedback successors SHALL commit both runs atomically

The canonical ledger SHALL provide a dedicated operation that creates one
successor run and appends ordered artifact batches to that successor and its
exact predecessor in one SQLite transaction. The operation SHALL require a
non-negative expected predecessor revision, reject an existing successor
identifier, and emit `run-created` plus one `artifact-appended` event for every
new artifact.

#### Scenario: A valid successor is persisted

- **WHEN** the predecessor revision matches and every parent reference is
  resolvable from immutable ledger state or an earlier entry in the transaction
- **THEN** the successor record, both ordered batches, all parent rows, all
  lineage events, and both run revisions SHALL become visible together

#### Scenario: A stale or invalid successor request is submitted

- **WHEN** the predecessor revision is stale, the successor already exists, a
  later entry has an invalid parent, or commit fails
- **THEN** neither run SHALL gain an artifact or event and no successor record
  SHALL remain
