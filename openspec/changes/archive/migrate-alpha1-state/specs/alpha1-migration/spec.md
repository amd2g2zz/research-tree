## ADDED Requirements

### Requirement: Alpha1 checkpoint compatibility is diagnostic-only

The system SHALL inventory known Alpha1 native and Hermes checkpoint paths
without modifying them. Every inventory item SHALL be source-bound, have a
stable diagnostic disposition, and carry no completion authority.

#### Scenario: Corrupt checkpoint state

- **WHEN** a checkpoint is malformed
- **THEN** the system reports `partial_or_corrupt_store` and creates no
  writable completion authority

### Requirement: Legacy completion retirement requires release evidence

The system SHALL retire legacy writable completion paths only after a registered
release gate has a passing status. Canonical completion SHALL remain
coordinator-only.

#### Scenario: Failed release gate

- **WHEN** a caller attempts cutover with a failing gate
- **THEN** the system rejects the cutover without changing legacy paths
