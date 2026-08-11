## 1. Contract And Red Tests

- [x] 1.1 Add `decision-frame-v1.json`, valid/invalid fixtures, explicit v3->v4 SQLite DDL/backfill/rollback contract, and migration tests.
- [x] 1.2 Add failing `tests/test_decision_frame.py` cases for literal wording, competing hypotheses, strict validation, bounded clarification, deterministic replay, and topic-word substitution.
- [x] 1.3 Add failing coordinator tests for stale/unready/cross-run frame rejection, exact lineage, primary/enabler traceability, no-progress disposition, idempotency/conflict, fault rollback, and technical-substitution bypasses.
- [x] 1.4 Run `uv run pytest -q tests/test_decision_frame.py tests/test_research_run_coordinator.py`, `uv run ruff check tests/test_decision_frame.py tests/test_research_run_coordinator.py`, and `uv run ruff format --check tests/test_decision_frame.py tests/test_research_run_coordinator.py`; record the expected red failures.

## 2. DecisionFrame Runtime

- [x] 2.1 Implement strict immutable hypothesis, clarification action, and DecisionFrame models with canonical serialization/digest validation.
- [x] 2.2 Implement deterministic reconnaissance/question selection with one-question maximum and no keyword/domain rule base.
- [x] 2.3 Persist exact frame lineage through the SQLite ledger with migration, expected-revision atomicity, idempotent replay, and event conflict rejection.
- [x] 2.4 Run focused pytest plus `uv run ruff check src/research_tree/decision_frame.py tests/test_decision_frame.py` and `uv run ruff format --check src/research_tree/decision_frame.py tests/test_decision_frame.py`.

## 3. Coordinator Gate

- [x] 3.1 Add a read-only exact-current `ready_for_strategy` frame guard for strategy projection, research plan, and autonomous dispatch.
- [x] 3.2 Retain the frame ref in dispatch/event lineage and keep legacy RunStore intent/brief projections non-authoritative.
- [x] 3.3 Add replay, cross-host canonical JSON, stale revision, lifecycle no-mutation, fault-prefix, and evaluator-owned black-box metric tests for all three hosts.
- [x] 3.3a Add evaluator-owned black-box fixtures/harness for intent-hypothesis fidelity, clarification-action appropriateness, premature-strategy rejection, primary-decision fidelity, decision-surface substitution, and enabler traceability, with a source-bound receipt path.
- [x] 3.4 Run focused coordinator tests plus `uv run ruff check src/research_tree/decision_frame.py src/research_tree/coordinator.py src/research_tree/run_ledger.py tests/test_decision_frame.py tests/test_research_run_coordinator.py` and matching `uv run ruff format --check`.

## 4. Group 31 Evidence And Delivery

- [ ] 4.1 Mark only Alpha2 group-31 tasks complete and add exact pytest/Ruff commands to task execution/verification registries.
- [ ] 4.2 Record source-bound group-31 output/receipt with environment, command, output digest, fault/replay fixture refs, and evaluator metric results.
- [ ] 4.3 Run full pytest, strict OpenSpec for this change and Alpha2, package parity, governance, delivery, and `git diff --check`.
- [ ] 4.4 Keep non-generated changes within the review limit, isolate any generated package commit, push one PR to `dev` with `Closes #87`, wait for hosted checks, merge, and clean the worktree/branches.
