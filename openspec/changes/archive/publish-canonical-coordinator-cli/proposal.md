# Publish the Canonical Coordinator CLI

## Why

The published `research-tree` executable is intentionally empty after #164
retired every prior-version command. #149 and #151 are now merged, so the
settled SQLite coordinator operations for HostEvent ingestion, crash recovery,
completion diagnostics, and terminal completion can become the first public
current-only commands.

## What Changes

- Publish `research-tree run ingest`, `recover`, `why-not-complete`, and
  `complete` as thin JSON boundaries over `ResearchRunCoordinator` and the
  caller-supplied SQLite workspace.
- Require explicit workspace, run ID, event input, actor, and expected revision
  whenever the underlying coordinator operation requires them.
- Define one deterministic JSON success/error envelope and preserve exact
  coordinator errors; stale revisions and unmet completion obligations retain
  their canonical classifications.
- Add a direct CLI/coordinator parity test, documentation, package validation,
  and installed-wheel smoke coverage.

## Non-goals

- No legacy command, alias, `RunStore`, importer, migration, compatibility
  reader, dual write, user-data mutation, or fallback.
- No `deliver`, `accept`, `reconcile-host`, `status`, or generic lifecycle
  command: no matching stable direct `ResearchRunCoordinator` operation exists
  for this public boundary.

## Impact

This changes only the reserved CLI entrypoint, focused CLI tests, README, and
the delivery-governance records for issue #150 / group 84. The generated host
packages are validated from their existing source; they do not gain a separate
runtime entrypoint.
