## 1. Preference Contracts

- [x] 1.1 Add failing tests for privacy-bounded PreferenceObservation and UserPreferenceProfile serialization, validation, and deterministic digests.
- [x] 1.2 Implement immutable observation/profile domain contracts and versioned JSON schemas.

## 2. Refresh And Administration

- [x] 2.1 Add failing tests for explicit precedence, five-turn refresh, one-step hysteresis, contested shadow state, aging, supersession, and reversal lineage.
- [x] 2.2 Implement preference refresh and project-scoped inspect, correct, reset, and delete controls.

## 3. Persistence And Strategy Influence

- [x] 3.1 Add failing reload/deletion tests for SQLite profile revisions and pending observations.
- [x] 3.2 Add SQLite v6 persistence and exact reload behavior without retaining transcript or sensitive fields.
- [x] 3.3 Add failing StrategyProjection tests for profile influence lineage and current-explicit precedence.
- [x] 3.4 Bind optional preference influence evidence into StrategyProjection with legacy-read compatibility.

## 4. Delivery Evidence

- [x] 4.1 Run focused/full tests, Ruff, strict local and umbrella OpenSpec validation, governance, and diff checks.
- [x] 4.2 Update alpha2 group 29 schemas, registries, task completion, and source-bound verification evidence.
