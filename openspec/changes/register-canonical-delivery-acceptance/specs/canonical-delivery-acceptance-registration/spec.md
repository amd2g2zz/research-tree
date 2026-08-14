## ADDED Requirements

### Requirement: Canonical delivery is a registered pair

The canonical ledger path SHALL register exactly one Technical Research
Package and one Human Research Report from the same run and expected revision.
The human surface SHALL name and parent the exact technical artifact revision.
Generic artifact append SHALL NOT create either registration.

#### Scenario: Generic lookalikes remain ordinary lineage

- **WHEN** a caller appends valid-looking technical, human, or acceptance
  payloads through the generic ledger API
- **THEN** no completion-input registration is created

#### Scenario: Pair append is atomic

- **WHEN** pair validation or commit fails
- **THEN** neither surface, registration, event, nor run-revision increment is
  visible

### Requirement: Delivery registration is exact and current

The writer SHALL reject mismatched pair refs, cross-run refs, stale parents,
quarantined parents, legacy human kinds, and replacement issuers before commit.

#### Scenario: A replacement or quarantined surface is submitted

- **WHEN** either delivery parent is no longer current or is quarantined
- **THEN** the pair is rejected without a partial registration

### Requirement: Acceptance binds the displayed pair

The typed acceptance writer SHALL require the exact `artifact_id@revision`
tokens, displayed-pair digest, shared manifest digest (or the deterministic
current-pair fallback), human actor, canonical kinds, and exact two-parent
lineage. A generic acknowledgement or non-human issuer SHALL NOT become an
acceptance registration.

#### Scenario: Acceptance is stale or forged

- **WHEN** a digest, actor, pair revision, parent, or issuer does not match
- **THEN** no delivery-acceptance artifact or registration is committed

#### Scenario: Matching acceptance is retried

- **WHEN** the same acceptance id, payload, and pair are written again
- **THEN** the original immutable acceptance is returned without a second
  registration or run-revision advance
