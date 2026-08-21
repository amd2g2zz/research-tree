## Why

The supported setup path still detects prior-version host links and silently
replaces them with current packages. That mutates user-owned targets and keeps
`migrated` and `planned_migration` outcomes alive after the project adopted its
current-only compatibility policy.

## What Changes

- **BREAKING**: Remove legacy-target recognition and automatic replacement from
  `research-tree-setup install` and `status`.
- **BREAKING**: Retire the `research-tree-setup refresh` command and its
  stale-link mutation helpers.
- Archive the completed cross-host activation change as historical evidence
  without synchronizing its retired setup delta into the active umbrella.
- Keep new installation and status reporting for current Codex, Claude Code,
  and Hermes package targets.
- Report any existing non-current target as unsupported without unlinking,
  moving, replacing, or otherwise modifying it.
- Register #169 as planned task group 57 with a source-bound acceptance command.

## Capabilities

### New Capabilities

- `current-only-skill-setup`: Install current host packages only into missing
  targets and reject existing non-current targets without mutation.

### Modified Capabilities

- `skill-activation-integrity`: Remove legacy/migration setup behavior while
  retaining current host installation and discovery checks.

## Impact

This changes `src/research_tree/skill_setup.py`, focused setup regressions,
the setup command help, Alpha2 execution registries, active installation
contracts, and generated host packages after rebuilding from source. It does
not inspect or alter any user-owned runtime directory, nor does it change
current host package layouts.
