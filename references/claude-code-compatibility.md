# Claude Code Compatibility

Use this reference when packaging or running the Claude Code variant. It is
not needed for ordinary research unless the task involves Claude-specific
installation or development.
The verified baseline is Claude Code 2.1.221.

## Package boundary

The installable package is `packages/claude-code/research-tree/`. It is a
self-contained Agent Skill with Claude Code frontmatter:

- `argument-hint` describes accepted request material;
- `user-invocable: true` exposes `/research-tree`;
- `disable-model-invocation: false` allows Claude Code to select the Skill when
  its description matches.

The package includes the dependency-free `scripts/native_execution_adapter.py`
but not the repository Python runtime, hooks, builder, or evaluation corpus.
Those remain development assets in the source checkout:

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

### Explicit body loading

Use the native `/research-tree` command in a fresh Claude Code session. Reading
`SKILL.md` through an ordinary file tool is not equivalent to Skill activation,
and wrappers that disable slash commands cannot claim this body's instructions
were injected. Confirm a session with `/research-tree --activation-probe`; the
only accepted response is `research-tree activation: RT-ACTIVE-V1-CLAUDE`.

## Invocation and alignment

Use `/research-tree <request>` for explicit invocation. Claude Code's current
tool set is session-dependent, so the Skill must use ordinary dialogue unless a
structured question tool is actually exposed. Do not assume Codex or Hermes
tool names.

A Markdown link, a `SKILL.md` path, or `$research-tree` text is not the Claude
Code invocation contract. Start a new Claude Code session after an install or
refresh, then run `/research-tree --activation-probe`. The exact Claude
sentinel is evidence that the loaded session saw this package body;
`research-tree-setup activation --host claude --source .` only proves the
generated package and configured target.

The Skill owns research alignment and report production; Claude Code owns
model calls, repository inspection, web access, shell execution, permissions,
and any delegation that is actually available.

Read `references/claude-native-orchestration.md` before delegation, compaction,
or recovery. It defines when to use parallel leaf agents, background execution,
agent teams, session resume, worktrees, task lists, and auto-memory without
confusing any of them with the durable research ledger.

## User questions

Claude Code's structured user-question tool is named `AskUserQuestion`. In the
Agent SDK it must be included in the session's `tools` list and handled by the
`canUseTool` callback; it supports multiple-choice questions and can block until
the user responds. Native availability is still session-dependent for a Skill,
so do not call the name unless the host exposes it. Use ordinary open-ended
dialogue for intent elicitation even when it is available. Reserve the tool for
a rare consequential discrete decision after the agent has explained the
distinction and invited the requester to respond in their own words. This tool
is distinct from permission prompts for dangerous tool calls.

## Optional project hooks

The repository template `hooks/claude-code.settings.template.json` contains
`SessionStart`, `SessionEnd`, `PreCompact`, `SubagentStop`, and `Stop` command
hooks. Merge only its `hooks` object into an
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
- [Claude Code subagents](https://code.claude.com/docs/en/sub-agents)
- [Claude Code agent teams](https://code.claude.com/docs/en/agent-teams)
- [Claude Code memory](https://code.claude.com/docs/en/memory)
- [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference)
