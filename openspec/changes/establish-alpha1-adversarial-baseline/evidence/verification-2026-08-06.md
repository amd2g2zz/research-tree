# Issue #55 Verification Receipt

Date: 2026-08-06

## Baseline Identity

`git rev-parse 0.0.1-a1^{commit}` returned
`8ab91ea4eb55c98441b5ee6001b80922a56ecdd1`, matching the manifest.

The historical checkout was inspected with `git cat-file` and `git ls-tree`.
It does not contain direct replay tests for the nine registered risk cases.
All cases are therefore intentionally recorded as `unavailable` with a reason;
no current-branch command is presented as an Alpha1 reproduction.

## Commands

| Command | Result |
| --- | --- |
| `uv run pytest -q tests/test_alpha1_baseline.py` | `9 passed` |
| `uv run pytest -q` | `269 passed` |
| `openspec validate establish-alpha1-adversarial-baseline --strict` | valid |
| `uv run python scripts/build_skill_packages.py --check` | Codex, Claude Code, and Hermes valid |
| `uv run python scripts/check_openspec_governance.py` | valid; Alpha2 remains not release-ready while groups are unfinished |
| `git diff --check` | exit 0 |

## Status

Task group 1 is `in_progress`, not `verified`: remote PR creation and CI are
still pending, and the corpus deliberately records unavailable historical
reproduction commands rather than asserting a false replay result.
