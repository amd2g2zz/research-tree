## MODIFIED Requirements

### Requirement: Adaptive research execution has no public RunStore scheduler

Current research execution SHALL not publish, use, or document a RunStore-backed
adaptive portfolio scheduler or a persisted `work-portfolio` API. It SHALL not
replace the retired boundary with an alias, bridge, adapter, migration,
fallback, dual state, or user-data operation.

#### Scenario: A caller seeks the retired execution surface

- **WHEN** a caller inspects current runtime and public package interfaces
- **THEN** no supported surface resolves the retired scheduler
