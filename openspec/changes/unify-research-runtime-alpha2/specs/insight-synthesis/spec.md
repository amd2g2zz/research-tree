## ADDED Requirements

### Requirement: InsightDigest is a first-class versioned artifact

The runtime SHALL persist and validate only a complete versioned InsightDigest with schema and producer versions, digest identity, source revisions, covered Decision Slots, classified statements, evidence classes, confirmed facts, hypotheses, contradictions, unresolved gaps, recommendations, limitations, confidence/calibration, changed beliefs, previous digest and parent references, realized delta, evidence baseline, transition index, policy signals, next actions, closure disposition, and Finding Pack count. It SHALL reject an unversioned, minimal, or otherwise incomplete payload before policy, scheduler, replay, or delivery consumption and SHALL NOT provide a compatibility reader, adapter, default, read projection, migration, or user-data operation.

#### Scenario: Findings are synthesized

- **WHEN** a new verified Finding Pack batch is ingested
- **THEN** the digest is recomputed from canonical inputs with every current required field and the prior digest remains immutable

#### Scenario: Prior minimal digest is supplied

- **WHEN** a caller supplies the former four-field digest or any payload missing a current required field
- **THEN** validation rejects it before it can affect current policy, scheduler, replay, or delivery state

### Requirement: Insight synthesis distinguishes fact, inference, recommendation, and unknown

The synthesizer SHALL classify each statement, link it to evidence and decisions, preserve competing hypotheses, and reject unsupported certainty language.

Synthesis SHALL be a deterministic reduction over sorted parent revisions: first normalize duplicate evidence by `(provenance_group, content_digest, selector)`, then group statements by Decision Slot, then classify each statement, then aggregate contradictions and gaps, and finally emit action triggers. A `fact` requires at least one resolvable anchor; an `inference` requires its assumptions and supporting anchors; a `recommendation` requires a consequence and reversal condition; an `unknown` requires a reason and next acquisition method. Confidence is calibration metadata, never a closure oracle. The digest SHALL persist the normalized input set and reducer version so replay can reproduce the same output.

#### Scenario: Two findings conflict

- **WHEN** findings support incompatible options
- **THEN** the digest records a contradiction set, affected Slots, evidence bases, and an adversarial or validation action

### Requirement: Insight changes trigger bounded research actions

Growth SHALL be triggered only by a newly exposed gap, contradiction, invalid premise, failed oracle, method limitation, or material implementation uncertainty represented in the digest.

#### Scenario: Digest has no closure-relevant change

- **WHEN** a new batch adds only duplicate provenance and no changed uncertainty
- **THEN** the digest records zero realized change and the policy applies a no-progress penalty without growing arbitrary branches

### Requirement: Insight lifecycle supports supersession and audit

Every digest SHALL record the previous digest reference, changed fields, reason, and whether it invalidates any closure token, readiness gate, delivery, or acceptance.

#### Scenario: New evidence invalidates a recommendation

- **WHEN** a digest marks a prior decision unsupported
- **THEN** dependent closure/readiness/delivery artifacts become stale with explicit lineage and next actions
