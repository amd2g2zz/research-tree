## ADDED Requirements

### Requirement: Retired RunStore scheduler source is absent

After the public retirement slice, the repository SHALL contain no
`src/research_tree/scheduler.py` implementation, import path, root export, or
dedicated scheduler behavior suite for the retired RunStore scheduler. It MUST
NOT add a replacement, alias, bridge, adapter, migration, fallback, or
user-data operation.

#### Scenario: Runtime source is inspected

- **WHEN** the runtime Python modules are parsed after the purge
- **THEN** `research_tree.scheduler` and relative `scheduler` imports resolve
  nowhere and the scheduler implementation file is absent

### Requirement: Current scheduler contract and package references are absent

The project SHALL not retain `RT-010` or any generated-package reference to
the retired `AdaptivePortfolioScheduler`, its error types, or its
`work-portfolio` writer boundary. Historical delivery artifacts MAY retain
immutable descriptions of the completed retirement.

#### Scenario: Current deliverables are inspected

- **WHEN** current documentation and generated packages are scanned
- **THEN** no retired scheduler public contract or generated artifact
  advertises the deleted boundary
