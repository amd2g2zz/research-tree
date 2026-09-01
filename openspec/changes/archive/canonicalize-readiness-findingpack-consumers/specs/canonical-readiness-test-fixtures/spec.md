## ADDED Requirements

### Requirement: Named readiness consumers SHALL construct canonical lineage directly

`tests/test_readiness.py` and the strict-evidence readiness consumer SHALL
construct Finding Pack, Decision, delivery, and readiness state through one
direct `RunLedger`, a matching ledger-backed `EvidenceResolver`, and
`CanonicalFindingPackCompiler`.

#### Scenario: A named readiness test creates a package

- **WHEN** it needs a Technical Research Package for readiness evaluation
- **THEN** it SHALL use direct canonical lineage and current expected revision

#### Scenario: A strict-evidence test needs a legacy-negative case

- **WHEN** it checks rejection of a legacy-unverified finding
- **THEN** it SHALL append the required negative artifact directly to the
  canonical ledger without copying a `RunStore` snapshot

### Requirement: Named consumers SHALL exclude retired fixture paths

The named canonical consumers SHALL not import the private legacy fixture,
construct `RunStore` fixture state, copy a `RunStore` graph, or construct the
retired Finding Pack compiler except for the dedicated rejected-construction
assertion.

#### Scenario: Static lineage regression

- **WHEN** focused regression inspects the named test consumers
- **THEN** it SHALL reject retired fixture paths and state-copy helpers while
  retaining the dedicated negative compiler assertion

### Requirement: Migration SHALL preserve readiness behavior

The canonical fixture migration SHALL retain current readiness gate,
repository-fit, package-integrity, and strict rejection assertions without a
runtime source change.

#### Scenario: Focused readiness regression

- **WHEN** readiness and strict-evidence test suites run
- **THEN** they SHALL pass using only direct canonical fixture lineage

### Requirement: Legacy coverage MUST remain explicitly isolated

This requirement MUST preserve assurance and exporter coverage as explicit
legacy consumers until they are separately migrated or retired. The private
fixture SHALL not become a runtime bridge or be imported by the named canonical
consumers.

#### Scenario: Canonical readiness migration completes

- **WHEN** this change removes readiness fixture imports
- **THEN** assurance and exporter tests retain their explicit legacy boundary
