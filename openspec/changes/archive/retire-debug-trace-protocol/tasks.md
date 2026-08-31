# Tasks: retire-debug-trace-protocol

## 1. Fold And Retire

- [x] 1.1 Fold `emit_trace` and its minimal closure into
  `src/research_tree/lifecycle_hook.py` (~130 lines, literal equivalence);
  remove the function-local import; retire the protocol surface (no protocol
  objects, no replay, no `summarize_traces`).
- [x] 1.2 Delete `src/research_tree/debug_trace.py` and the
  `research-tree-debug` pyproject entry point.
- [x] 1.3 Delete `tests/test_debug_trace.py` and `tests/test_replay.py`;
  carry the three emit_trace-anchored cases into
  `tests/test_lifecycle_hook.py` (one case narrowed: its
  `summarize_traces` block retires with the capability).

## 2. Docs And Packages

- [x] 2.1 Rewrite `references/debug-tracing.md` as emitter-only (35 lines,
  within the 80-line cap).
- [x] 2.2 Align the debug paragraphs in `skill-src/SKILL.template.md` and
  `skill-src/hermes-SKILL.template.md`; align `docs/guides/operator.md`.
- [x] 2.3 Regenerate host packages (generated-only commit).

## 3. Governance Registries

- [x] 3.1 Remove retired paths from the group 11/36/45/63 command pairs in
  task-execution-v1 and task-verification-v1 (pairing-only; each pair stays
  verbatim identical; historical receipt digests untouched).
- [x] 3.2 Re-point the delivery-matrix `runtime-observability` row to
  `lifecycle_hook.py`; strip retired symbols from the
  `semantic-replay-reconstruction` row; re-point the repository-paths
  `.research-tree-debug/` canonical command to `research-tree-hook --debug`.

## 4. Verification And Handoff

- [x] 4.1 Run the full gate battery: pytest (single known docker-env failure
  acceptable), ruff check + format, `build_skill_packages.py --check`,
  `check_openspec_governance.py`, `check_repository_layout.py`,
  `check_docs.py`, and `openspec validate retire-debug-trace-protocol --strict`.
- [x] 4.2 Grep gates: `grep -rn "debug_trace" src/ scripts/ hooks/ --include="*.py"`
  zero hits outside the lifecycle_hook definitions; packaged skills and docs
  name no `research-tree-debug` CLI.
- [x] 4.3 Verify the hook smoke path manually with a scratch run
  (`research-tree-hook --debug`): trace file lands under
  `.research-tree-debug/events/`, host response unchanged.
- [x] 4.4 Commit on `feat/issue-423-debug-trace-fold` in grouped commits and
  push; PR and merge are owned by the coordinator.
