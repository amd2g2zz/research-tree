## Why

The coordinator currently exposes a handoff state but does not persist one complete, requester-visible strategy artifact bound to explicit confirmation. This lets generic acknowledgements, stale plans, or host-local state authorize autonomous research without an auditable strategy boundary. Issue #85 makes that boundary explicit before the next Alpha2 strategy and depth work begins.

## What Changes

- Add an immutable, versioned `StrategyProjection` with a deterministic digest and complete strategy fields.
- Require the current displayed projection digest plus contextual, non-generic confirmation before stage-3 dispatch.
- Enforce four monotonic requester-visible stages while preserving existing internal lifecycle states.
- Persist same-round strategy revisions and rejected/superseded lineage; create a stage-1 successor for material target, authority, safety, outcome, or success changes.
- Preserve macro-stage identity across pause/resume and delivery resume.
- Project equivalent strategy semantics through Codex, Claude Code, and Hermes host adapters.
- **BREAKING**: direct or host-local dispatch and generic acknowledgement cannot authorize autonomous research.

## Capabilities

### New Capabilities

- `strategy-handoff`: Versioned strategy projections, exact digest confirmation, revision lineage, and four-stage handoff guards.

### Modified Capabilities

- `lifecycle-state-machine`: Require the strategy handoff guard and define macro-stage-preserving pause/resume transitions.
- `mutual-alignment`: Bind handoff confirmation to the displayed projection rather than a generic strategy string.
- `host-event-protocol`: Carry canonical strategy projection semantics without granting host-local authority.

## Impact

- Affects `src/research_tree/coordinator.py`, alignment handoff/controller modules, host event adapters, lifecycle registries, and SQLite schema/migrations.
- Adds public StrategyProjection and confirmation APIs, focused TDD fixtures, replay/migration evidence, and cross-host semantic parity checks.
- Depends on the merged coordinator, alignment, host-event, activation, correction, and DecisionFrame boundaries delivered by issues #57, #59, #60, #71, #73, and #87.
