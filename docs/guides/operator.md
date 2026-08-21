# Operator Guide

This guide covers installation, host configuration, lifecycle commands, and
diagnostics. It is for operators and integrating agents; most requesters only
need the [README](../../README.md).

## Environment

Use the repository-managed Python environment:

~~~bash
git clone https://github.com/amd2g2zz/research-tree.git
cd research-tree
uv sync
~~~

Do not run bundled scripts through an arbitrary system Python. Use
<code>uv run --frozen</code> after the lockfile is present.

## Install And Verify

~~~bash
uv run --frozen research-tree-setup install --host codex --source . --dry-run
uv run --frozen research-tree-setup install --host codex --source .
uv run --frozen research-tree-setup status --host codex --source .
uv run --frozen research-tree doctor --host all --source .
~~~

Choose <code>codex</code>, <code>claude</code>, or <code>hermes</code>. Use
<code>--mode copy</code> only when a symlink or junction is unsuitable. Setup
deploys the selected Skill and its global lifecycle hooks. Status verifies the
payload digest and hook configuration rather than trusting installation paths.

| Host | User installation | Project installation | Invocation |
| --- | --- | --- | --- |
| Codex | <code>$CODEX_HOME/skills/research-tree</code> | <code>.agents/skills/research-tree</code> | <code>$research-tree ...</code> |
| Claude Code | <code>~/.claude/skills/research-tree</code> | <code>.claude/skills/research-tree</code> | <code>/research-tree ...</code> |
| Hermes Agent | <code>~/.hermes/skills/research-tree</code> | <code>skills.external_dirs</code> | <code>/research-tree ...</code> |

Host packages are isolated and not interchangeable.

## Claude Code Marketplace

~~~bash
claude plugin marketplace add amd2g2zz/research-tree
claude plugin install research-tree@research-tree
claude plugin validate packages/claude-code/research-tree --strict
~~~

Invoke <code>/research-tree:research-tree ...</code>. Run
<code>/reload-plugins</code> after updating a local marketplace checkout.

## Hermes External Directory

Hermes has no native project Skill directory. To load the package from a
checkout, configure its parent directory:

~~~yaml
skills:
  external_dirs:
    - /absolute/path/to/research-tree/packages/hermes
~~~

Run <code>/reload-skills</code> after changing the configuration. Diagnose
provider and package status explicitly:

~~~bash
uv run --frozen python \
  packages/hermes/research-tree/scripts/hermes_skill_adapter.py doctor \
  --skill-dir packages/hermes/research-tree
~~~

A process exit code alone is not proof that a provider completed a model turn.

## Durable Lifecycle

~~~bash
uv run --frozen research-tree run \
  --workspace /path/to/workspace --host codex \
  --project-id selection --run-id selection-001 \
  --outcome "recommend a supportable option" \
  --scope "provided sources and operating constraints" \
  --authority "research and recommendation only" \
  --success-oracle "traceable evidence and explicit decision conditions"

uv run --frozen research-tree status \
  --workspace /path/to/workspace --host codex \
  --project-id selection --run-id selection-001

uv run --frozen research-tree resume \
  --workspace /path/to/workspace --host codex \
  --project-id selection --run-id selection-001

uv run --frozen research-tree verify \
  --workspace /path/to/workspace --host codex \
  --project-id selection --run-id selection-001
~~~

The interface returns versioned JSON and hides internal database and event
schemas. Prepared or durable state is not completion authority.

## Setup-Managed Lifecycle Hooks

`research-tree-setup install` deploys hooks into the selected host's global
configuration while preserving unrelated entries:

| Host | Template | Configuration target |
| --- | --- | --- |
| Codex | <code>hooks/codex.hooks.template.json</code> | <code>.codex/hooks.json</code> |
| Claude Code | <code>hooks/claude-code.settings.template.json</code> | <code>.claude/settings.json</code> |
| Hermes Agent | <code>hooks/hermes.config.template.yaml</code> | <code>~/.hermes/config.yaml</code> |

Codex and Claude commands run through the repository's `uv` environment;
Hermes uses the dependency-free hook in its installed package. Hooks record
bounded lifecycle metadata. They do not record prompts, model responses, tool
inputs, or environment variables, and they fail open. If no Research Tree
project/run binding is active, they return without creating or changing
Research Tree state.

## Debug Tracing

Enable traces only for a bounded diagnosis:

~~~bash
uv run --frozen research-tree-debug emit \
  --host codex --phase alignment_blocked --status blocked \
  --code missing-success-oracle
uv run --frozen research-tree-debug summary --limit 50
~~~

Traces contain approved reason codes and limited metadata. They are not a
source of completion authority.

## Package And Repository Checks

~~~bash
uv run --frozen python scripts/build_skill_packages.py --check
uv run --frozen python scripts/check_repository_layout.py
uv run --frozen python scripts/check_docs.py
uv run --frozen pytest -q
~~~

Edit canonical sources rather than generated host packages. See
[Documentation authority](../governance/documentation-authority.md) and
[Development workflow](../contributing/development-workflow.md).
