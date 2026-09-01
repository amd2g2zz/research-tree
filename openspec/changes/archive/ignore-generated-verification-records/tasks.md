## 1. Define the boundary

- [x] 1.1 Classify ephemeral verification output separately from normative
  OpenSpec and evaluation sources.
- [x] 1.2 Add precise ignore rules for generated verification and local tool
  output.

## 2. Enforce the boundary

- [x] 2.1 Write failing tests for the ignored destination and PR-added-record
  rejection.
- [x] 2.2 Route receipt generators to `.research-tree/verification-runs/` and
  reject tracked OpenSpec evidence destinations.
- [x] 2.3 Add the pull-request guard for force-added generated records.

## 3. Verify and hand off

- [x] 3.1 Run focused tests, layout/governance checks, package parity, and the
  full suite.
- [x] 3.2 Create follow-up issues for bounded historical artifact migrations.

## Verification note

The focused suite passed (`40 passed`). The full baseline suite reached
`627 passed, 1 failed`; the failure is the pre-existing group-60 committed
receipt digest mismatch in `tests/test_insight_digest.py`, reproduced on a
clean `origin/dev` checkout. It is intentionally assigned to the final
historical migration issue instead of being rewritten here.
