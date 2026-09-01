# Delta: independent-subagent-review

## ADDED Requirements

### Requirement: Reviews carry a write-time bound ledger principal

The typed registrar SHALL record, as the durable `issuer` of every
`alignment-verification` and `delivery-review` completion-input registration,
a principal derived at write time from the declared `verifier_identity` and
`session_context` (a one-way binding namespaced by the review issuer), and
SHALL repeat the principal in `issuer_evidence.principal`. The registrar
SHALL reject an empty principal.

#### Scenario: Registrar binds the declared identity pair into the durable principal

- **WHEN** an alignment verification or delivery review is registered through
  the typed registrar
- **THEN** the registration's recorded `issuer` equals the write-time binding
  of the payload's declared identity pair, and `issuer_evidence` carries the
  same principal

### Requirement: Gates judge independence against the durable principal

The alignment display gate and the delivery review gate SHALL judge
independence against the registration's durable `issuer` principal: a
verification whose declared identity names the coordinator principal is
self-issuance and never independent, and a registration whose durable
principal is not the write-time binding of the payload's declared identity
pair fails closed (`independent_verification_required` /
`verifier_not_independent`).

#### Scenario: Same-session rename with an unbound principal is rejected

- **WHEN** an alignment verification is appended straight to the ledger under
  the legacy review-issuer constant while its payload declares two differing
  identity names
- **THEN** the display gate rejects with `independent_verification_required`

#### Scenario: Coordinator-principal self-issuance is rejected

- **WHEN** a review registration is appended with the coordinator's canonical
  principal as its issuer
- **THEN** both the display gate and the delivery gate reject as
  not independent

#### Scenario: Honest registrar flow keeps passing

- **WHEN** a review is registered through the typed registrar with distinct
  declared identities
- **THEN** the display (respectively delivery) gate accepts it without any
  change to the #462 caller contract

### Requirement: Post-confirm revision requires explicit invalidation

A post-confirm revision SHALL NOT be written `displayed`: once an
authoritative confirmed projection exists, `revise_strategy` MUST append a
`strategy-projection-invalidation` marker artifact naming the superseded
projection reference, display digest, and authority fingerprint, and MUST
write the revision as an unconfirmed `draft` parented to the marker. The
confirmation SHALL be void until the new revision passes the full independent
display gate and is re-confirmed.

#### Scenario: Post-confirm broad revision is not displayed

- **WHEN** authority fields are widened through `revise_strategy` after
  confirmation
- **THEN** the revision is persisted as `draft`, a marker artifact naming the
  superseded projection is present, and no authoritative confirmed projection
  remains

#### Scenario: The new revision cannot ride the old verification

- **WHEN** the post-confirm revision's authority content is re-displayed
  without a fresh independent verification
- **THEN** the display gate rejects with `independent_verification_required`
