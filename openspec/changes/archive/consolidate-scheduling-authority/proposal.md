# Proposal: consolidate-scheduling-authority

## Why

issue #333: three parallel scheduling layers (dead orchestration.py, unwired
policy.py, production coordinator.dispatch). Every governance cycle had been
building beside the old layer instead of converging.

## What Changes

1. Delete `src/research_tree/orchestration.py` + all exports (no deprecation).
2. Wire `AdaptiveResearchPolicy` into `coordinator.dispatch` at the
   strategy-projection confirmation point: optional `policy=` constructor
   arg; top proposal id recorded as `policy_proposal_id` in lease lineage;
   no-policy behavior byte-identical.
3. ADR-006 records the decision, the 4-phase concept mapping, and the
   rejected retirement alternative.
4. tests/test_scheduling_authority.py (4 tests): export removal locked;
   no-policy backward compatibility; wired-policy consultation + lineage;
   rejection semantics unchanged with policy attached.

## Impact

- src/research_tree/{orchestration.py deleted, coordinator.py, __init__.py}
- docs/adr/ADR-006-single-scheduling-authority.md
- No runtime behavior change without opt-in `policy=`.
