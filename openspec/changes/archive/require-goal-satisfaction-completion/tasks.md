# Require Goal Satisfaction Completion — Tasks

## 1. Red Tests

- [x] 1.1 Add `tests/test_goal_gate.py` with the named §B3 contract tests: all-satisfied
      passes, unmet blocks complete, missing registration blocks, waived requires reason,
      duplicate fails oracle_duplicate, legacy/superseded run fails closed, why_not_complete
      names oracles.

## 2. Registrar Role (B3)

- [x] 2.1 Add completion-input role `goal_satisfaction` to the ledger whitelist (kind
      `goal-satisfaction`, pure addition; existing roles unchanged).
- [x] 2.2 Add `GOAL_SATISFACTION_*` constants,
      `validate_goal_satisfaction_payload` (verdict whitelist, waived⇒non-empty
      waiver_reason, non-waived⇒waiver_reason null, satisfied/partial⇒non-empty
      evidence_refs), and `CompletionInputRegistrar.write_goal_satisfaction` binding
      payload evidence_refs to exact parent lineage (issuer `coordinator`).

## 3. Manifold Diagnostic (B3)

- [x] 3.1 Add `_goal_satisfaction_diagnostic` to `_completion_manifold`: fail-closed
      `goal_satisfaction_unknown` when `strategy_projection.latest_confirmed` returns None;
      `oracle_duplicate` for multiple valid registrations per oracle; `oracle_uncovered`
      (missing, unmet, or evidence-unresolved) with the uncovered oracle id list; on pass,
      record `goal_satisfaction_refs` in the completion record manifold.
- [x] 3.2 Extend `why_not_complete` to append `resolve:goal_satisfaction:<oracle_id>` per
      uncovered oracle to `next_actions` alongside the generic obligation entry.

## 4. Fixtures and Gates

- [x] 4.1 Update completion fixtures for the fail-closed gate
      (waived registration with reason in the delivery-mechanics fixtures; the canonical
      completion test registers its own goal input), and run the full gates: pytest, ruff
      check/format, package check, openspec strict validation, docs and repository layout
      checks.
