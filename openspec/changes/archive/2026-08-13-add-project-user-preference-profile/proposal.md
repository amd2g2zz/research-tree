## Why

Research strategy currently treats every run as preference-free, so durable requester choices either disappear after compaction or risk being inferred from raw conversation history. A project-local, inspectable profile is needed to carry bounded preferences across runs while preserving the current request as the highest authority.

## What Changes

- Add immutable, privacy-bounded `PreferenceObservation` records and a revisioned project-local `UserPreferenceProfile`.
- Refresh inferred preferences only after five observed turns and advance them by at most one hysteresis state per refresh.
- Apply current explicit input immediately, represent contradictions as contested shadow changes, and retain supersession/reversal lineage.
- Persist observations and profiles in the workspace SQLite ledger with inspect, correct, reset, and delete controls that survive reload.
- Bind every material profile influence on a `StrategyProjection` to its observation, precedence, and reversal condition.
- Add versioned schemas, deterministic tests, and source-bound group 29 delivery evidence.

## Capabilities

### New Capabilities

- `project-user-preference-profile`: Project-scoped preference observation, hysteretic refresh, privacy, durable administration, and strategy-influence lineage.

### Modified Capabilities

- `strategy-handoff`: Strategy projections record preference influence evidence without allowing a profile to override the current explicit request.

## Impact

The change adds `src/research_tree/preferences.py`, extends the SQLite ledger schema, adds optional preference lineage to `StrategyProjection`, exports the new public contracts, and updates the alpha2 schemas, registries, and tests. It introduces no dependency and does not retain transcripts or create global profiles.
