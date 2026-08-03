## Hermes runtime adapter

- Resolve bundled paths from Hermes' injected `[Skill directory: ...]` value or
  load them with `skill_view`; never resolve them from the user's workspace.
- Read `references/hermes-agent-compatibility.md` before the first alignment or
  research action in a Hermes session.
- Use Hermes-native conversation, tools, skills, delegation, and `AIAgent`
  behavior. Do not assume LangGraph, LangChain, or their state/checkpoint model
  is present. If an external LangGraph workflow is explicitly supplied, treat
  it as a separate callable or service boundary.
- When the active Hermes toolset exposes native `clarify`, use it only for the
  1-3 consequential decisions before the Research Strategy handoff. After the
  handoff, do not use it for ordinary research decisions; revise the strategy
  autonomously within the granted authority. Otherwise use ordinary dialogue
  during pre-handoff alignment. Delegate only when delegation is exposed.
- Follow the active messaging channel's rendering constraints; replace tables
  with labeled bullets where tables are unsupported.
- Keep research artifacts in the writable task workspace. Do not modify the
  installed package during an ordinary research run.
- Use `scripts/hermes_skill_adapter.py` only for package validation or staging,
  never as part of the research workflow.
