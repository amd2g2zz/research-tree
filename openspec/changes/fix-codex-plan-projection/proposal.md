## Why

Durable host state and the visible Codex plan could disagree after a transition,
leaving completed work displayed as actionable.

## What Changes

- Emit a revision-bound Codex plan snapshot after each durable state write.
- Add idempotent `sync-plan` output for the host wrapper to project through
  Codex `update_plan`.
- Make `status` expose `current`, `stale`, or `unavailable` projection state.

## Boundary

The mirror is a UI projection and cannot write, replace, or authorize durable
completion state.
