## ADDED Requirements

### Requirement: Canonical delivery requires one strict ledger authority

The system SHALL expose a canonical delivery compiler that accepts a
`RunLedger`, a ledger-backed `EvidenceResolver` bound to that exact ledger, a
validated readiness projection mapping, and a caller-supplied expected run
revision. It SHALL reject a foreign ledger/resolver, malformed readiness
projection, or missing expected revision before producing either delivery.

#### Scenario: Canonical inputs are bound to the same ledger

- **WHEN** the compiler receives a `RunLedger`, a resolver whose `.ledger` is
  that ledger, a valid readiness projection, and a current expected run
  revision
- **THEN** it may enter strict delivery preflight using only that ledger's
  artifact graph

#### Scenario: Resolver or readiness authority is foreign

- **WHEN** the resolver belongs to another ledger, or the readiness argument
  is malformed or the expected revision is absent
- **THEN** the compiler SHALL fail before appending a technical package or
  human delivery

### Requirement: Strict preflight resolves every consequential evidence anchor

Before any output append, canonical delivery SHALL resolve every evidence
anchor in every linked Finding Pack through the matching strict resolver. It
SHALL require an exact current `ArtifactRef`, active authoritative evidence,
valid selector bounds, intact CAS content, and a direct parent reference from
the Finding Pack. The Decision and Finding SHALL belong to the exact supplied
Blueprint Target and Decision Slot; stale, missing, foreign, legacy, or
unresolvable lineage SHALL fail closed.

#### Scenario: Strict Finding, Decision, and evidence round-trip

- **WHEN** a current Finding Pack contains resolvable strict anchors, its exact
  evidence parents, and is linked by a current Decision for the supplied
  Target and Slot
- **THEN** strict preflight SHALL resolve the anchors and permit both delivery
  payloads to be built

#### Scenario: Evidence revision is stale or unavailable

- **WHEN** an observation anchor points to a superseded evidence revision,
  missing CAS content, an inactive artifact, an out-of-range selector, or an
  evidence artifact from another round
- **THEN** strict preflight SHALL fail and SHALL append neither output

#### Scenario: Payload claims evidence without parent lineage

- **WHEN** a Finding observation contains a valid strict anchor but its exact
  evidence `ArtifactRef` is absent from the Finding Pack `parent_refs`
- **THEN** strict preflight SHALL fail and SHALL append neither output

### Requirement: Strict outputs preserve exact evidence lineage

The canonical Technical Research Package and human-facing delivery SHALL
retain the exact Working Brief, Intent Model, Blueprint Target, Input,
Decision, Finding, and resolved Evidence `ArtifactRef` values in their parent
lineage. Typed strict anchors SHALL remain visible through the linked Finding
records; no URL, digest-only claim, or worker prose may substitute for an
exact reference.

#### Scenario: Delivery traceability contains resolved refs

- **WHEN** strict preflight succeeds for a set of findings and decisions
- **THEN** both output artifacts SHALL have parent refs for every resolved
  source and evidence revision, and the technical package SHALL render the
  typed Finding anchors without degrading them to URL-only text

#### Scenario: Resolved evidence is omitted from output lineage

- **WHEN** output construction would omit one of the resolved evidence refs or
  would retain a ref with a different revision
- **THEN** strict validation SHALL fail before either artifact is persisted

### Requirement: The output pair is atomically appended

The strict compiler SHALL append the technical package and human-facing
delivery as one `RunLedger` transaction guarded by the supplied expected run
revision. A stale revision, invalid parent, or storage failure SHALL leave no
new member of the pair and SHALL not advance the run revision.

#### Scenario: Concurrent run revision changes before append

- **WHEN** another writer advances the run after the caller captured
  `expected_revision`
- **THEN** the batch append SHALL fail with a ledger conflict and neither
  delivery artifact SHALL be present at a new revision

#### Scenario: Second output cannot be persisted

- **WHEN** persistence fails while preparing either member of the output pair
- **THEN** the transaction SHALL roll back both artifact rows, parent rows,
  events, and the run revision increment

### Requirement: Legacy delivery remains explicitly compatible

The existing `DeliveryCompiler` on `RunStore` SHALL retain its current
argument shape and compatibility behavior. It SHALL not be treated as strict
evidence delivery, and adding the canonical facade SHALL not rename or
rewrite historic `human-brief` artifacts.

#### Scenario: Existing RunStore caller compiles a legacy delivery

- **WHEN** an existing caller invokes `DeliveryCompiler(RunStore).compile`
  with the current readiness mapping
- **THEN** the call SHALL retain its prior result shape and legacy artifact
  compatibility without requiring a canonical resolver

#### Scenario: Legacy compiler is passed canonical-only controls

- **WHEN** a legacy RunStore compiler is asked to use an expected ledger
  revision or strict resolver
- **THEN** it SHALL reject the unsupported strict controls rather than
  silently claiming canonical evidence authority
