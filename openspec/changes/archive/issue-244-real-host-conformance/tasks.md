# Implementation Tasks

## 1. Spec + case freeze
- [x] Preflight at origin/dev@66b6213; OpenSpec strict.
- [x] 1.1 Freeze host-conformance-v1 case + schema with negative oracles.

## 2. Harness
- [x] 2.1 RED: case loader rejects synthetic identity/completion oracles.
- [x] 2.2 GREEN: loader + comparator library; result schema.
- [x] 2.3 RED: replay divergence detection fails closed.
- [x] 2.4 GREEN: replay comparator.

## 3. Mode runs (real hosts)
- [x] 3.1 Codex mode: two-leaf + contradiction + fault cells, Docker or accepted deviation.
- [x] 3.2 Hermes mode: same cells in the Docker envelope.
- [x] 3.3 Claude modes: agent/workflow/hybrid cells; unavailable recorded as blockers.

## 4. Replay + comparison table
- [x] 4.1 Replay each mode's persisted artifacts in a separate process; compare.
- [x] 4.2 Comparison table of prior synthetic attempts vs new receipts.

## 5. Gates + review + delivery
- [x] 5.1 Focused + full governed suites.
- [ ] 5.2 Independent reviewer reruns the matrix from a clean worktree.
- [ ] 5.3 One PR Closes #244.

## Rollback
git revert of the lane commits on test/issue-244-host-conformance.
