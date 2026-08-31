## ADDED Requirements

### Requirement: Project interaction state is revisioned and durable

The runtime SHALL maintain one project-scoped interaction projection under
`interaction/` with revisioned `state.yaml`, `durable.yaml`, bounded semantic
episodes, checkpoints, and a rebuildable recall index. The active semantic
window SHALL default to ten deltas. Eviction SHALL retain auditable episodes
and SHALL NOT remove explicit authority, corrections, or confirmed decisions.

#### Scenario: Active window evicts a transient delta

- **WHEN** more than ten meaningful deltas are reduced for a project
- **THEN** only the newest ten remain active while the evicted episode remains
  archived and promoted durable records remain available

### Requirement: Interaction writes are atomic and revision-checked

The controller SHALL accept state mutation only through a single writer with an
expected revision. It SHALL fsync a temporary projection, rename it atomically,
and verify the durable digest. A stale revision SHALL be rejected without
overwriting the current state. If the standalone durable projection is damaged
after an interrupted double write, the controller SHALL recover it from the
digest-verified embedded durable projection.

#### Scenario: Concurrent worker submits a stale delta

- **WHEN** a worker submits a delta using an old expected revision
- **THEN** the controller rejects it as stale and preserves the current
  revisioned projection

### Requirement: Lifecycle recovery preserves host behavior

Bound lifecycle records SHALL be consumed only after their project and run
identities are validated. Pre-compaction SHALL checkpoint the foreground state,
durable records, active window, and pending actions. Recovery SHALL mark an
action started before a crash as `unknown` and require repair rather than
assuming success. Lifecycle persistence failures SHALL NOT alter the host's
fail-open response.

#### Scenario: A host compacts during a pending action

- **WHEN** a bound `PreCompact` lifecycle record is observed while an action is
  started but incomplete
- **THEN** a checkpoint is written, the host response remains unchanged, and a
  later recovery reports that action as `unknown`

### Requirement: Recall and evidence boundaries remain safe

Recall SHALL rank archived semantic episodes without silently reactivating
superseded records. Unadmitted evidence MAY be archived as a candidate but
SHALL NOT mutate factual beliefs. An admitted claim MAY update beliefs, and a
contested claim SHALL retract its prior belief effect.

#### Scenario: Similar superseded plan is queried

- **WHEN** recall receives a query matching a superseded plan and its later
  correction
- **THEN** it returns the correction candidate and excludes the superseded plan
