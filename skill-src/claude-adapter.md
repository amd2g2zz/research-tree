## Claude Code runtime adapter

This is the Claude Code package of `research-tree`. Invoke with `/research-tree`
and use only capabilities exposed by the current session; never call tools from
another host merely because they appear in examples.

- Resolve bundled resources from the active skill directory, including
  `${CLAUDE_SKILL_DIR}` when the host provides it. Do not resolve
  `references/` or `assets/` from the user's working directory.
- Read `references/claude-code-compatibility.md` before the first alignment or
  research action, as well as before Claude-specific installation or hooks.
  Before handoff, delegation, compaction, or recovery, also read
  `references/claude-native-orchestration.md`.
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
- After strategy handoff, map ready waves onto Claude Code's native task list
  and Agent tool when exposed. Launch independent agents together, use
  background execution only when the host supports it, and continue coordinator
  work instead of polling. Use an agent team only when workers must debate or
  exchange discoveries; independent research remains cheaper and clearer as
  isolated leaf agents.
- Treat subagent messages as self-reports. Read the requested Finding Pack,
  inspect decisive evidence, and reconcile contradictions before updating the
  shared ledger. Keep auto-memory and conversation resume as secondary context;
  the workspace checkpoint is authoritative after compaction or restart.
- After handoff, use `scripts/native_execution_adapter.py` with host argument
  `claude` for atomic task attempts, crash recovery, Finding Pack validation,
  and completion checks when Python is available. The native task list mirrors
  this state; it does not replace it.
- The installed package contains `SKILL.md`, bundled references/assets, and the
  dependency-free native execution adapter. It does not contain the repository
  Python runtime, lifecycle hooks, builder, or evaluation corpus.

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
