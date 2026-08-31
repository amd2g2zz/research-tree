## 1. Transitive Graph Contract

- [x] 1.1 Register group 40 / issue #153 and add red regressions for unknown
  intermediates, independent branches, and restart-safe stale paths.
- [x] 1.2 Replace static correction-kind selection with canonical parent-graph
  traversal and deterministic quarantine diagnostics.

## 2. Authority Enforcement

- [x] 2.1 Reject stale dispatch, ingress, recovery, and completion paths while
  preserving independent work and immutable history.
- [ ] 2.2 Run focused and full acceptance, record group-40 evidence, and close
  #153 only after its delivery PR merges.
