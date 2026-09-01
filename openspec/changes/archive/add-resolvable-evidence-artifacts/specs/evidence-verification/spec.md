# Evidence Verification

## ADDED Requirements

### Requirement: typed evidence artifacts
The runtime SHALL validate EvidenceArtifact fields against the checked-in v1
artifact schema, including lowercase SHA-256 digest, positive revision,
acquisition timestamp, media type, provenance, applicability, confidence,
limitations, extractor version, and lifecycle status.

#### Scenario: malformed immutable metadata
- **WHEN** an artifact has an uppercase digest or invalid timestamp
- **THEN** the runtime rejects it with a typed validation error

### Requirement: typed anchors
The runtime SHALL validate all seven selector types and reject malformed,
negative, empty, or out-of-range selector values.

#### Scenario: image anchor
- **WHEN** an image anchor specifies non-negative coordinates and positive dimensions
- **THEN** the runtime accepts the selector

### Requirement: exact resolution
The runtime SHALL resolve an anchor only when the exact artifact revision is
active and the CAS bytes still match the declared digest and byte size.

#### Scenario: tampered CAS object
- **WHEN** CAS bytes no longer hash to the anchor artifact digest
- **THEN** resolution fails without returning bytes

### Requirement: boundary enforcement
Repository/path locators SHALL remain within the configured workspace. Missing,
changed, inactive, or out-of-scope evidence SHALL raise a typed validation
error rather than being silently accepted.

#### Scenario: path traversal
- **WHEN** a repository locator escapes the configured workspace
- **THEN** the runtime rejects the anchor

### Requirement: provenance independence
Evidence derived from the same origin SHALL share a provenance group, so URL
count alone SHALL NOT be treated as independent corroboration.

#### Scenario: derivative URLs
- **WHEN** two URLs share an origin but differ by path or tracking parameters
- **THEN** their default provenance group is identical

### Requirement: Finding Pack traceability
Consequential Finding Pack observations SHALL support typed resolvable anchors;
the compiler integration SHALL preserve an explicit compatibility path for
legacy string anchors during migration.

#### Scenario: strict compiler mode
- **WHEN** a FindingPackCompiler is configured with an EvidenceResolver
- **THEN** a generic string anchor is rejected and a resolvable typed anchor is required
