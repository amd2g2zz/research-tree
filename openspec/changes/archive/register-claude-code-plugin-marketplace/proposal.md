## Why

The checked-in Claude Code package is a direct Skill directory, so Claude Code
cannot discover it through a repository marketplace. Its package has no plugin
manifest and the repository has no marketplace definition. The project needs a
host-native registration path that preserves the existing isolated package and
does not turn generated output into a second authoring surface.

## What Changes

- Add a generated repository marketplace manifest at
  `.claude-plugin/marketplace.json` that points to the checked-in Claude Code
  plugin package.
- Convert the Claude Code package to the native plugin layout: plugin metadata
  at `.claude-plugin/plugin.json` and the `research-tree` Skill under
  `skills/research-tree/`.
- Extend the package builder and its check mode to generate and validate both
  manifests, the nested Skill layout, and host isolation.
- Keep direct `research-tree-setup` installation working by installing the
  nested Claude Skill directory into Claude's ordinary skills directory.
- Document marketplace installation, local validation, and the distinction
  between marketplace installation and direct-skill installation.

## Capabilities

### New Capabilities

- `claude-code-plugin-marketplace-registration`: Publish a structurally valid,
  generated Claude Code marketplace and plugin package for `research-tree`.

### Modified Capabilities

None.

## Impact

Affected areas are `scripts/build_skill_packages.py`,
`src/research_tree/skill_setup.py`, checked-in Claude package artifacts,
package/setup tests, CI package validation, and installation documentation.
Codex and Hermes package layouts remain unchanged.
