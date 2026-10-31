## ADDED Requirements

### Requirement: make-or-break claims run dual-seat with equal budgets

#### Scenario: equal budgets
- **WHEN** dual-seat runs with budgetPerSeat 5000
- **THEN** plaintiff and defense each carry budget_ms 5000

#### Scenario: attack goes first
- **WHEN** dual-seat runs
- **THEN** the plaintiff seat starts before the defense seat

#### Scenario: non-mob claims stay single-seat
- **WHEN** shouldRunDualSeat is called for a non-mob claim
- **THEN** it returns false

### Requirement: EVSI settles independently per seat

#### Scenario: independent settlement
- **WHEN** the plaintiff finds counter-evidence and the defense does not
- **THEN** the plaintiff's EVSI settlement exceeds the defense's and settlement is "independent"

### Requirement: posterior shift reflects the discovery rate

#### Scenario: counter-evidence shifts toward refutation
- **WHEN** the plaintiff finds counter-evidence and the defense does not
- **THEN** the direction is "toward-refutation" with a positive discovery rate

### Requirement: seat reports are engine facts

#### Scenario: audited seat reports
- **WHEN** dual-seat completes
- **THEN** at least two provider.action events land (one per seat)
