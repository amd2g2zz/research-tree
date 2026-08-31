## Design

### Context

The lane builds on four accepted foundations, all reachable from
`origin/dev@43977ed`:

- `src/research_tree/project_workspace.py` — project/run workspace authority,
  hook installation, `HOST_HOOK_EVENTS["hermes"]` (7 lifecycle events).
- `scripts/hermes_event_adapter.py` — `build_hermes_event` /
  `recovery_events` validated HostEvent builders (identifier-checked,
  sequence-checked, provider-failure sanitized).
- `src/research_tree/coordinator.py` — `ingest_host_events` canonical
  admission; attempts bind through coordinator dispatch/leases.
- `scripts/hermes_runtime_hook.py` — dependency-free hook recorder with
  copy-allowlist (`SAFE_EXTRA_KEYS`), `post_tool_call` filtered to
  `delegate_task`.

### Component 1 — Delegation bridge (scripts/hermes_execution_adapter.py)

New subcommand `run-delegation` (name aligned with the existing
subcommand style): takes a canonical wave description (action refs with
attempt IDs issued by the coordinator), invokes the supported synchronous
delegation channel as a real host process, captures the observed
`delegation_id`/`task_id`/`child_id` from the hook event stream, and emits
`build_hermes_event` envelopes for ingestion by the canonical coordinator.

Identity rules (fail closed):

- Each `(delegation_id, task_id, child_id)` triple must be observed in the
  hook stream for a bound attempt; a caller-invented triple is rejected
  because it never appears in observed events.
- One child identity binds to exactly one canonical attempt; rebinding an
  already-bound identity is `HermesExecutionError`.
- Finding Pack admission requires non-empty schema-valid JSON whose attempt
  ancestry matches the bound attempt; modified (digest mismatch) or
  cross-attempt packs are rejected.

`record-batch` changes from echo to validation: it verifies each finding
path exists inside the workspace, is non-empty, parses as an object, and
references the declared attempt; missing/empty/invalid/mismatched inputs
exit 1 with a stable message. Observational output stays
`authoritative: False`.

### Component 2 — Hook identity propagation (scripts/hermes_runtime_hook.py)

Apply the reviewed handoff patch: extend `SAFE_EXTRA_KEYS` with the identity
fields (`attempt_id`, `action_id`, `causation_id`, `tool_call_id`,
`child_subagent_id`, `parent_subagent_id`, `parent_turn_id`, `turn_id`,
`api_request_id`, `child_session_id`), validate `_id`-suffixed values with
the permissive host-identifier regex, map `child_subagent_id` → recorded
`agent_id` and `tool_call_id` → recorded `causation_id`, and accept
`RESEARCH_TREE_{TASK,ATTEMPT,ACTION}_ID` env fallbacks. The copy-allowlist
remains the only source of recorded fields; free text stays dropped; the
1 MiB bound and event whitelist are unchanged. Redundant
`packages/hermes/.../hermes_runtime_hook.py` copy regenerates through the
builder.

### Component 3 — Pinned dependency setup (src/research_tree/skill_setup.py + skill-src)

New dependency manifest for Hermes installs: pinned AnySearch source
(v2.1.0, revision `6ff6aa958ad9747659d669b5e9984f07c896f2aa`), installed
into run-local `HERMES_HOME/skills/anysearch` **before** Hermes starts.
`research-tree-setup --host hermes` gains a dependency phase:
verify expected revision/digest → clone/fetch pinned revision → verify
payload digest → install → status. Install and status are idempotent;
digest drift fails closed; no `~/.hermes/config.yaml` mutation, no bind
mount. The manifest source lives under `skill-src/` (authoring source) and
flows into the generated Hermes package via `build_skill_packages.py`.

### Component 4 — Recovery

Interruption of one child mid-batch: the bridge stops claiming the
interrupted attempt, emits `unknown_outcome` (reason `interrupted_child`)
via the existing `recovery_events` path, and re-dispatches the unresolved
task as a fresh attempt ID with a `retry` event (`retry_of` = old attempt).
The completed, verified sibling retains its accepted state. Provider
failure and cancellation emit `provider_failure`/`unknown_outcome` — never
a completion.

### Component 5 — Live evidence (Docker envelope)

Live-evidence subagent (not the implementer) runs from a clean project
root inside the Docker envelope: official image digest recorded, one setup
container installs pinned deps into the run-local `HERMES_HOME` volume,
then one Hermes container runs the project-mounted bridge for a two-task
batch, plus one fault-injected run (kill one child) demonstrating recovery.
Receipts: identities, events, ledger rows, digests, redacted `docker run`
flags, exit codes. Raw output stays in
`.research-tree/evaluation-runs/issue-242/<run-id>/`.

### Alternatives considered

- **Persistent `hermes chat` session with async delegation**: rejected —
  parent shutdown cancels children (proven regression); the synchronous
  channel is the documented supported primitive.
- **Reusing the unreachable `e4a28e4` chain**: rejected — not in any ref;
  re-implementation from `origin/dev` with reviewed patch reuse only.
- **Bind-mounting AnySearch from the host**: rejected by the issue contract;
  pinned run-local install replaces it.

### Risks

- Provider credential unavailability → live receipt records `blocked`
  honestly; deterministic work still lands with its own evidence.
- Image digest drift between pin and run → preflight re-verifies digest;
  mismatch aborts before any episode.
- Hook event shape variance across Hermes versions → hook tolerates missing
  optional identity fields but never fabricates them.
