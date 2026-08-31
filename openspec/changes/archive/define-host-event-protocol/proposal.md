## Why

Native adapters still keep local task/report state and can describe a host
wave as complete without a canonical attempt or lifecycle revision. The
coordinator needs one typed, replayable host-event boundary now so host
observations remain useful without becoming a second authority.

## What Changes

- Add a strict versioned `HostEvent` envelope and event-specific validators.
- Ingest events atomically through `ResearchRunCoordinator` with duplicate,
  stale, orphan, sequence, and crash-prefix handling.
- Refactor Codex and Claude adapters into thin envelope translators with no
  local completion or report-gate state machine.
- Generate shared adapter support from authoring sources and prove package
  parity, while keeping Hermes and activation work out of this change.

## Capabilities

### New Capabilities

- `host-event-protocol`: typed host observations, semantic digest, replay, and
  non-authoritative attempt projection.

### Modified Capabilities

- None.

## Impact

Affected modules are `host_events.py`, `coordinator.py`, the Codex/Claude native
adapter sources, package generation inputs, the host-event schema, and focused
protocol/adapter/coordinator/package tests. No new runtime database or lifecycle
authority is introduced.
