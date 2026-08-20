## ADDED Requirements

### Requirement: Durable state emits a Codex plan snapshot

The native adapter SHALL derive a plan snapshot from each successfully
persisted durable state revision. The snapshot SHALL include run revision,
status, task counts, ready tasks, unresolved obligations, and a
`why_not_complete` explanation.

#### Scenario: State transition invalidates an older mirror

- **WHEN** a durable task transition changes the run revision
- **THEN** the previous Codex plan mirror is reported as `stale`
- **AND** the visible plan is not treated as completion authority

### Requirement: Plan mirror rebuild is idempotent

The adapter SHALL provide an idempotent projection of the latest snapshot for
the Codex host wrapper.

#### Scenario: Restart rebuilds the visible plan

- **WHEN** the host restarts or uses a copied workspace with current durable
  state and mirror files
- **THEN** `status` reports `plan_projection=current`
- **AND** repeated `sync-plan` calls do not rewrite a matching mirror

### Requirement: Projection unavailability is explicit

The adapter SHALL report `plan_projection=unavailable` when the host has not
materialized a matching mirror.
