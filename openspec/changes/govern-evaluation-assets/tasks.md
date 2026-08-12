## 1. Contract And Red Tests

- [x] 1.1 Extend the evaluation path registry with enforceable class policies,
  compatibility, identifiers, byte limits, and entrypoint metadata.
- [x] 1.2 Add failing tests for canonical paths, schema/provenance errors,
  hidden-oracle leakage, oversized/raw transcripts, and non-destructive legacy
  inventory.

## 2. Schemas And Checker

- [x] 2.1 Add versioned schemas and safe fixtures for governed evaluation asset
  classes while preserving `evaluation/cases/v1.json` compatibility.
- [x] 2.2 Implement `scripts/check_evaluation_assets.py` with deterministic,
  read-only diagnostics and a public baseline validation entrypoint.
- [x] 2.3 Document the canonical namespace, tracked/disposable lifecycle, safe
  oracle reference boundary, and manual legacy migration policy.

## 3. Verification And Receipt

- [x] 3.1 Run focused tests and both Ruff gates, then the complete regression
  suite and strict issue-local/umbrella OpenSpec checks.
- [ ] 3.2 Record source-bound group-20 output/receipt, update verification state
  and owned umbrella tasks only from passing evidence, then run governance,
  delivery, and diff checks.
