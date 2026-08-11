# Adaptive Research Policy

## Why

Recursive growth currently makes opaque local choices from incomplete evidence.
The runtime needs deterministic, lineage-bound policy values and a
non-authoritative compatibility boundary before those choices can guide the
coordinator.

## What Changes

- Add typed, evidence-bound proposals with deterministic replay and pruning.
- Replace scalar realized delta with an attributable six-component vector.
- Validate and synthesize versioned, lineage-rich Insight Digests.
- Demote recursive-search completion/delivery to observations and blockers.
- Record focused pytest, Ruff lint, and Ruff format checks for every TDD slice.

## Scope

Runtime modules: `policy.py`, `evidence_delta.py`, `insights.py`, and the
recursive compatibility surface, plus focused tests and group 6/16 receipts.
No persistence, dispatch, host adapter, alignment, invalidation, capture, or
portfolio authority is added.
