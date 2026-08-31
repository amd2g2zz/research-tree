## 1. Deletion And Relocation

- [x] 1.1 Delete the five graph-verified dead modules (`assurance`,
  `preferences`, `alignment_protocol`, `durable_interaction_state`,
  `interaction_state`) with no alias, bridge, adapter, replacement,
  migration, fallback, or user-data operation.
- [x] 1.2 Relocate the two modules with hard consumers, byte-identical:
  `src/research_tree/openspec_governance.py` → `scripts/openspec_governance.py`
  (CI delivery-gate dependency), `src/research_tree/context_ledger.py` →
  `scripts/context_ledger_contract.py` (packaged adapter contract); record the
  relocations here as relocations, not silent disappearances.
- [x] 1.3 Remove the retired `__init__` re-export blocks and `__all__` entries;
  point `scripts/check_openspec_governance.py` at the sibling module; update the
  three governance suites to the scripts-path precedent
  (`test_hermes_host_events.py`) and restore the context-ledger suite at its
  original path `tests/test_context_ledger.py`, importing
  `context_ledger_contract` from `scripts/` via the same sys.path precedent;
  adapters import `context_ledger_contract` directly; packages regenerated via
  `build_skill_packages.py`.
- [x] 1.4 Delete the nine dedicated test suites and trim the
  alignment_protocol / durable-interaction cases from the surviving suites;
  retire the displayed-confirmation case in `test_feedback_rounds.py` (it
  constructed `AlignmentProtocol` directly) together with its only consumer
  of the cross-file `candidate` fixture.

## 2. Dangling Reference Removal

- [x] 2.1 Remove the `lifecycle_hook` durable try-block: lifecycle events keep
  being recorded to the run event stream; the optional durable interaction
  state mirror is retired with its module.
- [x] 2.2 Remove the retired module paths from the alpha2 group-7/23/29
  acceptance commands and their paired verification receipts (kept identical),
  and from the `project-user-preference-profile` delivery-matrix
  `source_modules` row.
- [x] 2.3 Review follow-up (dangling-reference purge, pairing-only): drop the
  retired `tests/test_assurance_adapters.py` parameter and the pre-existing
  missing `tests/legacy_runstore_fixture.py` parameter (absent from `dev`
  already) from the group-79 command pair — minimal path removal, exit-0
  semantics preserved; repoint the group-82 command pair at
  `scripts/openspec_governance.py` (module relocated in task 1.2); drop the
  retired `src/research_tree/alignment_protocol.py` entry from
  `delivery-policy-v1.json` `canonical_generation_inputs`; drop the retired
  `PreferenceService` symbol from the `project-user-preference-profile`
  delivery-matrix row, leaving `public_surface` present as an empty array
  (schema-legal precedent: the `alpha2-contract-ratification` row in the same
  matrix). Command edits are pairing-only: each `acceptance_command` and its
  paired receipt `command` remain identical, while receipt digests and
  `source_revision` are historical records bound to their recorded source
  revision and are intentionally not rewritten when command text is
  re-paired. Group 7's bare commands are the mechanical result of removing
  every retired path parameter (none survived), not a semantic expansion.
- [x] 2.4 Final review sweep (pairing-only): drop the dev-absent
  `tests/test_alpha1_baseline.py`, `tests/test_execution_boundary.py`, and
  `tests/test_native_dynamic_workflows.py` parameters (suites deleted by
  PR #434 / ee524ab) from the group 1/17/26/42 command pairs — minimal path
  removal, exit-0 semantics preserved. Group 1 and 17 keep bare
  `uv run pytest -q` commands as the mechanical result of removing every
  retired path parameter (task 2.3 precedent). Receipt digests,
  `source_revision`, and `recorded_at` are historical records bound to their
  recorded source revision and are intentionally not rewritten; each
  `acceptance_command` and its paired receipt `command` remain identical.
- [x] 2.5 Close the defect class mechanically: `scripts/openspec_governance.py`
  now scans every task-execution alpha2 acceptance command plus its paired
  task-verification receipt command for `tests/` path tokens and reports a
  `missing_tests_entrypoint` violation when the path is absent from repository
  HEAD, for every group state (planned included) — closing the gap that let
  dev-absent suites survive review rounds. Red-first tests added to
  `tests/test_openspec_governance.py`; the gate was verified to fail on a
  reintroduced residue (group 17) and to pass (exit 0, zero violations) on the
  repaired registries.

## 3. Verification And Handoff

- [x] 3.1 Run the full local gate battery: pytest, ruff check + format,
  `build_skill_packages.py --check`, `check_openspec_governance.py`,
  `check_docs.py`, `check_repository_layout.py`, retired-name zero-hit greps,
  and `openspec validate retire-dead-mechanisms-batch2 --strict`.
- [x] 3.2 Commit in waves on `feat/issue-421-dead-chain` and push; PR and merge
  are owned by the coordinator.
