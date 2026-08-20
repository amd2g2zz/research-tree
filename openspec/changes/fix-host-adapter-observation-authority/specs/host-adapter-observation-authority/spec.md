## ADDED Requirements

### Requirement: Host review is observational only

The host adapter SHALL retain a successfully reviewed Finding Pack as a
submitted observation and SHALL NOT write a completed task or canonical run
completion state.

#### Scenario: Reviewed submission enables only host dependency observation

- **WHEN** a submitted Finding Pack has a passed validation result and an
  independently observed review receipt
- **THEN** its host task remains `submitted` with verified review evidence
- **AND** a dependent host task may become ready
- **AND** adapter run output remains `complete=false` with
  `completion_authority=coordinator_only`

### Requirement: Review identity is independently evidenced

The adapter SHALL reject a review unless its reviewer principal, session, and
lease are recorded by the same host's lifecycle hook, differ from the worker
binding, and reference a distinct reviewed evidence-custody copy.

#### Scenario: Self or forged review is rejected

- **WHEN** the reviewer reuses the worker principal, session, lease, a foreign
  host identity, an unobserved identity, or the worker artifact path
- **THEN** verification fails closed
- **AND** the task remains an unverified submission

### Requirement: Validation gates review observation

The adapter SHALL reject missing, failed, or inconclusive validation results
before recording a verified review observation.

#### Scenario: Inconclusive validation remains unresolved

- **WHEN** a submitted Finding Pack has `validation_result.status` equal to
  `inconclusive`
- **THEN** verification fails closed
- **AND** the adapter does not report the task or run as observed complete

### Requirement: Hermes has no inferred completion

The Hermes bridge SHALL expose itself as non-authoritative and SHALL NOT infer
an observed completed run from report paths alone.

#### Scenario: Hermes completion command lacks canonical evidence

- **WHEN** the Hermes compatibility command receives report paths without a
  canonical coordinator completion record
- **THEN** it reports `complete=false` and `observed_complete=false`
