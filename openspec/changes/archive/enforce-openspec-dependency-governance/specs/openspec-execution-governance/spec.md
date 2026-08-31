## ADDED Requirements

### Requirement: Task group lifecycle is evidence-bearing
The repository SHALL maintain one versioned verification record for every
registered Alpha2 task group. The record SHALL use exactly one lifecycle state
from `planned`, `in_progress`, `blocked`, `unavailable`, `verified`, or
`superseded`. A `verified` record SHALL contain resolvable evidence references,
an acceptance-command receipt with zero exit code, environment digest, output
digest, and rollback disposition.

#### Scenario: Verified group has complete evidence
- **WHEN** a task group is declared `verified`
- **THEN** the validator accepts it only when its evidence and command receipt
  resolve and satisfy the registered completion contract

#### Scenario: Structural success cannot verify a group
- **WHEN** a task group has checked Markdown tasks but no valid verification record
- **THEN** the validator reports the group as incomplete rather than verified

#### Scenario: Unavailable evidence remains incomplete
- **WHEN** a group records an unavailable host or external dependency
- **THEN** the validator preserves its blocker and SHALL NOT treat the group as
  verified or release-ready

### Requirement: Verified groups have verified dependency closure
The validator SHALL reject a verified task group when any direct or transitive
dependency is absent, non-verified, or part of a cycle. Diagnostics SHALL name
the verified group, the violating dependency path, and the observed state.

#### Scenario: Direct dependency is incomplete
- **WHEN** group B is verified and directly depends on group A in `planned`
- **THEN** validation fails with the path `B -> A` and state `planned`

#### Scenario: Transitive dependency is incomplete
- **WHEN** group C is verified, depends on B, and B depends on A in `blocked`
- **THEN** validation fails with the path `C -> B -> A` and state `blocked`

#### Scenario: Dependency graph has a cycle
- **WHEN** two or more registered groups form a dependency cycle
- **THEN** validation fails before lifecycle verification and reports the cycle

### Requirement: Issue and capability ownership is resolvable
The repository SHALL maintain a checked-in issue execution map for every tracked
Alpha2 implementation issue. Each map entry SHALL identify one primary task
group, its owned capabilities, and its issue-scoped OpenSpec change. Every
group referenced by a delivery-matrix capability row SHALL exist and be owned
by the row's mapped issue or be explicitly listed as a supporting group.

#### Scenario: Delivery row references a missing group
- **WHEN** a capability row references group 25 and the task registry omits it
- **THEN** validation fails with a missing-group diagnostic

#### Scenario: Two issues claim one primary group
- **WHEN** two issue-map entries declare the same primary task group
- **THEN** validation fails with both issue identifiers and the conflicting group

#### Scenario: Capability owner mismatch is detected
- **WHEN** a capability row names an issue that does not own its task group
- **THEN** validation fails unless the issue map declares that group as support

### Requirement: Alpha2 graph has explicit non-cyclic boundaries
The Alpha2 registry SHALL distinguish deterministic cross-host harness and
release gates (#64) from paired baseline/candidate benchmark ownership (#84).
It SHALL distinguish alignment action selection (#59), DecisionFrame (#87),
correction invalidation (#73), and strategy projection/handoff (#85). The
validator SHALL reject the historical #69/#55 and #85/#64/#72 dependency cycles.

#### Scenario: Paired benchmark follows harness
- **WHEN** the #84 group is registered
- **THEN** it depends on the deterministic #64 harness group and has a distinct
  primary issue owner

#### Scenario: Strategy handoff does not depend on evaluation cycle
- **WHEN** the #85 group is registered
- **THEN** it depends only on its alignment/correction prerequisites and not on
  #64 or #72 solely to display or confirm a strategy

### Requirement: Governance report is deterministic and release-facing
The repository SHALL provide a read-only command that validates the governance
registries and emits deterministic JSON containing group states, unresolved
dependencies, issue mappings, capability coverage, and a release-ready verdict.
The command SHALL exit non-zero for any semantic governance violation.

#### Scenario: Valid registry report
- **WHEN** all registry references and verified dependency closures are valid
- **THEN** the command emits a stable report and zero exit code

#### Scenario: Invalid registry report
- **WHEN** any lifecycle, evidence, ownership, or graph invariant is violated
- **THEN** the command emits all deterministic diagnostics and exits non-zero
