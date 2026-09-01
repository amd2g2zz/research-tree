## ADDED Requirements

### Requirement: Setup installs only into missing current-host targets

The setup implementation SHALL create a current Codex, Claude Code, or Hermes
package target only when the resolved target does not exist. It SHALL report an
already current target as unchanged and SHALL retain the host-specific package
layout and payload validation.

#### Scenario: Missing targets install current packages

- **WHEN** setup installs each supported host into a missing target
- **THEN** it creates only the selected current package targets and reports
  `installed` or `planned` for those missing targets

#### Scenario: Current target remains unchanged

- **WHEN** setup is rerun for a target that already resolves to its current
  host package
- **THEN** it reports `current`/`unchanged` and does not modify the target

### Requirement: Existing non-current targets are unsupported without mutation

The setup implementation SHALL classify every existing target that is not the
current host package as `unsupported`. Installation and status SHALL not
resolve a prior-version source as a migration input, and setup SHALL not unlink,
move, replace, copy over, or otherwise mutate the target.

#### Scenario: Legacy checkout link remains untouched

- **WHEN** a target links to the former repository-root installation location
  and a caller runs setup install or status
- **THEN** install rejects it as unsupported, status reports it unsupported,
  and the link target remains unchanged

#### Scenario: Former Claude plugin-root link remains untouched

- **WHEN** a Claude target links to the old plugin-root package instead of the
  current nested skill directory
- **THEN** install rejects it as unsupported without changing the link

### Requirement: Setup migration and refresh surfaces are absent

The project SHALL not expose legacy-target detection parameters, migration
actions, `migrated` or `planned_migration` result values, a setup `refresh`
command, or stale-link refresh helpers.

#### Scenario: Retired refresh command is not discoverable

- **WHEN** a caller requests setup help or invokes `research-tree-setup refresh`
- **THEN** help omits the command and argparse rejects the invocation before
  any target path is accessed
