## Hermes runtime adapter

### Activation probe
`research-tree-activation-contract:v1:hermes`
Follow `references/skill-activation.md`: only exact `/research-tree activation-probe v1 <correlation-id>` or `/skill research-tree` equivalent may return only `research-tree-activation:v1:hermes:<correlation-id>` without tools; paths, links, and bare names are `activation_unverified`.

- Resolve bundled paths from Hermes' injected `[Skill directory: ...]` value or
  load them with `skill_view`; never resolve them from the user's workspace.
- Read `references/hermes-agent-compatibility.md` before the first alignment or
  research action in a Hermes session. Before strategy handoff, delegation, or
  recovery, also read `references/hermes-native-orchestration.md`.
- Use Hermes-native conversation, tools, skills, delegation, and `AIAgent`
  behavior. Do not assume LangGraph, LangChain, or their state/checkpoint model
  is present. If an external LangGraph workflow is explicitly supplied, treat
  it as a separate callable or service boundary.
- When the active Hermes toolset exposes native `clarify`, use it only for a
  rare discrete decision after open-ended intent guidance and before the
  Research Strategy handoff. After the
  handoff, do not use it for ordinary research decisions; revise the strategy
  autonomously within the granted authority. Otherwise use ordinary dialogue
  during pre-handoff alignment.
- After handoff, use Hermes' native plan-to-execute model: mirror the current
  wave in `todo`, persist the authoritative checkpoint in the task workspace,
  and dispatch dependency-ready leaf work as one `delegate_task(tasks=[...])`
  batch. The parent continues coordinator work while children run and verifies
  their artifact paths, URLs, and claims before ingestion. Never poll children
  by repeatedly calling delegation.
- Use `session_search` to recover relevant earlier dialogue and `memory` only
  for durable, reusable preferences or lessons. Neither replaces the current
  workspace checkpoint. Use a skill-backed `cronjob` only when granted
  autonomy requires continuation beyond the current process or session.
- Treat an interrupted delegation as `unknown`, inspect persisted artifacts
  and Hermes live delegation transcripts before retrying, and never count a
  child summary as execution evidence by itself.
- Run `scripts/hermes_execution_adapter.py probe-host` with explicit live
  observations before selecting delegation, goals, Kanban, hooks, or scheduled
  drain. Use `project-workflow` for the bounded delegation batch and
  `reconcile-host` after restart. Optional surfaces may fall back independently;
  absent or denied native workflow support selects `coordinator-dispatch-v1`,
  and no goal, Kanban card, hook, or drain result owns completion.
- Follow the active messaging channel's rendering constraints; replace tables
  with labeled bullets where tables are unsupported.
- Keep research artifacts in the writable task workspace. Do not modify the
  installed package during an ordinary research run.
- Use `scripts/hermes_skill_adapter.py` only for installation diagnostics,
  hook rendering, package validation, or staging, never as a research worker.
- When the checkout runtime is available, use the same stable lifecycle
  sequence as other hosts: `research-tree install`, `research-tree doctor`,
  `research-tree run`, `research-tree resume`, `research-tree status`, and
  `research-tree verify`. Pass a normal workspace and plain-language authority
  fields; do not construct internal HostEvent or SQLite inputs. A prepared or
  pending verification receipt does not grant completion authority.
