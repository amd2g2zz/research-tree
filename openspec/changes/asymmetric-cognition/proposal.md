# Proposal: asymmetric-cognition

## Why

issue #315: cognition was a single global score. Branch-level alignment is required because the agent's confidence in different branches of the problem tree diverges — a single scalar cannot capture this.

## What Changes

NEW `src/research_tree/cognition.py`:
- `CognitionState` composes 4 forest spaces (requester/agent/shared-via-filter/evidence) into a unified projection.
- `compute_alignment_per_branch(state) -> dict[str, AlignmentScore]` (per-branch, never a global scalar).
- `compute_understanding_debt(state)` returns `UnderstandingDebt` summary.
- `catch_up_triggers(state)` returns sequence of catch-up obligations per branch.
- `DisclosureTrigger` enum for transparency rules.

## Impact

src/research_tree/cognition.py (new). No behavior change to existing modules. Per-branch alignment is consumed by #317 (dispute) and #318 (growth).

## Acceptance ↔ test
| Acceptance | Test |
|---|---|
| compute_alignment_per_branch returns dict | test_compute_alignment_returns_per_branch_dict |
| per-branch coverage_total=0 returns zero score | test_per_branch_zero_coverage_returns_zero |
| catch_up_triggers identifies gap branches | test_catch_up_triggers_identifies_gaps |
| disclosure_triggers respect authority scope | test_disclosure_triggers_respect_authority |
| CognitionState raises on bad input | test_cognition_state_raises_on_bad_input |
