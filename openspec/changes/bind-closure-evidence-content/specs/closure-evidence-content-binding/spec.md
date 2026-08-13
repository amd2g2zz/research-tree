## ADDED Requirements

### Requirement: Closure evidence has durable canonical content

The closure assessor SHALL accept a strict Finding Pack as closure evidence
only when every observation has an exact EvidenceAnchor for a current direct
`evidence-artifact` parent whose canonical payload and available ledger content
binding resolve to readable CAS bytes whose digest and byte size agree with the
typed payload. An artifact whose `evidence_class` is `legacy_unspecified` SHALL
not be authoritative closure evidence. Each anchor SHALL pass strict selector
bounds and repository locator validation. Each evidence artifact
SHALL have exactly one succeeded direct `acquisition-receipt` parent and that
receipt SHALL have exactly one direct, committed `source-capture` parent with
matching capture, attempt, method, and provider identities. Every declared
origin capture SHALL resolve to a current canonical capture with an available,
matching content binding.

#### Scenario: Bound CAS bytes are unavailable or tampered
- **WHEN** an otherwise canonical evidence artifact, source capture, or origin
  capture has a bound content record but its CAS bytes are missing or no longer
  match the bound digest or byte size
- **THEN** the assessment is inconclusive and cannot issue a closure token

#### Scenario: Raw bound evidence remains legacy-unspecified
- **WHEN** a raw ledger EvidenceArtifact has valid bound CAS content but its
  `evidence_class` is `legacy_unspecified`
- **THEN** the assessment is inconclusive and cannot issue a closure token

#### Scenario: Strict anchor selector or locator is invalid
- **WHEN** a strict anchor selects beyond its canonical evidence bytes or its
  evidence artifact declares a repository locator outside the workspace
- **THEN** the assessment is inconclusive and cannot issue a closure token

#### Scenario: Repository revision cannot be verified
- **WHEN** a strict evidence artifact uses a repository-path locator but its
  declared source revision cannot be verified by the strict resolver
- **THEN** the assessment is inconclusive and cannot issue a closure token

#### Scenario: Shape-correct graph has no capture content binding
- **WHEN** a source capture, receipt, and evidence graph has syntactically
  valid IDs and parents but the source capture has no ledger CAS binding
- **THEN** the assessment is inconclusive and cannot issue a closure token

#### Scenario: Evidence does not resolve to its canonical receipt and capture
- **WHEN** an EvidenceArtifact, AcquisitionReceipt, or SourceCapture has a
  mismatched direct parent or conflicting typed identity
- **THEN** that Finding is not authoritative closure evidence and no passed
  assessment is persisted from the graph

#### Scenario: Origin capture is not durably bound
- **WHEN** a capture declares an origin whose canonical payload lacks a
  matching available content binding
- **THEN** the derived evidence is rejected before closure can pass

### Requirement: Closure input includes every current decision Finding

Before assessing a Decision Ledger entry, the closure assessor SHALL derive all
current `finding-pack` direct parents that are bound to the exact selected
blueprint target and decision slot. The supplied Finding sequence SHALL resolve
to exactly that reference set; it SHALL not omit, substitute, or add a Finding.

#### Scenario: Caller omits a current contradictory Finding
- **WHEN** a decision has a current target-and-slot-bound Finding whose option
  effect contradicts the selected option and the caller omits it
- **THEN** the assessor rejects the input before appending an assessment

#### Scenario: Caller supplies an unrelated Finding
- **WHEN** the caller includes a current Finding that is not a qualifying
  direct parent of the decision
- **THEN** the assessor rejects the input before appending an assessment

#### Scenario: Decision has a mismatched Finding parent
- **WHEN** a direct current Finding parent does not bind the selected target and
  decision slot
- **THEN** the assessor rejects the malformed decision before assessing a
  partial Finding set

#### Scenario: Assessment lineage is foreign, stale, or mixed
- **WHEN** an assessment input belongs to another run, a decision directly
  references a superseded Finding revision, or a receipt declares a capture
  other than its direct capture parent
- **THEN** the assessor fails closed with a deterministic rejection or
  inconclusive evidence result and cannot issue a closure token

### Requirement: Content-bound evidence preserves the assessment API boundary

The evidence-content admission boundary SHALL preserve the existing
`SlotClosureAssessor.assess()` argument shape and SHALL not derive quality,
counterevidence, contradiction, token-currentness, completion, or delivery
state in this child slice.

#### Scenario: Existing evaluator call shape remains accepted
- **WHEN** a caller invokes `assess()` with the existing evaluator and quality
  arguments plus a canonical, complete evidence graph
- **THEN** the assessor evaluates the graph without requiring a new caller API
