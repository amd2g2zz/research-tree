## ADDED Requirements

### Requirement: Canonical claims derive conflicts independently of worker effects

The system SHALL compare canonical claims by normalized subject, predicate,
value, polarity, scope, version, time range, platform, conditions, and
modality. Opposite polarity or incompatible values with overlapping applicable
fields SHALL create a material unresolved Contradiction Packet; caller-authored
option effects SHALL NOT suppress it.

#### Scenario: Two corroborated claims directly disagree

- **WHEN** independently corroborated canonical claims have the same subject,
  predicate, scope, version, time range, platform, conditions, and modality
  but opposite polarity or incompatible values
- **THEN** the system persists an unresolved packet and neither claim is
  decision-authoritative for an affected selected option

#### Scenario: Claims are scope separated

- **WHEN** claims differ by an explicit non-overlapping scope, version, time
  range, platform, condition, or modality
- **THEN** the packet records `scope-separated` and does not retract either
  claim outside its own applicability boundary

### Requirement: Unresolved contradiction closes dependent authority

The system SHALL retract affected durable belief and pending-action effects,
quarantine dependent selected decisions, closure tokens, readiness outputs, and
deliveries, and create successor resolution work. A later packet SHALL reopen a
previously delivered affected thread.

#### Scenario: Contradiction arrives after delivery

- **WHEN** a new material packet targets claims used by a delivered decision
- **THEN** its dependent authority becomes stale and durable interaction state
  reopens the affected thread instead of treating the previous delivery as
  current
