## 1. Contract And Governance

- [x] 1.1 Define the issue-local content-binding and complete-Finding contract.
- [x] 1.2 Register group 46 / issue #160 as a planned Alpha2 child slice.

## 2. Focused Regressions

- [x] 2.1 Replace shape-only closure fixtures with compact durable
  SourceCapture, AcquisitionReceipt, EvidenceArtifact, and origin graphs.
- [x] 2.2 Add failing regressions for a shape-correct no-CAS graph and for
  caller omission of a current decision-bound contradictory Finding.
- [x] 2.3 Add missing and tampered evidence, capture, and origin CAS regressions,
  plus a raw content-bound legacy-evidence rejection.
- [x] 2.4 Add invalid strict-selector and escaped repository-locator regressions.
- [x] 2.5 Add a malformed direct decision-Finding parent regression.
- [x] 2.6 Add an unverifiable repository-revision regression.
- [x] 2.7 Preserve coverage for core evaluator authorization, oracle absence,
  stale references, and idempotent replay.
- [x] 2.8 Add cross-run, stale direct-parent, and mixed receipt/capture lineage
  regressions from the issue contract.

## 3. Content And Finding Admission

- [x] 3.1 Resolve and validate exact current canonical evidence, receipt,
  capture, and origin relationships with matching ledger bindings and CAS bytes.
- [x] 3.2 Reuse strict evidence resolution for canonical selector and locator admission.
- [x] 3.3 Derive the complete current decision Finding set and reject caller
  pruning or expansion before assessment append.
- [x] 3.4 Make unverifiable evidence inconclusive without changing the
  `assess()` signature or adding #161 quality/currentness behavior.

## 4. Verification And Handoff

- [x] 4.1 Run focused tests and Ruff checks for closure code and tests.
- [x] 4.2 Run full tests, strict issue and umbrella OpenSpec validation,
  package check, governance check, and `git diff --check`.
- [x] 4.3 Count non-generated changed lines; record group-46 verification only
  after its source-bound acceptance evidence is available.
