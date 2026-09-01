## ADDED Requirements

### Requirement: Pinned Alpha1 adversarial manifest
The system SHALL provide a versioned public manifest for the `0.0.1-a1`
baseline. The manifest MUST identify the full immutable commit, all three host
package locations, unique case identifiers, an execution disposition, replay
command when executable, category, host, and opaque oracle identifier.

#### Scenario: Manifest pins the released baseline
- **WHEN** the Alpha1 manifest is loaded
- **THEN** validation accepts only tag `0.0.1-a1` with its expected full commit
  and all required host package keys

#### Scenario: Manifest rejects malformed case metadata
- **WHEN** a case has a duplicate id, unknown host, unknown category, missing
  oracle identifier, or an executable disposition without a command
- **THEN** validation SHALL reject the manifest with a specific error

### Requirement: Worker-visible fixture material excludes answer keys
The public manifest SHALL contain replay inputs and opaque oracle identifiers
only. It MUST NOT contain an expected unsafe outcome, hidden acceptance
material, or a fix verdict.

#### Scenario: Public fixture is inspected
- **WHEN** a caller loads every public case mapping
- **THEN** no mapping SHALL expose an unsafe outcome or confirmed-fix field

### Requirement: Evaluator classifies observations conservatively
The evaluator SHALL classify a reproduced unsafe behavior as
`vulnerability_reproduced`, an unverified non-reproduction as `inconclusive`,
and a non-reproduction with nonempty corroborating evidence as `fix_confirmed`.

#### Scenario: Non-reproduction lacks corroboration
- **WHEN** a case is evaluated with no unsafe observation and no evidence
  references
- **THEN** the result status SHALL be `inconclusive`

#### Scenario: Candidate evidence corroborates a safe observation
- **WHEN** a case is evaluated with no unsafe observation and one or more
  evidence references
- **THEN** the result status SHALL be `fix_confirmed`

### Requirement: Result receipts preserve replay provenance
The evaluator SHALL produce a deterministic manifest result with baseline
identity, one result per registered case, opaque oracle identity, status,
execution disposition, and evidence references. Aggregate counts SHALL equal
the contained result statuses.

#### Scenario: A complete observation map is evaluated
- **WHEN** the evaluator processes a valid manifest and observation mapping
- **THEN** it SHALL produce one receipt per case and accurate aggregate counts
