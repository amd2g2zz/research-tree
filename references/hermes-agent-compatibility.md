# Hermes Agent Compatibility

Use this reference only when `research-tree` runs under Hermes Agent or when
packaging it for Hermes. The compatibility baseline is Hermes Agent v2026.8.3.

## Runtime contract

Hermes follows the Agent Skills open format and accepts this Skill's minimal
`name` and `description` frontmatter. Hermes injects the absolute skill
directory when a skill is loaded and enumerates files under `references/`,
`templates/`, `scripts/`, and `assets/`.

### Explicit body loading

Use `/research-tree` or `/skill research-tree` after the skill directory has
been loaded. A manual `skill_view` or ordinary file read can load supporting
text but does not establish that the Skill entrypoint was injected for the
turn. Confirm a fresh Hermes session with `/research-tree --activation-probe`;
the only accepted response is `research-tree activation: RT-ACTIVE-V1-HERMES`.

Adapt these host differences:

- Load supporting files with `skill_view(name="research-tree",
  file_path="<relative-path>")` or from the injected absolute skill directory.
- Do not assume `ask_user_question` exists. Use ordinary dialogue unless the
  active Hermes toolset exposes a structured input tool.
- Map long-horizon execution through
  `references/hermes-native-orchestration.md`. Hermes top-level delegation is
  background-native; batch independent leaf tasks rather than serializing
  them, and verify returned artifacts instead of trusting child summaries.
- Respect Hermes messaging-platform guidance. Replace Markdown tables with
  labeled bullets on channels that do not render tables.
- Treat the external skill directory as mutable unless filesystem permissions
  make it read-only. Do not patch this Skill during ordinary research.
- Do not assume LangGraph or LangChain is installed. Hermes' native embedding
  boundary is the synchronous `AIAgent.chat()` / `run_conversation()` API. If a
  user explicitly supplies a LangGraph workflow, invoke it as an independent
  callable or service and choose one owner for conversation/checkpoint state.

## User questions

Hermes' native structured question tool is `clarify` in the `clarify` toolset.
It supports open-ended questions, up to four single-select choices, and
`multi_select` choices. It is available in the default `hermes-cli` and most
gateway platform presets, but is explicitly removed from `hermes-acp` and
`hermes-api-server`; inspect the active toolset before using it. Do not confuse
`kanban_block` with a general user-question mechanism. Use ordinary open-ended
dialogue for intent elicitation even when `clarify` is present; reserve it for
a rare consequential discrete decision after explanation. If `clarify` is
absent, continue ordinary conversation and keep the Alignment Checkpoint open.

## Full-fidelity local loading

Add only the isolated Hermes package directory, not the repository root or a
Codex/Claude package, to `~/.hermes/config.yaml`:

```yaml
skills:
  external_dirs:
    - D:/absolute/path/to/research-tree/packages/hermes
```

Linux and macOS paths work the same way. Paths support `~` and `${VAR}`
expansion. Start a new session or run `/reload-skills`, then invoke:

```text
/research-tree <research request>
```

Hermes also supports `/skill research-tree` for explicit loading. A name
collision between a local skill and this external directory must be resolved;
Hermes intentionally refuses to guess between duplicate names.

A raw file URL, a `SKILL.md` path, or an ordinary message mentioning the skill
does not establish multi-file package activation. After installation or a
configuration change, run `/reload-skills` or start a new session, then use
`/research-tree --activation-probe`. The exact Hermes sentinel is live
activation evidence; `research-tree-setup activation --host hermes --source .`
only proves the package and installation target.

Validate the Hermes package before loading it:

```bash
python scripts/hermes_skill_adapter.py validate --mode external-dir
python scripts/hermes_skill_adapter.py doctor
```

The doctor reports the detected CLI, package validity, config visibility, and
whether the package-native observability hook is configured. It does not edit
Hermes configuration.

## Native lifecycle hooks

Generate a hook fragment containing absolute interpreter and package paths:

```bash
python scripts/hermes_skill_adapter.py render-hooks
```

Merge the output into `~/.hermes/config.yaml`, review it, then approve it on
first use. The self-contained hook records session, delegation, and subagent
lifecycle metadata under each task workspace. It does not import the
`research_tree` development package and does not record prompts, task bodies,
summaries, or secrets.

The checked-in `hooks/hermes.config.template.yaml` is a source-checkout example.
Installed copies should use `render-hooks` so paths are correct on that host.

## Installation and publishing

For a user-scoped install from this source checkout, use the repository setup
entry point. It installs into Hermes' own primary skill directory rather than a
Codex or Claude Code directory:

```bash
uv run research-tree-setup install --host hermes --source .
uv run research-tree-setup status --host hermes --source .
```

Use `skills.external_dirs` instead when Hermes should load a shared or
repository-owned directory without installing it under `~/.hermes/skills/`.

Do not install the raw `SKILL.md` URL. Hermes direct-URL installation is
single-file and cannot discover this package's references and templates, so it
is not a valid installation of the Hermes variant.

Hermes GitHub-directory installation downloads the complete skill directory.
Install or publish `packages/hermes/research-tree/`; never point Hermes at the
Codex or Claude Code package. A tap-compatible release can be staged with:

```bash
python scripts/hermes_skill_adapter.py stage /tmp/research-tree-hermes
python scripts/hermes_skill_adapter.py validate \
  --skill-dir /tmp/research-tree-hermes/skills/research-tree \
  --mode github-bundle
```

Publish the staged `skills/research-tree/` directory as a release artifact or
use the checked-in Hermes package as a GitHub-directory source. Regenerate all
host packages with `python scripts/build_skill_packages.py`; do not manually
copy compatibility changes across host variants.

## Verified Hermes constraints

- `SKILL.md` starts at byte zero with `---` and has a non-empty body.
- `name` is at most 64 characters and uses a safe lowercase identifier.
- `description` is at most 1024 characters. Hermes shows only its first 60
  characters in the compact skill index, so the trigger must appear first.
- `SKILL.md` is at most 100,000 characters.
- Supporting paths remain under `references`, `templates`, `scripts`, or
  `assets`.
- Model-facing `delegate_task` calls do not set `background`, `toolsets`, or
  `max_iterations`. Current Hermes controls concurrency and iteration budgets
  from its delegation configuration.
- Completed background notifications survive restart, but in-flight child
  execution does not resume after a host process crash. Recovery verifies
  workspace artifacts and live delegation logs before retrying.

Primary sources:

- [Hermes v2026.8.3 release](https://github.com/NousResearch/hermes-agent/releases/tag/v2026.8.3)
- [Hermes skill authoring guide](https://github.com/NousResearch/hermes-agent/blob/v2026.8.3/skills/software-development/hermes-agent-skill-authoring/SKILL.md)
- [Hermes skills user guide](https://github.com/NousResearch/hermes-agent/blob/v2026.8.3/website/docs/user-guide/features/skills.md)
- [Hermes Python library guide](https://github.com/NousResearch/hermes-agent/blob/v2026.8.3/website/docs/guides/python-library.md)
- [Hermes skill loader](https://github.com/NousResearch/hermes-agent/blob/v2026.8.3/agent/prompt_builder.py)
- [Hermes Skills Hub implementation](https://github.com/NousResearch/hermes-agent/blob/v2026.8.3/tools/skills_hub.py)
- [Hermes built-in tools reference](https://hermes-agent.nousresearch.com/docs/reference/tools-reference)
- [Hermes toolsets reference](https://hermes-agent.nousresearch.com/docs/reference/toolsets-reference)
- [Hermes clarify implementation](https://github.com/NousResearch/hermes-agent/blob/main/tools/clarify_tool.py)
