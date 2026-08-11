# Verification Evidence

Commands were run from the issue-110 worktree:
`D:\codebase\research-tree-worktrees\issue-110-strict-delivery-lineage`.

- Strict delivery tests: `uv run pytest -q tests/test_strict_delivery_lineage.py` -> 22 passed.
- Delivery, readiness, strict evidence, and SQLite regression tests: 54 passed.
- Full regression: `uv run pytest -q` -> 341 passed in 62.73s.
- Python compilation: `uv run python -m compileall -q src tests` -> passed.
- OpenSpec: `openspec validate preserve-strict-evidence-delivery-lineage --strict` -> valid.
- Host package parity: `uv run python scripts/build_skill_packages.py --check` -> Codex, Claude Code, and Hermes valid.
- Policy: `uv run python scripts/check_delivery_workflow.py validate` -> valid; integration branch is `dev`.
- Governance: `uv run python scripts/check_openspec_governance.py` -> valid with no violations; release readiness remains false because unrelated Alpha2 groups are unverified.
- Scope: issue #110 strict delivery lineage only; no #56, #62, #109, or #112 behavior is claimed here.
