## Codex CLI runtime adapter

- Read `references/codex-cli-compatibility.md` before host-specific alignment.
- Codex may expose the experimental `request_user_input` app-server request;
  when exposed, use it for 1-3 consequential alignment decisions.
- Do not assume it exists in a Skill shell or non-interactive `codex exec` run;
  use ordinary dialogue when it is absent.
