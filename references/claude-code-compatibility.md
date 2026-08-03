# Claude Code Compatibility

Use this reference when packaging or running the Claude Code variant. It is
not needed for ordinary research unless the task involves Claude-specific
installation or development.

## Package boundary

The installable package is `packages/claude-code/research-tree/`. It is a
self-contained Agent Skill with Claude Code frontmatter:

- `argument-hint` describes accepted request material;
- `user-invocable: true` exposes `/research-tree`;
- `disable-model-invocation: false` allows Claude Code to select the Skill when
  its description matches.

The package does not include the repository Python runtime, hooks, builder, or
evaluation corpus. Those remain development assets in the source checkout:

```text
hooks/research_hook.py
src/research_tree/
scripts/
evaluation/
```

Never resolve those paths relative to an installed Skill directory. They are
available only when the source checkout is present and the task explicitly
requires development work.

## Resource loading

Resolve bundled `assets/` and `references/` from the active Skill directory.
Claude Code may expose that directory through `${CLAUDE_SKILL_DIR}`. A source
checkout path or the user's current working directory is not a substitute for
the installed Skill directory.

## Invocation and alignment

Use `/research-tree <request>` for explicit invocation. Claude Code's current
tool set is session-dependent, so the Skill must use ordinary dialogue unless a
structured question tool is actually exposed. Do not assume Codex or Hermes
tool names.

The Skill owns research alignment and report production; Claude Code owns
model calls, repository inspection, web access, shell execution, permissions,
and any delegation that is actually available.

## User questions

Claude Code's structured user-question tool is named `AskUserQuestion`. In the
Agent SDK it must be included in the session's `tools` list and handled by the
`canUseTool` callback; it supports multiple-choice questions and can block until
the user responds. Native availability is still session-dependent for a Skill,
so do not call the name unless the host exposes it. When absent, use ordinary
dialogue with the same 1-3 decision limit. This tool gathers requirements; it
is distinct from permission prompts for dangerous tool calls.

## Optional project hooks

The repository template `hooks/claude-code.settings.template.json` contains
`SessionStart` and `Stop` command hooks. Merge only its `hooks` object into an
existing `.claude/settings.json`. The hooks are not installed with the Skill,
are not required for research, and must not be enabled without requester
consent. They invoke `uv run --locked research-tree-hook` from the source
checkout and write sanitized records under the ignored
`.research-tree-hooks/events/` directory.

## Development verification

From the source checkout:

```bash
uv sync
python scripts/build_skill_packages.py --check
uv run pytest -q
```

After changing the common template or Claude adapter, rebuild all host packages:

```bash
python scripts/build_skill_packages.py
```

Do not manually edit `packages/claude-code/research-tree/SKILL.md`; it is a
generated artifact.

Primary documentation:

- [Claude Code skills](https://code.claude.com/docs/en/skills)
- [Claude Code hooks](https://code.claude.com/docs/en/hooks)
- [Claude Code settings](https://code.claude.com/docs/en/settings)
- [Claude Code user input](https://code.claude.com/docs/en/agent-sdk/user-input)
- [Claude Code tools reference](https://code.claude.com/docs/en/tools-reference)
