## 1. Contract And Red Tests

- [x] 1.1 Add failing focused tests for strict correction/reopen fields, exact five-role revision/digest bindings, separate task/domain identity, replay conflict, and transaction rollback.
- [x] 1.2 Add failing integration tests for immutable predecessor history, explicit supersedes/reopens lineage, successor alignment state, and exact stale quarantine.
- [x] 1.3 Run the red slice through `uv run pytest -q tests/test_feedback_rounds.py`, `uv run ruff check tests/test_feedback_rounds.py`, and `uv run ruff format --check tests/test_feedback_rounds.py`; record pytest as expected-red and require both Ruff commands to pass.

## 2. Typed Correction And Atomic Application

- [x] 2.1 Implement the frozen correction/reopen value and affected artifact bindings in `src/research_tree/feedback.py`, with strict validation and stable payload serialization.
- [x] 2.2 Implement `ResearchRunCoordinator.apply_correction` as one correction/quarantine/successor-state ledger batch with idempotent replay and changed-id conflict detection.
- [x] 2.3 Run `uv run pytest -q tests/test_feedback_rounds.py`, `uv run ruff check src/research_tree/feedback.py src/research_tree/coordinator.py tests/test_feedback_rounds.py`, and `uv run ruff format --check src/research_tree/feedback.py src/research_tree/coordinator.py tests/test_feedback_rounds.py`; all three commands must pass before this slice is green.

## 3. Stale Authority Guards

- [x] 3.1 Add failing tests proving stale alignment/strategy/handoff bindings reject dispatch, handoff confirmation, delivery compilation/acceptance, and direct completion without lifecycle or lease mutation.
- [x] 3.2 Centralize post-correction current-authority validation in the coordinator and accept only current non-quarantined exact bindings for sensitive actions.
- [x] 3.3 Run focused coordinator/feedback pytest plus `uv run ruff check` and `uv run ruff format --check` over every touched Python file; any Ruff failure keeps the slice red.

## 4. Alignment Authority Regression

- [x] 4.1 Preserve focused tests proving a response must match the active pending action and agent-authored evidence cannot resolve a human-only field.
- [x] 4.2 Add the wrong-subject/stale-plan regression fixture and prove the old strategy is quarantined while a fresh successor-bound action remains usable.
- [x] 4.3 Run `uv run pytest -q tests/test_feedback_rounds.py tests/test_alignment_protocol.py tests/test_research_run_coordinator.py` plus scoped Ruff lint and format checks; all must pass.

## 5. Group 23 Evidence And Delivery Gates

- [x] 5.1 Update only group 23 task evidence and add a source-bound receipt containing the exact commit, environment, correction fixture ids/digests, predecessor/successor refs, stale reasons, task/domain ids, and commands.
- [x] 5.2 Run `openspec validate invalidate-stale-alignment-state --strict`, `openspec validate unify-research-runtime-alpha2 --strict`, the full pytest suite, full touched-file Ruff lint/format checks, package check, OpenSpec governance, delivery workflow validation, and `git diff --check`.
- [x] 5.3 Inspect the final diff, keep generated packages absent unless rebuilt from authoring source in a separate generated-only commit, and commit the issue-local source/OpenSpec changes without pushing or merging.
