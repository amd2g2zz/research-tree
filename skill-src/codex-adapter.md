## Codex CLI runtime adapter

- Read `references/codex-cli-compatibility.md` before host-specific alignment.
- Codex may expose the experimental `request_user_input` app-server request;
  when exposed, use it only for a rare discrete decision after open-ended
  intent guidance and before the Research Strategy handoff. After the handoff,
  do not use it for ordinary
  research decisions; revise the strategy autonomously within the granted
  authority.
- Do not assume it exists in a Skill shell or non-interactive `codex exec` run;
  use ordinary dialogue when it is absent.
