# Tasks: host-hook-signals

## 1. Fail-open launcher (defect 1, RED first)

- [x] 1.1 RED: `tests/test_lifecycle_hook_launcher.py` — launcher subprocess in a
  plain workspace exits 0 with exactly one labeled response and no stderr
  traceback; invalid payload inside a checkout still exits 0; unknown flags
  still exit 0.
- [x] 1.2 GREEN: `scripts/lifecycle_hook_launcher.py` — stdlib-only fail-open
  launcher (no uv, no venv, no project context required).

## 2. Standalone imports + packaging

- [x] 2.1 RED: launcher test records a signal through the checkout source tree
  and through an installed-style flat copy.
- [x] 2.2 GREEN: fallback flat imports in lifecycle_hook; launcher packaged via
  COMMON_FILES, lifecycle_hook/origins via COMMON_FILE_MAP; hermes executable
  closure extended; host adapters reference the four scripts so skill_setup
  deploys them; packages regenerated.

## 3. Template + setup rendering

- [x] 3.1 RED: template test asserts UserPromptSubmit present (claude+codex),
  no `uv run`, no `--locked`, launcher filename + `|| exit 0` present;
  hermes N/A preserved.
- [x] 3.2 GREEN: codex/claude templates generated from HOST_HOOK_EVENTS;
  setup_hooks renders launcher commands with `|| exit 0` and detects
  ownership via launcher filename; `research-tree-hook` entry remains.

## 4. Prompt classification signals (defect 2, RED first)

- [x] 4.1 RED: `tests/test_prompt_signal.py` — rule-table per-category unit
  tests (correction/interruption/insight/answer/neutral), case-insensitivity,
  first-match-wins, wellformed table.
- [x] 4.2 RED: observe UserPromptSubmit end-to-end — payload in, sanitized
  signal record on disk, readable back; append-only independence.
- [x] 4.3 GREEN: `PROMPT_SIGNAL_RULES` + `classify_prompt_signal` +
  `_observe_prompt_signal` + `_feed_correction_signal` in lifecycle_hook;
  UserPromptSubmit accepted for claude/codex only.

## 5. Gates

- [x] 5.1 Full pytest (only the known docker loader test fails), ruff check +
  format, build --check, governance, layout, docs gates all green.
