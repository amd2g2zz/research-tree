## ADDED Requirements

### Requirement: Copy installations are content-addressed

The installer SHALL report a non-link target as `current` only when its
validated payload digest equals the selected host package digest.

#### Scenario: Clean copies are current across hosts

- **WHEN** Codex, Claude, and Hermes packages are installed by copy
- **THEN** each status is `current` with `payload_digest_match`
- **AND** source and target payload digests are equal

### Requirement: Non-current installations are diagnosable

The installer SHALL report deterministic reasons for conflicts without
overwriting user-owned paths.

#### Scenario: Tampered or incomplete copy

- **WHEN** a copied payload is edited or a referenced resource is removed
- **THEN** status is `conflict`
- **AND** the reason identifies digest mismatch or missing referenced resource

#### Scenario: Foreign link

- **WHEN** a target link does not resolve to the selected package
- **THEN** status is `conflict` with `link_target_mismatch`
- **AND** the foreign target payload is not read
