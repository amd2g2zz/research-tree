## 1. Contract and Governance

- [ ] 1.1 Register group 43, issue ownership, delivery matrix, and an exact
  focused acceptance command as planned.
- [ ] 1.2 Add strict typed models and schema validation for issuer-bound
  completion-input registrations.
- [ ] 1.3 Add red tests proving generic valid-looking role artifacts cannot
  enter a canonical registration.

## 2. Registration Boundary

- [ ] 2.1 Add an atomic, expected-revision registration writer that generic
  `RunLedger.append_artifact()` cannot impersonate.
- [ ] 2.2 Resolve exact refs, current revisions, quarantine, run identity,
  issuer identity, and role lineage before registration.
- [ ] 2.3 Make identical registrations replay-safe and reject stale, foreign,
  mixed-lineage, malformed, and replacement-issuer inputs without mutation.

## 3. Role Writers

- [ ] 3.1 Register only `SlotClosureAssessor.is_current()` closure assessments.
- [ ] 3.2 Migrate canonical insight, readiness, and evaluation writers to the
  dedicated issuer-bound registration boundary.
- [ ] 3.3 Add currentness and atomicity regressions for all four input roles.

## 4. Verification

- [ ] 4.1 Run the focused TDD command, Ruff, strict issue and umbrella OpenSpec
  validation, governance, package check, full regression, and diff check.
- [ ] 4.2 Record the source-bound group-43 receipt and mark only this child
  verified after its implementation commit.
