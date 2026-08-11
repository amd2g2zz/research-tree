## ADDED Requirements

### Requirement: Verified task groups have source-bound receipts
The system SHALL accept a task group as `verified` only when its record contains
the task group's exact registered acceptance command, a successful exit code,
source revision, environment and output digests, retained raw-output evidence,
recorded timestamp, and rollback instruction.

#### Scenario: substituted command
- **WHEN** a verified group supplies `true` instead of its registered acceptance command
- **THEN** governance rejects the verification record

### Requirement: Receipt generation preserves raw output
The receipt helper SHALL execute only a registered task-group command and SHALL
write the command's combined output and matching digest before returning a
receipt record.

#### Scenario: passing registered command
- **WHEN** a registered focused test command exits zero
- **THEN** the helper emits a receipt whose output digest matches the retained output bytes

### Requirement: Verification reflects actual task boundaries
The task registry SHALL not mark an aggregate group verified for responsibilities
assigned to distinct later groups. A blocked group SHALL state its concrete
unmet boundary and successor work without being relabeled verified.

#### Scenario: incomplete strict evidence
- **WHEN** a group lacks mandatory default strict evidence enforcement
- **THEN** it remains non-verified with a successor reference

### Requirement: Integrated strict-slice evidence is separately traceable
The system SHALL record a source-bound integration receipt for a cross-issue
verification task. The receipt MUST list each merged slice (issue, pull request,
and merge revision), every validation command and retained raw output digest,
the unresolved future task groups, and the boundary that remains owned by the
OracleRun issue.

#### Scenario: merged slices and future gaps
- **WHEN** the integrated receipt is generated from a clean `dev` revision
- **THEN** it records the merged strict slices and keeps groups with missing
  acceptance paths in `planned` state

#### Scenario: legacy guard is not OracleRun closure
- **WHEN** the receipt includes the #109 worker-validation guard
- **THEN** it identifies #109 as a legacy guard and leaves #56/OracleRun open
