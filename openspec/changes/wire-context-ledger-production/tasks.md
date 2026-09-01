# Tasks: context-ledger production wiring + admission cross-check

## 1. Admission cross-check (gate 9, RED first)

- [x] 1.1 RED: `tests/test_v2_context_wiring.py` — registry load verifies the
  immutable digest; declared-vs-registry mismatch fails closed with canonical
  reasons (`baseline-role-score-mismatch:<role>`, `baseline-run-name-mismatch`,
  `baseline-registry-missing`, `baseline-registry-digest-mismatch`); doc and
  registry agree.
- [x] 1.2 GREEN: `evaluation/baselines/senior-user-ux-v2-baseline.json`
  (digest-sealed baseline payload: run name + three role scores with scales),
  `evaluation/cases/senior-user-ux-v2.json` (case_id anchor),
  `evaluation/harness/v2_baseline_admission.py`
  (`load_baseline_registry`, `cross_check`, `BaselineAdmissionError`).

## 2. Production wiring (RED first)

- [x] 2.1 RED: governed run creates the ledger at
  `run_root/context/read-ledger.json` with the declared budget; receipt
  discloses the real `declared_budget`; admission record persisted on match;
  run start blocked before any run state exists on mismatch.
- [x] 2.2 GREEN: `run_governed_evaluation` admits, then creates the
  `ContextReadLedger`, declares the budget in the confirmed projection's
  autonomy envelope + `context-admission-record`, seals and reads cell
  receipts through the ledger.
- [x] 2.3 RED/GREEN: budget exhaustion -> ledger `budget_exceeded` resumable
  unknown checkpoint, context-discipline `unmet`, completion gate blocks,
  receipt `status: failed` with a resumable blocker — never a pass.

## 3. Receipt -> evidence (#466 producer obligation, RED first)

- [x] 3.1 RED: `pack-context-evidence` exists with `es-budget-receipt` in
  `evidence_standard_ids` and claim groundings; the context-discipline
  goal-satisfaction registration cites it and is `satisfied`; waived set no
  longer contains the oracle.
- [x] 3.2 GREEN: `_finding_packs` grounds the ledger receipt into the pack;
  `_register_goal_satisfactions` wires the context pack; `RUNTIME_ORACLES`
  gains `oracle-context-discipline`; `WAIVED_REASONS` loses it;
  `tests/test_v2_evaluation.py` disclosures test now asserts the real
  declared budget.

## 4. Governance

- [x] 4.1 Doc updated: registry named as machine-readable source of record;
  recorded-requirement sentence marked implemented.
- [x] 4.2 Full suite, ruff, layout + openspec governance
  (`openspec validate wire-context-ledger-production --strict`),
  `check_evaluation_assets`, `build_skill_packages --check`, gitnexus
  analyze + detect-changes.
