## ADDED Requirements

### Requirement: Content bytes are immutable and tamper evident
The system SHALL store bytes under a digest-derived workspace locator and SHALL
verify the digest and byte size before publication and on every read.

#### Scenario: Equal bytes are ingested twice
- **WHEN** identical bytes are ingested twice
- **THEN** both operations resolve to one digest and one immutable object

#### Scenario: Published bytes are modified
- **WHEN** a published object no longer matches its digest
- **THEN** reads fail with a typed integrity error

### Requirement: Canonical metadata binds exact content
The system SHALL persist media type, byte size, locator, availability, and
digest in SQLite and SHALL bind registered content to an exact artifact
revision.

#### Scenario: Metadata is registered twice
- **WHEN** identical metadata is registered again
- **THEN** registration is idempotent; conflicting metadata is rejected

#### Scenario: An artifact references unknown content
- **WHEN** a binding is attempted for an unregistered digest
- **THEN** the binding is rejected without changing canonical state

### Requirement: Interrupted publication cannot become evidence
The system SHALL stage and verify bytes before publication and SHALL quarantine
unreferenced staging or published objects during recovery.

#### Scenario: Registration fails after publication
- **WHEN** a published object has no committed ledger metadata or binding
- **THEN** recovery moves it to quarantine and canonical reads exclude it
