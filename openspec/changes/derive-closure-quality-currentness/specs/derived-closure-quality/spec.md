## ADDED Requirements

### Requirement: Closure quality is derived from the current graph

The closure assessor SHALL derive provenance independence, counterevidence,
reviewer/method independence, and contradiction status from exact current
Finding, evidence, and adjudication references. Caller-supplied groups,
strings, and booleans SHALL NOT create a passing quality check.

#### Scenario: Same-method evidence is not independent
- **WHEN** two current evidence branches use the same acquisition method
- **THEN** provenance independence is false and no closure token is issued

#### Scenario: Same-worker review is not independent
- **WHEN** the adjudication reviewer matches a producing worker
- **THEN** reviewer independence is false and no closure token is issued

#### Scenario: Missing adjudication is not counterevidence
- **WHEN** a decision has no current bound closure adjudication
- **THEN** caller-provided counterevidence text cannot satisfy the check

#### Scenario: Contradiction is derived from Finding effects
- **WHEN** a complete current Finding set contains a contradiction without a
  resolving adjudication
- **THEN** contradiction disposition is active and closure remains inconclusive

### Requirement: Closure tokens are revision-bound

The token digest SHALL bind the complete current graph and derived quality
payload using deterministic canonical serialization. `is_current()` SHALL
recompute and compare that digest and SHALL return false when any bound
EvidenceArtifact, adjudication, OracleRun, Finding, Decision, or target is
superseded, missing, or changed.

#### Scenario: Equivalent graph produces an equivalent token
- **WHEN** the same current graph is assessed with different assessment IDs
- **THEN** the issued closure token is identical

#### Scenario: Superseding evidence invalidates a token
- **WHEN** a bound EvidenceArtifact receives a newer revision
- **THEN** `is_current()` returns false for the prior assessment

#### Scenario: Superseding adjudication or OracleRun invalidates a token
- **WHEN** a bound adjudication or OracleRun receives a newer revision
- **THEN** `is_current()` returns false for the prior assessment
