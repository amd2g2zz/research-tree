## 1. Bootstrap Evidence and Policy Contract

- [x] 1.1 Establish and protect `dev` while retaining `master` as the repository default and release branch.
- [x] 1.2 Add the versioned delivery policy registry and the `dev` bootstrap receipt for `db7e256b3d0f261487cce8455971244eaf5986bd`.
- [x] 1.3 Add JSON schemas for the policy and bootstrap receipt.
- [x] 1.4 Generate and review the current worktree recovery inventory without removing any worktree.

## 2. Executable Governance Checker (#90)

- [x] 2.1 Add contract tests for policy and bootstrap semantic validation.
- [x] 2.2 Add preflight tests and deterministic read-only implementation.
- [x] 2.3 Add PR gate tests and implementation, including release ancestry and review limits.
- [x] 2.4 Add generated-package drift and separate-commit verification.
- [x] 2.5 Add deterministic inventory and non-destructive cleanup planning.
- [x] 2.6 Verify Windows path normalization and POSIX-compatible Git output parsing.

## 3. CI and Contributor Workflow (#91)

- [ ] 3.1 Add a GitHub Actions workflow that runs the PR delivery gate for pull requests to `dev` and `master`.
- [ ] 3.2 Run generated-package parity independently in CI.
- [ ] 3.3 Document `dev` development, release promotion, worktree creation, exception review, and post-merge cleanup.
- [ ] 3.4 Link the contributor workflow from the repository README.

## 4. Verification and Delivery

- [x] 4.1 Run strict OpenSpec validation, full regression, package parity, and `git diff --check` for the #88 specification/bootstrap slice.
- [ ] 4.2 Open one PR for #88 with base `dev`, resolve all review threads, and merge only after current-head CI passes.
- [ ] 4.3 Deliver #90 and #91 sequentially from fresh `origin/dev` worktrees.
