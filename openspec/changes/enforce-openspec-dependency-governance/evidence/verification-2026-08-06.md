# Verification Evidence

Executed from the clean #89 worktree before opening its pull request.

| Command | Result |
| --- | --- |
| `uv run pytest -q tests/test_openspec_execution_governance.py` | `11 passed` |
| `uv run python scripts/check_openspec_governance.py` | Exit 0; valid governance graph, release-ready false because groups 1--32 are planned |
| `uv run python scripts/check_openspec_governance.py --require-release-ready` | Exit 1 as required; the valid but unverified plan cannot pass a release gate |
| `uv run pytest -q` | `260 passed in 55.97s` |
| `openspec validate enforce-openspec-dependency-governance --strict` | Valid |
| `openspec validate unify-research-runtime-alpha2 --strict` | Valid |
| `uv run python scripts/build_skill_packages.py --check` | Codex, Claude Code, and Hermes packages valid |
| `git diff --check` | Exit 0 |

The planned state is intentional. This governance change validates dependency
semantics and records unproven Alpha2 groups as non-verified; it does not claim
that the Alpha2 runtime is release-ready.
