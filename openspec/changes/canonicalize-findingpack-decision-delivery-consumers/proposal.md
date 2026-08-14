## Why

The retained decision, delivery, and strict-delivery lineage tests still
establish some Finding Pack graphs through `RunStore` fixtures and the retired
`FindingPackCompiler`. That obscures the canonical authority exercised by the
consumers and leaves test coverage coupled to a compatibility path.

The assurance suite is a separate legacy-runtime boundary: its selector and
runner only accept `RunStore`, and its blocked path uses the legacy decision
compiler. The still-legacy readiness suite also consumes the old delivery fixture
until #181 migrates it. Both use one private test-only `RunStore` fixture, which
the named canonical consumers never import.

## What Changes

- Replace the decision, delivery, and strict-delivery test fixtures with direct, isolated `RunLedger`
  graphs.
- Compile Finding Packs with the existing `CanonicalFindingPackCompiler` and
  its matching ledger-backed `EvidenceResolver`.
- Preserve each canonical test's behavior and assertions while removing fixture
  migration from `RunStore` and construction through the retired compiler.
- Add narrow regression checks that the retained fixtures expose canonical
  ledger state and do not use the retired compiler.
- Move the preserved legacy `RunStore` setup into a private test-only fixture
  for assurance and readiness until their designated follow-up migrations.
- Do not add a runtime shim, dual store, or production change.

## Capabilities

### New Capabilities

- `canonical-findingpack-test-fixtures`: Retained Finding Pack consumers use
  direct canonical fixtures that exercise only the canonical ledger path.

### Modified Capabilities

- None. This is test-only canonicalization; runtime APIs and persisted
  production contracts do not change.

## Impact

- Changes are limited to the decision, delivery, assurance, readiness, and
  strict-delivery lineage tests plus canonical and legacy test-only fixture
  helpers; the legacy fixture does not claim canonical runtime coverage.
- No runtime facade, adapter, legacy state helper, fallback parser, alias,
  dual store, compatibility migration, compiler deletion, registry, or receipt
  is included until the #175 delivery queue is merged.
