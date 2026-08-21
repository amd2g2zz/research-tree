## ADDED Requirements

### Requirement: Parent completion acceptance binds reachable child evidence

The parent completion-integrity acceptance SHALL require groups 43, 44, and
45 as dependencies, SHALL verify their source-bound receipt revisions are
reachable from the parent source revision, and SHALL map Issue #149 to group
36 without reusing a child group or receipt.

#### Scenario: All child receipts are reachable
- **WHEN** group 36 acceptance runs after groups 43, 44, and 45 are merged
- **THEN** it verifies each child receipt revision is an ancestor of the
  parent source revision and reports the parent group as independently
  verifiable

#### Scenario: A child receipt is not reachable
- **WHEN** a required child receipt revision is absent from the parent history
- **THEN** parent acceptance fails before it can record or claim group-36
  verification

### Requirement: Parent acceptance rejects false completion and proves reopen

The parent acceptance SHALL run the canonical completion-manifold regressions
that prove generic ledger artifacts cannot satisfy completion, registered
canonical inputs complete idempotently, and a superseded or quarantined parent
reopens the current manifold without deleting immutable completion history.

#### Scenario: Generic artifacts imitate completion inputs
- **WHEN** generic artifacts have the same kinds and payload shapes as
  completion inputs but have no typed registrations
- **THEN** the coordinator reports incomplete diagnostics and creates no new
  completion record

#### Scenario: A registered parent becomes stale
- **WHEN** a previously valid registered completion input is superseded or
  quarantined after completion
- **THEN** the current manifold reopens with deterministic field diagnostics
  while the historical completion record remains immutable

### Requirement: Group 36 evidence is parent-only and source-bound

Group 36 SHALL be recorded only after the final parent acceptance source
commit, SHALL retain local generated-output references with the exact command,
revision, and digests, and SHALL close only Issue #149.

#### Scenario: Parent verification is recorded
- **WHEN** the group-36 acceptance command exits successfully at the final
  parent source revision
- **THEN** the verification registry records group 36 as verified with that
  command receipt and the parent-only evidence references
