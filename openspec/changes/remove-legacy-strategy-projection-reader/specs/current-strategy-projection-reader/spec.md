## ADDED Requirements

### Requirement: StrategyProjection accepts only the current canonical payload

The runtime SHALL require the complete current `StrategyProjection` field set
for direct construction and serialized loading, including
`preference_influences` in the outer object and its bound display payload. It
SHALL validate one canonical display digest and content hash and SHALL not
infer defaults, map aliases, coerce prior shapes, or expose a legacy reader,
migration, read projection, or compatibility response.

#### Scenario: Canonical projection round-trips

- **WHEN** a caller constructs and serializes a projection with every current
  required field and matching digest values
- **THEN** loading returns the semantically identical projection

#### Scenario: Prior minimal projection is supplied

- **WHEN** a serialized projection omits `preference_influences` from either
  required payload boundary, or direct construction omits it
- **THEN** validation rejects it with a stable field-schema diagnostic before
  any current state is created or changed

### Requirement: Active governance retires the legacy strategy reader

Active Alpha2 contracts SHALL register group 59 / issue #173 as the strict
strategy-projection reader retirement slice. They SHALL not advertise
compatibility reads, default normalization, or legacy projection parsing.
Completed compatibility planning and its evidence SHALL remain only in the
OpenSpec archive.

#### Scenario: Governance resolves the strict reader slice

- **WHEN** maintainers validate active task, verification, issue, and delivery
  registries
- **THEN** group 59 is planned or source-bound verified with the exact strict
  reader acceptance command, and active contracts contain no legacy reader
  requirement
