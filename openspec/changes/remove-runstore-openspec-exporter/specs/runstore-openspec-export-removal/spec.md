## ADDED Requirements

### Requirement: RunStore OpenSpec exporter is absent

The project SHALL not publish `OpenSpecExporter`, `OpenSpecExport`,
`OpenSpecExportError`, or `InvalidOpenSpecExportError`, and
`research_tree.openspec` SHALL not be importable. It SHALL not provide a
replacement exporter, bridge, alias, compatibility reader, migration, fallback,
dual-state path, or user-data operation for retired RunStore OpenSpec export.

#### Scenario: A caller resolves the retired boundary

- **WHEN** a caller inspects `research_tree` or resolves
  `research_tree.openspec`
- **THEN** none of the retired symbols or module resolves and no user-owned
  runtime data is accessed or changed

### Requirement: Legacy exporter consumers are removed

The dedicated exporter behavior suite SHALL be absent, together with the E2E
consumer that imports its RunStore/Finding Pack fixture. Current canonical
ledger and Finding Pack runtime interfaces SHALL remain available.

#### Scenario: Maintainers inspect the runtime test boundary

- **WHEN** maintainers inspect the source tree after retirement
- **THEN** no runtime source imports the retired module, no dedicated exporter
  or E2E consumer remains, and canonical runtime interfaces still resolve

### Requirement: Active authority no longer advertises export

Active product, operational, reference, Alpha2 registry, and generated package sources SHALL not
advertise the retired OpenSpec exporter, its module, or its dedicated test/E2E
paths. Historical governed documentation MAY retain factual audit material only.

#### Scenario: Active sources are inspected after retirement

- **WHEN** maintainers validate current documentation, registry ownership, and
  generated packages
- **THEN** group 82 / issue #176 owns the removal, no active source advertises
  the retired export boundary, and historical material is not treated as a
  current contract

### Requirement: Historical verified commands remain source-bound

The governance validator SHALL preserve a verified group command receipt as
historical evidence. When an accepted Python entrypoint has been retired from
the current tree, the validator SHALL accept it only if Git resolves the exact
entrypoint at that receipt's `source_revision`; an absent current entrypoint
without that proof SHALL remain a governance violation.

#### Scenario: A verified legacy test is intentionally retired

- **WHEN** the current tree no longer contains a Python entrypoint named in a
verified group's acceptance command
- **THEN** validation accepts the historical command only when the receipt's
  source revision is an ancestor of the current revision and contains that
  exact path
