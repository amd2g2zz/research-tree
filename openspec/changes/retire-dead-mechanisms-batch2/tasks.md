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
  three governance suites and the context-ledger suite to the scripts-path
  precedent (`test_hermes_host_events.py`); adapters import
  `context_ledger_contract` directly; packages regenerated via
  `build_skill_packages.py`.
- [x] 1.4 Delete the eight dedicated test suites and trim the
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

## 3. Verification And Handoff

- [x] 3.1 Run the full local gate battery: pytest, ruff check + format,
  `build_skill_packages.py --check`, `check_openspec_governance.py`,
  `check_docs.py`, `check_repository_layout.py`, retired-name zero-hit greps,
  and `openspec validate retire-dead-mechanisms-batch2 --strict`.
- [x] 3.2 Commit in waves on `feat/issue-421-dead-chain` and push; PR and merge
  are owned by the coordinator.
