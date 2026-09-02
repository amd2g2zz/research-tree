## Context

Issue #494: the acquisition pipeline records that a source was found
(`MethodExecutionOutcome` with `disposition="captured"`) but never requires
drilling into it. `BATCH_SOURCE_DEPTH_LEVELS` already distinguishes
snippet/summary/full-source/experiment engagement, and
`assess_acquisition_batch` (search_portfolio.py:1525) reacts to shallow depth —
but only by choosing a `deepen` disposition for *its own batch decision*; the
closure side never sees it. `evaluate_research_stop` (recursive_search.py)
judges closure from finding/anchor counts, so a slot whose evidence is all
README-depth can still become a closure candidate. The only depth floor
anywhere is the report-manifest check (`_report_manifest`: bytes + headings),
satisfied by a shallow writeup. Cross-comparison dedup groups captures by
provenance clusters (upstream identity, `cluster_provenance_components` in
claims.py), so two *different* projects with the same mechanism produce zero
duplicates and inflate the "distinct implementations" story.

## Goals / Non-Goals

**Goals:**

- A promoted source must carry a `mechanism` artifact: what the approach is,
  how it works, and evidence beyond the README (code inspected, design doc, or
  experiment). README-only writeups fail promotion.
- Mechanism-level clustering in cross-comparison: equivalent mechanisms merge
  or are explicitly contrasted; "distinct implementations" is a mechanism
  cluster count.
- Shallow source depth blocks closure for landscape slots and schedules a
  deeper follow-up batch on the same source, instead of only penalizing a
  score.

**Non-Goals:**

- Coordinator/CLI closure wiring, quality gates on deliverables, or pruning
  evidence retention (#495 owns the deliverable quality gate and combines with
  this change later).
- Rewriting the provenance clustering in `claims.py` (unchanged; mechanism
  clustering is an additional layer, not a replacement).
- Prompt-layer regeneration: no `skill-src/`, `references/`, or `packages/`
  changes in this change.
- Persisting new artifacts: mechanism records ride existing payload surfaces
  (batch assessments, finding packs); no new ledger artifact kinds.

## impact_scope

Symbols modified (GitNexus blast radius, direction upstream, index rebuilt via
`run.cjs analyze` at branch tip c95c183 on this worktree):

| Symbol | Risk | Direct upstream callers | Affected processes |
|---|---|---|---|
| `search_portfolio.assess_acquisition_batch` | LOW | `SearchPortfolioExecutor.execute`, tests | batch assessment |
| `search_portfolio.BatchCoverageAssessment` | LOW | `__init__`, coordinator, cross_comparison, cli, delivery, ledger consumers | batch assessment |
| `cross_comparison.compare_portfolio_batch` | LOW | `SearchPortfolioExecutor.run` | batch cross-comparison |
| `cross_comparison.CaptureRecord` | LOW | `compare_portfolio_batch`, tests | batch cross-comparison |
| `cross_comparison.BatchCrossComparison` | LOW | `apply_cross_comparison`, tests | batch cross-comparison |
| `recursive_search.evaluate_research_stop` | LOW | `apply_research_results`, `initialize_research_state`, coordinator `ingest`/`recover`/`initialize` | recursive search stop |
| `recursive_search.apply_research_results` | LOW | coordinator `ingest`, `recover` | recursive search ingest |
| `recursive_search.initialize_research_state` | LOW | `alignment_handoff`, coordinator | recursive search init |
| `recursive_search._update_slot_evidence` | LOW | `apply_research_results`, `initialize_research_state` | evidence ingest |
| `recursive_search._ensure_slot_frontier` | LOW | `apply_research_results`, `initialize_research_state` | frontier growth |
| `recursive_search._slot_state` | LOW | `initialize_research_state` | slot bootstrap |

All changes are additive (new optional payload keys, new fields with defaults,
new blocker branches gated on newly declared data). Detect-changes
reconciliation against this table is recorded in `evidence/` before push.

## Decisions

### The mechanism contract is strict, the tree absorption is lenient

`SourceMechanism` validates on construction: `approach` and `how_it_works` are
non-empty, `evidence_refs`/`evidence_kinds` are parallel non-empty unique
sequences, kinds come from `{readme, code-inspected, design-doc, experiment}`,
and at least one kind must be beyond the README — a README-only record cannot
exist, which is exactly the issue's "restates a README" failure mode expressed
as a type error. `assess_acquisition_batch` normalizes its `mechanism_records`
strictly (invalid records raise), because the batch assessment is the
promotion gate. The recursive-search slot absorption is lenient: a finding
payload's `mechanism` mapping that fails validation is treated as *not
covered* (the source stays mechanism-missing and the drill-down is scheduled),
rather than rejecting the whole evidence batch — the drill-down loop is the
recovery path, and a malformed record must not lose the batch's other
evidence.

### The promotion gate blocks only the `stop` disposition

`assess_acquisition_batch` computes `missing_mechanism_refs` = captured refs
without a covering `source_ref`. When the final disposition is `stop` (the
submit-for-closure promotion) and refs are missing, the disposition becomes
`deepen` with next action `require-source-mechanism`. Every other path
(failures, contradictions, cross-validation, incomplete coverage) already
blocks promotion; duplicating the gate there would only relabel existing
blockers. Explicitly-passed dispositions via direct `BatchCoverageAssessment`
construction are untouched — the gate lives in the assessment *function*,
which is the pipeline's promotion validation surface.

### Mechanism clustering is a second layer over provenance clusters

Provenance clustering (same upstream identity) keeps its semantics and its
`duplicates` output. Mechanism clustering groups captures that declare
equivalent `mechanism_summary` values (whitespace/case-normalized), regardless
of upstream identity. A capture that is already a provenance duplicate is not
re-tagged as a mechanism duplicate (one honest duplicate tag per capture);
provenance-distinct captures with an equivalent mechanism are tagged in
`mechanism_duplicates` against the cluster's first capture — the explicit
contrast the issue asks for. `distinct_implementations` is the mechanism
cluster count, so the killer case (N different-URL projects, one mechanism)
reports 1, not N. Captures without a declared summary land in
`undeclared_mechanism_capture_refs` instead of pretending to be distinct
mechanisms. Novelty write-back participates: a mechanism-duplicate capture no
longer counts as a `new` unique identity for its outcome.

### Landscape requirement defaults on, with an explicit opt-out

Every decision slot's root action is a `landscape` action ("The evidence
landscape is mapped...") and the portfolio planner makes mechanism coverage a
P0 obligation for every slot, so `_slot_state` defaults
`landscape_required=True`; a slot mapping may pass `landscape_required=false`
for oracles orthogonal to landscape coverage. Only *declared* engagement
counts: sources are known through the finding payload's `sources`
(`{ref, depth}`) key, which legacy Finding Packs do not carry — so existing
states and tests are unaffected until depth is actually declared. Declared
`none`/`snippet`/`summary` depth is shallow; a source engaged at
full-source/experiment depth without a valid mechanism record blocks closure
on the mechanism requirement. The deeper follow-up batch is a mandatory
`deep_dive` node named after the source (identity-deduplicated by
`_add_node`), scheduled at ingest so it is scored, pruned, and surfaced on the
frontier like any other action. `evaluate_research_stop` stays read-only for
nodes and adds the two named blockers, excluding the slot from closure
candidates while they stand; drilling the source (full-source/experiment depth
plus a valid mechanism record) clears both blockers.

### Rejected designs

- **Keyword matching on the slot's oracle text to detect "landscape"
  coverage**: fragile natural-language heuristics; the engine's established
  style is structured flags (the root landscape action and the planner's
  mechanism coverage already exist as structure). An explicit
  `landscape_required` opt-out keeps the default honest without parsing prose.
- **Folding mechanism duplicates into the existing `duplicates` tuple**: would
  silently change `dedup_ratio` and provenance-duplicate semantics that
  existing consumers and tests rely on; a separate `mechanism_duplicates`
  surface keeps both layers auditable.
- **Raising on malformed finding-level mechanism records inside
  `apply_research_results`**: would discard an entire evidence batch because
  one optional record is malformed; the lenient absorption plus drill-down
  scheduling recovers by asking for the real artifact.
- **Schema bump to a required `mechanism` field on Finding Packs**: legacy
  ledgers and the alignment-handoff baseline producers (owned by other
  agents) do not emit it; optional keys with fail-closed gates at the closure
  surface achieve the same guarantee without breaking readers.
- **Downgrading only the score (status quo) or hard-failing the whole batch on
  shallow depth**: the issue explicitly rejects both — a score penalty never
  blocks closure, and a hard failure gives the agent no drill-down path; the
  closure blocker + mandatory follow-up action is the middle that matches the
  requested behavior.

## Risks / Trade-offs

- [Producers that never declare `sources`/`mechanism` keep the old hole] ->
  the portfolio-level promotion gate (`missing_mechanism_refs`) still forces
  the drill-down at batch assessment time, and the recursive-search blockers
  bite as soon as depth is declared; #495's deliverable quality gate builds on
  this surface next.
- [Drill-down nodes add frontier pressure] -> one node per named source,
  identity-deduplicated, mandatory so it survives pruning; bounded by the
  distinct source count of the slot.
- [Schema version 2 on the two comparison/assessment payloads] -> additive
  only; `from_dict` still decodes version 1 payloads by filling defaults, so
  persisted ledgers remain readable.

## Migration Plan

No data migration. New payload keys are optional; version 1 payloads decode
with defaults; gates apply only when the new data is declared. OpenSpec change
archives after merge along the repository convention.
