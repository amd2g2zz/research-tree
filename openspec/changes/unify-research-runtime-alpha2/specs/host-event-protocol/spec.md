## ADDED Requirements

### Requirement: Host events use one versioned semantic envelope
The system SHALL represent dispatch, attempt start, finding submission, review completion, provider failure, unknown outcome, retry request, worker completion, and non-authoritative run-completion claims with a versioned envelope containing run, round, Decision Slot, action, attempt, host, event identity, and expected ledger revision.

The wire object validated by `schemas/host-event-v1.json` is embedded as the
canonical entity envelope payload. Storage adds the common entity fields and
content hash; adapters never persist the wire object as an independent state store.

#### Scenario: Duplicate worker completion is delivered
- **WHEN** the same host event identity is received more than once
- **THEN** ingestion is idempotent and no artifact or state transition is duplicated

#### Scenario: Event targets a stale revision or attempt
- **WHEN** a host event references a superseded attempt or stale expected revision
- **THEN** the event is rejected or recorded as stale without mutating current canonical state

### Requirement: Compatibility identifiers map without creating a second authority

HostEvent may carry round_id for alpha1 compatibility, but the coordinator SHALL resolve it to the canonical run_id and active lineage revision before validation. A mismatched round_id/run_id pair is rejected; round_id alone can never select or mutate canonical state.

#### Scenario: Legacy adapter sends only round_id

- **WHEN** an alpha1-compatible event lacks run_id but names a registered round_id
- **THEN** the compatibility translator resolves the pair through the migration map and emits a canonical event with both identifiers
- **AND** the original event remains attached as imported evidence

### Requirement: Host adapters are execution translators only
The system SHALL allow Codex, Claude Code, and Hermes adapters to dispatch native work and translate lifecycle events, but SHALL prohibit them from issuing closure tokens, readiness verdicts, delivery verification, or run completion.

Adapter-local vocabulary SHALL distinguish `all_tasks_verified` or
`wave_verified` from canonical completion. A delivery candidate projection may
be marked `delivery_pending`, but neither report presence nor byte count,
heading count, an empty frontier, or a completed worker wave may produce
`complete`. Legacy adapter `complete` commands SHALL fail with an explicit
migration action instead of preserving a second completion authority.

#### Scenario: Native adapter has completed all local tasks
- **WHEN** the adapter-local task projection has no remaining work
- **THEN** it reports worker events to the coordinator and does not mark the canonical run complete

#### Scenario: A legacy adapter requests completion

- **WHEN** Codex, Claude Code, Hermes, or recursive-search compatibility code attempts to complete a run from local state
- **THEN** the request is rejected or projected as `delivery_pending`
- **AND** only the coordinator may evaluate exact delivery acceptance and enter `completed`

The repository SHALL ship an executable completion-authority audit covering
canonical source, all generated host packages, hooks, and compatibility
adapters. The audit SHALL fail when a non-coordinator surface writes canonical
lifecycle completion or derives a completion claim from local task/report
proxies. Local task status named `completed` is permitted only when the owning
object is explicitly a task or attempt rather than a ResearchRun.

### Requirement: Host-specific interaction preserves shared alignment semantics
The system SHALL use each platform's available conversation and delegation features without turning a multiple-choice tool, hook, goal judge, or visible plan into the authority for intent or completion.

#### Scenario: Host question tool cannot express an open prompt
- **WHEN** a native question tool requires preset choices that would constrain intent elicitation
- **THEN** the adapter uses an ordinary conversational open question while preserving the canonical pending alignment attempt

### Requirement: Provider failures are durable and retryable
The system SHALL record provider and model identity, retry category, opaque error code, attempt identity, and safe gateway-log reference while excluding raw sensitive diagnostics, and SHALL transition the attempt to retryable, unknown, or terminal failure rather than success.

#### Scenario: Provider fails after retries
- **WHEN** Hermes or another host reports provider exhaustion before a Finding Pack is submitted
- **THEN** the attempt remains incomplete, the run checkpoint remains resumable, and the coordinator selects retry, alternate provider, or method switch within authority

### Requirement: Hermes native features cannot weaken canonical gates
The system SHALL use Hermes delegation, goals, Kanban, and lifecycle hooks for execution continuity while treating hook and goal-judge outcomes as non-authoritative signals.

The Hermes adapter SHALL be a stateless translator in normal alpha2 execution.
It SHALL project one exact canonical Work Item and Attempt Lease into goal or
Kanban acceptance criteria, and SHALL translate bounded Hermes observations
back into HostEvents. It SHALL NOT persist batches, report manifests, delivery
status, lifecycle state, or another event ledger. Alpha1 `.research-tree-hermes`
state is read-only migration input and SHALL NOT be written by the alpha2 path.

Goal and Kanban acceptance criteria SHALL carry the canonical run, exact Work Item artifact revision and digest,
Decision Slot, action, attempt, expected revision, permission profile, expected
Finding Pack contract, evidence standard, closure oracle, retry policy, and a
statement that Hermes completion is non-authoritative. Missing or stale
canonical refs make the projection invalid.

Canonical attempt count SHALL project to Hermes task retry limits only. It
SHALL NOT be reused as a goal turn budget because reasoning turns and external
attempt identities have different semantics.

#### Scenario: Hermes hook fails open
- **WHEN** a lifecycle hook raises an error or is skipped
- **THEN** evidence, closure, and completion requirements remain unchanged and reconciliation detects any missing host event

Hermes hooks MAY touch a content-free operational wake-up marker. The marker
SHALL contain no task, attempt, evidence, provider, report, acceptance, or
completion data; it is neither a HostEvent nor replay authority. Missing,
stale, duplicated, or unwritable markers SHALL be semantically equivalent and
recovery SHALL use canonical state plus a fresh Hermes snapshot.

#### Scenario: Hermes goal judge reports success
- **WHEN** a goal judge or Kanban task reports success without an accepted Finding Pack and current OracleRun
- **THEN** the adapter emits a non-authoritative completion or worker observation
- **AND** the coordinator does not close the Decision Slot or complete the run

#### Scenario: Hermes projection is repeated
- **WHEN** the same canonical Work Item and Attempt Lease are projected again after restart
- **THEN** the adapter returns the same task identity and acceptance contract digest
- **AND** no adapter-local business state is created

### Requirement: Hermes recovery is ledger-led and policy-bounded

The system SHALL reconcile a fresh Hermes task/run snapshot against canonical
attempts after restart. A running, stale, missing, or ambiguous host outcome
without accepted output SHALL become `attempt_unknown`. A valid submitted
artifact SHALL be reviewable but not implicitly verified. Retry, alternate
provider, and method switch SHALL preserve the predecessor and create a new
attempt identity and dispatch digest according to the canonical AttemptPolicy
and confirmed authority.

Provider failure normalization SHALL retain provider/model identity, retry
category, bounded opaque error code, attempt identity, and a safe gateway-log
reference or digest. It SHALL reject raw provider messages, exception text,
response bodies, prompts, credentials, or gateway-log content.

#### Scenario: Retryable provider failure survives restart
- **WHEN** Hermes exhausts provider retries, the process restarts, and the canonical attempt has no accepted Finding Pack
- **THEN** recovery retains the failed predecessor, emits an unknown or retryable observation, and selects the next policy-authorized attempt
- **AND** the run remains non-terminal without human intervention

#### Scenario: Provider fallback is outside authority
- **WHEN** an alternate provider would violate the confirmed authority or permission profile
- **THEN** the adapter records an authority blocker and does not silently switch provider or downgrade the method

#### Scenario: Hook event is missing but host state changed
- **WHEN** a hook timed out or returned invalid JSON and a later Hermes snapshot differs from the canonical attempt
- **THEN** reconciliation emits `reconciliation_detected` and the required recovery event
- **AND** hook absence cannot satisfy evidence, closure, readiness, or completion

### Requirement: Cross-host semantic parity is testable
The system SHALL produce equivalent canonical artifacts and lifecycle outcomes when semantically equivalent event traces are executed through Codex, Claude Code, and Hermes.

#### Scenario: Equivalent fixture runs on three hosts
- **WHEN** each host submits the same evidence, oracle outcomes, and acceptance events under the shared protocol
- **THEN** the resulting Decision Ledger, closure tokens, readiness, and terminal state have matching semantic digests

### Requirement: Each event type has a defined payload and state effect

The protocol SHALL define and validate the payload and canonical state effect for every event type. The required payload minimums are:

- dispatch_requested: work item, permission profile, dispatch digest, and lease policy;
- attempt_started: worker identity, lease expiry, tool capability digest, and start timestamp;
- finding_submitted: Finding Pack digest, evidence refs, submission status, and output digest;
- review_completed: reviewer identity, accepted/rejected refs, field diagnostics, and review digest;
- provider_failed: provider/model identity, retry category, opaque code, and safe log ref;
- attempt_unknown: reconciliation reason, last heartbeat, and observed host state;
- retry_requested: predecessor attempt, method/provider change, and retry policy;
- worker_finished: terminal worker status and all produced artifact refs;
- completion_claimed: claim kind, claimed canonical state, safe source ref, and
  adapter-local status. Claim kind is one of `host_status`, `worker_status`,
  `hook_success`, `report_file`, `empty_frontier`, or `completed_wave`;
- acceptance_recorded: DeliveryAcceptance ref and displayed digest;
- reconciliation_detected: host observation, canonical observation, conflict class, and next action.

#### Scenario: Event payload omits a required field

- **WHEN** a host submits a valid envelope with an incomplete event-specific payload
- **THEN** ingestion returns a field-level protocol error and does not advance the ledger

#### Scenario: Event protocol version is unknown

- **WHEN** an event uses an unsupported protocol version
- **THEN** the adapter records it as quarantined evidence and returns unsupported_protocol_version without guessing a translation

#### Scenario: A local proxy claims run completion

- **WHEN** a host emits `completion_claimed` from local status, worker status,
  hook success, report existence, an empty frontier, or a completed wave
- **THEN** the coordinator stores the host observation and one idempotent
  `accepted=false` rejection with reason `completion_claim_rejected`
- **AND** the run revision, lifecycle state, state digest, and obligations remain unchanged

### Requirement: Causation and ordering are explicit

Every event SHALL carry a causation id, optional correlation id, emitted timestamp, sequence position, and expected revision. The coordinator SHALL distinguish duplicate, stale, out-of-order, conflicting, and orphan events.

#### Scenario: A finding arrives before attempt_started

- **WHEN** a finding event references an attempt with no accepted start event
- **THEN** it is retained as orphan evidence and cannot affect closure until reconciled
