## ADDED Requirements

### Requirement: Delivery metrics are receipt-backed

The host adapter SHALL derive task, validation, review, host-availability, and
unresolved-obligation metrics from one revision-bound delivery receipt
snapshot. It SHALL embed the snapshot digest in each delivery projection.

#### Scenario: Reports share one exact snapshot

- **WHEN** the adapter renders a Technical Research Package and a Human
  Research Report for a run
- **THEN** both reports identify the same receipt snapshot digest and revision
- **AND** their metrics are deterministic projections of that snapshot

### Requirement: Edited delivery claims fail closed

The host adapter SHALL reject delivery registration when a report differs from
the canonical projection of its current receipt snapshot.

#### Scenario: Reported pass count differs from receipt

- **WHEN** the receipt contains 33 passed validations and a report says 30
- **THEN** delivery registration fails with a field-level metric mismatch
- **AND** no host completion authority is asserted
