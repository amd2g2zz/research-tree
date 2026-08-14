## 1. Repair the historical metadata

- [x] 1.1 Reproduce the mismatch from a clean `origin/dev` worktree.
- [x] 1.2 Verify the committed raw output bytes are unchanged from the original
  group-60 recording.
- [x] 1.3 Correct only the receipt and canonical registry output digests.

## 2. Verify and hand off

- [x] 2.1 Run the group-60 focused acceptance suite and Ruff checks.
- [x] 2.2 Run OpenSpec, delivery, governance, package, and repository-layout
  checks.
- [x] 2.3 Open one PR that closes only #195 and coordinate file ownership with
  #194 before the historical artifact migration begins.
