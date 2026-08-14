## ADDED Requirements

### Requirement: Retained Finding Pack consumers SHALL use canonical fixtures

The decision, delivery, and strict-delivery lineage test consumers SHALL construct their Finding Pack state through one direct `RunLedger` and a matching ledger-backed `EvidenceResolver`. Each retained Finding Pack SHALL be compiled with the existing `CanonicalFindingPackCompiler`.

#### Scenario: A retained consumer needs a Finding Pack

- **WHEN** a decision, delivery, or strict-delivery consumer constructs a Finding Pack fixture
- **THEN** its fixture SHALL create canonical ledger state directly and compile
  the Finding Pack with `CanonicalFindingPackCompiler`

#### Scenario: A fixture is restarted

- **WHEN** a test reopens its fixture ledger to inspect persisted artifacts
- **THEN** the reopened `RunLedger` SHALL contain the same canonical artifact
  lineage and no source `RunStore` migration is required

### Requirement: Named consumers SHALL exclude retired fixture paths

The named canonical consumers SHALL not import or construct the retired Finding
Pack compiler through a `RunStore` fixture. They SHALL not introduce a runtime
facade, adapter, runtime old-state helper, fallback parser, alias, dual store, or
compatibility migration to preserve the old test setup.

#### Scenario: Static regression inspection

- **WHEN** focused canonical-fixture regression coverage inspects each named
  canonical consumer suite
- **THEN** it SHALL find no `FindingPackCompiler` construction and no
  `RunStore` fixture setup for its Finding Pack path

### Requirement: Canonical fixture migration SHALL preserve consumer behavior

The canonical test fixtures SHALL preserve the existing consumer assertions
for decision lineage, delivery output, and strict delivery evidence lineage.

#### Scenario: Focused canonical-consumer regression

- **WHEN** the decision, delivery, and strict-delivery focused suites run
  against the canonical fixture
- **THEN** they SHALL pass without a production source change

### Requirement: Legacy coverage SHALL retain its explicit boundary

The assurance suite SHALL remain `RunStore` runtime coverage until #165
supplies a verified canonical replacement or retires the runtime. The readiness
suite MAY use the same private test-only legacy fixture until #181 migrates it.
That fixture SHALL not be imported by the named canonical consumers, nor become
a runtime shim, adapter, dual store, or weakened assertion that appears
canonical.

#### Scenario: Canonical consumer fixtures change

- **WHEN** the decision fixture becomes canonical
- **THEN** assurance and retained readiness coverage SHALL not depend on it for
  their legacy-runtime setup

#### Scenario: Legacy regression runs after canonical migration

- **WHEN** the canonical consumer suites run
- **THEN** the assurance and retained readiness regression suites SHALL still
  pass against the private legacy fixture
