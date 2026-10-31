# single-seat-verification

## Why

Issue #558 (T1 row 4, docs 01 A4): dual-seat adversarial evidence lands T2 (#564); T1 runs single-seat with a **mandatory counter-evidence quota** — every make-or-break claim gets ≥1 dedicated refutation-seeking round, and convergence is blocked while the quota is unmet (fail-closed). H4 first test: citation audit ≥95%.

## What changes

- `verification/seat.ts`: VerificationEngine —
  - **method-layer selection** per claim type (literature → multi-source cross + verbatim anchors; logic → fresh-context blind re-derivation; market/judgment → triangulation ≥3; empirical → pre-registered experiment [T2]);
  - **counter-evidence quota** audit + `assertConvergenceReady` gate;
  - **verdict promotion**: single-source claims stay honestly marked (`supported-single-source`), never promoted to plain supported (pinned);
  - **search envelope** disclosure (查了什么/没查什么/没查到什么);
  - every verification is a `provider.action` engine fact.
- Evidence sha256 content-addressing enforced on inputs.

## impact_scope

- `rt-core/src/verification/seat.ts` (new)
- tests: `rt-core/test/verification.test.ts`
