## ADDED Requirements

### Requirement: sources register with provenance into the reasoning path

#### Scenario: registration persists through the #547 surface
- **WHEN** a source with origin/reliability/incentive-vector is registered
- **THEN** the sources table holds it for downstream scoring

### Requirement: reliability-weighted point estimate

#### Scenario: conflicting verdicts resolve toward reliability
- **WHEN** a high-reliability source supports and a low-reliability source refutes
- **THEN** the point estimate posterior is > 0.5 (method weighted-vote)

### Requirement: citation chains collapse to the independent root

#### Scenario: citing source merges into the original
- **WHEN** s2's provenance cites s1's origin and both are listed
- **THEN** the independence roots are exactly [s1]

### Requirement: quick-check flags conflicts inline

#### Scenario: contradiction flagged
- **WHEN** a new refuting verdict arrives for a claim whose evidence index holds a supporting verdict
- **THEN** quickCheck reports conflict with the contradicting source

#### Scenario: consistent evidence passes
- **WHEN** a new verdict agrees with the index
- **THEN** no conflict is flagged

#### Scenario: conflict index counts contradicting pairs
- **WHEN** one supporting and one refuting verdict exist for a claim
- **THEN** the conflict index reports 1 pair
