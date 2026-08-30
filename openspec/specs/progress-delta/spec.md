## ADDED Requirements

### Requirement: visible progress is derived from canonical delta
Every user-visible update names a canonical delta kind (new_evidence, changed_model, changed_decision, changed_phase, new_blocker, changed_authority, changed_next_action). Repeated unchanged context collapses.

#### Scenario: recoverable failure aggregates
- **WHEN** the same tool-failure kind repeats
- **THEN** the projection groups them with a count and raw receipt refs; the user sees the count, not the noise

#### Scenario: scope/authority change promotes to user-visible
- **WHEN** a failure changes scope, authority, or expected completion
- **THEN** the projection surfaces it as a user-visible delta

#### Scenario: recoverable failure without scope/authority change is internal
- **WHEN** a failure is purely internal (api timeout, transient error)
- **THEN** the projection does NOT surface it; the user only sees canonical deltas
