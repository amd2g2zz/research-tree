# Claude Code Compatibility

Use this reference when packaging or running the Claude Code variant. It is
not needed for ordinary research unless the task involves Claude-specific
installation or development.
The verified baseline is Claude Code 2.1.226.

## Package boundary

The repository marketplace is `.claude-plugin/marketplace.json`. Its
`research-tree` entry resolves to the plugin package
`packages/claude-code/research-tree/`, which contains:

```text
.claude-plugin/plugin.json
skills/research-tree/SKILL.md
skills/research-tree/assets/
skills/research-tree/references/
skills/research-tree/scripts/
```

The nested Skill is self-contained and has Claude Code frontmatter:

- `argument-hint` describes accepted request material;
- `user-invocable: true` exposes `/research-tree:research-tree` when loaded
  through the marketplace plugin;
- `disable-model-invocation: false` allows Claude Code to select the Skill when
  its description matches.

`research-tree-setup install --host claude` is a separate direct-Skill
compatibility path. It links or copies `skills/research-tree/` into a normal
`.claude/skills/research-tree/` directory, where the explicit command remains
`/research-tree`. Do not mix the direct-Skill command with the marketplace
plugin command.

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

## Invocation and alignment

Use `/research-tree:research-tree <request>` after marketplace installation,
or `/research-tree <request>` only for the direct-Skill compatibility path.
Claude Code's current tool set is session-dependent, so the Skill must use
ordinary dialogue unless a structured question tool is actually exposed. Do not
assume Codex or Hermes tool names.

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
claude plugin validate packages/claude-code/research-tree --strict
uv run pytest -q
```

`claude plugin validate` proves the checked-in plugin is structurally valid. It
does not prove a running model turn loaded or followed the Skill; live activation
remains a separate host-native check.

After changing the common template or Claude adapter, rebuild all host packages:

```bash
python scripts/build_skill_packages.py
```

Do not manually edit
`packages/claude-code/research-tree/skills/research-tree/SKILL.md` or either
generated manifest; they are generated artifacts.

Primary documentation:

- [Claude Code skills](https://code.claude.com/docs/en/skills)
- [Claude Code plugins](https://code.claude.com/docs/en/plugins)
- [Claude Code plugin marketplaces](https://code.claude.com/docs/en/plugin-marketplaces)
- [Claude Code hooks](https://code.claude.com/docs/en/hooks)
- [Claude Code settings](https://code.claude.com/docs/en/settings)
- [Claude Code user input](https://code.claude.com/docs/en/agent-sdk/user-input)
- [Claude Code tools reference](https://code.claude.com/docs/en/tools-reference)
- [Claude Code subagents](https://code.claude.com/docs/en/sub-agents)
- [Claude Code agent teams](https://code.claude.com/docs/en/agent-teams)
- [Claude Code memory](https://code.claude.com/docs/en/memory)
- [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference)
