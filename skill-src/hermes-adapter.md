## Hermes runtime adapter

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
  wave in `todo`, project the authoritative canonical Work Item and Attempt
  Lease into a Hermes goal/Kanban task, and dispatch dependency-ready leaf work
  as one `delegate_task(tasks=[...])` batch. The parent continues coordinator
  work while children run and verifies their artifact paths, URLs, and claims
  before ingestion. Never poll children by repeatedly calling delegation.
- Use `session_search` to recover relevant earlier dialogue and `memory` only
  for durable, reusable preferences or lessons. Neither replaces the current
  workspace checkpoint. Use a skill-backed `cronjob` only when granted
  autonomy requires continuation beyond the current process or session.
- Treat an interrupted delegation as `unknown`, compare a fresh Hermes snapshot
  with the canonical SQLite ledger, inspect persisted artifacts and Hermes live
  delegation transcripts before retrying, and never count a child summary as
  execution evidence by itself.
- Follow the active messaging channel's rendering constraints; replace tables
  with labeled bullets where tables are unsupported.
- Keep research artifacts in the writable task workspace. Do not modify the
  installed package during an ordinary research run.
- Use `scripts/hermes_skill_adapter.py` only for installation diagnostics,
  hook rendering, package validation, or staging, never as a research worker.
