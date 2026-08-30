## ADDED Requirements

### Requirement: state projection is canonical
A single StateProjection carries phase, active branch, reconciliation delta, current action + reason, next action, blockers, authority waits, disputes, experiments, resumable.

#### Scenario: consumers share one projection
- **WHEN** a CLI/hook/brief/adapter renders a status
- **THEN** the underlying data comes from `StateProjection.from_coordinator_snapshot(snapshot)` where snapshot is the canonical `coordinator.self_state(run_id)` result

#### Scenario: compact view names every facet
- **WHEN** `render_progress_summary(projection)` is invoked
- **THEN** phase / active_branch / reconciliation_delta / current_action / current_action_reason / blockers / authority_waits / disputes / next_action all appear in the rendered string
