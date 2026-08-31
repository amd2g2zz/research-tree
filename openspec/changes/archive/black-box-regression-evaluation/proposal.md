# Proposal: black-box-regression-evaluation

## Why

issue #323: existing tests can encode evidence-free human beliefs as supported
readiness fields.  We need black-box fixtures that resist such pressure and
prove the Agent builds the correct problem topology.

## What Changes

NEW `src/research_tree/black_box_regression.py`:
- `BlackBoxFixture`: id / domain / prompt / expected_outcome / evidence_requirements
- `FixtureSuite`: bundles fixtures under one scenario (cognition / growth /
  disagreement per issue #323 acceptance)
- `parse_fixture(path)`: whitelist JSON loader
- `discover_fixtures(suite_id)`: built-in registry of issue-323 fixtures
- `score_run(fixture, run_record)`: requires every evidence_requirement to
  be present + truthy in run_record (rejects evidence-free beliefs as
  regressions)

## Impact

- src/research_tree/black_box_regression.py (new) — no behavior change to existing modules.

## Acceptance ↔ test
| Acceptance | Test |
|---|---|
| Suite covers cognition/growth/disagreement | test_discover_fixtures_returns_suites + test_discover_fixtures_filters_by_suite_id |
| Suite carries metadata | test_fixture_suite_carries_metadata |
| Evidence-free belief NOT promoted | test_black_box_fixture_requires_evidence_not_belief |
| Parser is whitelist | test_parse_fixture_loads_valid_record |
| Both topology and pressure-resistance required | test_score_run_requires_both_problem_topology_and_pressure_resistance |
