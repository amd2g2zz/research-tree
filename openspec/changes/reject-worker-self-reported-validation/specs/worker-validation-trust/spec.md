## ADDED Requirements

### Requirement: Worker validation observations remain non-authoritative

The legacy recursive-search Finding Pack ingestion boundary SHALL treat every
recognized worker-provided `validation_result` mapping as an observation. It
SHALL NOT set or clear the authoritative `validation_passed` value from a
worker-owned status string. A worker-reported `passed` status SHALL be recorded
as `reported_passed_untrusted`.

#### Scenario: Worker reports a validation pass

- **WHEN** a fresh Finding Pack reports `validation_result.status="passed"`
- **THEN** the affected slot SHALL remain unvalidated unless evaluator-owned
  code had already established an authoritative pass
- **AND** its observation status SHALL be `reported_passed_untrusted`

#### Scenario: Worker result follows an authoritative evaluator pass

- **WHEN** a slot already has evaluator-owned `validation_passed=true` and a
  worker later reports any validation status
- **THEN** the worker observation SHALL NOT clear that authoritative value

### Requirement: Worker-reported passes require verifier-needed continuation

For an unvalidated slot, the runtime SHALL create one active mandatory
validation continuation requesting evaluator-owned or independently verified
proof when a worker reports a pass. The continuation is an obligation and SHALL
NOT itself be treated as proof of evaluator ownership or independent
verification. It SHALL not be suppressed by unrelated frontier work. Repeated
fresh reports SHALL retain one active continuation while its current epoch is
open; a later report after that node completes and the slot remains unvalidated
SHALL create a new active continuation epoch. The protocol-owned continuation
SHALL use an identity namespace distinct from worker-proposed nodes, and both
`frontier` and `running` nodes SHALL count as active.

#### Scenario: A reported pass cannot unlock delivery

- **WHEN** a worker-reported pass supplies otherwise sufficient evidence
- **THEN** the slot SHALL remain open with a mandatory verifier-needed
  validation action in the frontier
- **AND** delivery finalization SHALL reject the state for unresolved
  decision-slot closure

#### Scenario: Unrelated frontier work cannot suppress the continuation

- **WHEN** a worker-reported pass also contains a normal research continuation
  or the slot already has unrelated frontier work
- **THEN** the slot SHALL still have one active mandatory verifier-needed
  validation action

#### Scenario: Repeated reports retain one active continuation

- **WHEN** multiple fresh Finding Packs for the same slot each report a pass
- **THEN** the runtime SHALL retain exactly one active mandatory verifier-needed
  validation continuation for that slot
- **AND** its worker-observation attempt count MAY increase once per fresh
  Finding Pack

#### Scenario: Completed continuation is replaced while validation remains open

- **WHEN** the current verifier-needed validation node has completed, the slot
  remains unvalidated, and a later fresh Finding Pack reports a pass
- **THEN** the runtime SHALL create a new active mandatory verifier-needed
  validation continuation

#### Scenario: A worker cannot claim verifier node identity

- **WHEN** a worker proposes a validation continuation whose question matches
  the protocol verifier question
- **THEN** the runtime SHALL retain a distinct protocol-owned verifier node
- **AND** that node SHALL remain mandatory and independently verifiable

### Requirement: Failure and malformed observation compatibility is retained

The runtime SHALL preserve worker failure attempt/failure accounting and its
existing independent-method retry behavior. A recognized status is one of
`passed`, `failed`, or `inconclusive`. Missing, non-mapping, or malformed
validation results (including an absent, non-string, empty, or unrecognized
`status`) SHALL not create an authoritative validation state or a new
validation attempt.

#### Scenario: Worker reports a failed validation

- **WHEN** a fresh Finding Pack reports `validation_result.status="failed"`
- **THEN** the slot SHALL increment its attempt and failure counters
- **AND** the existing mandatory independent-method retry SHALL remain
  available

#### Scenario: Validation result is missing or malformed

- **WHEN** a Finding Pack omits `validation_result`, supplies a non-mapping
  value, or supplies a mapping with an invalid `status`
- **THEN** the runtime SHALL leave authoritative validation state and attempt
  counters unchanged

### Requirement: Historical authority is not retroactively certified

This change SHALL protect newly ingested worker observations. It SHALL NOT
claim that an existing persisted `validation_passed=true` value is
evaluator-owned, because the legacy state has no provenance field. Canonical
OracleRun migration and quarantine of historical authority remain outside this
change.

#### Scenario: Existing legacy pass receives a worker observation

- **WHEN** a legacy slot already has `validation_passed=true` and a worker
  later reports a validation result
- **THEN** the worker observation SHALL NOT change that existing value
- **AND** the runtime SHALL NOT treat this scenario as evidence that the legacy
  pass was evaluator-owned
