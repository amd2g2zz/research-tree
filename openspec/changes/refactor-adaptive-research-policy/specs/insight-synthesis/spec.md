## MODIFIED Requirements

### Requirement: versioned lineage-rich digest
Insight Digest SHALL validate and expose schema/producer version, exact source and Slot references, classified statements, evidence classes, facts, hypotheses, contradictions, gaps, limitations, confidence/calibration, changed beliefs, recommendations, previous digest, parent references, and realized delta. It SHALL expose uncovered, thin, contested, qualified, and converging signals as policy inputs, but SHALL NOT issue closure or completion.

#### Scenario: findings are synthesized
- **WHEN** a verified Finding Pack batch is ingested
- **THEN** sorted canonical inputs produce a lineage-rich digest without lifecycle mutation.

### Requirement: bounded growth trigger
Growth SHALL be attributable to a new gap, contradiction, invalid premise, failed oracle, method limitation, or material uncertainty. Duplicate-only input SHALL record zero closure-relevant change and no-progress, without persisting an action or mutating run state.

#### Scenario: malformed lineage
- **WHEN** a digest contains a missing, duplicate, stale, or wrong-slot reference
- **THEN** validation rejects it before policy consumption.
