## ADDED Requirements

### Requirement: Completion consumes an exact registered manifold

The coordinator SHALL resolve completion from current typed completion-input
registrations, not from the latest artifact of each kind. Every P0 decision
slot SHALL have exactly one current passed closure token. Singleton insight,
readiness, evaluation, technical delivery, human delivery, and acceptance roles
SHALL have exactly one current registration; generic `append_artifact()` rows
SHALL NOT satisfy these fields.

#### Scenario: Generic lookalikes cannot complete a run

- **WHEN** a caller appends valid-looking completion artifacts through the
  generic ledger API
- **THEN** the lifecycle remains blocked and no completion record is created

#### Scenario: Missing or ambiguous registration is explicit

- **WHEN** a required role is absent or has multiple current registrations
- **THEN** completion is rejected and `why_not_complete` identifies that field
  with a deterministic diagnostic

### Requirement: Delivery acceptance binds the current pair

The coordinator SHALL require the human report to reference and parent the
exact technical package revision. Acceptance SHALL have exactly those two
parents, matching technical and human revision tokens, displayed pair digest,
manifest digest, accepted decision, and a human actor. Invalid references or
digests SHALL be reported as a field-level failure.

#### Scenario: Forged acceptance is rejected

- **WHEN** an acceptance has an extra parent, stale pair digest, malformed
  delivery reference, or non-human actor
- **THEN** the acceptance field remains unresolved and completion is blocked

### Requirement: Completion records are manifold-bound and reopen safely

The terminal completion record SHALL contain a canonical manifold and digest,
parent every resolved manifold input, and be idempotent for the same manifold.
If a resolved parent is superseded or quarantined after completion, the record
remains immutable but the current run SHALL expose the affected field and SHALL
NOT silently return the stale terminal result as a valid completion.

#### Scenario: A current parent is replaced or quarantined

- **WHEN** a registered completion parent is no longer current or is
  quarantined
- **THEN** `why_not_complete` reopens the corresponding obligation while the
  historical completion record remains present
