## ADDED Requirements

### Requirement: Worker assignments have bounded execution contracts

Every assignment SHALL specify role, objective, Decision Slot, inputs, allowed tools, permission profile, expected Finding Pack schema, success oracle, timeout, heartbeat interval, retry policy, and cancellation behavior.

The default retry policy SHALL be explicit per method: at most three attempts for a retryable failure, one method switch after the configured switch ordinal, exponential backoff values recorded in the AttemptLease, and no retry for permission, integrity, or authority failures. A provider failure without a classified code is `unknown`, not success; a method switch creates a new attempt with a new dispatch digest and preserves the failed attempt as evidence.

#### Scenario: Assignment is dispatched without an oracle

- **WHEN** the scheduler compiles an assignment lacking a closure oracle or explicit human-only outcome
- **THEN** dispatch is rejected and the Slot remains open

### Requirement: Leases and heartbeats prevent orphaned work

The coordinator SHALL issue renewable leases with owner, attempt id, start time, expiry, heartbeat sequence, and last-seen timestamp. Expired leases SHALL become unknown and require reconciliation before reuse.

#### Scenario: Worker stops heartbeating

- **WHEN** the heartbeat deadline passes
- **THEN** the coordinator records heartbeat_timeout, releases or quarantines the attempt according to policy, and schedules a distinct retry identity

### Requirement: Fan-out and fan-in preserve independence

Parallel workers SHALL declare independence groups and method identities. Fan-in SHALL record all submissions, reviewer decisions, quorum policy, disagreements, and duplicate provenance; completion SHALL not be inferred from worker count.

#### Scenario: Two workers use the same source

- **WHEN** their findings share an origin or derivative provenance group
- **THEN** fan-in marks the evidence as non-independent and requests a distinct method or source where required

### Requirement: Worker outputs are typed and partially recoverable

Worker submission SHALL contain attempt identity, observations, evidence anchors, source capture refs, an AnalysisCheckpoint ref, option effects, uncertainties, continuation proposals, tool failures, and validation references. Invalid, empty, or partial submissions SHALL be stored with a disposition and next action rather than silently dropped.

#### Scenario: Worker returns an empty result

- **WHEN** an attempt returns no observation or diagnostic
- **THEN** the coordinator records empty_submission, applies a bounded no-progress penalty, and selects retry or method switch

#### Scenario: Worker output has one malformed observation

- **WHEN** only part of a submission validates
- **THEN** valid portions remain tied to the attempt, malformed portions are rejected with field errors, and the Slot cannot close from the partial result alone

### Requirement: Consequential review is independent of production

For adversarial and validation actions, the coordinator SHALL bind the review to a distinct worker, method, or evaluator identity and SHALL reject a self-review as independent evidence. Review SHALL verify the required evidence refs and current oracle lineage; anchor presence alone is insufficient for a validation action.

#### Scenario: A worker submits and reviews the same validation result

- **WHEN** the producer and reviewer identities are equal
- **THEN** the result remains submitted but non-independent and a successor review is scheduled

### Requirement: Workers checkpoint evidence-bearing analysis before completion

A worker SHALL persist SourceCapture refs as material is acquired and SHALL commit a bounded AnalysisCheckpoint before `worker_finished`. The checkpoint SHALL include scope, source refs, extracted facts, hypotheses with status, contradictions, unresolved questions, failed methods, completed actions, and successor proposals. It SHALL exclude full prompts, secrets, and private chain-of-thought.

#### Scenario: Worker tries to finish with unsaved sources

- **WHEN** a terminal worker event lacks the required capture and checkpoint refs for successful acquisitions
- **THEN** the event is rejected as incomplete and the attempt remains resumable

#### Scenario: Worker stops after a partial analysis

- **WHEN** a provider failure, cancellation, or crash occurs after one or more durable checkpoints
- **THEN** the coordinator preserves the partial artifacts and dispatches a successor with exact refs and remaining obligations

### Requirement: Successor workers resume before reacquiring

Before scheduling duplicate acquisition, the coordinator SHALL expose reusable SourceCaptures, AcquisitionReceipts, AnalysisCheckpoints, and accepted partial observations from predecessor attempts and SHALL record why any reusable artifact is rejected or reacquired.

#### Scenario: Successor can continue from a valid checkpoint

- **WHEN** the prior capture digest and checkpoint schema validate under current permissions
- **THEN** the successor starts from those refs and rediscovery burden is recorded if it repeats the same acquisition

### Requirement: Scheduler ticks detect no progress and replan

Each scheduling tick SHALL persist frontier size, open P0 obligations, last realized-delta vector, active leases, stale attempts, and selected/rejected actions. Repeated no-change ticks SHALL trigger method switch, recovery, or explicit blocker according to a registered policy.

#### Scenario: Several rounds repeat the same evidence

- **WHEN** the no-change threshold is reached while a P0 obligation remains
- **THEN** the scheduler changes method or records an authority blocker and never emits completion merely because the queue is drained
