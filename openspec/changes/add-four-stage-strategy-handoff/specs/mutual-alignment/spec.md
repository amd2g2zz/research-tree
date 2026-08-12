## ADDED Requirements

### Requirement: Alignment handoff binds the complete StrategyProjection
An AlignmentHandoff SHALL reference the current DecisionFrame, displayed StrategyProjection id, revision, digest, display receipt, requester response, and contextual confirmation disposition; a generic strategy string or acknowledgement SHALL NOT authorize research.

#### Scenario: Alignment changes after projection display
- **WHEN** alignment or DecisionFrame lineage changes after a projection is displayed
- **THEN** the display and confirmation candidates become stale and a new StrategyProjection revision is required

