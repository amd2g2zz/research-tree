## ADDED Requirements

### Requirement: InsightDigest is a first-class versioned artifact

The runtime SHALL persist an InsightDigest with source revisions, covered Decision Slots, confirmed facts, hypotheses, contradictions, unresolved gaps, confidence/calibration, changed beliefs, recommended actions, and limitations. It SHALL have a producer version and exact parent references.

A synthesis checkpoint SHALL reject while any attempt remains `leased` or
`running`. Once no attempt is in flight, an empty or partial accepted batch is
still reduced: every active Decision Slot without an accepted Finding Pack
becomes an explicit blocking `landscape` gap. If a prior InsightDigest exists,
the caller MUST provide its exact current artifact reference and the successor
MUST persist it as both predecessor metadata and immutable parent lineage.

#### Scenario: Findings are synthesized

- **WHEN** a new verified Finding Pack batch is ingested
- **THEN** the digest is recomputed from canonical inputs and the prior digest remains immutable

#### Scenario: Worker is still executing

- **WHEN** a synthesis checkpoint is requested while an attempt is `leased` or `running`
- **THEN** the coordinator rejects `batch_incomplete` without writing a digest or changing lifecycle state

#### Scenario: Active Slot has no accepted Finding Pack

- **WHEN** the settled batch leaves an active Decision Slot uncovered
- **THEN** the digest records a blocking gap and a landscape successor trigger for that exact Slot

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
