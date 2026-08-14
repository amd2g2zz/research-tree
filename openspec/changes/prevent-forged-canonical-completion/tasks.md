## 1. Parent Acceptance Contract

- [x] 1.1 Register group 36 with exact dependencies on groups 43, 44, and 45.
- [x] 1.2 Map Issue #149 and the canonical-completion-integrity delivery row
  without changing child ownership.
- [x] 1.3 Add a parent acceptance test for child-receipt reachability and
  parent-only registration.

## 2. False-Completion Verification

- [x] 2.1 Run the delivered manifold regressions for generic lookalikes,
  idempotent canonical completion, and stale/quarantined reopening.
- [x] 2.2 Run strict OpenSpec and governance validation for the parent
  registry state.

## 3. Evidence and Delivery

- [x] 3.1 Commit the parent acceptance source before recording group-36
  evidence.
- [x] 3.2 Generate local source-bound group-36 output and receipt, then mark
  group 36 verified with the generated command metadata.
- [ ] 3.3 Run final governance and PR delivery checks, merge the one #149 PR,
  close #149, and clean its worktree.
