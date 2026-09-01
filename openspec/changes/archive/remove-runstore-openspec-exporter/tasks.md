## 1. Contract And Governance

- [x] 1.1 Define the current-only RunStore OpenSpec exporter removal contract
  and no-user-data-operation boundary.
- [x] 1.2 Register issue #176 / group 82 after verified group 81 with its exact
  source-removal acceptance command.

## 2. Focused Regression

- [x] 2.1 Add a failing absence/current-runtime test for root exports, module
  importability, runtime imports, active authority, generated packages, and
  the retired legacy test/E2E consumer.

## 3. Breaking Removal

- [x] 3.1 Delete `src/research_tree/openspec.py`, its root-package exports,
  and the dedicated legacy exporter behavior suite without a compatibility
  replacement.
- [x] 3.2 Delete the E2E importer/consumer that depends on the exporter-only
  RunStore/Finding Pack fixture; do not alter the #165 assurance fixture.
- [x] 3.3 Remove active documentation and registry claims, then regenerate
  checked-in host packages from the authoritative reference source.

## 4. Verification And Handoff

- [x] 4.1 Run the group-82 focused command, strict OpenSpec validation,
  governance, documentation, package, Ruff, and full regression checks.
- [x] 4.2 Inspect the diff and commit the green source-removal boundary before
  recording any source-bound receipt. Keep raw output local and ignored.
- [x] 4.3 Record the local-only source-bound group-82 receipt, mark the
  registry verified, and rerun the final checks.
