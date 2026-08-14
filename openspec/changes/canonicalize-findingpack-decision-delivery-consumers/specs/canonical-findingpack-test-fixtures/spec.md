## ADDED Requirements

### Requirement: Retained Finding Pack consumers SHALL use canonical fixtures

Decision, delivery, and strict-delivery consumers SHALL construct Finding Pack
state through one direct `RunLedger`, matching ledger-backed `EvidenceResolver`,
and existing `CanonicalFindingPackCompiler`.

#### Scenario: A retained consumer needs a Finding Pack

- **WHEN** a named consumer creates a Finding Pack fixture
- **THEN** it SHALL compile the pack from direct canonical ledger state

#### Scenario: A fixture is restarted

- **WHEN** a test reopens its fixture ledger
- **THEN** the canonical artifact lineage SHALL remain available without a
  source `RunStore` migration

### Requirement: Named consumers SHALL exclude retired fixture paths

Named canonical consumers SHALL not construct `FindingPackCompiler` or
`RunStore` fixture state, or introduce a runtime facade, adapter, runtime
old-state helper, fallback, alias, dual store, or compatibility migration.

#### Scenario: Static regression inspection

- **WHEN** focused regression inspects every named canonical suite
- **THEN** it SHALL find no retired compiler or `RunStore` fixture path

### Requirement: Canonical fixture migration SHALL preserve behavior

Canonical fixtures SHALL preserve existing decision lineage, delivery output,
and strict delivery evidence-lineage assertions.

#### Scenario: Focused canonical-consumer regression

- **WHEN** the three named suites run against the canonical fixture
- **THEN** they SHALL pass without a production source change

### Requirement: Legacy coverage SHALL retain its explicit boundary

Assurance and export SHALL remain `RunStore` coverage until separately migrated
or retired. Readiness MAY use the same private test-only fixture
until #181. Named canonical consumers SHALL not import it, and it SHALL not
become a runtime shim, adapter, dual store, or weakened assertion.

#### Scenario: Canonical consumer fixtures change

- **WHEN** a named fixture becomes canonical
- **THEN** assurance, export, and retained readiness SHALL keep their legacy setup

#### Scenario: Legacy regression runs after canonical migration

- **WHEN** canonical consumers run
- **THEN** assurance, export, and retained readiness regressions SHALL still pass
