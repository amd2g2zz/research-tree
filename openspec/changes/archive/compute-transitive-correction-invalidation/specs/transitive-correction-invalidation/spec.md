## ADDED Requirements

### Requirement: Corrections quarantine every reachable descendant

The system SHALL compute correction invalidation by traversing canonical
artifact parent references from each corrected root. Every reachable descendant,
including one behind an unknown artifact kind, SHALL be quarantined without
deleting immutable history. Artifacts without a path from a correction root
SHALL remain current.

#### Scenario: Unknown intermediate artifact

- **WHEN** a corrected artifact has a descendant through an unclassified
  intermediate artifact kind
- **THEN** the descendant is quarantined and cannot satisfy authority checks

### Requirement: Stale authority reports a deterministic path

The system SHALL reject dispatch, ingress, recovery, and completion authority
that depends on a quarantined descendant and SHALL expose a deterministic
correction-to-descendant stale path.

#### Scenario: Restart after correction

- **WHEN** the coordinator restarts after a correction quarantined a work item
- **THEN** the work item remains rejected with the same stale-path diagnostic
