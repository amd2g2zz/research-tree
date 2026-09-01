## ADDED Requirements

### Requirement: Typed contradiction classification

The system SHALL compare normalized canonical claims at admission, recall,
revision, experiment, and feedback boundaries through one typed detector.
Version, platform, time, scope, condition/default mode, modality, polarity,
value interval, precondition, and effect dimensions SHALL remain explicit.

#### Scenario: Scope separates claims

- **WHEN** incompatible values apply to non-overlapping versions, platforms,
  times, condition modes, or modalities
- **THEN** the packet is `scope-separated` and names every separating dimension

#### Scenario: Overlap conflicts

- **WHEN** applicability overlaps and authority values are incompatible
- **THEN** the packet is `contested`, both values remain visible, and neither
  participating claim is decision-authoritative

### Requirement: Resolution authority is immutable

Packets and resolutions SHALL be append-only revisions. Resolutions SHALL
preserve packet, prior-resolution, resolver, evidence, transition, selected
claim, and authority lineage.

#### Scenario: Resolution is superseded

- **WHEN** a terminal resolution is later superseded
- **THEN** historical revisions remain queryable and current authority blocks
  every formerly participating claim until a valid new terminal resolution

### Requirement: Propagation fails closed

An active contested or unresolved packet SHALL revoke dependent decisions,
readiness, delivery claims, closure assessments, durable beliefs, and pending
actions. It SHALL cancel unstarted dependent attempts, quarantine started
attempts, create successor work, and reopen delivered state.

#### Scenario: Dependent state is invalidated

- **WHEN** a selected decision depends on a newly contested claim
- **THEN** retraction lineage records stale descendants and readiness/delivery
  diagnostics name the packet and claim IDs

#### Scenario: Terminal resolution does not revive history

- **WHEN** an exact decision revision was invalidated by a retraction
- **THEN** readiness and delivery still reject it until fresh decision lineage
  descends from a terminal resolution

### Requirement: Propagation is atomic and retryable

Ledger propagation SHALL commit as one batch keyed by contradiction identity
and exact claim set. A failure before commit SHALL leave no partial authority
change; a durable-controller failure after commit SHALL recover without a
duplicate packet or retraction.

#### Scenario: Retry after controller failure

- **WHEN** the packet is committed but durable retraction fails
- **THEN** retry retracts once and leaves packet/retraction revision counts
  unchanged

### Requirement: Packets render deterministically

The system SHALL render packet identity, lifecycle, exact normalized claims,
source passages and provenance, tested scope, conflicting values, invalidated
revisions, successor path, safe fallback, and blocked operations without
mutable run state.
