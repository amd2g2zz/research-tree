## MODIFIED Requirements

### Requirement: Current host setup preserves installation ownership

The skill setup path SHALL support the current Codex, Claude Code, and Hermes
package targets while treating an existing non-current target as unsupported
without mutation. It SHALL not expose an automatic migration, stale-link
refresh, or compatibility result state for a prior-version target.

#### Scenario: Supported current installations remain available

- **WHEN** a caller installs or checks a missing/current target for Codex,
  Claude Code, or Hermes
- **THEN** the current host-specific package contract remains available

#### Scenario: Existing non-current target has no setup mutation

- **WHEN** setup encounters an existing non-current target
- **THEN** it reports unsupported or rejects installation and does not unlink,
  move, replace, or modify that target
