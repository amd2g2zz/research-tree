## ADDED Requirements

### Requirement: Completion inputs use a typed transactional boundary

The system SHALL register canonical closure, insight, readiness, and evaluation
inputs only through a typed completion-input writer. The registration SHALL be
committed in the same transaction as the immutable artifact, parent lineage,
and ledger event. A generic `RunLedger.append_artifact()` call SHALL NOT create
or populate a completion-input registration.

#### Scenario: Generic valid-looking input is not registered

- **WHEN** a caller appends a schema-valid completion-looking artifact through
  the generic ledger API
- **THEN** the artifact remains ordinary lineage and is absent from registered
  completion inputs

#### Scenario: Typed retry is replay-safe

- **WHEN** a typed writer retries the same id, payload, and exact parents
- **THEN** it returns the existing immutable revision without a second
  registration or run-revision advance

### Requirement: Registration validates exact current authority inputs

The system SHALL reject registration before mutation when the run is wrong,
the expected revision is stale, any parent belongs to another run, any parent
is superseded or quarantined, required payload schema is malformed, or payload
lineage differs from supplied exact parents. A closure registration SHALL also
require a passed v2 assessment issued by the configured core evaluator and its
exact token evidence.

#### Scenario: Rejected registration remains atomic

- **WHEN** validation or the transaction commit fails
- **THEN** no completion artifact, registration, event, or run revision is
  persisted

### Requirement: Existing canonical writers use the registration boundary

The canonical closure, insight, readiness, and evaluation writers SHALL route
eligible canonical outputs through the typed registration boundary. Inconclusive
closure assessments MAY remain ordinary diagnostic lineage and SHALL NOT be
registered as completion inputs.

#### Scenario: Stale closure proof is not replaced locally

- **WHEN** a closure token is stale under `SlotClosureAssessor.is_current()`
- **THEN** this registration slice does not issue a replacement token or alter
  completion consumption
