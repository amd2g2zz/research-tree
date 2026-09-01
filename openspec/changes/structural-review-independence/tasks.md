# Tasks: structural-review-independence

## 1. Structural independence

- [x] 1.1 Add `verification_principal` one-way identity-pair binding to
      `independent_review.py`
- [x] 1.2 Add `COORDINATOR_ISSUER` canonical coordinator principal to
      `completion_inputs.py` and use it for coordinator-authored registrations
- [x] 1.3 Bind the durable `issuer` principal at write time in
      `write_alignment_verification` and `write_delivery_review`
- [x] 1.4 Expose `RunLedger.completion_input_registration_principals`
- [x] 1.5 Harden `verify_identity_independent` (issuer parameter,
      coordinator-principal exclusion) and wire both coordinator gates to the
      durable principals

## 2. Post-confirm write invalidation

- [x] 2.1 Add `strategy-projection-invalidation` marker kind, schema version,
      and payload validator to `strategy_projection.py`
- [x] 2.2 Implement supersede semantics in `coordinator.revise_strategy`
      (marker + draft, never displayed post-confirm)
- [x] 2.3 Reorder the `handoff_confirmed` guard so content checks (including
      `authority_fingerprint_drift`) name the violated rule before the
      displayed-status check

## 3. Validation

- [x] 3.1 Attack regressions red-first in
      `tests/test_issue471_structural_independence.py` (rename attacks and
      post-confirm write attack fail before the fix, pass after)
- [x] 3.2 Existing #441/#443/#462 suites pass unmodified
- [x] 3.3 Full suite, ruff, layout, and openspec governance gates green
- [x] 3.4 GitNexus impact analysis and detect-changes gates run
