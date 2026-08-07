## 1. Discovery and SDD

- [x] 1.1 Create an independent #55 branch from clean
  `origin/dev@904ca6f9e1c254587e50bd5235be9b7b4997f396`.
- [x] 1.2 Run operational and evaluation-auditor black-box reviews of the prior
  candidate and record its non-replayable failure.
- [x] 1.3 Complete root-cause/TDD review; identify filler-report as the first
  real Alpha1 semantic replay.

## 2. TDD slice: replayable filler-report baseline

- [x] 2.1 Add a failing contract/replay test for a clean pinned Alpha1 checkout,
  actual Hermes package identity, headings-plus-padding fixture, and semantic
  `vulnerability_reproduced` receipt.
- [x] 2.2 Implement evaluator-only checkout, command receipt, fixture integrity,
  and Hermes filler-report replay without host package dependency.
- [x] 2.3 Record the redacted filler-report baseline output and rerun the focused
  replay suite.

## 3. Remaining confirmed Alpha1 defects

- [ ] 3.1 Add executable semantic fixtures for forged validation and missing
  evidence; do not treat opaque strings as oracle/evidence proof.
- [ ] 3.2 Add executable state/trace fixtures for empty frontier, active
  contradiction, repeated reconnaissance, and adapter-only completion.
- [ ] 3.3 Add deterministic provider-failure and crash-recovery boundary
  fixtures with an explicit lost/recovered obligation predicate.
- [ ] 3.4 Ensure all nine named #55 defects have a clean-checkout command,
  environment, package/input/output digests, and redacted receipt.

## 4. Delivery

- [ ] 4.1 Run focused replay/contract tests, full pytest, strict OpenSpec,
  governance, package parity, and local PR checks.
- [ ] 4.2 Run post-implementation operational and evaluation black-box replay;
  record gaps without calling baseline reproduction a fix confirmation.
- [ ] 4.3 Push this branch and create a Draft PR to `dev` when GitHub WRITE
  permission is available.
