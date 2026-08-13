## ADDED Requirements

### Requirement: Published legacy CLI commands are removed

The `research-tree` parser SHALL not register the legacy `create-round`,
`show-round`, `tree-init`, `tree-init-alignment`, `tree-next`, `tree-ingest`,
`tree-recover`, `tree-deliver`, `profile-inspect`, `profile-correct`,
`profile-reset`, or `profile-delete` commands. It SHALL not import a legacy
store, preference service, coordinator, or compatibility dispatcher for these
commands. It SHALL not return an `authority_blocked` payload, migration action,
alias, redirect, or replacement command.

#### Scenario: Retired command cannot be parsed or write state
- **WHEN** a caller invokes any retired command with a path that does not
  exist
- **THEN** argparse rejects the command with a nonzero parse failure and the
  path remains absent

#### Scenario: Retired commands are not discoverable
- **WHEN** a caller requests `research-tree --help`
- **THEN** no retired command appears in the help output

### Requirement: Standalone Alpha1 migration surface is removed

The project SHALL not publish `research-tree-migrate`,
`research_tree.migration_cli`, or the Alpha1 migration service as a public
module or root-package export. The layout workflow probe SHALL not invoke that
surface.

#### Scenario: Installed-script metadata does not publish migration
- **WHEN** a caller inspects project script metadata
- **THEN** it contains no `research-tree-migrate` entry

### Requirement: Public source and generated documentation omit retired commands

The project SHALL ensure maintained README content, source templates, references,
and rebuilt host packages omit retired command registrations and describe only
the Python API or future canonical boundary without a legacy command recipe.

#### Scenario: Generated packages have no stale command registration
- **WHEN** host packages are rebuilt from the maintained source templates
- **THEN** package validation succeeds and no retired command registration is
  present in the generated package content
