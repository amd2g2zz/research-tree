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
