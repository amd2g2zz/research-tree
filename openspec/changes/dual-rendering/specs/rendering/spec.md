## ADDED Requirements

### Requirement: the report narrative carries all 7 sections

#### Scenario: section presence
- **WHEN** a snapshot renders
- **THEN** all 7 sections appear in order with claim posteriors by weight

### Requirement: confidence is qualitative only

#### Scenario: no fake percentages
- **WHEN** a report renders with confidence band "moderate"
- **THEN** the band name appears and no numeric percentage is present

### Requirement: report and 底稿 are same-source projections

Both derive from one snapshot; contradiction is structurally impossible.

#### Scenario: mob claim in both
- **WHEN** a make-or-break claim is committed
- **THEN** the report narrative and the 底稿 supported_claims both carry it

#### Scenario: unverified claims excluded from 底稿 supported
- **WHEN** a minor claim sits below the promotion threshold
- **THEN** the 底稿 lists it under unverified_assumptions, not supported_claims

### Requirement: deleted nodes are disclosed

#### Scenario: audit appendix
- **WHEN** a snapshot carries deleted_nodes
- **THEN** the report discloses them in the audit appendix and the 底稿 carries deleted_nodes_disclosed

### Requirement: refuted claims ground downstream

#### Scenario: refuted_and_disposition
- **WHEN** a refuted claim exists
- **THEN** the 底稿 lists it with a do-not-retry disposition
