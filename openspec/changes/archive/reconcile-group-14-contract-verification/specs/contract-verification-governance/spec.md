## ADDED Requirements

### Requirement: Verified acceptance entrypoints resolve from source
The governance checker SHALL reject a verified task group when a repository-relative Python entrypoint named by its registered acceptance command is absent from the bound source tree. Planned groups SHALL NOT be rejected solely because their future entrypoint is not implemented yet.

#### Scenario: Verified command names a missing script
- **WHEN** a task group is marked verified and its acceptance command names a missing repository-relative Python script
- **THEN** governance reports a structured missing-acceptance-entrypoint violation and release readiness remains false

#### Scenario: Planned command names a future script
- **WHEN** a task group remains planned and its registered acceptance command names a future script
- **THEN** governance preserves the plan without treating the missing entrypoint as verification evidence

### Requirement: Contract group ownership is dependency-safe
The group 14 contract gate SHALL own only ratified architecture, lifecycle, and registry validation outputs, and the task dependency graph MUST remain acyclic. Outputs implemented by groups that depend on group 14 SHALL remain owned by those downstream groups.

#### Scenario: Downstream outputs are inspected
- **WHEN** maintainers inspect group 14 and groups 25-27
- **THEN** SourceCapture, NativeWorkflowRun, and SearchPortfolio work appears only in the downstream task groups and group 14 can be verified first

#### Scenario: Dependency cycle is introduced
- **WHEN** a primary group is changed to depend directly or transitively on one of its dependent groups
- **THEN** governance reports the dependency cycle and rejects the registry

### Requirement: Group verification is source-bound
A verified group 14 record SHALL contain the exact acceptance command, zero exit code, environment and output digests, immutable source revision, raw output reference, recorded time, evidence references, and rollback disposition.

#### Scenario: Complete receipt is recorded
- **WHEN** the contract acceptance command succeeds against a committed source revision
- **THEN** task verification records group 14 as verified with all receipt fields and leaves groups 25-27 planned

#### Scenario: Receipt omits source binding
- **WHEN** group 14 is marked verified without a valid source revision or raw output reference
- **THEN** governance rejects the verification record as incomplete
