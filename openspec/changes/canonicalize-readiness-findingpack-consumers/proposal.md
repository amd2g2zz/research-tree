## Why

After #180, `tests/test_readiness.py` still obtains its package graph from the
private `legacy_runstore_fixture`, and strict-evidence tests copy a `RunStore`
snapshot into a `RunLedger`. Those are test-only compatibility paths that
obscure the canonical readiness boundary.

## What Changes

- Move named readiness and strict-evidence consumers to direct `RunLedger`,
  ledger-backed evidence, and `CanonicalFindingPackCompiler` fixtures.
- Preserve existing readiness, closure, repository-fit, and strict rejection
  assertions.
- Add regression checks that forbid the retired fixture path and state-copy
  helper in the named canonical consumers.

## Capabilities

### New Capabilities

- `canonical-readiness-test-fixtures`: readiness and strict-evidence tests
  exercise canonical Finding Pack lineage without copied `RunStore` state.

### Modified Capabilities

- None; runtime APIs and persisted contracts do not change.

## Impact

- Only test fixtures, their targeted tests, the issue-local OpenSpec change,
  and the shared execution registry/receipt after acceptance change.
- No runtime bridge, adapter, alias, fallback, dual store, compiler deletion,
  assurance migration, or exporter change is included.
