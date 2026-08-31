## ADDED Requirements

### Requirement: Typed evidence is canonical-only

The runtime SHALL require an explicit `evidence_class`, a canonical evidence
artifact status, and an exact `ArtifactRef` for every `EvidenceAnchor`. It
SHALL reject `legacy_unverified` artifact statuses and anchor payloads, missing
artifact references, and the `allow_legacy` compatibility reader.

#### Scenario: A caller submits a legacy typed anchor

- **WHEN** a caller constructs or parses an anchor without an exact
  `ArtifactRef`, with `legacy_unverified`, or through `allow_legacy`
- **THEN** the runtime rejects the input before it can become a canonical
  Finding, decision, delivery, or readiness input

### Requirement: Evidence resolution is ledger-backed

`EvidenceResolver` SHALL resolve evidence only from the matching `RunLedger`
and its bound content. It SHALL not accept an in-memory artifact map or expose
the legacy provenance normalization helper as a public API.

#### Scenario: A caller attempts map-backed resolution

- **WHEN** a caller constructs an `EvidenceResolver` with an artifact map
- **THEN** construction fails, while `EvidenceResolver.from_ledger` continues
  to resolve canonical content, selectors, locator bounds, and extractor
  metadata

### Requirement: Retained compiler cannot parse legacy typed evidence

The retained `FindingPackCompiler` SHALL remain available for #165's separate
retirement work, but its typed evidence normalization SHALL use the canonical
anchor parser. No compatibility reader, parser, adapter, or fallback SHALL be
introduced.

#### Scenario: A legacy typed evidence payload reaches the retained compiler

- **WHEN** a Finding Pack observation supplies a `legacy_unverified` typed
  anchor
- **THEN** compilation rejects that observation and no Finding Pack is stored

### Requirement: Historical format records remain non-authoritative

The runtime SHALL treat historical governed records as non-authoritative even
when they retain factual references to removed formats. Active schemas, public
exports, runtime sources, and current tests SHALL not advertise or admit those
formats.

#### Scenario: Maintainers inspect current authority after cutover

- **WHEN** maintainers validate active schema and package surfaces
- **THEN** group 83 / issue #168 owns the strict admission boundary and only
  canonical evidence forms are admitted
