# Proposal: mechanism-level-research-depth

## Why

Issue #494: research treats "found a source" as done. Nothing requires drilling
from a found project into its principle/implementation, and the diversity check
deduplicates only on upstream provenance identity — so N projects that all do
the same thing in the same way are reported as "N distinct implementations"
because they have N different URLs. The user report (2026-09-02): multiple
near-identical projects were presented as five or six implementations, each
described only from its README. Landscape claims are fake-diverse and
mechanism-empty, so decision support fails exactly where it matters.

## What Changes

1. `search_portfolio.py`: a `SourceMechanism` contract record — what the
   approach *is* (`approach`), *how it works* (`how_it_works`), and evidence
   refs/kinds that must include at least one beyond the README
   (`code-inspected`, `design-doc`, `experiment`). `assess_acquisition_batch`
   gains a `mechanism_records` input and a promotion gate: a batch that would
   otherwise submit for closure (`stop`) is forced to `deepen` with a
   `require-source-mechanism` next action while captured sources lack a
   mechanism record; the uncovered refs are carried on the assessment
   (`missing_mechanism_refs`). A README-only record cannot be constructed, so
   a writeup that only restates a README fails promotion.
2. `cross_comparison.py`: mechanism-level clustering beyond provenance
   clusters. Captures may declare a `mechanism_summary`; equivalent summaries
   collapse into one mechanism cluster regardless of upstream identity,
   provenance-distinct captures with an equivalent mechanism are tagged as
   mechanism duplicates (explicit contrast), and the comparison reports
   `distinct_implementations` from mechanism clusters — not raw sources.
   Captures without a declared summary are reported as
   `undeclared_mechanism_capture_refs` so the gap is visible.
3. `recursive_search.py`: shallow source depth blocks closure instead of only
   downgrading a score. Finding Packs may declare per-source engagement
   (`sources: [{ref, depth}]`) and a `mechanism` record. Landscape slots
   (default; `landscape_required: false` opts out) record the deepest
   engagement per cited source: a source whose best engagement is still
   snippet/summary/none depth raises a named closure blocker, and a source
   engaged at full-source/experiment depth without a valid mechanism record
   blocks closure too; in both cases a mandatory `deep_dive` follow-up action
   is scheduled on the same source. Drilling the source clears the blockers.
4. Tests: scenario-named RED tests in `tests/test_search_portfolio.py`,
   `tests/test_cross_comparison.py`, and `tests/test_recursive_search.py`
   cover the issue's killer cases (N same-mechanism different-URL projects are
   not N distinct implementations; shallow depth blocks landscape-slot closure
   and schedules a deeper batch; promotion without a mechanism artifact
   fails).

## Capabilities

### New Capabilities

- `mechanism-level-research-depth`: mechanism artifacts per promoted source,
  mechanism-level cross-comparison clustering, and shallow-depth closure
  blockers for landscape slots.

### Modified Capabilities

- None (the touched payload schemas gain optional additive fields; version-1
  readers remain valid).

## Impact

- src/research_tree/search_portfolio.py: new `SourceMechanism`; promotion gate
  in `assess_acquisition_batch`; `BatchCoverageAssessment` schema v2 with two
  additive fields.
- src/research_tree/cross_comparison.py: `CaptureRecord.mechanism_summary`,
  `MechanismCluster`, mechanism duplicate tagging, `distinct_implementations`;
  `BatchCrossComparison` schema v2 with additive fields.
- src/research_tree/recursive_search.py: slot state gains
  `landscape_required`/`source_depths`/`mechanism_source_refs`/
  `closure_blockers`; Finding Pack payloads may declare `sources` and
  `mechanism`; closure evaluation grows two named blockers and the drill-down
  scheduler.
- No changes to alignment_graph.py, decision_frame.py, lifecycle_hook.py,
  tree_state.py, turn_contract.py, skill-src/**, references/**, or packages/**.
