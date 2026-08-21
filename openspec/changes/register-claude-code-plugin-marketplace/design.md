## Context

The repository currently generates three host packages with a common package
root containing `SKILL.md`. Claude Code's plugin system has a different
registration boundary: a marketplace manifest is read from the repository
root, a plugin manifest is read from the plugin's `.claude-plugin` directory,
and Skill components are discovered below the plugin root's `skills/` directory.

The existing direct installer must continue to support user and project-scoped
Skill directories. Codex and Hermes must keep their current package layouts.
Package output is generated from `skill-src/`; checked-in packages and the
marketplace manifest are distribution artifacts, not independent sources.

## Goals / Non-Goals

**Goals:**

- Generate a valid Claude Code marketplace and plugin from repository-owned
  metadata.
- Keep the Claude plugin self-contained and preserve relative resource paths.
- Make package checks fail on stale, malformed, misplaced, or cross-host
  metadata.
- Let `research-tree-setup` install the nested Claude Skill itself while
  reporting the plugin package root for diagnostics.
- Provide reproducible local validation commands and GitHub installation
  instructions.

**Non-Goals:**

- Adding Claude hooks, commands, agents, MCP servers, or dynamic workflow
  behavior in this change.
- Changing Codex or Hermes package formats.
- Automatically mutating user-owned Claude plugin caches or marketplaces.
- Claiming that a manifest check proves a live Claude session loaded the Skill;
  that remains part of the activation work in #71.

## Decisions

### Native nested Skill layout

The Claude package will use:

```text
packages/claude-code/research-tree/
  .claude-plugin/plugin.json
  skills/research-tree/SKILL.md
  skills/research-tree/assets/
  skills/research-tree/references/
  skills/research-tree/scripts/
```

This follows Claude Code's native plugin discovery contract. The builder will
render the existing host-specific Skill into the nested directory rather than
maintaining a second hand-edited copy.

Claude namespaces a Skill loaded through a plugin as
`/research-tree:research-tree` because both the plugin and Skill are named
`research-tree`. The direct installer remains a separate compatibility path
whose normal command is `/research-tree`.

### Repository-owned metadata and generated manifests

Canonical metadata lives under `skill-src/` (`claude-plugin.json` and
`claude-marketplace.json`). The builder copies those files to the plugin and
repository `.claude-plugin/` locations and validates JSON, names, source paths,
and version consistency with `pyproject.toml`. A check run is read-only and
reports marketplace and package errors together.

### Installer source resolution

`resolve_package()` continues to identify the host package root. A separate
internal resolver maps Claude's package root to
`skills/research-tree/` for direct Skill link/copy installation. This keeps
the installed direct-skill target compatible with Claude's ordinary
`.claude/skills/research-tree/SKILL.md` discovery while preserving the plugin
root in status output.

### Validation boundaries

The builder validates only repository-owned generated artifacts. It does not
invoke the Claude CLI or mutate a user's plugin registry. Documentation uses
`claude plugin validate` as an optional host-side structural smoke test when the
Claude executable is available.

## Risks / Trade-offs

- [Risk] Existing callers may assume the Claude package root directly contains
  `SKILL.md` -> the installer and package tests resolve the nested Skill path;
  the compatibility reference documents the new boundary.
- [Risk] Marketplace/plugin versions drift from the Python project version ->
  the builder compares both manifests with `pyproject.toml` during every check.
- [Risk] A malformed marketplace source can make discovery fail -> JSON shape,
  source existence, and plugin-name consistency are checked before output is
  accepted.
- [Risk] Users may confuse a static manifest check with live activation -> docs
  explicitly separate `discovered`, `static_ready`, and `live_verified`.

## Migration Plan

1. Add source metadata and update the builder in one PR.
2. Regenerate checked-in packages and the repository marketplace manifest.
3. Run Python tests, package parity, OpenSpec validation, and (when installed)
   `claude plugin validate packages/claude-code/research-tree`.
4. Existing direct Claude installations are not overwritten automatically;
   rerun `research-tree-setup install --host claude` to migrate a managed copy.
5. Rollback is a normal PR revert; no user cache or marketplace state is
   modified by the repository build.

## Open Questions

- Live activation probes and cache refresh behavior remain in #71.
- A future release may publish a tagged marketplace ref rather than the
  default branch; this change keeps the source path relative so that either
  policy can be adopted later.
