## 1. Contract and Red Tests

- [x] 1.1 Add replay tests for exact event/state lineage, deterministic ordering, digest verification, missing causes, and forks.
- [x] 1.2 Add debug-trace tests for run/action explanations, complete obligation evidence, privacy rejection, and read-only host reconciliation.
- [x] 1.3 Confirm the new focused tests fail for the intended missing behavior, then run Ruff check and Ruff format-check on the touched test files; any Ruff failure keeps the red slice unresolved.

## 2. Causal Projection and Replay

- [x] 2.1 Implement stable causal trace records projected from `RunLedger` lifecycle artifacts with bounded allowlisted fields.
- [x] 2.2 Implement deterministic lifecycle replay, cause/reference verification, fork detection, and terminal state-digest verification.
- [x] 2.3 Implement run and action explanations with exact artifact references and additive evidence-gap detail for why-not-complete.

## 3. Host Reconciliation and CLI

- [x] 3.1 Implement bounded read-only host observation reconciliation for missing, stale, duplicate, divergent, and uncertain outcomes.
- [x] 3.2 Add `research-tree-debug` commands for explain-run, why-action, why-not-complete, replay, and reconcile-host.
- [x] 3.3 Preserve existing opt-in debug emit/summary behavior as a non-authoritative compatibility surface.

## 4. Verification and Delivery

- [x] 4.1 Run `uv run pytest -q tests/test_debug_trace.py tests/test_replay.py tests/test_research_run_coordinator.py`.
- [x] 4.2 Run `uv run ruff check src/research_tree/debug_trace.py tests/test_debug_trace.py tests/test_replay.py` on every touched Python file.
- [x] 4.3 Run `uv run ruff format --check src/research_tree/debug_trace.py tests/test_debug_trace.py tests/test_replay.py`; pytest plus both Ruff commands form one required gate.
- [ ] 4.4 Run full pytest, strict OpenSpec validation, package parity, delivery workflow, and `git diff --check`.
- [ ] 4.5 Record source-bound group-11 execution/verification receipts, isolate generated output if any, and inspect the final diff before PR delivery.
