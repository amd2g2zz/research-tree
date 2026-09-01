## ADDED Requirements

### Requirement: Strict evidence resolves through immutable ledger lineage

The system SHALL resolve an authoritative anchor only through its exact
`ArtifactRef`, a matching canonical evidence artifact, its bound CAS content,
and the current RunLedger revision. It MUST reject missing, stale, inactive,
out-of-scope, changed, source-revision-unverifiable, reversed, or
out-of-range evidence before it affects canonical research state.

#### Scenario: A stale or reversed anchor is presented

- **WHEN** an anchor identifies a non-current evidence revision or a fragment
  whose end precedes its start
- **THEN** strict resolution SHALL fail without producing a usable observation

#### Scenario: A repository source cannot prove its inspected revision

- **WHEN** a repository-path evidence artifact has no matching current source
  revision oracle
- **THEN** strict resolution SHALL fail closed

### Requirement: Canonical research decisions retain exact evidence parents

The system SHALL compile strict Finding Packs and Decisions only through the
RunLedger. Each consequential strict observation MUST contain a typed anchor
and its exact evidence reference MUST appear in Finding Pack parent lineage.
Every selected or conditional canonical Decision MUST retain a non-empty strict
Finding Pack for its exact Target, Slot, selected option, and evidence parents.
A canonical Decision MUST reject non-strict findings.

#### Scenario: A generic legacy finding is supplied to canonical convergence

- **WHEN** a caller supplies a legacy or caller-map "strict" finding
- **THEN** canonical decision convergence SHALL reject it

#### Scenario: A lower-priority selected decision lacks strict evidence

- **WHEN** a caller selects or conditions any Decision Slot without a strict
  Finding Pack
- **THEN** canonical decision convergence SHALL reject it regardless of the
  slot priority

### Requirement: Strict readiness cannot be satisfied by legacy evidence

The system SHALL re-resolve consequential evidence for canonical readiness and
verify each selected or conditional Decision has a matching strict Finding Pack,
support for its selected option, and exact evidence parent closure. Legacy
history MAY remain readable through its compatibility path, but it MUST NOT
produce a passing strict closure/readiness result.

#### Scenario: A legacy generic anchor appears in a technical package

- **WHEN** strict readiness evaluates the package
- **THEN** decision closure and implementation readiness SHALL not pass
