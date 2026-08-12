## ADDED Requirements

### Requirement: Co-primary deliveries share canonical lineage
The system SHALL compile the Technical Research Package and Human Research Report from the same exact Working Brief, Intent Model, Blueprint Target, Finding Pack, Decision Ledger, evidence, readiness, and source-ledger revisions, and SHALL reject arbitrary worker prose as a canonical delivery input.

#### Scenario: Artifact revisions diverge
- **WHEN** the two delivery surfaces name different manifests or source-ledger digests
- **THEN** semantic delivery validation fails before either surface can be accepted

### Requirement: Consequential claims are machine-traceable
Every consequential fact, inference, recommendation, unknown, or limitation SHALL have a typed claim-index entry whose source chain and surface selectors resolve to exact canonical records appropriate to its class.

#### Scenario: Consequential claim is orphaned
- **WHEN** a finding or recommendation has no resolvable claim-index lineage
- **THEN** validation fails with a diagnostic naming the missing claim or boundary

### Requirement: Delivery quality is semantic
The delivery gate SHALL assess problem fidelity, evidence quality and independence, counterevidence, alternatives and trade-offs, implementation boundary, risks and failure modes, validation path, uncertainties, and operational meaning, and SHALL NOT use headings, byte count, URL count, or prose length as substitutes.

#### Scenario: Filler text meets formatting thresholds
- **WHEN** a long, well-sectioned report lacks evidence-backed reasoning or implementation meaning
- **THEN** its depth assessment fails and identifies targeted follow-up work

### Requirement: The Human Research Report is co-primary
The Human Research Report SHALL expose evidence and reasoning, alternatives and trade-offs, expected capability, applicability, implementation meaning, risks, and uncertainty in a form the requester can evaluate independently of the Technical Research Package.

#### Scenario: Human report only lists conclusions
- **WHEN** the human surface omits evidence, reasoning, alternatives, uncertainty, or first-slice implementation meaning
- **THEN** semantic readiness fails even if the technical surface is otherwise complete

### Requirement: Implementation readiness has observable boundaries
Each proposed implementation slice and consequential recommendation SHALL identify repository touchpoints or an explicit greenfield validation boundary, validation, blockers, rollout, and rollback as applicable.

#### Scenario: Recommendation lacks an implementation boundary
- **WHEN** an implementation item has neither repository touchpoints nor a greenfield validation boundary
- **THEN** readiness fails with an implementation-boundary diagnostic

### Requirement: Acceptance binds the exact displayed pair
DeliveryAcceptance SHALL bind both exact output revisions, the displayed pair digest, the manifest digest, the human actor, contextual feedback, and a typed decision. Generic acknowledgement SHALL NOT create acceptance.

#### Scenario: A stale pair is accepted
- **WHEN** the displayed digest does not match the current run and exact technical and human revisions
- **THEN** acceptance is rejected as stale

#### Scenario: Generic acknowledgement is supplied
- **WHEN** feedback contains only a generic continuation or approval phrase
- **THEN** no authoritative acceptance is created

### Requirement: Corrective feedback drives successor work
Rejected, partially accepted, deeper-research, intent-correction, and withdrawn outcomes SHALL preserve feedback lineage and deterministically select same-round research, awaiting acceptance, or successor-round work without completing the run.

#### Scenario: User rejects report depth
- **WHEN** contextual feedback requests deeper research without changing target, scope, or intent
- **THEN** acceptance records same-round research as the lifecycle action

#### Scenario: User corrects the intended target
- **WHEN** contextual feedback changes target, scope, or intent
- **THEN** acceptance records a successor round as the lifecycle action

### Requirement: Legacy Human Brief is read-only compatibility
The system SHALL recognize existing `human-brief` artifacts as legacy inputs while emitting `human-research-report` for every new human-facing delivery, and legacy artifacts SHALL NOT satisfy Alpha2 semantic acceptance.

#### Scenario: New compiler attempts a legacy write
- **WHEN** a new delivery is registered with kind `human-brief`
- **THEN** the canonical write or acceptance path rejects it as a legacy delivery kind

### Requirement: Canonical dual writes are atomic and replay-safe
The canonical ledger path SHALL validate both delivery payloads before one atomic batch append and SHALL reject stale expected revisions without leaving a single-surface delivery.

#### Scenario: Second surface cannot be persisted
- **WHEN** batch persistence fails while writing the pair
- **THEN** neither delivery revision becomes visible and a retry against the unchanged revision is safe
