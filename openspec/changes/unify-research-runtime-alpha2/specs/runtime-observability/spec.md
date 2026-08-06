## ADDED Requirements

### Requirement: Every lifecycle transition has a causal trace
The system SHALL record run, round, Decision Slot, action, attempt, host, prior revision, next revision, cause event, decision inputs, score components, result, and reason for each canonical transition.

#### Scenario: Research action is pruned
- **WHEN** the adaptive policy defers a duplicate or dominated action
- **THEN** the trace records the retained action, comparison inputs, exemption checks, and prune reason

#### Scenario: Completion candidate is rejected
- **WHEN** a host or caller requests completion before all gates pass
- **THEN** the trace identifies the request and every unmet canonical obligation

### Requirement: Operators can explain current and historical decisions
The system SHALL provide commands or equivalent APIs for explaining a run, the selected action, non-completion reasons, event replay, and host reconciliation.

#### Scenario: User reports that research stopped too early
- **WHEN** an operator runs `why-not-complete` or inspects the terminal transition
- **THEN** the output identifies whether the run is complete, paused, blocked, superseded, or awaiting acceptance and lists evidence-backed reasons

### Requirement: Replay is deterministic
The system SHALL rebuild canonical projections from immutable events and artifacts and SHALL produce the same semantic state digest for repeated replay of the same revisions.

#### Scenario: Projection cache is removed
- **WHEN** a run projection is rebuilt from the authoritative ledger
- **THEN** its lifecycle, active actions, consumed findings, closure state, and delivery references match the recorded digest

### Requirement: Diagnostics preserve privacy and provider boundaries
The system SHALL exclude secrets, credentials, private chain-of-thought, full prompts, and raw provider errors from persisted traces while retaining safe identifiers and diagnostic references.

#### Scenario: Provider returns sensitive raw details
- **WHEN** a host reports a provider failure containing request or credential material
- **THEN** the trace persists only normalized category, provider/model identifiers, opaque code, retry count, and safe gateway-log reference

### Requirement: Host reconciliation identifies missing or divergent events
The system SHALL compare host-visible tasks with canonical attempts and mark missing, stale, duplicate, or uncertain outcomes without trusting host-local completion.

#### Scenario: Host shows completed task absent from ledger
- **WHEN** reconciliation finds a host completion with no accepted Finding Pack event
- **THEN** the canonical attempt remains incomplete and the discrepancy is recorded for recovery

### Requirement: Trace events have a stable export schema

Every causal trace SHALL contain trace_id, run_id, event_id, causation_id, correlation_id, sequence, emitted_at, actor, host, prior_digest, next_digest, action, inputs, score_components, outcome, redaction_class, and retention_class. Export SHALL preserve ordering and hashes without exposing secrets or private reasoning.

#### Scenario: Two events share a timestamp

- **WHEN** events cannot be ordered by timestamp alone
- **THEN** sequence and causation ids determine deterministic replay order

#### Scenario: Diagnostic export is requested

- **WHEN** an operator runs export-audit or replay
- **THEN** the output includes schema versions, redaction status, unresolved references, and verification commands

### Requirement: Research depth and continuity are observable

The trace SHALL record SearchPortfolio revision, query rewrite reason, method/provider boundary, batch coverage assessment, depth disposition, strategy pivot refs, SourceCapture and AnalysisCheckpoint persistence, native workflow projection, and successor resume lineage. It SHALL distinguish a provider returning results from a Decision Slot becoming sufficiently closed.

#### Scenario: A shallow search triggers deepening

- **WHEN** a batch is marked `deepen`
- **THEN** `why-action` resolves the missing evidence dimension, the source/checkpoint refs considered, and the selected deepening action

#### Scenario: Research pivots after invalidating evidence

- **WHEN** a successor strategy is created
- **THEN** replay shows the invalidating evidence, stale actions, successor revision, and whether the pivot remained within authority
