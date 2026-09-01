## ADDED Requirements

### Requirement: Assurance SHALL use the canonical ledger directly

The public assurance selector and runner SHALL require a `RunLedger`; the
runner SHALL also require a matching ledger-backed `EvidenceResolver`. Every
write SHALL receive an explicit expected run revision.

#### Scenario: A high-assurance decision is evaluated

- **WHEN** a canonical selection and decision are evaluated
- **THEN** selection, evidence, follow-up or blocked decision, and resolution
  artifacts SHALL be appended through the same `RunLedger` with exact parents

#### Scenario: A stale assurance writer submits a result

- **WHEN** its expected revision is no longer current
- **THEN** the ledger SHALL reject the write before any assurance artifact is
  appended

### Requirement: Failed assurance SHALL preserve canonical decision lineage

Failed block-mode assurance SHALL revise the decision through
`CanonicalDecisionLedgerCompiler` and retain canonical Finding Pack and
evidence references.

#### Scenario: An assurance review blocks a decision

- **WHEN** a selected block-mode review fails
- **THEN** the resulting decision revision SHALL be blocked and the resolution
  SHALL reference it without mutating prior artifacts

### Requirement: The legacy assurance boundary SHALL be absent

The retired `RunStore` assurance classes and their private fixture SHALL not be
published, imported, or retained as aliases, adapters, fallbacks, or migration
paths.

#### Scenario: Assurance imports are inspected

- **WHEN** the runtime and focused assurance suite are inspected
- **THEN** they SHALL contain no RunStore or legacy decision compiler path
