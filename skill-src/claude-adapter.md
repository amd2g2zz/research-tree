## Claude Code runtime adapter

This is the Claude Code package of `research-tree`. Invoke with `/research-tree`
and use only capabilities exposed by the current session; never call tools from
another host merely because they appear in examples.

- Resolve bundled resources from the active skill directory, including
  `${CLAUDE_SKILL_DIR}` when the host provides it. Do not resolve
  `references/` or `assets/` from the user's working directory.
- Read `references/claude-code-compatibility.md` before the first alignment or
  research action, as well as before Claude-specific installation or hooks.
- When the current session exposes `AskUserQuestion`, use it only for a rare
  discrete decision after open-ended intent guidance and before the Research
  Strategy handoff. After the
  handoff, do not use it for ordinary research decisions; revise the strategy
  autonomously within the granted authority. Otherwise use ordinary dialogue
  during pre-handoff alignment; never assume `AskUserQuestion`,
  `ask_user_question`, or another host tool exists.
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
- Treat the installed package as read-only; keep research reports, briefs,
  evidence ledgers, and other task artifacts in the writable workspace.
- The installed package contains only `SKILL.md`, bundled references, and
  assets, not the repository's Python runtime, lifecycle hooks, builder, or
  evaluation corpus.

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

Hooks are opt-in repository settings, not normal Skill behavior. Read the
compatibility reference before explicitly enabling them; never enable them for
an ordinary research run.
