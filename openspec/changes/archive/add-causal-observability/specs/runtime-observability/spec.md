## ADDED Requirements

### Requirement: Every canonical lifecycle transition has a verifiable causal trace
The system SHALL project each canonical lifecycle transition with exact run, event, prior-state, next-state, actor, action, reason, digest, and artifact-reference lineage. It MUST reject a transition whose cause event is missing, dangling, duplicated, or inconsistent with the state edge.

#### Scenario: Transition cause is missing
- **WHEN** replay encounters a state revision without its exact lifecycle cause event
- **THEN** verification fails with the unresolved reference and does not infer a cause

#### Scenario: Completion candidate is rejected
- **WHEN** a caller requests completion before all canonical gates pass
- **THEN** the explanation identifies the rejected action and every unmet obligation with available evidence references

### Requirement: Replay is deterministic and digest verified
The system SHALL order lifecycle state by lifecycle revision, reconstruct every transition from immutable ledger artifacts, recompute recorded state digests, and return the same terminal semantic digest for repeated replay of unchanged revisions.

#### Scenario: Timestamps do not provide unique ordering
- **WHEN** multiple artifacts share or reorder timestamps
- **THEN** lifecycle revision and exact lineage determine replay order

#### Scenario: State payload is inconsistent with its digest
- **WHEN** replay detects a state-digest mismatch or a forked lifecycle revision
- **THEN** replay fails without returning a verified terminal state

### Requirement: Operators can explain runs and actions
The system SHALL provide JSON APIs and CLI commands for `explain-run`, `why-action`, `why-not-complete`, `replay`, and `reconcile-host`, with deterministic ordering and exact artifact references.

#### Scenario: Research appears to stop early
- **WHEN** an operator requests a run or non-completion explanation
- **THEN** the output states the current lifecycle state, verified terminal digest status, all blockers, and their evidence gaps

#### Scenario: Action selection is questioned
- **WHEN** an operator requests an action explanation by exact action identifier
- **THEN** the output resolves its policy or work artifact, inputs, score components, outcome, and causal references or reports it unresolved

### Requirement: Diagnostics preserve privacy and provider boundaries
The system MUST exclude prompts, credentials, secrets, tokens, private reasoning, raw gateway errors, and unbounded provider values from persisted or exported causal traces. It SHALL retain only allowlisted bounded identifiers, categories, opaque codes, counters, and workspace-relative diagnostic references.

#### Scenario: Provider failure includes sensitive detail
- **WHEN** a provider observation contains a sensitive key or raw free-form diagnostic value
- **THEN** the diagnostic projection rejects or redacts that value and emits no sensitive content

### Requirement: Host reconciliation is read-only and non-authoritative
The system SHALL compare bounded host-visible attempt observations with canonical leases and host events, classify missing, stale, duplicate, divergent, and uncertain outcomes, and MUST NOT alter lifecycle state or accept host-local completion.

#### Scenario: Host reports an unrecorded completion
- **WHEN** a host marks a task complete but no canonical accepted result event exists
- **THEN** reconciliation reports the discrepancy while the canonical attempt and run remain incomplete

#### Scenario: Host repeats the same event
- **WHEN** duplicate host observations share an event identifier
- **THEN** reconciliation reports the duplicate deterministically without double-counting it

### Requirement: Ruff is part of the TDD acceptance gate
Each implementation slice SHALL require focused behavioral tests, `ruff check`, and `ruff format --check` to pass before it is considered green, and the final verification receipt SHALL record the combined command.

#### Scenario: Behavioral tests pass but formatting does not
- **WHEN** focused pytest passes and either Ruff command fails
- **THEN** the TDD slice remains unverified
