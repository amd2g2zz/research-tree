## ADDED Requirements

### Requirement: Legacy RunStore import is idempotent and source-addressed
The system SHALL fingerprint each source round from its retained file content
and SHALL record a durable receipt for imported, already-imported, quarantined,
or conflicting input.

#### Scenario: Unchanged source is imported twice
- **WHEN** a valid source round is imported again
- **THEN** the second operation reports `already_imported` and creates no new
  canonical artifacts or events

#### Scenario: A different source collides with a canonical run id
- **WHEN** another source digest maps to an existing run id
- **THEN** it receives a conflict receipt and does not mutate the existing run

### Requirement: Imported claims remain historical and unverified
The system SHALL wrap legacy artifacts and events with a `legacy_unverified`
disposition and SHALL not expose legacy validation, closure, or completion text
as a canonical Alpha2 decision.

#### Scenario: Legacy validation says passed
- **WHEN** an imported artifact contains a passed validation string
- **THEN** its copied kind and payload remain historical-only

### Requirement: Invalid sources are quarantined without partial import
The system SHALL validate a complete legacy round before opening a canonical
target run and SHALL retain a quarantine receipt for malformed input.

#### Scenario: A stored artifact payload is malformed
- **WHEN** the importer cannot reconstruct the source round
- **THEN** it records `quarantined` and creates no target run
