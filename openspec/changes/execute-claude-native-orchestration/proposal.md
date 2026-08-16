## Why

The Claude Code package currently projects generic workflow actions with
synthetic child attempt IDs.  It neither selects Agent, Workflow, and hybrid
execution separately nor binds native runtime identities before those
observations reach the canonical coordinator.

## What Changes

- Add a Claude-package-only orchestration contract that selects `agent`,
  `workflow`, `hybrid`, or `infeasible` from explicit observed capabilities.
- Validate source-bound native Claude receipts: Agent mode needs two distinct
  child identities; Workflow mode needs two phase identities and workflow/run
  identities; hybrid needs both, with bounded first-level child delegation.
- Preserve deterministic fallback: unavailable Workflow selects Agent when it
  remains available; unavailable Agent selects Workflow-only when available.
- Emit a non-authoritative, attempt-bound bridge record carrying version,
  model, package, environment, script, child, phase, session, and hook
  identity evidence.  The bridge never declares coordinator closure.
- Package the Claude-only contract and document its invocation and evidence
  boundary.  Add deterministic contract tests and OpenSpec coverage.

## Non-Goals

- Launching a nested `claude` process, fabricating native execution, or
  treating fixtures as live Claude evidence.
- Changing Codex, Hermes, coordinator closure, or generic host capability
  semantics.

## Impact

Only the Claude package bridge, its generated package contents, Claude
orchestration reference, and Claude-specific tests change.  Live receipt
collection remains an external Claude Code/Agent SDK gate and is recorded as
unavailable when this environment does not expose it.
