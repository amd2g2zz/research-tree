# Proposal: structural-review-independence

## Why

Issue #471 closes the gate-3 residual reproduced by the v2 blind verifier:
independence was a string inequality between two self-declared payload fields,
so a coordinator could self-issue a review under a different name
(same-execution rename), and `revise_strategy` wrote a broad displayed
projection into the durable ledger after confirmation with no invalidation
marker. Write-time binding and explicit supersede semantics close both holes.

## What Changes

- Structural independence (#462 contract hardening, backward compatible for
  honest flows):
  - New `verification_principal(salt, verifier_identity, session_context)` —
    an HMAC-SHA256 binding of the declared identity pair keyed with a per-run
    secret salt the ledger generates at run creation
    (`run_principal_salts` table; lazily seeded for pre-existing runs) and
    hands out only through the registrar/gate channel
    (`RunLedger.verification_principal`). The registrar
    (`CompletionInputRegistrar.write_alignment_verification` /
    `write_delivery_review`) records the bound principal as the
    registration's durable `issuer` and in `issuer_evidence.principal` at
    write time.
  - New ledger read surface
    `RunLedger.completion_input_registration_principals(run_id)` exposes the
    durable issuer per current registration.
  - Production predicate `verify_independent_review_principal(verifier,
    session, *, issuer, principal)` requires both principals as mandatory
    keywords — a gate lookup miss fails closed; a review whose declared
    identity names the coordinator principal is self-issuance; the durable
    `issuer` must equal the recomputed run-salted binding. The two-argument
    `verify_identity_independent` remains as the #462 compatibility predicate
    and is not used by production call sites (enforced by a source-scan test).
  - Threat model (restated): tamper-evidence + channel separation +
    coordinator-principal exclusion, NOT proof of execution. Out-of-process /
    cross-session adversaries cannot mint from public material; the residual
    (same-process adversary reads the salt) is the tracked gate-3 boundary;
    the follow-up path is ledger-side attribution to a real subagent
    execution record.
  - The coordinator's display and delivery gates pass the durable principal,
    so a review written straight to the ledger under the legacy constant or
    the coordinator principal — the exact v2 rename attacks — now fails
    closed.
- Post-confirm write invalidation (`revise_strategy` supersede semantics):
  - Branch selection keys on the projection id's confirmation history (a
    `handoff_confirmed` event has ever named it), not the `latest_confirmed`
    snapshot — the snapshot is permanently None after the first supersede,
    which let a second post-confirm revision fall back to the legacy displayed
    branch (review A/B HIGH-1).
  - When history exists, `revise_strategy` appends the revision as an
    unconfirmed `draft` FIRST (fail-closed: the prior authority stays the
    latest valid display and the draft cannot display without the gate), then
    appends a `strategy-projection-invalidation` marker artifact (new schema-1
    kind with validator) naming the superseded revision's reference, display
    digest, and authority fingerprint. The marker is invalidation evidence in
    the run record; it has no dedicated diagnostics reader in this change.
  - The confirmation is void: `latest_confirmed` returns None after a
    post-confirm revision, so every completion gate fails closed until the
    superseding revision is re-displayed through the full #462 display gate
    (fingerprint-bound independent verification) and re-confirmed. The new
    lifecycle-matrix edge `("autonomous_research", "alignment_feedback") →
    ("alignment", "human")` lets the human return a post-supersede run to
    alignment so a legitimate fix-up can reach re-confirmation instead of
    permanently blocking `delivery_accepted`.
  - The `handoff_confirmed` transition guard now runs the content checks
    (digest, confirmation, authority fingerprint drift) before the displayed
    status check, so a tampered or replayed confirmation naming a superseded
    draft still fails with the named reason instead of an undifferentiated
    failure.
- New coordinator error/failed-guard reasons: `verifier_not_independent`
  (already named), `strategy_projection_not_displayed`.

## Impact

- Affected specs: `independent-subagent-review` (new requirements),
  `strategy-handoff` (new requirement).
- Affected code:
  - `src/research_tree/independent_review.py` (verification_principal,
    verify_identity_independent issuer binding)
  - `src/research_tree/completion_inputs.py` (COORDINATOR_ISSUER, write-time
    principal binding on both review writers)
  - `src/research_tree/run_ledger.py` (completion_input_registration_principals)
  - `src/research_tree/coordinator.py` (gates read durable principals,
    revise_strategy supersede semantics, guard ordering)
  - `src/research_tree/strategy_projection.py` (invalidation marker kind,
    schema, validator)
  - `src/research_tree/__init__.py` (exports)
- Tests: `tests/test_issue471_structural_independence.py` (attack
  regressions, red-first)
