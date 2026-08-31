## 1. Red Tests

- [x] 1.1 Add a public `CanonicalReadinessVerifier` fault-injection fixture
  where Finding and Decision name a foreign Target and assert both strict
  gates fail.
- [x] 1.2 Keep a same-Target canonical readiness regression green.

## 2. Readiness Binding

- [x] 2.1 Pass the package-resolved Blueprint Target into strict evidence
  authorization.
- [x] 2.2 Reject foreign strict Findings and selected/conditional Decisions
  with actionable closure diagnostics.

## 3. Verification and Handoff

- [x] 3.1 Run focused and full regression suites, OpenSpec strict validation,
  package parity, and the delivery gate.
- [ ] 3.2 Mark this change complete, commit atomically, push the issue branch,
  and open the only PR for #117 targeting `dev`.
