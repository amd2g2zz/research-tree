## ADDED Requirements

### Requirement: Continuous interaction reduction

The system SHALL reduce every meaningful interaction event from a prior
interaction state into a successor state and explicit next disposition.  The
controller SHALL remain usable after delivery and SHALL NOT own lifecycle or
completion transitions.

#### Scenario: Consequential vague request

- **WHEN** a requester makes a high-consequence request with missing intended
  use, constraints, or authority
- **THEN** the reducer SHALL request one consequential decision derived from
  those missing slots before direct execution

#### Scenario: Reversible clear request

- **WHEN** a requester gives a clear reversible request with explicit authority
- **THEN** the reducer SHALL record the authority and select execution

### Requirement: Scoped stance and conservative invalidation

The system SHALL preserve agreement, rejection, uncertainty, and correction
per proposition.  A correction SHALL supersede its target, invalidate every
transitively dependent pending unexecuted action while retaining unrelated
work, and select repair.

#### Scenario: Coexisting stances

- **WHEN** a requester agrees with claim A, rejects B, and is uncertain of C
- **THEN** all three scoped stances SHALL remain independently addressable

### Requirement: Authority cannot be inferred

The system SHALL NOT increase authority from inference, reconnaissance,
acknowledgement, silence, or `continue`.

#### Scenario: Continue does not grant a write

- **WHEN** the requester says `continue` without prior write authority
- **THEN** the successor state SHALL retain the previous authority envelope
