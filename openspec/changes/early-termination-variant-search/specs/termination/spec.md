## ADDED Requirements

### Requirement: variant search is mechanical over the kill graph

{relax | replace | bypass} candidates are filtered by whether the DAG still stands.

#### Scenario: standing variants survive
- **WHEN** three candidates exist and one has dag_still_stands=false
- **THEN** only the two standing variants are returned

#### Scenario: no standing variant means 埋了 is honest
- **WHEN** no candidate keeps the DAG standing
- **THEN** searchVariants returns empty

### Requirement: the inquiry presents choices, never a verdict

#### Scenario: three-choice inquiry
- **WHEN** the inquiry is built for a refuted make-or-break
- **THEN** choices are [bury, continue, switch-variant] with the evidence summary and standing variants; no verdict field is populated

### Requirement: bury recommends NO-GO (final verdict at freeze)

#### Scenario: bury recommendation
- **WHEN** the user buries
- **THEN** the recommendation is NO-GO with is_final=false

### Requirement: budget savings measured against the H5 threshold

#### Scenario: savings ≥50%
- **WHEN** actual run = 4h vs full-run 12h
- **THEN** savings ratio ≈ 2/3 and meets_h5_threshold is true

#### Scenario: savings <50%
- **WHEN** actual run = 10h vs 12h
- **THEN** meets_h5_threshold is false
