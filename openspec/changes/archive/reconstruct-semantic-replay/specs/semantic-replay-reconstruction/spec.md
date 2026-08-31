## ADDED Requirements

### Requirement: Replay recomputes canonical lifecycle semantics

The replay operation SHALL rebuild lifecycle state from immutable initialization
parents, canonical lifecycle events, correction events, and canonical host
event inputs. It SHALL compare the recomputed state with materialized state
without using the materialized state as the source of truth.

#### Scenario: A self-consistent forged projection is present

- **WHEN** a stored state has a valid self-digest but its event is not a legal
  lifecycle edge or violates actor authority
- **THEN** replay reports `chain_intact: true`, `verified: false`, and the
  earliest divergent event/field

#### Scenario: Materialized state rows are absent

- **WHEN** cached `research-run-state` rows are unavailable but immutable
  lifecycle/correction events and their input artifacts remain
- **THEN** replay reconstructs the terminal state without writing projections,
  sets `projection_rebuilt: true`, and returns the same semantic digest as a
  replay with the cache present

### Requirement: Replay exposes semantic evidence

Replay output SHALL include the stored and recomputed terminal digests, a
deterministic semantic digest, unresolved completion obligations, legal next
actions, and earliest divergence evidence.

#### Scenario: Canonical state is replayed twice

- **WHEN** immutable inputs and events are unchanged
- **THEN** repeated replay returns identical semantic digests and transition
  evidence

#### Scenario: Acceptance references a superseded delivery

- **WHEN** a completion record points to an older delivery while a newer
  canonical delivery is current
- **THEN** replay reports `verified: false` with completion-input divergence
  instead of treating the terminal state as accepted
