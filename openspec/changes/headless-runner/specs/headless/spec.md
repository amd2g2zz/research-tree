## ADDED Requirements

### Requirement: the launch script drives the state machine; every step is a JSON Lines record

#### Scenario: full chain emits events
- **WHEN** a script walks confirm→attach→sign→research-completed→open-draft with a pre-signed verdict
- **THEN** the outcome is success and the emitted JSON Lines include the state transitions in order

### Requirement: detailed logs correlate by task

#### Scenario: transitions logged with correlations
- **WHEN** a run completes
- **THEN** the detailed log lines carry the transition and task_id correlation

### Requirement: the consent model never silently auto-signs

#### Scenario: unhandled gate pauses with a resume token
- **WHEN** an early-termination gate fires and the script has no pre-signed choice
- **THEN** the outcome is paused-pending-decision with a resume token; resuming with the pre-signed choice continues the same run (no ledger fork)

### Requirement: converged without a verdict parks

#### Scenario: park fallback
- **WHEN** the run converges with no pre-signed verdict
- **THEN** the outcome is park (12h-cap matrix consistent)
