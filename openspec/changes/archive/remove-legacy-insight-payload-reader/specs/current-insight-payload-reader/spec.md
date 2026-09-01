## ADDED Requirements

### Requirement: Insight Digest admits only the complete current payload

The runtime SHALL accept an Insight Digest only when it contains every field
emitted by the current versioned synthesizer, has the supported schema version,
and satisfies current lineage and semantic checks. It SHALL reject a minimal,
unversioned, aliased, defaulted, coerced, or otherwise prior payload before it
can enter policy, scheduler, replay, or delivery state. The runtime SHALL NOT
provide a compatibility reader, adapter, read projection, migration, or
user-data operation.

#### Scenario: Canonical rich digest is supplied

- **WHEN** a caller supplies an unmodified payload emitted by the current
  synthesizer
- **THEN** validation accepts it and current policy/scheduler boundaries may
  consume it without mutation

#### Scenario: Prior minimal digest is supplied

- **WHEN** a caller supplies the former four-field digest or any payload
  missing a current required field
- **THEN** validation rejects it before any current policy, scheduler, replay,
  or delivery state is created or changed

### Requirement: Active governance owns the strict digest reader

Active Alpha2 contracts SHALL register group 60 / issue #174 as the
current-only Insight Digest reader retirement slice. Active schemas and
examples SHALL describe the complete current payload and SHALL NOT publish a
minimal reader contract or fallback parsing behavior.

#### Scenario: Governance resolves strict reader ownership

- **WHEN** maintainers validate the active task, verification, issue, and
  delivery registries
- **THEN** group 60 is planned or source-bound verified with its exact
  acceptance command, and active contracts contain no legacy payload reader
  requirement
