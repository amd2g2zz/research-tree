## 1. Mechanism artifact contract (RED first)

- [x] 1.1 RED: `SourceMechanism` accepts a valid beyond-README record and
  rejects empty approach/how-it-works, mismatched or duplicate evidence refs,
  unknown evidence kinds, and README-only evidence (scenario: a README-only
  mechanism record is rejected).
- [x] 1.2 RED: `assess_acquisition_batch` without mechanism records for
  captured sources forces `deepen` + `require-source-mechanism` on a
  would-be-`stop` batch and names `missing_mechanism_refs` (scenario:
  promotion without a mechanism artifact fails).

## 2. Mechanism artifact contract (GREEN)

- [x] 2.1 `search_portfolio.py`: `SourceMechanism`, evidence-kind constants,
  assessment `mechanism_records` input, promotion gate, `BatchCoverageAssessment`
  schema v2 with additive fields and v1 read compatibility.
- [x] 2.2 GREEN: sections 1.1-1.2 pass; a covered batch keeps `stop`;
  existing portfolio suites stay green.

## 3. Mechanism clustering (RED first)

- [x] 3.1 RED: two different-URL captures with equivalent mechanism summaries
  collapse into one mechanism cluster, tag a mechanism duplicate, report
  `distinct_implementations == 1`, and do not credit the duplicate outcome
  `new` novelty (scenario: N same-mechanism different-URL projects do not
  count as N distinct implementations).
- [x] 3.2 RED: different mechanisms stay distinct; summary-less captures are
  reported undeclared and do not inflate the count; provenance duplicates are
  not double-tagged; the comparison round-trips canonically at schema v2 and
  still decodes v1.

## 4. Mechanism clustering (GREEN)

- [x] 4.1 `cross_comparison.py`: `CaptureRecord.mechanism_summary`,
  `MechanismCluster`, mechanism duplicate tagging, `distinct_implementations`,
  `undeclared_mechanism_capture_refs`, novelty participation, schema v2 with
  v1 read compatibility.
- [x] 4.2 GREEN: sections 3.1-3.2 pass; existing cross-comparison suites stay
  green.

## 5. Shallow-depth closure blockers (RED first)

- [x] 5.1 RED: a Finding Pack declaring a snippet-depth source blocks
  landscape-slot closure with a named blocker and schedules a mandatory
  drill-down action naming the source (scenario: shallow depth blocks
  landscape-slot closure and schedules a deeper batch).
- [x] 5.2 RED: a full-source source with a README-only mechanism record keeps
  the mechanism blocker; drilling to full-source/experiment depth with a valid
  record clears both blockers; `landscape_required=false` slots are exempt;
  legacy findings without declared sources are unaffected.

## 6. Shallow-depth closure blockers (GREEN)

- [x] 6.1 `recursive_search.py`: slot state fields (`landscape_required`,
  `source_depths`, `mechanism_source_refs`), finding payload absorption,
  `_ensure_mechanism_drilldown` scheduling at both ingest paths, and the two
  named blockers in `evaluate_research_stop`.
- [x] 6.2 GREEN: sections 5.1-5.2 pass; existing recursive-search suites stay
  green.

## 7. Gates and evidence

- [x] 7.1 Full local gates green: `uv run --frozen pytest -q`, ruff check +
  format, `check_delivery_workflow.py validate`, `check_openspec_governance.py`,
  `build_skill_packages.py --check`.
- [x] 7.2 `impact-scope.json` recorded; GitNexus `detect-changes` output
  reconciled against the declared scope and stored in `evidence/`.
