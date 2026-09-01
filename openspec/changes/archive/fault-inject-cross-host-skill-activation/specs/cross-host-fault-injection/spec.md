## ADDED Requirements

### Requirement: Host loader faults fail closed

Codex, Claude, and Hermes SHALL reject a loader receipt after any first,
middle, or final byte mutation, truncation, stale session, or wrong host.

#### Scenario: Mutated skill body

- **WHEN** a host's installed `SKILL.md` differs after receipt creation
- **THEN** the loader status is `invalid_loader_receipt`

### Requirement: Activation boundary faults remain blocked

The activation gate SHALL reject missing loader proof, incomplete alignment,
implicit handoff, unsupported actions, and provider/context failure states.

#### Scenario: Pre-handoff dispatch injection

- **WHEN** a caller requests dispatch before explicit handoff
- **THEN** the disposition is `blocked` and no research artifact is authorized
