## Codex CLI runtime adapter

- Read `references/codex-cli-compatibility.md` before host-specific alignment.
  Before repository execution, delegation, compaction, or recovery, also read
  `references/codex-native-orchestration.md`.
- Codex may expose the experimental `request_user_input` app-server request;
  when exposed, use it only for a rare discrete decision after open-ended
  intent guidance and before the Research Strategy handoff. After the handoff,
  do not use it for ordinary
  research decisions; revise the strategy autonomously within the granted
  authority.
- Do not assume it exists in a Skill shell or non-interactive `codex exec` run;
  use ordinary dialogue when it is absent.
- After strategy handoff, map the active plan-to-execute wave onto Codex-native
  `update_plan`, parallel tool calls, and collaboration subagents when exposed.
  The plan UI is a session mirror; persist the Living Brief, execution state,
  evidence ledger, and next wave in the writable workspace before delegation or
  compaction.
- Give each subagent a disjoint Decision Slot and Finding Pack path. Dispatch
  independent agents concurrently, continue coordinator work while they run,
  and call `wait` only when no useful local work remains. Verify artifacts and
  sources before accepting a subagent summary.
- Treat applicable `AGENTS.md` files as scoped execution constraints. After a
  resume, fork, or context compaction, reload the workspace checkpoint and
  re-check external side effects before retrying unknown work.
- After handoff, use `scripts/codex_execution_adapter.py` with `emit` only to translate
  a Codex-native observation into one HostEvent. Feed that exact JSON to the
  canonical `research-tree run ingest` command. The adapter is stateless: it
  owns no task ledger, evidence verdict, readiness, report, or completion state.
