## 1. Contract And Governance

- [x] 1.1 Define the strict evidence-admission boundary, explicit breaking
  API cutover, and #165 compiler/fixture non-goal.
- [x] 1.2 Register issue #168 / group 83 after verified group 82 with its
  exact source-removal acceptance command.

## 2. Focused Regression

- [x] 2.1 Add RED tests for legacy anchor parsing, omitted artifact reference,
  implicit class, legacy status, map resolver construction, and legacy exports.
- [x] 2.2 Rewrite the old map-only evidence contract coverage against the
  canonical RunLedger resolver.

## 3. Breaking Admission Cutover

- [x] 3.1 Remove legacy anchor serialization/parsing, status, default class,
  and provenance helper exports without a compatibility path.
- [x] 3.2 Remove map-backed resolver behavior and require ledger-bound content
  and selector metadata validation.
- [x] 3.3 Route the retained compiler's typed evidence normalization through
  the strict anchor parser; preserve #165's compiler and fixture boundary.

## 4. Verification And Handoff

- [ ] 4.1 Run group-83 focused, lint, formatting, OpenSpec, governance,
  documentation, package, and full regression checks.
- [ ] 4.2 Inspect and commit the green source cutover before recording any
  source-bound receipt; keep raw output local and ignored.
- [ ] 4.3 Record the source-bound group-83 receipt, mark verification complete,
  and rerun final checks.
