## ADDED Requirements

### Requirement: Canonical entity envelopes are exact and versioned

Every canonical run, artifact revision, Decision Slot, work item, action attempt, Evidence Artifact, OracleRun, HostEvent, readiness record, delivery artifact, and acceptance record SHALL use a versioned envelope with the exact fields `schema_version`, `kind`, `id`, `run_id`, `revision`, `created_at`, `actor`, `status`, `payload`, `parent_refs`, and `content_hash`.

`schemas/host-event-v1.json` is the host wire payload carried inside the canonical
HostEvent entity envelope; its protocol fields are not a second persistence schema
or lifecycle authority.

The validator MUST reject missing or extra fields, invalid identifiers, non-UTC timestamps, non-finite numbers, unresolved parent references, and a digest that does not equal canonical UTF-8 JSON of the envelope body. Canonical JSON is UTF-8 without BOM, NFC-normalized strings, lexicographically sorted object keys, no insignificant whitespace, and finite JSON numbers; `content_hash` is SHA-256 of that representation with the `content_hash` member omitted. No serializer may use UTF-8-SIG.

#### Scenario: Implementer submits a partial entity

- **WHEN** an entity omits `actor`, `parent_refs`, or `content_hash`
- **THEN** the canonical ingestion API rejects it with a stable machine-readable error code
- **AND** no revision or event is committed

#### Scenario: Entity schema is upgraded

- **WHEN** a future schema version is encountered
- **THEN** the runtime either invokes a registered lossless migrator or returns `unsupported_schema_version`
- **AND** it never silently interprets the payload as the current schema

### Requirement: Run lifecycle is a closed transition system

The coordinator SHALL implement and publish the only allowed transitions among `alignment`, `handoff_pending`, `autonomous_research`, `synthesis`, `readiness`, `delivery_pending`, `awaiting_acceptance`, `completed`, `paused`, `blocked`, `superseded`, `authority_blocked`, and `failed`.

The authoritative transition data is `registries/lifecycle-matrix-v1.json`; prose
cannot add an edge. The current lifecycle revision, state digest, and unresolved
obligation set are committed in the same SQLite transaction as the transition event.

Each transition MUST declare preconditions, emitted event kind, state digest update, allowed actor, and the next legal actions. A transition not in the published matrix MUST fail without mutation.

#### Scenario: Worker wave finishes with open obligations

- **WHEN** a host reports every dispatched attempt finished while a P0 Slot, oracle, readiness gate, or delivery acceptance is open
- **THEN** the run remains in a non-terminal state and persists the unmet obligation and next action

#### Scenario: Completion is requested twice

- **WHEN** `complete` is called for a completed or superseded run
- **THEN** the second call returns an idempotent terminal result with the original completion revision
- **AND** it does not append a second completion transition

### Requirement: Decision Slot and work contracts are executable

Each Decision Slot SHALL define `slot_id`, `priority`, `question`, `decision_consequence`, `options`, `required_evidence_classes`, `required_oracles`, `fallback`, `reversal_condition`, `status`, and exact lineage references. Each Work Item SHALL define `work_item_id`, `slot_id`, `action_kind`, `objective`, `inputs`, `method`, `expected_output`, `success_oracle`, `dependencies`, `permission_profile`, `attempt_policy`, and `completion_evidence`.

Allowed Slot statuses SHALL be `open`, `researching`, `contested`, `conditionally_closed`, `closed`, `blocked`, or `superseded`; allowed Work Item statuses SHALL be `pending`, `leased`, `running`, `submitted`, `verified`, `retryable`, `unknown`, `rejected`, `deferred`, `completed`, or `superseded`.

#### Scenario: Work item has no success oracle

- **WHEN** dispatch compilation receives a Work Item without an executable or explicitly human-only oracle and closure consequence
- **THEN** dispatch is rejected as `unverifiable_work_item`

#### Scenario: A closed Slot is modified

- **WHEN** a new finding targets a closed Slot without a feedback or supersession lineage
- **THEN** the finding is stored as evidence but cannot mutate the closed decision
- **AND** the coordinator creates a same-round replan or successor round according to the impact policy

### Requirement: Attempts, leases, and host events are idempotent

Every external attempt SHALL have a unique `attempt_id`, an immutable dispatch payload hash, a lease owner, lease expiry, retry ordinal, and an idempotency key. Host event ingestion MUST be atomic on `(run_id, event_id)` and MUST bind the event to the active `attempt_id` and expected ledger revision.

#### Scenario: Duplicate submission is retried

- **WHEN** a host resubmits an event with the same event id and payload hash
- **THEN** ingestion returns the original result without duplicating findings or transitions

#### Scenario: Same event id has a different payload

- **WHEN** an event id is reused with a different payload hash
- **THEN** ingestion fails with `event_id_conflict` and marks the run for audit

#### Scenario: Lease expires during a crash

- **WHEN** an attempt lease expires without a terminal event
- **THEN** recovery marks it `unknown`, records the lease evidence, and forbids treating the old attempt as successful

### Requirement: Canonical execution stages are revision-bound transactions

The coordinator SHALL expose stage commands for `dispatch`, `ingest`,
`synthesize`, `converge`, `readiness`, and `successor-work`. Every command
MUST receive `run_id`, `expected_revision`, an idempotency identity, and exact
artifact references for every previously persisted input. An exact artifact
reference contains `run_id`, `artifact_id`, positive `revision`, and
`content_hash`; a bare id, latest-revision lookup, host-local path, or inline
replacement payload is not sufficient.

Each command SHALL validate all inputs before its first write, start one
`BEGIN IMMEDIATE` transaction, and atomically commit the complete stage write
set:

- `dispatch` resolves one current Work Item and Blueprint Target, verifies its
  dependencies, permission profile, executable success oracle, and current
  strategy authority, then commits the immutable dispatch identity, Attempt
  Lease, run revision, revision snapshot, and `action_dispatched` event;
- `ingest` binds one Finding Pack to the exact active attempt, Work Item,
  Blueprint Target, Evidence Artifacts, and OracleRuns, applies the existing
  Finding Pack semantic validator, then commits the artifact, attempt
  disposition, run revision, revision snapshot, and `finding_ingested` event;
- `synthesize` consumes an explicit ordered set of accepted Finding Pack refs,
  invokes the canonical InsightDigest producer, and commits the digest and
  `batch_checkpoint` transition together;
- `converge` applies the existing Decision Ledger validator to exact Blueprint
  Target, Finding Pack, InsightDigest, and prior decision refs, commits each
  immutable decision revision, recomputes closure consequences, and commits a
  ConvergenceRecord plus either `all_slots_closed` or `closure_deficit`;
- `readiness` invokes the existing ReadinessVerifier over exact current
  lineage and commits the ReadinessRecord, obligation disposition, and either
  `readiness_passed` or `readiness_deficit` together; and
- `successor-work` commits deterministic Work Items whose ids are derived from
  an exact ConvergenceRecord or ReadinessRecord deficit, contradiction, failed
  oracle, method limitation, or readiness diagnostic. A successor never
  overwrites its trigger or prior Work Item. A transition event, host-local
  queue, or inline diagnostic cannot replace the exact trigger artifact.

The stage transaction SHALL roll back its artifact, attempt update, lifecycle
or obligation update, revision snapshot, and accepted event together. A retry
with the same idempotency identity and identical input digest SHALL return the
committed result without adding a revision or event. Reuse with different
inputs SHALL fail as `idempotency_conflict`. A stale expected revision SHALL
fail before semantic compilation and without mutation.

#### Scenario: Dispatch loses the database race

- **WHEN** two dispatch requests name the same expected run revision
- **THEN** exactly one commits an Attempt Lease and `action_dispatched` event
- **AND** the other fails as `stale_revision` without an orphan attempt

#### Scenario: Finding ingestion crashes after artifact insertion

- **WHEN** a fault is injected after the Finding Pack row but before the
  attempt disposition, revision snapshot, or event is written
- **THEN** reopening the ledger exposes none of that stage's writes
- **AND** retrying the same ingestion identity commits exactly once

#### Scenario: Synthesis still exposes a decision deficit

- **WHEN** the InsightDigest contains an uncovered, contested, thin, or
  qualified P0 Slot
- **THEN** convergence returns to `autonomous_research` through
  `closure_deficit` and commits evidence-linked successor Work Items
- **AND** an empty host queue cannot substitute for those items

#### Scenario: Synthesis checkpoint races an active attempt

- **WHEN** any canonical attempt remains `leased` or `running`
- **THEN** the `synthesize` stage returns `batch_incomplete` without mutation
- **AND** a host-local empty queue or worker-count observation cannot override the guard

#### Scenario: InsightDigest is superseded

- **WHEN** the run already has an active InsightDigest
- **THEN** the next `synthesize` stage requires its exact artifact reference
- **AND** commits the old digest as an immutable parent of the successor rather than overwriting it

#### Scenario: Readiness validator reports a deficit

- **WHEN** the exact current package fails any required readiness gate
- **THEN** the ReadinessRecord and targeted successor Work Items are retained
  as evidence, the run returns to `autonomous_research`, and no delivery
  obligation is satisfied

### Requirement: Coordinator APIs and CLI commands are stable

The implementation SHALL expose a Python coordinator API and JSON CLI commands using the canonical form research-tree run <verb> for init, status, next, ingest, retry, recover, explain, why-action, why-not-complete, replay, reconcile-host, deliver, accept, supersede, and export-audit. Flat run-<verb> names and existing observability names may remain aliases but SHALL route to the same coordinator operation. Every command MUST document required inputs, output schema, exit codes, and whether it mutates state.

`research-tree run init` SHALL be the canonical transition from persisted
alignment state into autonomous research. It MUST receive the exact current
`AlignmentHandoff` and `BlueprintTarget` artifact references plus the expected
run revision. A caller cannot initialize autonomous research from task text,
an adapter checkpoint, a generic acknowledgement, or an unpersisted payload.
The low-level run-row creation API is an alignment bootstrap and migration
boundary only; it is not autonomous initialization.

Before changing lifecycle state, the coordinator SHALL resolve both artifacts,
verify their content hashes and statuses, verify that the handoff contains a
human confirmation bound to the displayed strategy digest, and verify that the
initial Blueprint Target has exact parent lineage to that handoff, its Working
Brief, and its Intent Model. Initialization advances through the published
`alignment_projection_ready` and `handoff_confirmed` transitions and binds the
Blueprint Target. Repeating the same request after any committed prefix SHALL
resume or return the same final state without duplicating transitions or
bindings; a different reference or digest SHALL fail without rewriting prior
state.

#### Scenario: Confirmed alignment initializes autonomous research

- **WHEN** `run init` receives current exact handoff and Blueprint Target refs
  whose confirmation and parent lineage validate
- **THEN** the coordinator enters `autonomous_research`, binds the exact active
  Slot set, and records the lifecycle and binding events

#### Scenario: Blueprint Target is not derived from the confirmed handoff

- **WHEN** the target omits or changes the handoff, Working Brief, or Intent
  Model parent revision
- **THEN** initialization fails with `blueprint_lineage_invalid`, leaves the
  lifecycle and binding unchanged, and records no successful handoff

Existing `create-round`, `show-round`, and `tree-*` commands SHALL either become thin compatibility aliases to the coordinator or fail with an explicit migration message; they SHALL not maintain an alternate completion authority.

The canonical JSON result envelope SHALL use these exit codes: `0` for a committed or idempotent success, `2` for invalid input, `3` for stale revision or optimistic-concurrency conflict, `4` for a persisted blocked or unresolved obligation, `5` for retryable provider or tool failure, `6` for permission or safety denial, `7` for integrity or digest failure, `8` for unsupported schema or protocol version, `9` for canonical-store unavailability, and `10` for a terminal rejection, supersession, or authority block. The JSON body SHALL always include `code`, `category`, `retryability`, `run_id`, `safe_message`, `unmet_obligations`, `evidence_refs`, and `next_action` when applicable.

#### Scenario: CLI is called with an invalid revision

- **WHEN** a command receives a stale revision, unknown event, or unresolved artifact reference
- **THEN** it exits non-zero, emits a stable error code in JSON, and leaves the ledger unchanged

#### Scenario: Operator resumes after restart

- **WHEN** `recover` is run repeatedly against the same workspace
- **THEN** it produces the same canonical state digest and a bounded list of newly reconciled attempts

### Requirement: Persistence and projection boundaries are explicit

SQLite SHALL be the sole canonical state store. Content-addressed files, generated reports, traces, and host projections MUST be referenced by digest and revision from the ledger and MUST be rebuildable or disposable according to their registered class.

#### Scenario: A projection file is deleted

- **WHEN** a rebuildable host projection or cached frontier file is removed
- **THEN** the coordinator reconstructs it from SQLite and CAS without changing semantic state

#### Scenario: Canonical ledger is unavailable

- **WHEN** an adapter can only see a stale local projection
- **THEN** it cannot emit a completion claim and reports `canonical_store_unavailable`
