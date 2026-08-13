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

### Requirement: Coordinator APIs and CLI commands are stable

The implementation SHALL expose a Python coordinator API and JSON CLI commands using the canonical form research-tree run <verb> for init, status, next, ingest, recover, explain, why-action, why-not-complete, replay, reconcile-host, deliver, accept, supersede, and export-audit. Flat run-<verb> names and existing observability names may remain aliases but SHALL route to the same coordinator operation. Every command MUST document required inputs, output schema, exit codes, and whether it mutates state.

Legacy round, tree, and profile commands SHALL be removed from the published CLI without an alias, refusal response, migration message, or alternate completion authority.

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
