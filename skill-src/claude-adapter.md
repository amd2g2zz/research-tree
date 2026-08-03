## Claude Code runtime adapter

This is the Claude Code package of `research-tree`. Invoke it with
`/research-tree`; use only Claude Code capabilities that are exposed in the
current session. Do not call a named tool from another host merely because it
appears in an example.

- Resolve bundled resources from the active skill directory, including
  `${CLAUDE_SKILL_DIR}` when the host provides it. Do not resolve
  `references/` or `assets/` from the user's working directory.
- Read `references/claude-code-compatibility.md` before Claude-specific
  installation, hooks, or source-checkout development work.
- Use ordinary dialogue for alignment unless Claude Code exposes a structured
  question capability in the current session. Never assume that
  `ask_user_question`, `multi_tool_use`, or another host-specific tool exists.
- In Claude Code, "I don't know", "I don't understand", or a correction means
  the brief needs teaching or verification. Explain the missing context in
  plain language, update the Living Brief, and continue the bounded research
  cycle; never treat it as a stop signal.
- When the requester gives a concrete failure mode, inspect the relevant source,
  consult available documentation or web search, and try safe alternatives
  before asking another generic preference question. Do not finish after only
  listing causes, options, or proposed fixes; return an evidence-bearing interim
  result in the same turn. Ask only for a consequential choice that cannot be
  recovered autonomously.
- Never claim completion merely because a Blind-Spot Packet or research tree was
  displayed. The requested investigation must have a report or a clearly
  labeled, evidence-bearing interim package.
- Treat the installed package as read-only. Keep research reports, briefs,
  evidence ledgers, and other task artifacts in the writable workspace.
- The installed Claude package contains only `SKILL.md`, bundled references,
  and bundled assets. It does not contain the repository's Python runtime,
  lifecycle hooks, builder, or evaluation corpus.

### Source checkout development boundary

When Claude Code is operating inside the `research-tree` source checkout and
the requester explicitly asks for development, packaging, hooks, or evaluation
work, these repository paths are available:

| Path | Role | Development contract |
| --- | --- | --- |
| `hooks/research_hook.py` | Lifecycle hook launcher | Run through `uv run` from the checkout; it imports `research_tree` and is not part of the installed skill package. |
| `src/research_tree/` | Python artifact runtime | Edit only when the task changes runtime behavior; use the public API and run the full test suite. |
| `scripts/` | Host package builder and Hermes staging/validation tools | Run `python scripts/build_skill_packages.py --check` after package-affecting changes. |
| `evaluation/` | Evaluation cases and forward-test material | Treat as development/evaluation input, not as a user research source or runtime dependency. |

Before using these paths, verify the checkout with `pyproject.toml`, `src/`,
`skill-src/`, and `packages/`. Run `uv sync` first. Do not claim that an
installed `/research-tree` package can execute these files; when the checkout
is unavailable, report the missing development capability and continue with
the host-native skill workflow.

### Claude Code hooks

Hooks are opt-in repository settings, not automatic Skill behavior. If the
requester explicitly enables them, merge
`hooks/claude-code.settings.template.json` into the project's
`.claude/settings.json` without replacing unrelated settings or hooks. The
hook command requires the source checkout and `uv`; it records only sanitized
lifecycle metadata and fails open on errors. Do not enable it for an ordinary
research run.
