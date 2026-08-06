## ADDED Requirements

### Requirement: Both research deliveries are compiled from canonical lineage
The system SHALL compile the Technical Research Package and Human Research Report from exact Working Brief, Intent Model, Blueprint Target, Finding Pack, Decision Ledger, and Readiness revisions and SHALL reject arbitrary worker prose as a canonical delivery input.

#### Scenario: Filler Markdown meets size and heading thresholds
- **WHEN** a caller supplies long, well-sectioned Markdown without canonical decision lineage
- **THEN** delivery compilation fails regardless of byte count or heading count

### Requirement: Technical Research Package is implementation-ready
The Technical Research Package SHALL include scope, non-goals, intent basis, baseline, research strategy, findings, source quality, architecture, interfaces, state flows, permissions, decisions, alternatives, consequences, implementation order, repository touchpoints, tests, evaluation, observability, migration, rollout, rollback, unknowns, risks, and traceability as applicable.

#### Scenario: Recommendation lacks an implementation boundary
- **WHEN** a consequential recommendation has no repository touchpoint or explicitly labeled greenfield validation boundary
- **THEN** implementation readiness fails and targeted follow-up work is generated

### Requirement: Human Research Report is a co-primary professional deliverable
The Human Research Report SHALL explain the agent's understood problem, evidence-backed direction, alternatives, trade-offs, expected capability, applicability, risks, uncertainties, implementation meaning, and material changes in language the requester can evaluate without being a compressed courtesy summary.

#### Scenario: Human report only lists conclusions
- **WHEN** the report omits evidence, reasoning, alternatives, or consequential uncertainty
- **THEN** its semantic delivery gate fails even if the technical package passes

### Requirement: Readiness verifies semantic and operational closure
The system SHALL apply intent alignment, Decision Slot closure, traceability, repository fit, implementation readiness, and operational quality gates at the selected risk tier before requesting final acceptance.

#### Scenario: P0 decision is conditionally selected
- **WHEN** a P0 decision depends on a pending validation task
- **THEN** readiness records the conditional state and blocks final completion until the required risk-tier rule is satisfied

### Requirement: Final acceptance binds exact delivery revisions
The system SHALL require contextual user acceptance of both exact delivery revisions and SHALL preserve rejection, requested depth, and intent correction as feedback lineage.

#### Scenario: User rejects report depth
- **WHEN** the user states that the report is shallow or does not answer the intended problem
- **THEN** the run remains non-complete and creates a revised brief, successor round, or evidence-bearing follow-up according to the feedback impact

#### Scenario: User gives generic acknowledgement
- **WHEN** the user responds without accepting the displayed conclusions and trade-offs
- **THEN** no DeliveryAcceptance artifact is issued

### Requirement: Legacy Human Brief artifacts migrate explicitly
The system SHALL recognize alpha1 Human Brief artifacts as legacy inputs while naming all new human-facing deliveries Human Research Report and requiring current semantic gates before acceptance.

#### Scenario: Legacy Human Brief is imported
- **WHEN** migration encounters a valid alpha1 Human Brief
- **THEN** it retains lineage under a legacy disposition but does not satisfy the alpha2 human delivery requirement

### Requirement: Delivery kinds and compatibility aliases are fixed

The canonical kinds SHALL be technical-research-package and human-research-report. human-brief is accepted only by the migration reader, is rewritten with legacy_unverified disposition, and is rejected by the alpha2 acceptance writer.

#### Scenario: New compiler emits a legacy kind

- **WHEN** a compiler or adapter attempts to register human-brief as a new delivery
- **THEN** registration fails with legacy_delivery_kind

#### Scenario: Legacy template is imported

- **WHEN** an alpha1 template uses Human Brief headings or fields
- **THEN** migration records the template revision and compatibility mapping and the new compiler emits the canonical Human Research Report kind

### Requirement: Delivery manifests and claim classes are machine-checkable

Each delivery SHALL include a DeliveryManifest with technical_revision, human_revision, source_ledger_digest, compiler_version, template_version, encoding, output_paths, generated_at, and claim index. Every claim SHALL be classified as fact, inference, recommendation, unknown, or limitation and SHALL reference the exact Decision Ledger entry, Finding Pack, Evidence Anchor, and OracleRun where applicable.

#### Scenario: Claim has no source chain

- **WHEN** a report contains a consequential claim without a resolvable claim-index entry
- **THEN** semantic delivery validation fails and names the missing lineage

#### Scenario: Report is edited after compilation

- **WHEN** output bytes differ from the DeliveryManifest digest
- **THEN** the delivery revision is stale and cannot be accepted

### Requirement: Professional depth uses a required rubric

The delivery gate SHALL evaluate problem fidelity, evidence quality and independence, counterevidence, alternatives and trade-offs, implementation boundary, risks and failure modes, validation path, uncertainties, and operational meaning. Each dimension SHALL have pass/fail/unknown evidence and a diagnostic; headings, byte count, URL count, and prose length SHALL never satisfy a missing dimension.

#### Scenario: Human report is a short conclusion list

- **WHEN** the report lacks reasoning, alternatives, uncertainty, or implementation meaning
- **THEN** the depth rubric returns fail with targeted follow-up work

#### Scenario: Technical package is detailed but not applicable

- **WHEN** recommendations have no repository touchpoint, greenfield boundary, or applicability statement
- **THEN** the implementation-readiness gate returns fail even when all sections are present

### Requirement: Acceptance supports rejection, partial acceptance, and withdrawal

DeliveryAcceptance SHALL bind both exact output revisions and the displayed digest and SHALL support accepted, rejected, needs_deeper_research, needs_intent_correction, and partially_accepted decisions. A later withdrawal or material correction SHALL invalidate acceptance and create feedback lineage.

#### Scenario: Old digest is confirmed

- **WHEN** a user response refers to a prior delivery revision
- **THEN** acceptance is rejected as stale and the current digest is displayed again

#### Scenario: Only one report is accepted

- **WHEN** the user accepts the technical package but requests a deeper human report
- **THEN** the run remains non-complete and records partial acceptance plus the missing delivery work

### Requirement: Deliveries expose research continuity and material pivots

The Technical Research Package and Human Research Report SHALL resolve the SearchPortfolio, SourceCapture, AcquisitionReceipt, AnalysisCheckpoint, Finding Pack, and strategy successor refs that support consequential claims. A material deepen, broaden, validate, or pivot disposition SHALL be disclosed with its trigger evidence, superseded strategy revision, and resulting decision impact.

#### Scenario: Initial research direction is invalidated

- **WHEN** the coordinator completes a successor strategy after contradictory evidence
- **THEN** both deliveries explain the pivot and do not present the superseded plan as the original uninterrupted method

#### Scenario: A report cites an uncaptured source

- **WHEN** a consequential claim has only a URL or worker prose without a durable SourceCapture and selector
- **THEN** delivery readiness rejects the claim or labels it unresolved and the run cannot complete
