# Tasks: adaptive multi-engine portfolio + cross-comparison + evidence-driven recursion

- [x] Extract `cluster_provenance_components` from `ClaimAdmissionEvaluator._clusters` (claims.py) with byte-identical behavior
- [x] Add `research_tree.cross_comparison` (CaptureRecord, identity groups, duplicates, relevance, measured outcomes, apply-back) reusing claims clustering
- [x] Add plan fan-out contract: `provider_fanout` + fail-closed distinct-provider coverage (search_portfolio.py)
- [x] Wire optional `captures`/`intent_terms` into `SearchPortfolioExecutor.run` (no-op when undeclared)
- [x] Add `RecursiveSearchConfig` declared constants: transition_budget, novelty threshold, damping band, quality weights, low-confidence threshold
- [x] Measure per-ingest quality (expandability/completeness/heuristic/implicit association) and damp node confidence
- [x] Quarantine low-confidence findings; corroboration + verification pass/fail recording
- [x] Evidence-driven prune order: depth guardrail (unchanged) -> budget -> saturation -> existing thresholds
- [x] Emit `recursion_receipt` falsifiability signals; extend tree-state validation keys
- [x] Red-first tests: tests/test_adaptive_portfolio.py, tests/test_cross_comparison.py, tests/test_adaptive_recursion.py
- [x] Full suite green, ruff check + format clean, openspec validate --strict
- [x] Fix round: pack compile carries search_comparison + comparison_status (H1); claim-overlap + distinct-cluster corroboration (H2); quarantine-aware deficit + self-excluded completeness (H3); zero-signal clamp (M4); live quarantine_count (M5); per-slot novelty + measured coverage gate (M6); conservative source-quality default + min aggregation (M7); tree-state schema 2 (L8); per-batch dedup single-count (L9)
