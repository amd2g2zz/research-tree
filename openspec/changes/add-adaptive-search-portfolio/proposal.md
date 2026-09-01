# Proposal: adaptive multi-engine portfolio + cross-comparison + evidence-driven recursion

## Why

Issue #476 (with the user directive addendum): multi-engine search must
proactively fan out across distinct available providers, batch results must be
cross-compared (provenance dedup + relevance), and the recursive descent's
continue/stop decision must be evidence-driven instead of depth-burning. The
`max_depth` hard guardrail keeps its value and force unchanged; it remains the
termination guarantee against infinite recursion. All changes affect only the
continue/stop decision within the guardrail.

## What Changes

- `IntentDerivedSearchPortfolioPlanner` plans must fan out across every
  distinct available provider (registry availability semantics unchanged:
  `unavailable` filtered, `degraded` selectable). Plans expose the measured
  `provider_fanout` count and fail closed if a plan does not cover every
  distinct available provider.
- NEW `research_tree.cross_comparison`: after each portfolio batch, captures
  are compared across providers. Deduplication reuses the provenance-clustering
  upstream identity (`cluster_provenance_components`, extracted verbatim from
  `ClaimAdmissionEvaluator._clusters`). Relevance is scored per provider
  against intent terms; measured `novelty`/`coverage`/`source_quality`/
  `contradictions` are written back into `MethodExecutionOutcome` fields
  (previously placeholders). `SearchPortfolioExecutor.run` accepts optional
  `captures`/`intent_terms` and applies the stage when declared; without them
  its behavior is byte-identical to before.
- `recursive_search` continues while (unresolved contradictions exist OR a
  coverage gap vs intent remains OR marginal novelty is above the declared
  threshold) and stops early inside the guardrail with `terminal_reason`
  `evidence-saturated`; a declared `transition_budget` stop reports
  `budget-exhausted`. `maximum depth guardrail reached` keeps its exact
  string, ordering-first position, and semantics as the hard backstop.
- Recursion-confidence damping model (addendum): per-ingest quality is
  measured on four dimensions (`expandability`, `completeness`,
  `heuristic_value`, `implicit_association`) with declared weights;
  `confidence(child) = confidence(parent) * (1 - damping)` with
  `damping = d_min + (d_max - d_min) * (1 - quality)` inside declared bands
  (0.05-0.35) - every recursion level loses confidence, never gains.
  Findings below `low_confidence_threshold` are quarantined
  (`cross_validation: required`) and cannot ground satisfied evidence until
  corroborated by an independent trusted finding sharing an anchor or an
  explicit verification pass; verification failures are recorded with
  attempts and reason, never dropped.
- Falsifiability receipts: every state carries `recursion_receipt` with
  per-run provider fan-out count, dedup ratio, `terminal_reason_distribution`
  (an all-`maximum depth` run is directly visible), confidence
  distribution + damping parameters, quarantine count, and cross-validation
  failure count. Tree-state validation accepts the two new state keys.

## Impact

- `gitnexus impact`: `execute` LOW (1), `apply_research_results` LOW (2),
  `prune_research_state` LOW (7), `evaluate_research_stop` LOW (7),
  `_grow_from_finding` LOW (7), `_slot_state` LOW (4), `_clusters` LOW (5),
  `plan` LOW (1, lower-bound), `run` UNKNOWN (confirmed by text search:
  no in-repo callers; change is additive optional kwargs only).

## Fix Round (review round 2 on PR #477)

- Producer wiring (H1/A-M1): `CanonicalFindingPackCompiler.compile` now carries
  the batch comparison into the Finding Pack payload (`search_comparison`
  with fanout/duplicates/captures/coverage_met/contradictions + a
  `comparison_status` of `measured`/`skipped`, fail-closed validation), so
  production packs feed `slot["contradiction_refs"]` and the receipt signals.
- Quarantine lift independence (H2/A-M3): corroboration now requires claim
  overlap with DISJOINT provenance clusters (via
  `cluster_provenance_components`); a same-source mirror no longer lifts.
- Quarantine containment (H3): `_slot_closure_deficit` counts trusted
  findings/anchors only (residual risk stays positive under quarantine), and
  ingest completeness is measured against a snapshot excluding the finding
  under judgment (no self-credit). Zero-signal completeness clamps to 0
  (M4), so `d_max` is reachable. Mandatory closure obligations re-open when
  their grounding is quarantined; a failed validation oracle grows the
  independent-method retry first.
- Receipt truthing (M5/M7/L9): `quarantine_count` is the live
  per-slot sum (ledger size renamed `cross_validation_records`); dedup
  totals single-count per batch (keyed by comparison id); missing/unknown
  source quality defaults to a conservative 0.5 and baseline aggregation is
  min.
- Per-slot novelty (M6): saturation consumes the slot's own latest-ingest
  marginal novelty, and once comparisons are recorded it is additionally
  gated on measured intent coverage (captured-but-never-complete stays a
  coverage gap).
- Tree-state schema bumped to 2 with the new required keys (L8).
