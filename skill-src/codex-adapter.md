## Codex CLI runtime adapter

- Read `references/codex-cli-compatibility.md` before host-specific alignment.
- Codex may expose the experimental `request_user_input` app-server request;
  use it only when the current session actually exposes that capability.
- Do not assume it exists in a Skill shell or non-interactive `codex exec` run;
  use ordinary dialogue when it is absent.
