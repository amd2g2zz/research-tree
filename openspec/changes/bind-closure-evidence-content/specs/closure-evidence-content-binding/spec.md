## ADDED Requirements

### Requirement: Closure evidence has durable canonical content

The closure assessor SHALL accept a strict Finding Pack as closure evidence
only when every observation has an exact EvidenceAnchor for a current direct
`evidence-artifact` parent whose canonical payload and available ledger content
binding agree on digest, media type, and byte size. Each evidence artifact
SHALL have exactly one succeeded direct `acquisition-receipt` parent and that
receipt SHALL have exactly one direct, committed `source-capture` parent with
matching capture, attempt, method, and provider identities. Every declared
origin capture SHALL resolve to a current canonical capture with an available,
matching content binding.

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

### Requirement: Content-bound evidence preserves the assessment API boundary

The evidence-content admission boundary SHALL preserve the existing
`SlotClosureAssessor.assess()` argument shape and SHALL not derive quality,
counterevidence, contradiction, token-currentness, completion, or delivery
state in this child slice.

#### Scenario: Existing evaluator call shape remains accepted
- **WHEN** a caller invokes `assess()` with the existing evaluator and quality
  arguments plus a canonical, complete evidence graph
- **THEN** the assessor evaluates the graph without requiring a new caller API
