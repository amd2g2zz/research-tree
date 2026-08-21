# Development Workflow

Research Tree uses two protected long-lived branches with different roles:

- `master` is the GitHub default branch and the release branch.
- `dev` is the development integration branch.

GitHub defaults new pull requests to `master`. That does not make `master` a
valid base for ordinary Alpha2 work; explicitly change the base to `dev`.

Before changing documentation, consult the
[documentation authority model](documentation-authority.md). Edit the listed
canonical authoring source, not a generated package or historical record, and
run `uv run python scripts/check_docs.py` with the normal delivery checks.

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

## Repository Layout And Clean Checkout

The [repository path registry](../openspec/changes/unify-research-runtime-alpha2/registries/repository-paths-v1.json) is the authority for sources, generated distributions, local installations, and runtime or operator-managed material. Edit `skill-src/`, `assets/`, `references/`, and `scripts/`; regenerate and check `packages/` and `.claude-plugin/` rather than editing generated files.

Repository-local `.agents/`, `.claude/`, `.codex/`, `.research-tree*/`, raw material, research runs, build output, and caches remain ignored protected material. The layout checker only classifies and reports them.

```bash
uv run python scripts/check_repository_layout.py
uv run python scripts/check_repository_layout.py --workflow-probe
uv run python scripts/check_repository_layout.py --migration-plan
```

The workflow probe runs package validation/tests, a temporary project-scoped Codex install, and migration inventory without changing the checkout. A migration plan is inspection-only; resolve collisions and retain its confirmation token before any separately approved manual relocation.

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
maintainer applies the exact `delivery:oversized-approved` pull-request label.
PR body text and similar labels do not grant the exception. Generated host
packages must be reproducible from canonical source and isolated in their own
commit.

## Promote A Release

Open a pull request from the current `dev` branch to `master`. The head must be
exactly `dev`; feature branches and release candidates cannot use this
promotion path. All changes must already have entered `dev` through their
issue-scoped pull requests.

The delivery gate treats `dev` to `master` as an integration promotion. It
does not reapply per-feature issue, size, or generated-output checks to the
already reviewed history. After the pull request merges, create the version
tag and GitHub Release from the resulting `master` commit.

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
