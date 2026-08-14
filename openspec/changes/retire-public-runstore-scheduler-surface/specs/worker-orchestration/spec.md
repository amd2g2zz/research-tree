## MODIFIED Requirements

### Requirement: Worker orchestration does not advertise a RunStore scheduler

Current worker orchestration SHALL remain governed by coordinator and host-native
contracts without publishing or depending on a RunStore-backed adaptive
portfolio scheduler or persisted `work-portfolio` artifact. It SHALL not add a
bridge, alias, adapter, migration, fallback, or dual-state execution path.

#### Scenario: Current orchestration authority is inspected

- **WHEN** maintainers inspect active worker-orchestration ownership and
  delivery records
- **THEN** no active authority names the retired scheduler as a dependency
