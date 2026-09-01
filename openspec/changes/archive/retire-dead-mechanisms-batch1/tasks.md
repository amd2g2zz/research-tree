## 1. Deletion

- [x] 1.1 Delete the 12 graph-verified dead modules (`alpha1_adversarial`,
  `best_of_n`, `black_box_regression`, `progress_delta`, `state_projection`,
  `operating_model`, `cognition`, `growth`, `native_workflows`,
  `shared_brief`, `context_cost`, `schemas`) with no alias, bridge, adapter,
  replacement, migration, fallback, or user-data operation.
- [x] 1.2 Remove their `__init__` re-export blocks and `__all__` entries.
- [x] 1.3 Delete their dedicated test suites (11 files); trim the surviving
  `tests/test_context_ledger.py` of its retired `context_cost` references.

## 2. Dangling Reference Removal

- [x] 2.1 Remove `problem_forest.py`'s dead `cognition` import and the two
  string annotations that named the retired type.
- [x] 2.2 Remove `coordinator.py` `confirm_handoff`'s opt-in `branch`
  parameter, its growth-aware payload branch, and the `growth` import (F3).
- [x] 2.3 Remove `alignment_protocol.py`'s `growth` import and the
  `growth_aware_readiness` method (the last production growth caller).
- [x] 2.4 Remove the retired `src/research_tree/native_workflows.py` path from
  the alpha2 group-61 acceptance command and its paired verification receipt.

## 3. Verification And Handoff

- [x] 3.1 Run the full local gate battery: pytest, ruff check + format,
  `build_skill_packages.py --check`, `check_docs.py`,
  `check_repository_layout.py`, retired-name zero-hit greps, and GitNexus
  `detect-changes --scope all`.
- [x] 3.2 Commit on `feat/issue-420-dead-modules-batch1` and push; PR and merge
  are owned by the coordinator.
