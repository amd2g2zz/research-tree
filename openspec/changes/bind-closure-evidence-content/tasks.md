## 1. Contract And Governance

- [x] 1.1 Define the issue-local content-binding and complete-Finding contract.
- [x] 1.2 Register group 46 / issue #160 as a planned Alpha2 child slice.

## 2. Focused Regressions

- [ ] 2.1 Replace shape-only closure fixtures with compact durable
  SourceCapture, AcquisitionReceipt, EvidenceArtifact, and origin graphs.
- [ ] 2.2 Add failing regressions for a shape-correct no-CAS graph and for
  caller omission of a current decision-bound contradictory Finding.
- [ ] 2.3 Preserve coverage for core evaluator authorization, oracle absence,
  stale references, and idempotent replay.

## 3. Content And Finding Admission

- [ ] 3.1 Resolve and validate exact current canonical evidence, receipt,
  capture, and origin relationships with matching ledger content bindings.
- [ ] 3.2 Derive the complete current decision Finding set and reject caller
  pruning or expansion before assessment append.
- [ ] 3.3 Make unverifiable evidence inconclusive without changing the
  `assess()` signature or adding #161 quality/currentness behavior.

## 4. Verification And Handoff

- [ ] 4.1 Run focused tests and Ruff checks for closure code and tests.
- [ ] 4.2 Run full tests, strict issue and umbrella OpenSpec validation,
  package check, governance check, and `git diff --check`.
- [ ] 4.3 Count non-generated changed lines; record group-46 verification only
  after its source-bound acceptance evidence is available.
