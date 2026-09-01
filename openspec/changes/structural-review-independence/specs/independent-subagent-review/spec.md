# Delta: independent-subagent-review

## ADDED Requirements

### Requirement: Reviews carry a write-time bound ledger principal

The typed registrar SHALL record, as the durable `issuer` of every
`alignment-verification` and `delivery-review` completion-input registration,
a principal derived at write time from the declared `verifier_identity` and
`session_context`: an HMAC-SHA256 of the declared identity pair keyed with a
per-run secret salt the ledger generates at run creation and hands out only
through the registrar/gate channel, and SHALL repeat the principal in
`issuer_evidence.principal`.

Threat model: this is tamper-evidence, channel separation, and
coordinator-principal exclusion — NOT proof of subagent execution. Because
the salt is secret, an out-of-process or cross-session adversary cannot mint
a principal from public material. The residual — an adversary executing
inside the coordinator process with full ledger access can read the salt —
is the tracked gate-3 boundary (unsupervised same-process authorization);
the follow-up path is ledger-side attribution of reviews to a real subagent
execution record.

#### Scenario: Registrar binds the declared identity pair into the durable principal

- **WHEN** an alignment verification or delivery review is registered through
  the typed registrar
- **THEN** the registration's recorded `issuer` equals the run-salted HMAC
  binding of the payload's declared identity pair, and `issuer_evidence`
  carries the same principal

### Requirement: Gates judge independence against the durable principal

The alignment display gate and the delivery review gate SHALL judge
independence with a production predicate that requires both the
registration's durable `issuer` and the gate-recomputed principal as mandatory
arguments: a present registration whose principal cannot be resolved is not
independent (lookup miss fails closed), a review whose declared identity
names the coordinator principal is self-issuance, and a registration whose
durable principal is not the run-salted binding of the payload's declared
identity pair fails closed (`independent_verification_required` /
`verifier_not_independent`). The two-argument #462 predicate remains for
compatibility and is not used by production call sites.

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

#### Scenario: A minted principal cannot satisfy the gate

- **WHEN** a review registration is appended under a principal minted from
  public material (the pre-#471 bare-SHA-256 scheme) or under a foreign salt
- **THEN** the display gate rejects with `independent_verification_required`,
  because the run-salted HMAC binding of the declared pair differs

#### Scenario: A registration whose principal cannot be resolved fails closed

- **WHEN** a review registration is present in the gate's listing but absent
  from the principal map
- **THEN** the production predicate receives a missing issuer and rejects as
  not independent

#### Scenario: Honest registrar flow keeps passing

- **WHEN** a review is registered through the typed registrar with distinct
  declared identities
- **THEN** the display (respectively delivery) gate accepts it without any
  change to the #462 caller contract

### Requirement: Post-confirm revision requires explicit invalidation

A post-confirm revision SHALL NOT be written `displayed`: once the projection
id carries confirmation history (a `handoff_confirmed` event has ever named
it — keyed on history, not the `latest_confirmed` snapshot), `revise_strategy`
MUST first append the revision as an unconfirmed `draft` and then append a
`strategy-projection-invalidation` marker artifact naming the superseded
revision's reference, display digest, and authority fingerprint. The
confirmation SHALL be void until the superseding revision passes the full
independent display gate and is re-confirmed; the marker is invalidation
evidence in the run record (surfaced through the artifact record, not a
dedicated diagnostics reader in this change).

#### Scenario: Post-confirm broad revision is not displayed

- **WHEN** authority fields are widened through `revise_strategy` after
  confirmation
- **THEN** the revision is persisted as `draft`, a marker artifact naming the
  superseded revision is present, and no authoritative confirmed projection
  remains

#### Scenario: Every later post-confirm revision stays draft

- **WHEN** `revise_strategy` runs again on a once-confirmed projection whose
  `latest_confirmed` snapshot is already void
- **THEN** the branch keys on confirmation history, the new revision is
  persisted as `draft`, and a second marker names the superseded draft

#### Scenario: The new revision cannot ride the old verification

- **WHEN** the post-confirm revision's authority content is re-displayed
  without a fresh independent verification
- **THEN** the display gate rejects with `independent_verification_required`
