## ADDED Requirements

### Requirement: proposal-shaped gaps require a proportionality assessment

When the engine emits contract terms for a proposal-shaped gap, the required
traces include `proportionality_assessment`; the engine verifies presence and
schema of direction/finding/alternative/reframing and never the content.

#### Scenario: pointing response on a proposal-shaped gap
- **WHEN** the cap is discrimination and the gap is proposal-shaped
- **THEN** required traces are `option-set` and `proportionality_assessment`

#### Scenario: generation response on a proposal-shaped gap
- **WHEN** the cap is generation and the gap is proposal-shaped
- **THEN** required traces are `possibility-survey` and `proportionality_assessment`

#### Scenario: misunderstood-intent gaps stay guess-shaped
- **WHEN** the gap is disputed or reopened by a correction
- **THEN** required traces are `guess-statement` only

### Requirement: the registry append is conservative

The new type enters the frozen registry once; duplicates are rejected and the
initial-type export moves with it.

#### Scenario: duplicate registration is rejected
- **WHEN** `proportionality_assessment` is registered again
- **THEN** `DuplicateTraceTypeError` names the type

#### Scenario: a turn without the required assessment fails verification
- **WHEN** a recorded turn omits the required `proportionality_assessment` trace
- **THEN** `verify_traces` fails closed naming the missing term
