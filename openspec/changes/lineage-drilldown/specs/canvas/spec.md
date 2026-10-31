## ADDED Requirements

### Requirement: <= 3 clicks from any conclusion node to raw evidence

#### Scenario: committed claim resolves
- **WHEN** a claim is committed in version v0
- **THEN** the lineage path has ≤ 3 clicks with layers canvas-node / detail-drawer / raw-evidence

#### Scenario: historical version preserves lineage
- **WHEN** a claim from a historical version is resolved
- **THEN** the raw evidence from that version's snapshot is reachable

#### Scenario: unknown claims return null (no fake lineage)
- **WHEN** a nonexistent claim id is resolved
- **THEN** the result is null
