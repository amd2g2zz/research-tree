## Design

### Context

- `scripts/native_execution_adapter.py` (874 lines): `init`/`add-task`/
  `start`/`bind-agent`/`finish`/`verify`/`recover`/`status`/`complete`/
  `emit-event` subcommands with per-run JSON state under the project
  workspace. `bind_agent` currently raises for `host != "claude"`.
- `src/research_tree/lifecycle_hook.py`: `observe()` records sanitized
  identity keys (`session_id`, `turn_id`, `agent_id`, `task_id`,
  `attempt_id`, `causation_id`) for all hosts but has Codex-specific
  extraction only for nothing — Claude has SubagentStop/PostToolUse paths.
- Preserved handoff patch (`~/rt-241-handoff-20260818.patch`): deterministic
  fail-closed binding bridge + hook enrichment in
  `src/research_tree/project_workspace.py` + orchestration non-authoritative
  marking. Review-first integration.

### Component 1 — Codex identity binding (bind_agent extension)

Allow `host == "codex"` in `bind_agent` with the same contract as Claude:
running task, matching active attempt, unique hook-observed `agent_id`,
session/causation identifiers recorded, reuse rejected. The Codex child
identity source is the project hook stream (SubagentStart with agent id),
mirroring `_observed_delegation_ids` from the Hermes lane: the caller-declared
identity must appear in the observed hook events for the run before binding.

### Component 2 — Hook child-identity extraction (lifecycle_hook.py)

For `host == "codex"`, `SubagentStart`/`SubagentStop` payloads may carry the
spawned agent identity in `tool_response`/`extra` shapes. Extract
allowlist-sanitized identifiers (`agent_id`, `session_id`, `turn_id`,
`causation_id` from `tool_use_id` where present) and record a
`binding_status` of `candidate`/`host_identity_recorded` exactly like the
Claude path. Free text is never copied.

### Component 3 — Collaboration event translation (emit-event + recover)

Map hook-observed Codex lifecycle to canonical kinds:

| Codex hook event | Canonical kind |
|---|---|
| SubagentStart (bound) | `attempt_started` |
| SubagentStop (completed + verified) | `worker_finished` |
| SubagentStop (interrupted/cancelled/absent) | `unknown_outcome` |
| Stop (parent, attempts active) | `unknown_outcome` per active attempt |
| provider error observation | `provider_failure` |
| re-dispatch after unknown | `retry` (`retry_of` set, fresh attempt) |

Parent interruption recovery: `recover` marks active attempts `unknown`,
preserves verified siblings, retry creates a fresh attempt ID. Existing
adapter state machine already implements most of this; the delta is Codex
host admission in the binding + hook extraction feeding real identities.

### Component 4 — Live in-session receipt

Docker envelope where possible (Codex CLI in a container with the skill
installed and project hooks active). If the interactive collaboration
surface cannot run in-container, record an explicit §12a deviation (clean
dedicated worktree, no host-global mutation, network limited to provider)
accepted by the reviewer. Minimum: two concurrent independent tasks, actual
two child IDs, distinct Finding Packs, hook sequence, ledger rows, exact
host/package/model/environment fingerprints.

### Stop condition (from plan + ledger)

If the live surface still exposes no bindable child ID after the probe:
post the blocker receipt on the issue, leave #241 OPEN, withdraw the WIP
branch. Deterministic bridge work may still land only as fail-closed
scaffolding with no closure claim — but per the plan's stop rule, prefer
leaving the lane open over merging contract-only adapters.

### Risks

- Host-capability blocker persists (High): stop condition governs; no fake
  closure.
- Preserved patch conflicts with post-`f95b5e0` adapter changes: cherry-pick
  review-first; re-run spec task mapping.
