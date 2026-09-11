# Tasks: risk-scaled-gates

## 1. Priority-scaled blocker subsets

- [x] 1.1 RED: a P2 slot with a shallow source, met evidence floor, and
  passed oracle presents an empty `closure_blockers` list while the
  drill-down stays scheduled (scenario: a P2 slot closes without landscape,
  mechanism, or coverage blockers).
- [x] 1.2 RED: the same shallow-source situation at P0 still names the
  shallow source depth and the frontier remnants and withholds the
  coordinator assessment (scenario: a P0 slot keeps the full blocker set).
- [x] 1.3 RED: a P1 slot's blockers are exactly {evidence floor, oracle} then
  exactly {coordinator assessment}; never landscape/mechanism/coverage
  (scenario: a P1 slot runs the middle blocker set).
- [x] 1.4 RED: a P1 slot with `landscape_gates: true` regains the
  shallow-source-depth blocker (scenario: a P1 slot can opt back into the
  landscape gates).
- [x] 1.5 GREEN: `recursive_search.py` — subset selection in
  `evaluate_research_stop`, `landscape_gates` compiled in `_slot_state`;
  producers (`_shallow_source_refs`, `_missing_mechanism_refs`,
  `_ensure_mechanism_drilldown`) untouched; full suite green.

## 2. Config profile

- [x] 2.1 RED: profile defaults load for small/standard/deep, the config
  round-trips, an unknown profile raises `ValueError`, and explicit fields
  beat the profile (scenarios: profile defaults load; unknown profile is
  rejected).
- [x] 2.2 RED: one finding satisfies a P2 slot's floor under `small` but not
  under `standard` (scenario: the profile scales the evidence floor at
  evaluation time).
- [x] 2.3 GREEN: `RecursiveSearchConfig` gains `profile`/`minimum_evidence`
  with the documented profile table; the evidence-floor and closure-deficit
  helpers take the resolved floor; full suite green.

## 3. Never-scaling gates

- [x] 3.1 RED: on a P2-only tree a stale-digest quality review, a malformed
  authority fingerprint, and an illegal phase transition are all still
  rejected (scenario: never-scaling gates still fire on a P2-only tree).
- [x] 3.2 GREEN: ADR in `design.md` records the never-scaling list (authority
  fingerprint, phase transitions, digest binding, evidence strict mode).

## 4. Gates and evidence

- [x] 4.1 Full local gates green: `uv run --frozen pytest -q`, ruff check +
  format, `check_delivery_workflow.py validate`, `check_openspec_governance.py`,
  `build_skill_packages.py --check`.
- [x] 4.2 GitNexus `impact` recorded pre-edit (LOW, 8 impacted,
  epistemic exact) and `detect-changes` output reconciled against the
  declared scope in `evidence/`.
