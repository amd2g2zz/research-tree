## Context

#160 and #161 are merged, independently source-bound children of #152. The
parent needs a small, reproducible acceptance boundary without reviving the
old exploratory worktree or duplicating either child's closure implementation.

## Goals / Non-Goals

**Goals:**

- Register group 39 with exact child-group dependencies and a focused parent
  acceptance command.
- Prove the child receipts are verified and their source revisions are
  reachable from the parent integration baseline.
- Record one parent receipt and close only #152.

**Non-Goals:**

- Changing `closure.py`, child schemas, generic-writer authority, correction
  invalidation, or any public API.
- Reusing the stale #152 exploratory runtime worktree.

## Decisions

- Add a parent-only governance test rather than replaying child implementation
  logic. The registry is the authoritative integration boundary and the child
  suites already test their runtime behavior.
- Make group 39 depend exactly on 46 and 47. This prevents a parent receipt
  from being recorded if either child is unverified.
- Use the normal CI receipt locator and keep generated command output local,
  matching the post-#188 verification policy.

## Risks / Trade-offs

- [A registry receipt alone can hide stale child commits] -> Assert each child
  source revision is an ancestor of the current parent baseline before group 39
  is verified.
- [The old #152 WIP contains broader changes] -> Preserve it read-only and use
  a fresh worktree for this parent-only acceptance.
