## ADDED Requirements

### Requirement: Typed canonical completion inputs are issuer-bound

The system SHALL admit closure, insight, readiness, and evaluation evidence to
a canonical completion-input registration only through a typed registrar. Every
registered role SHALL contain an exact current artifact reference, a dedicated
issuer reference, the owning run identifier, and the ledger revision at which
the registration committed. Generic artifact append SHALL NOT create either a
completion-input registration or its issuer record.

#### Scenario: Generic artifacts resemble valid completion evidence

- **WHEN** a caller appends structurally valid closure, insight, readiness, or
  evaluation artifacts through the generic ledger writer
- **THEN** the registrar rejects them without creating a canonical registration

#### Scenario: Dedicated writer registers exact current evidence

- **WHEN** a dedicated role writer submits a current artifact and its matching
  issuer under the expected ledger revision
- **THEN** the registrar commits one immutable registration bound to those refs

### Requirement: Completion-input admission is atomic and replay-safe

The registrar SHALL validate run identity, current revision, role schema,
lineage, issuer replacement, quarantine, and role currentness before mutation.
It SHALL commit all role registrations atomically and return the existing
registration for an identical replay.

#### Scenario: One submitted role is stale or foreign

- **WHEN** a registration contains a stale, superseded, quarantined, foreign,
  malformed, or mixed-lineage role ref
- **THEN** the registrar rejects the request and commits no registration rows

#### Scenario: A valid request is replayed

- **WHEN** the same valid typed registration is submitted with the same
  idempotency identity
- **THEN** the registrar returns the original immutable registration without
  appending another one

### Requirement: Closure currentness is delegated to the closure assessor

The closure role SHALL be admitted only when
`SlotClosureAssessor.is_current()` returns true for the exact stored assessment.
The registrar SHALL NOT reimplement closure graph or token-currentness rules.

#### Scenario: A closure token is stale after evidence changes

- **WHEN** a passed closure assessment no longer replays as current
- **THEN** closure registration is rejected without relying on its status or
  token string alone
