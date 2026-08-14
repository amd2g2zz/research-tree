## 1. Contract And Baseline

- [x] 1.1 Validate this issue-local OpenSpec change strictly before source edits.
- [x] 1.2 Record a focused red test proving a named retained consumer still
  uses the retired Finding Pack / RunStore fixture path.

## 2. Canonical Fixtures

- [x] 2.1 Add the minimum direct `RunLedger` fixture graph and matching
  ledger-backed evidence resolver.
- [x] 2.2 Compile Finding Packs through the existing
  `CanonicalFindingPackCompiler`.
- [x] 2.3 Migrate the decision, delivery, and strict-delivery lineage retained
  consumers without changing runtime code.
- [x] 2.4 Keep assurance and retained readiness on an isolated test-only
  legacy-runtime fixture until #181; do not add a shim, dual store, or
  production change.

## 3. Verification And Queue Handoff

- [ ] 3.1 Run focused and relevant full regression tests plus `ruff`.
- [ ] 3.2 Run strict OpenSpec, governance, package, and delivery validation.
- [ ] 3.3 After #175's queue is merged, rebase and record the required
  source-bound receipt/registry entry; otherwise stop at the issue without a
  PR.
