# Development Workflow

Research Tree uses two protected long-lived branches with different roles:

- `master` is the GitHub default branch and the release branch.
- `dev` is the development integration branch.

GitHub defaults new pull requests to `master`. That does not make `master` a
valid base for ordinary Alpha2 work; explicitly change the base to `dev`.

## Start One Issue

Each delivery issue owns one branch, one worktree, and one pull request. Start
from the current remote integration revision:

```bash
git fetch origin dev
git worktree add ../research-tree-issue-123 \
  -b feat/issue-123-adaptive-frontier origin/dev
cd ../research-tree-issue-123
```

Allowed branch prefixes are `feat`, `fix`, `docs`, `test`, and `chore`. Before
implementation, run the read-only preflight:

```bash
uv run python scripts/check_delivery_workflow.py preflight \
  --issue 123 \
  --base-ref origin/dev
```

Preflight fails on dirty tracked, staged, or untracked state; a stale base;
invalid naming; duplicate issue ownership or worktree paths; or unavailable
remote metadata. It never stashes, resets, deletes, or repairs the worktree.

## Deliver To dev

An ordinary delivery PR must target `dev`, close exactly one delivery issue,
and pass the shared local/CI gate:

```bash
uv run python scripts/check_delivery_workflow.py validate
uv run python scripts/check_delivery_workflow.py check-pr \
  --base dev \
  --head feat/issue-123-adaptive-frontier \
  --body "Closes #123"
```

More than 25 non-generated files or 800 changed non-generated lines requires a
split-review rationale. More than 50 files or 1,500 lines fails unless a
maintainer-approved exception is explicitly recorded. Generated host packages
must be reproducible from canonical source and isolated in their own commit.

## Promote A Release

Create `release/<version>` at the current `dev` revision and target `master`.
The gate rejects a release branch that is not derived from `dev` or contains
commits that have not already entered `dev`. Release PRs promote integrated
work; they are not a path for feature delivery to bypass `dev`.

## Review Cleanup

Inventory and cleanup planning are read-only:

```bash
uv run python scripts/check_delivery_workflow.py inventory
uv run python scripts/check_delivery_workflow.py cleanup-plan
```

Dirty, detached, closed-unmerged, orphaned, or ambiguous worktrees remain in
place. A clean worktree is only eligible for explicit removal when its PR is
merged, its head is reachable from `origin/dev`, and the branch has no later
commits. The tool never removes a worktree itself.
