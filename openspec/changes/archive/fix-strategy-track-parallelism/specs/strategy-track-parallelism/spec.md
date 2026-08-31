## ADDED Requirements

### Requirement: Active strategy tracks have exact Slot coverage

An explicit strategy track SHALL define an identifier, priority, closure
oracle, and evidence boundary. Every active track SHALL map to at least one
executable Decision Slot, and every Slot SHALL identify exactly one valid track.

#### Scenario: Four independent tracks remain independent

- **WHEN** an accepted strategy defines four active tracks and four mapped
  research questions
- **THEN** handoff compilation emits four track-bound Decision Slots
- **AND** each Slot retains its track priority, closure oracle, and evidence
  boundary

### Requirement: Dependency serialization is justified

Each native dependency edge SHALL include a machine-readable kind, rationale,
and evidence reference proving either an exact producer artifact relation or a
confirmed authority constraint.

#### Scenario: Arbitrary chain is rejected

- **WHEN** a caller supplies `--depends-on` without structured justification
- **THEN** task registration fails

#### Scenario: Confirmed serialization remains observable

- **WHEN** a confirmed authority constraint justifies serialization
- **THEN** task registration records the edge
- **AND** status and delivery projections expose the blocked dependency and its
  rationale
