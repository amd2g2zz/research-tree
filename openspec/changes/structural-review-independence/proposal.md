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
  - New `verification_principal(verifier_identity, session_context)` — a
    one-way SHA-256 binding of the declared identity pair, namespaced by the
    #462 review issuer. The registrar (`CompletionInputRegistrar.
    write_alignment_verification` / `write_delivery_review`) records the bound
    principal as the registration's durable `issuer` and in
    `issuer_evidence.principal` at write time.
  - New ledger read surface
    `RunLedger.completion_input_registration_principals(run_id)` exposes the
    durable issuer per current registration.
  - `verify_identity_independent` gains an optional `issuer` parameter: a
    verification whose declared identity names the coordinator principal is
    self-issuance and never independent, and a gate that supplies the
    registration's durable principal requires it to equal the write-time
    binding of the declared pair. Unbound, legacy-constant, and coordinator
    principals fail closed. Two-argument #462 call sites keep their honest
    behavior.
  - The coordinator's display and delivery gates pass the durable principal,
    so a review written straight to the ledger under the legacy constant or
    the coordinator principal — the exact v2 rename attacks — now fails
    closed.
- Post-confirm write invalidation (`revise_strategy` supersede semantics):
  - When a confirmed projection exists, `revise_strategy` no longer writes
    `displayed`: it appends a `strategy-projection-invalidation` marker
    artifact (new schema-1 kind with validator) that names the superseded
    projection reference, display digest, and authority fingerprint, then
    writes the revision as an unconfirmed `draft` parented to the marker.
  - The confirmation is void: `latest_confirmed` returns None after a
    post-confirm revision, so every completion gate fails closed until the
    new revision is re-displayed through the full #462 display gate
    (fingerprint-bound independent verification) and re-confirmed.
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
