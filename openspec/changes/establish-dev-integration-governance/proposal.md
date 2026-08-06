## Why

Alpha2 development currently has no stable integration branch and has accumulated
stacked PRs, mixed-issue branches, oversized commits, and dirty worktrees. A
mechanically enforced delivery boundary is required before additional runtime work
can be developed or reviewed reliably.

## What Changes

- Establish `dev` as the protected Alpha2 development/integration branch while
  keeping `master` as the repository default and release branch.
- Require every Alpha2 delivery issue to use one dedicated branch, worktree, and PR
  based on the current `origin/dev` revision.
- Add preflight checks for worktree cleanliness, issue ownership, branch naming,
  base revision, and duplicate active delivery surfaces.
- Add PR gates for target branch, review size, generated artifact separation, and
  current-base verification.
- Add a non-destructive inventory and cleanup contract for merged, dirty, orphaned,
  and historical worktrees.
- Deliver the contract and bootstrap evidence in #88, the executable checker in
  #90, and CI/documentation integration in #91.

## Capabilities

### New Capabilities

- `integration-delivery-governance`: Defines the authoritative integration branch,
  issue-isolated development topology, preflight and PR gates, and safe post-merge
  cleanup behavior.

### Modified Capabilities

None.

## Impact

- GitHub branch protection for `dev` and `master`.
- Follow-up repository validation scripts in #90 and CI workflow checks in #91.
- Follow-up contributor and repository-governance documentation in #91.
- Local worktree inventory and cleanup procedures.
- All future Alpha2 branches and PRs.
