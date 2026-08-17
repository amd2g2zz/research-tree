## Why

Codex collaboration is real in-session — the CLI models `spawnAgent`/
`SubagentStart`/`SubagentStop` lifecycle in its event history and fires
project hooks — but the current runtime cannot bind a real Codex child
identity to a canonical attempt: `bind_agent` is Claude-only, the lifecycle
hook records Codex `SubagentStart` without extracting a bindable child
identity, and no validated translation from Codex collaboration events to
canonical HostEvents exists. The preserved deterministic bridge
(`~/rt-241-handoff-20260818.patch`, reviewed handoff of commits
`e500aa2`+`b6f9929`) fail-closed on missing hook-supplied identities but was
never accepted because the live surface exposed no bindable child ID.

## What Changes

- Extend `bind_agent` (or add a Codex equivalent) to accept a
  hook-observed Codex child `agent_id` for a running task attempt on host
  `codex`: unique, active-attempt-matched, reused-identity-rejected.
- Extract bindable child identities from Codex `SubagentStart`/`SubagentStop`
  hook payloads in the lifecycle hook (allowlist-sanitized), analogous to the
  Claude `PostToolUse`/`Agent` path.
- Translate Codex collaboration lifecycle (SubagentStart, SubagentStop,
  Stop, cancellation, provider failure, resume, fork) into
  revision/sequence-bound canonical HostEvents via the existing
  `emit-event` surface: Stop/cancellation/unknown become `unknown_outcome`,
  never completion.
- Keep the coordinator active while workers run; dispatch ready leaves up to
  advertised capacity; dependents release only after schema/hash/attempt/
  anchor checks pass (existing `finish_task`/`verify_task` contract).
- On parent interruption: active attempts → `unknown`, verified siblings
  preserved, unresolved work retried with a fresh attempt ID.
- Capture a live in-session Codex collaboration receipt with at least two
  concurrent tasks: actual child IDs, distinct Finding Packs, hook sequence,
  ledger rows, host/package/model/environment fingerprints — Docker-isolated
  where the host surface permits, otherwise an explicit reviewed isolation
  deviation (standards §12a).

## Non-Goals

- No nested Codex CLI/process; no app-server RPC spawn (proven absent in
  CLI 0.147.0).
- No Claude/Hermes behavior changes (both closed lanes).
- No synthetic child IDs, manually authored Finding Packs, or capability
  strings as evidence; all-green unit tests alone are insufficient.

## Non-Acceptance Conditions

- `advance_execution()`-style task-ID-only returns, supplied `worker_id`,
  projected workflow JSON, or manually written Finding Packs never create
  canonical completion.
- Dispatch responses without an actual Codex `agent_id`, or with duplicate,
  missing, stale, or cross-attempt IDs, are rejected.
- A capability probe (schema inspection, `--version`) is availability
  evidence only.

## Non-Regression Constraints (blocker ledger)

| Constraint | Source |
|---|---|
| Codex CLI 0.147.0 app-server exposes no client-callable spawn/collaboration request method; `spawnAgent` exists only as in-session tool history. Only Skill-driven in-session collaboration can produce a real bindable child ID | Issue #241 capability audit + blocker receipt |
| Nested Codex is prohibited for this acceptance path | Same |
| If the active surface still exposes no bindable child ID: stop after the capability probe, post the blocker receipt, leave #241 open — do NOT convert the deterministic bridge into a passing PR | Plan stop condition |
| Preserved handoff patch re-enters only through review (cherry-pick/apply), never a blind rebase of the stale branch | Task 0 disposition comment |
