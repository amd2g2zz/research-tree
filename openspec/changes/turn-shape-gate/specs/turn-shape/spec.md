## ADDED Requirements

### Requirement: turn records measure composition shape

Each alignment turn record may carry a `turn_shape` section with three
measured dimensions — length, decision_count, question_count — plus the #499
`transformation_ratio` slot, and a mechanical verdict against named caps.

#### Scenario: compliant shape is recorded
- **WHEN** a composed turn is measured within all caps and appended
- **THEN** the persisted record carries `turn_shape.verdict == "compliant"` with no violations

#### Scenario: over-long turns are flagged with the named dimension
- **WHEN** the composed turn exceeds `MAX_TURN_LENGTH`
- **THEN** the record's verdict is `violated` naming `length`, and the record still persists as the continuity grounding

#### Scenario: more than one decision point is a mechanical violation
- **WHEN** a turn carries more than one decision point or more than one question
- **THEN** the verdict is `violated` naming `decision_count` / `question_count`

### Requirement: legacy records stay readable

Schema 1 records (pre-turn-shape) remain valid inputs to the store and the
continuity gate.

#### Scenario: schema 1 record without turn_shape reads fine
- **WHEN** the record file contains a schema 1 record
- **THEN** it parses, grounds continuity, and reports `last_turn_shape: None`

### Requirement: the shape verdict is surfaced to the next turn

The refresh receipt carries the latest record's shape verdict.

#### Scenario: receipt reports the last shape verdict
- **WHEN** refresh_validation runs over a record file whose latest record is violated
- **THEN** the receipt reports `last_turn_shape: "violated"`

### Requirement: the verdict is derived, never asserted

A record whose verdict contradicts its recorded violations is a schema error.

#### Scenario: inconsistent verdict is rejected
- **WHEN** a turn_shape section claims `compliant` while carrying violations
- **THEN** the append or read raises a turn-record schema error
