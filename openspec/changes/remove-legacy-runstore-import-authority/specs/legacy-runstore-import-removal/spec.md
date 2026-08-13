## ADDED Requirements

### Requirement: Legacy RunStore import authority is absent

The project SHALL not publish `LegacyRunStoreImporter`, `LegacyImportError`,
`LegacyImportReceipt`, `LegacyImportResult`, or the
`research_tree.legacy_import` module. It SHALL not provide an importer,
compatibility alias, read projection, migration route, or replay mechanism for
retired filesystem `RunStore` payloads.

#### Scenario: Retired programmatic imports cannot resolve

- **WHEN** a caller inspects the root package or resolves
  `research_tree.legacy_import`
- **THEN** no retired symbol is published and the module cannot be imported

### Requirement: New SQLite ledgers omit legacy receipt state

A newly initialized `RunLedger` SHALL not create a `legacy_imports` table or
provide `record_import_receipt` or `get_import_receipt` APIs. It SHALL retain
current canonical run, artifact, event, and content tables.

#### Scenario: New ledger contains only current authority tables

- **WHEN** a caller initializes a new workspace ledger
- **THEN** `legacy_imports` is absent, receipt APIs are absent, and the
  canonical `runs`, `artifacts`, `events`, and `content_objects` tables exist

### Requirement: Active Alpha2 governance no longer advertises import

Active execution, verification, issue-map, delivery-matrix, and umbrella task registries SHALL remove the legacy import capability and group 34. They SHALL register group 55 / issue #167 as a planned breaking-removal slice before verification evidence is recorded.

#### Scenario: Governance resolves the removal slice

- **WHEN** the Alpha2 governance registry is validated before implementation
- **THEN** group 55 is planned with the exact removal acceptance command and
  no active capability row names legacy RunStore import
