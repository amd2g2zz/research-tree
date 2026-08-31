# Proposal: canonical-reconnaissance

## Why

issue #319 (confirmed): alpha2 separates ask_one from reconnaissance, requires
callers to preconstruct search portfolios, performs no retrieval or dispatch
in the planner, forces rigid coverage categories.  Reconnaissance is easily
reduced to search or pushed back to the requester.

## What Changes

NEW `src/research_tree/reconnaissance.py`:
- `MethodHypothesis`: method + score + basis_refs + rationale
- `ReconnaissancePlan`: slot_id + tuple of independent methods
- `ReconnaissanceChoice`: selected method + score + rationale
- `propose_methods(...)` generates ≥2 methods when ≥2 available (decouples
  ask_one from reconnaissance)
- `select_method(plan, tie_break=...)` picks highest-score deterministically

## Impact

- src/research_tree/reconnaissance.py (new) — no behavior change to existing modules.
- Reconnaissance now offers multiple independent methods per slot.

## Acceptance ↔ test
| Acceptance | Test |
|---|---|
| planner decouples ask_one from reconnaissance | test_reconnaissance_decouples_ask_one_from_reconnaissance + test_reconnaissance_methods_are_decoupled_from_ask_one |
| ≥2 methods when ≥2 available | test_reconnaissance_methods_are_decoupled_from_ask_one |
| methods carry basis_refs + method independence | test_methods_carry_basis_refs_and_method_independence_marker |
| select_method picks highest score | test_select_method_picks_highest_score_with_rationale |
| malformed input rejected | test_method_hypothesis_requires_nonempty_method_and_basis + test_propose_methods_rejects_empty_method_set |
