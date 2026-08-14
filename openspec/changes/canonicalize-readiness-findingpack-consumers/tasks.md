## 1. Contract and RED Evidence

- [x] 1.1 Validate this issue-local OpenSpec change strictly before source edits.
- [x] 1.2 Add and run a focused RED regression proving the named consumers
  still use the retired fixture or state-copy path.

## 2. Canonical Test Fixtures

- [x] 2.1 Migrate readiness helpers to direct canonical ledger, resolver, and
  canonical Finding Pack fixture state while preserving assertions.
- [x] 2.2 Replace strict-evidence's `RunStore` copy with a direct canonical
  negative fixture and retain the legacy-compiler rejection assertion.
- [x] 2.3 Add static regression coverage prohibiting the retired fixture,
  `RunStore` state copy, and old compiler construction in named consumers.

## 3. Verification and Queue Handoff

- [x] 3.1 Run focused and full regression tests plus `ruff`.
- [x] 3.2 Run strict OpenSpec, governance, docs, package, and delivery gates.
- [ ] 3.3 After source acceptance, register group 80 and its source-bound
  receipt, then open the sole non-WIP PR for #181 targeting `dev`.
