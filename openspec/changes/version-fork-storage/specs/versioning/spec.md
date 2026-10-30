## ADDED Requirements

### Requirement: drafts are the only writable state

Drafts hold the working set without hash, never entering the version line;
`freeze` is the only draft→version channel and fails closed without a draft.

#### Scenario: draft work never creates versions
- **WHEN** a draft is opened and mutated
- **THEN** the versions table stays empty and the draft has no hash

#### Scenario: freeze without a draft fails closed
- **WHEN** freeze is called for a task without a draft
- **THEN** it raises a ledger integrity error

#### Scenario: copy-on-write inherit
- **WHEN** a draft is opened from a committed version
- **THEN** the draft starts from a copy of that snapshot with base_v set

### Requirement: commits are immutable and whole

freeze hashes the entire snapshot (sha256, canonical JSON); v is per-task
monotonic; committed rows have no update path and re-hash under verification.

#### Scenario: partial commits do not exist
- **WHEN** a version is committed
- **THEN** its commit_hash verifies against the whole snapshot content

#### Scenario: identical re-commit is rejected
- **WHEN** a task freezes an unchanged snapshot twice
- **THEN** the second freeze raises a duplicate-commit integrity error

#### Scenario: raw-SQL tampering is detected
- **WHEN** a committed snapshot row is modified in place and verifyIntegrity runs
- **THEN** it raises a hash-mismatch integrity error

#### Scenario: append-only v sequence
- **WHEN** a version insert skips the per-task sequence
- **THEN** it is rejected naming the expected v

### Requirement: fork(v) creates a new task with inherited v0 and bidirectional lineage

#### Scenario: fork copies the source snapshot
- **WHEN** t1@v0 is forked to t2
- **THEN** t2@v0 carries the source snapshot and lineage resolves both directions (child→source, source→children)

#### Scenario: forks from nonexistent versions are refused
- **WHEN** a fork names a nonexistent source version
- **THEN** it raises a ledger integrity error

### Requirement: deleted nodes ride the snapshot

deleted_nodes are part of the committed snapshot (产物删除 auditable).

#### Scenario: deleted nodes are disclosed with the version
- **WHEN** a snapshot carries deleted_nodes and is frozen
- **THEN** the committed version exposes them
