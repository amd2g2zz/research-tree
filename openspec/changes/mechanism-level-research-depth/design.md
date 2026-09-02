## Context

Issue #494: the pipeline records that a source was found
(`MethodExecutionOutcome` with `disposition="captured"`) but never requires
drilling into it. `BATCH_SOURCE_DEPTH_LEVELS` already distinguishes
snippet/summary/full-source/experiment engagement and `assess_acquisition_batch`
reacts to shallow depth, but only for its own batch decision — the closure side
never sees it. `evaluate_research_stop` judges closure from finding/anchor
counts, so a slot whose evidence is all README-depth can still become a closure
candidate; the only depth floor anywhere is the report-manifest check (bytes +
headings). Cross-comparison dedup groups captures by provenance clusters
(upstream identity, `cluster_provenance_components`), so two *different*
projects with the same mechanism produce zero duplicates.

## Goals / Non-Goals

**Goals:** a promoted source carries a `mechanism` artifact (what the approach
is, how it works, evidence beyond the README); mechanism-level clustering in
cross-comparison with `distinct_implementations` counted from mechanism
clusters; shallow source depth blocks landscape-slot closure and schedules a
deeper follow-up batch on the same source.

**Non-Goals:** deliverable quality gates and pruning evidence retention (#495);
rewriting the provenance clustering in `claims.py` (mechanism clustering is an
additional layer); prompt-layer regeneration; new ledger artifact kinds
(mechanism records ride existing payload surfaces).

## impact_scope

Symbols modified (GitNexus blast radius, direction upstream, index rebuilt via
`run.cjs analyze` at branch tip c95c183 on this worktree; all LOW risk):

| Symbol | Direct upstream callers |
|---|---|
| `search_portfolio.assess_acquisition_batch` | `SearchPortfolioExecutor.execute`, tests |
| `search_portfolio.BatchCoverageAssessment` | `__init__`, coordinator, cli, delivery, ledger consumers |
| `search_portfolio.SearchPortfolioExecutor.run/execute` | coordinator, tests |
| `cross_comparison.compare_portfolio_batch` / `CaptureRecord` / `BatchCrossComparison` | `SearchPortfolioExecutor.run`, tests |
| `recursive_search.evaluate_research_stop` | `apply_research_results`, `initialize_research_state`, coordinator `ingest`/`recover`/`initialize` |
| `recursive_search.apply_research_results` / `initialize_research_state` | coordinator, `alignment_handoff` |
| `recursive_search._update_slot_evidence` / `_ensure_slot_frontier` / `_slot_state` | both ingest paths |

All changes are additive (new optional payload keys, fields with defaults,
blocker branches gated on newly declared data). Detect-changes reconciliation
against this table is recorded in `evidence/` before push.

## Decisions

### The mechanism contract is strict, the tree absorption is lenient

`SourceMechanism` validates on construction: non-empty `approach` and
`how_it_works`, unique non-empty `evidence_refs`/`evidence_kinds`, kinds from
`{readme, code-inspected, design-doc, experiment}`, at least one beyond the
README — a README-only record cannot exist, which is exactly the issue's
"restates a README" failure as a type error. `assess_acquisition_batch`
normalizes `mechanism_records` strictly (the batch assessment is the promotion
gate). The recursive-search absorption is lenient: a malformed finding-level
record means the source stays mechanism-missing and the drill-down is
scheduled, instead of rejecting a whole evidence batch — the drill-down loop
is the recovery path.

### The promotion gate blocks only the `stop` disposition

`assess_acquisition_batch` computes `missing_mechanism_refs` = captured refs
without a covering `source_ref`. When the final disposition is `stop` (the
submit-for-closure promotion) and refs are missing, it becomes `deepen` with
next action `require-source-mechanism`. Every other path (failures,
contradictions, cross-validation, incomplete coverage) already blocks
promotion; duplicating the gate there would only relabel existing blockers.
Direct `BatchCoverageAssessment` construction is untouched — the gate lives in
the assessment function, the pipeline's promotion validation surface.

### Mechanism clustering is a second layer over provenance clusters

Provenance clustering keeps its semantics and `duplicates` output. Captures
declaring equivalent normalized `mechanism_summary` values collapse into one
cluster regardless of upstream identity; provenance-distinct captures with an
equivalent mechanism are tagged in `mechanism_duplicates` against the cluster's
first capture (one honest duplicate tag per capture — provenance duplicates are
not re-tagged). `distinct_implementations` is the mechanism cluster count, so
the killer case (N different-URL projects, one mechanism) reports 1, not N.
Captures without a declared summary land in
`undeclared_mechanism_capture_refs` instead of pretending to be distinct
mechanisms. Novelty write-back participates: a mechanism-duplicate capture no
longer counts as a `new` unique identity for its outcome.

### Landscape requirement defaults on, with an explicit opt-out

Every slot's root action is a `landscape` action and the planner makes
mechanism coverage a P0 obligation for every slot, so `_slot_state` defaults
`landscape_required=True`; a slot mapping may opt out for oracles orthogonal to
landscape coverage. Only *declared* engagement counts: sources are known via
the finding payload's `sources` (`{ref, depth}`), which legacy Finding Packs do
not carry, so existing states are unaffected until depth is declared. The slot
records the *deepest* engagement per source — a source is drilled once engaged
at full-source/experiment depth, and re-declaring it shallowly later cannot
un-drill it. A source whose best engagement is still none/snippet/summary
raises the shallow-depth blocker; a deep source without a valid mechanism
record raises the mechanism blocker. The deeper follow-up batch is a mandatory
`deep_dive` node named after the source (identity-deduplicated), scheduled at
ingest so it is scored, pruned, and surfaced like any action.
`evaluate_research_stop` stays read-only for nodes, adds the two named
blockers to a per-slot observable `closure_blockers` list, and withholds the
slot from closure candidates while they stand.

### Rejected designs

- **Keyword matching on oracle text to detect landscape coverage**: fragile
  natural-language heuristics; the engine's style is structured flags (the
  root landscape action and the planner's mechanism coverage already exist).
- **Folding mechanism duplicates into `duplicates`**: would silently change
  `dedup_ratio` and provenance-duplicate semantics existing consumers rely on.
- **Raising on malformed finding-level records in `apply_research_results`**:
  discards an entire evidence batch over one optional record; lenient
  absorption plus drill-down recovers by asking for the real artifact.
- **Required `mechanism` field on Finding Packs**: legacy ledgers and the
  alignment-handoff baseline producer (owned by other agents) do not emit it;
  optional keys with fail-closed closure gates achieve the guarantee without
  breaking readers.
- **Only downgrading a score or hard-failing the batch on shallow depth**: the
  issue rejects both — a score penalty never blocks closure, and a hard
  failure leaves no drill-down path; blocker + mandatory follow-up action is
  the requested middle.

## Risks / Trade-offs

- [Producers that never declare `sources`/`mechanism` keep the old hole] -> the
  portfolio-level promotion gate still forces the drill-down at batch
  assessment time, and the closure blockers bite once depth is declared; #495
  builds on this surface next.
- [Drill-down nodes add frontier pressure] -> one node per named source,
  identity-deduplicated, mandatory so it survives pruning; bounded by the
  slot's distinct source count.
- [Schema version 2 on two payloads] -> additive only; `from_dict` decodes
  version 1 payloads by filling defaults, so persisted ledgers stay readable.

## Migration Plan

No data migration. New payload keys are optional; version 1 payloads decode
with defaults; gates apply only when the new data is declared.
