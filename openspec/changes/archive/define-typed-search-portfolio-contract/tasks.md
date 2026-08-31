## 1. Contract And Governance

- [x] 1.1 Define the issue-local strict SearchPortfolio and MethodRegistry contract.
- [x] 1.2 Register planned group 48 / issue #163 without changing parent group 27.

## 2. Focused Regressions

- [x] 2.1 Create `tests/test_search_portfolio.py` with strict decoding and
  deterministic serialization regressions.
- [x] 2.2 Add method/provider independence, unavailable method, degradation,
  duplicate, unknown-field, and raw-query rejection regressions.

## 3. Typed Portfolio Implementation

- [x] 3.1 Implement immutable strict portfolio, subquestion, method selection,
  rejected method, reassessment, registration, and registry values.
- [x] 3.2 Validate registry-backed selections and expose deterministic
  method/provider independence inspection.
- [x] 3.3 Export the focused public contract without adding planning,
  persistence, policy, capture, coordinator, or CLI behavior.
- [x] 3.4 Add the versioned strict SearchPortfolio schema and example fixture
  to match the typed public payload, removing the superseded v1 schema and
  fixture.

## 4. Verification And Handoff

- [x] 4.1 Run the group-48 focused test and Ruff acceptance command.
- [x] 4.2 Run full tests, strict issue and umbrella OpenSpec validation,
  package check, governance check, and `git diff --check`.
- [ ] 4.3 Record a source-bound group-48 receipt only after merged delivery;
  keep group 48 planned in this issue branch.
