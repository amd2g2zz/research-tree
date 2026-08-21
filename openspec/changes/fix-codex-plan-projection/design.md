## Design

The durable adapter writes `codex-plan-snapshot.json` only after atomically
persisting `state.json`. The snapshot includes the durable revision, status,
task counts, ready wave, unresolved obligations, and host-side
`why_not_complete` explanation. Failure to write that optional projection does
not alter the completed durable transition.

`sync-plan` rebuilds a `codex-plan-mirror.json` from the current snapshot and
returns the exact items for Codex `update_plan`. `status` compares revision,
digest, and items; a missing mirror is `unavailable`, while an older or altered
mirror is `stale`.
