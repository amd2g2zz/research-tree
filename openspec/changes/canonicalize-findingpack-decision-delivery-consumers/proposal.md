## Why

Decision, delivery, and strict-delivery lineage tests still build some Finding
Packs with `RunStore` and the retired `FindingPackCompiler`, obscuring the
canonical authority under test.

Assurance and export remain `RunStore` boundaries, while readiness consumes the
old delivery fixture until #181. They use one private test-only legacy fixture;
canonical consumers never import it.

## What Changes

- Move the three named consumers to direct `RunLedger`, ledger-backed evidence,
  and `CanonicalFindingPackCompiler` graphs.
- Preserve their behavioral assertions and add static regression checks.
- Isolate unchanged assurance/export/readiness legacy setup without a runtime shim,
  dual store, or production change.

## Capabilities

### New Capabilities

- `canonical-findingpack-test-fixtures`: retained Finding Pack consumers test
  the canonical ledger path directly.

### Modified Capabilities

- None; runtime APIs and persisted contracts do not change.

## Impact

- Only decision, delivery, strict-delivery, assurance, export, readiness, and
  test-only fixture files change.
- No runtime facade, adapter, compatibility migration, compiler deletion,
  registry, or receipt is included until #175 is reachable from `dev`.
