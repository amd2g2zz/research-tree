## ADDED Requirements

### Requirement: actions are selected by EVSI/cost, uniformly

#### Scenario: better ratio wins
- **WHEN** an expensive high-EVSI action competes with a cheap moderate-EVSI action
- **THEN** the higher EVSI/cost ratio wins

#### Scenario: empty candidate set
- **WHEN** no candidates exist
- **THEN** selectAction returns null

### Requirement: make-or-break claims always go first

#### Scenario: mob action beats a better-ratio non-mob action
- **WHEN** a make-or-break claim's action competes with a non-mob action of better EVSI/cost
- **THEN** the mob action is selected

### Requirement: selections are replayable with regret disclosure

#### Scenario: replay discloses candidates and hindsight-best
- **WHEN** an action is selected
- **THEN** the replay carries the full scored candidate table, the chosen id, and the hindsight-best id

### Requirement: zero-cost candidates raise

#### Scenario: degenerate winner guarded
- **WHEN** a candidate has cost 0
- **THEN** selection raises EVSIError (nothing is free)
