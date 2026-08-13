## 1. Contract And Governance

- [x] 1.1 Define the current-only removal contract and the no-user-data
  mutation boundary for legacy RunStore import authority.
- [x] 1.2 Replace active group-34/import capability ownership with planned
  group 55 / issue #167 registry entries and an exact acceptance command.

## 2. Focused Regressions

- [x] 2.1 Add failing absence tests for root exports, the retired module, ledger
  receipt APIs, and the `legacy_imports` DDL.

## 3. Breaking Removal

- [x] 3.1 Delete the legacy importer module, root exports, and dedicated
  importer tests without a compatibility replacement.
- [x] 3.2 Remove legacy receipt DDL, type-only imports, helper functions, and
  `RunLedger` APIs while preserving current ledger tables.
- [x] 3.3 Remove maintained active documentation and registry references to
  legacy RunStore import; retain historical source only through Git history.

## 4. Verification And Handoff

- [ ] 4.1 Run the group-55 focused acceptance command, strict OpenSpec
  validation, governance validation, and regression checks.
- [ ] 4.2 Commit the source removal before recording source-bound group-55
  verification evidence.
- [ ] 4.3 Record the group-55 receipt, mark the registry verified, and run the
  required final checks.
