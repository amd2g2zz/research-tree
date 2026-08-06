## Context

The repository previously used `master` as both release and integration branch.
Alpha2 work then accumulated in stacked intermediate branches and a closed branch
with 86 unique commits. The repository also has 31 registered worktrees, including
dirty and orphaned states. GitHub now has `dev` at
`db7e256b3d0f261487cce8455971244eaf5986bd`; both `dev` and `master` require PRs,
disallow force pushes and deletion, and require conversation resolution. `master`
remains the repository default branch; Alpha2 development PRs explicitly target
`dev`.

## Goals / Non-Goals

**Goals:**

- Make issue ownership and integration topology mechanically checkable.
- Prevent stale or dirty worktrees from becoming implementation bases.
- Reject wrong-base, mixed-issue, oversized, and generated-drift PRs.
- Produce an auditable, non-destructive cleanup plan after merge.

**Non-Goals:**

- Automatically deleting worktrees or user-owned files.
- Replaying the closed PR #74 implementation.
- Validating OpenSpec task dependency semantics, which belongs to issue #89.
- Replacing semantic code review with line-count thresholds.

## Decisions

### Use dev as the development integration branch

`dev` is created from the last verified specification-only `master` revision rather
than from `origin/alpha2/spec-foundation@6b44bc8`. The latter combines #53 content
into the final #55 merge topology, so using it would preserve incorrect issue
ownership. #55 and #53 will be replayed independently after #88.

Alternative considered: bootstrap from the latest stacked Alpha2 branch. Rejected
because it imports mixed issue ownership and unreviewed implementation history.

### Implement one policy script with explicit subcommands

Add `scripts/check_delivery_workflow.py` with four read-only operations:

- `preflight`: verify issue, branch, worktree, base SHA, and clean state.
- `check-pr`: verify base/head topology, issue ownership, size, and generated parity.
- `inventory`: emit the registered worktree recovery inventory.
- `cleanup-plan`: classify eligibility without deleting anything.

The script emits deterministic JSON and human-readable diagnostics. Destructive
cleanup remains an explicit maintainer action after reviewing the generated plan.

Alternative considered: separate shell scripts. Rejected because Windows and POSIX
behavior would diverge and JSON evidence would be duplicated.

### Store policy in a versioned registry

Add `openspec/changes/establish-dev-integration-governance/registries/delivery-policy-v1.json`
for branch roles, naming patterns, review thresholds, generated paths, and allowed
release promotion topology. The checker consumes the registry instead of embedding
policy constants.

### Enforce the same policy locally and in GitHub Actions

Add a workflow that invokes the checker for pull requests. Local preflight and CI
use the same registry and script, preventing documentation-only rules from drifting
from enforcement.

### Treat the bootstrap as an explicit exception

Because `dev` did not exist, its initial ref could not be created through a PR to
`dev`. The bootstrap receipt records this one exception. Every subsequent Alpha2
change must enter through a PR whose base is `dev`.

## Risks / Trade-offs

- **Risk: size limits reject a cohesive change** -> Allow a versioned exception with
  issue-specific rationale and reviewer identity; never infer an exception from a
  label alone.
- **Risk: GitHub API is unavailable during local preflight** -> Separate local Git
  invariants from remote ownership checks and report remote checks as unavailable,
  never passed.
- **Risk: existing historical branches trigger duplicate ownership** -> Scope active
  ownership to open PRs and explicitly registered active worktrees; historical
  branches remain visible in the recovery inventory.
- **Risk: Windows path normalization causes duplicate misses** -> Resolve absolute
  paths case-insensitively on Windows and preserve canonical paths in receipts.
- **Risk: GitHub defaults new PRs to master** -> The PR gate rejects Alpha2 feature
  PRs whose base is not explicitly changed to `dev`; documentation calls this out
  before branch creation.

## Migration Plan

1. Record the verified bootstrap SHA and baseline command results.
2. Create and protect `dev`; keep `master` as the repository default branch.
3. Merge the #88 policy and bootstrap evidence into `dev`.
4. Deliver the checker and tests through #90, then CI and documentation through
   #91, each from a fresh current `origin/dev` worktree.
5. Replay #55 and #53 independently from current `origin/dev` without their stacked
   merge commits.
6. Inventory all existing worktrees; preserve dirty and unresolved historical work.
7. Apply cleanup only after each related PR is merged and reachability is proven.

Rollback keeps `dev` and `master` protected, disables the CI workflow, and retains
all receipts and inventory output. It never deletes worktrees automatically.

## Open Questions

None required for implementation. Review-size exceptions are deliberately modeled
as explicit artifacts so their approval mechanism can evolve without changing the
base invariants.
