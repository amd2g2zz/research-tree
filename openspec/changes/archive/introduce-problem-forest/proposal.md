# Proposal: introduce-problem-forest

## Why

issue #314: Requester Brief was modeled as opaque text. The four-forest cognitive model needs an explicit Requester-side forest to track problem definition over time and reconcile against the agent's tree.

## What Changes

NEW `src/research_tree/problem_forest.py`:
- `ForestSpace` enum: REQUESTER/AGENT/SHARED/RECONCILIATION/EVIDENCE.
- `ReconciliationKind` enum: same_problem/partial_match/missing_in_agent/agent_expansion_unconfirmed/topology_mismatch/oracle_mismatch/contradiction/superseded.
- `Forest` (frozen dataclass): nodes + edges + space.
- `ReconciliationGraph`: edges between forests with ReconciliationKind.
- Mutation API: append/supersede/split/merge/regress_confidence.
- `authority.py`: `Authority` enum + `role_of` lookup (41 lines).

## Impact

src/research_tree/problem_forest.py + src/research_tree/authority.py (new). No behavior change to existing modules. Coordinates with #315 (cognition reads forests).

## Acceptance ↔ test
| Acceptance | Test |
|---|---|
| ForestSpace has 5 spaces | test_forest_space_has_5_values |
| ReconciliationKind has 8 kinds | test_reconciliation_kind_has_8_values |
| Forest mutation preserves invariants | test_forest_mutation_preserves_invariants |
| ReconciliationGraph supports all 8 kinds | test_reconciliation_graph_supports_all_kinds |
| Forest supersede records audit | test_forest_supersede_records_audit |
| Authority role_of resolves | test_authority_role_of_resolves |
