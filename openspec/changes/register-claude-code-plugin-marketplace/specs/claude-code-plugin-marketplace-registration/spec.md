## ADDED Requirements

### Requirement: The repository exposes a Claude Code marketplace

The repository SHALL contain `.claude-plugin/marketplace.json` with valid JSON,
an owner with a non-empty `name`, a marketplace name and version, and exactly
one plugin entry named `research-tree`. The entry source SHALL be the relative
path `./packages/claude-code/research-tree`, and that path SHALL exist in the
same checkout.

#### Scenario: Marketplace discovery resolves the checked-in plugin

- **WHEN** a Claude Code user adds the repository as a marketplace
- **THEN** the marketplace manifest SHALL parse and its `research-tree` source
  SHALL resolve to the checked-in Claude plugin directory

#### Scenario: A stale marketplace source is rejected

- **WHEN** the marketplace source points to a missing path or a different
  plugin name
- **THEN** the package check SHALL fail with a diagnostic naming the invalid
  field or path

### Requirement: The Claude package uses the native plugin boundary

The Claude package SHALL contain `.claude-plugin/plugin.json` and
`skills/research-tree/SKILL.md`. Under this repository's packaging policy, the
plugin manifest SHALL declare the name `research-tree`, a valid semantic
version, a description, an author, and the repository URL. All Skill resources
referenced by the nested `SKILL.md` SHALL remain under that Skill directory.

#### Scenario: Claude validates a local plugin

- **WHEN** `claude plugin validate packages/claude-code/research-tree` is run
  against a built checkout
- **THEN** the plugin structure and Skill frontmatter SHALL be accepted by the
  Claude CLI, and the marketplace invocation SHALL be namespaced as
  `/research-tree:research-tree`

#### Scenario: Host-specific metadata does not leak

- **WHEN** the package builder validates Codex or Hermes output
- **THEN** neither package SHALL contain Claude's `.claude-plugin` metadata or
  nested Claude Skill-only files

### Requirement: Generation and direct installation stay consistent

The package builder SHALL generate the marketplace and plugin manifests from
repository-owned source metadata and SHALL fail its check mode when generated
output, versions, names, or paths drift. `research-tree-setup` SHALL resolve
the nested Claude Skill directory for link/copy installation without changing
Codex or Hermes resolution.

#### Scenario: Rebuilding is deterministic

- **WHEN** the package builder runs twice from the same checkout
- **THEN** the Claude manifests, Skill body, and bundled resources SHALL be
  byte-for-byte identical and `--check` SHALL report valid

#### Scenario: Direct Claude installation targets a Skill directory

- **WHEN** `research-tree-setup install --host claude` runs in copy or link mode
- **THEN** the target SHALL contain `SKILL.md` at its root and the result SHALL
  report the Claude plugin package root as its package provenance
