# Proposal: growth-aware-readiness

## Why

issue #318: readiness was a single boolean derived from global state. Growth-aware readiness needs per-branch handoff so that a run can advance some branches while holding others.

## What Changes

NEW `src/research_tree/growth.py`:
- `BranchState` frozen dataclass: branch_id + node_count + revision + last_seen.
- `BranchHandoff`: source branch → target branch with explicit acknowledgment.
- `ReadinessDelta`: per-branch readiness change (advance / hold / regress).
- `seal_branch(branch, siblings_open=True)`: confirm handoff; siblings remain open.
- `coordinator.is_branch_ready(branch_id)`: per-branch readiness check.

## Impact

src/research_tree/growth.py (new). Growth-aware: branches advance independently; seal does not close siblings.

## Acceptance ↔ test
| Acceptance | Test |
|---|---|
| BranchState validates non-negative counts | test_branch_state_validates_non_negative |
| seal_branch leaves siblings open | test_seal_branch_leaves_siblings_open |
| ReadinessDelta tracks per-branch change | test_readiness_delta_per_branch |
| BranchHandoff records source/target lineage | test_branch_handoff_records_lineage |
| is_branch_ready respects per-branch state | test_is_branch_ready_per_branch |
