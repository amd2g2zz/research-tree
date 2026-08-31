## ADDED Requirements

### Requirement: Delegation identities bind to exactly one canonical attempt
The Hermes bridge SHALL capture actual `delegation_id`, `task_id`, and `child_id` from observed hook events and MUST bind each child identity to exactly one canonical attempt issued by the coordinator. Caller-supplied identities that never appear in the observed event stream MUST be rejected.

#### Scenario: Observed identity binds
- **WHEN** a real delegation batch's hook stream contains a child identity for a dispatched attempt
- **THEN** the bridge binds that identity to the attempt and subsequent artifacts reference the binding

#### Scenario: Invented identity is rejected
- **WHEN** a caller supplies a delegation/task/child identity that does not appear in observed hook events
- **THEN** the bridge fails closed and no canonical event or artifact references it

#### Scenario: Identity reuse is rejected
- **WHEN** a child identity already bound to one attempt is offered for a second attempt
- **THEN** the bridge rejects the rebinding without mutating either attempt

### Requirement: Finding Pack admission fails closed
The `record-batch` path MUST verify each Finding Pack exists inside the workspace, is non-empty, parses as an object, matches its declared digest, and has attempt ancestry matching the bound attempt, before recording it. Missing, empty, schema-invalid, modified, or cross-attempt packs MUST be rejected.

#### Scenario: Valid pack is recorded as observation
- **WHEN** a Finding Pack for a bound attempt is present, intact, and ancestry-matched
- **THEN** record-batch records a non-authoritative observation referencing it

#### Scenario: Modified pack is rejected
- **WHEN** a Finding Pack's content no longer matches its declared digest
- **THEN** record-batch exits nonzero with a stable message and records nothing

#### Scenario: Cross-attempt pack is rejected
- **WHEN** a Finding Pack's attempt ancestry names a different attempt than the batch's bound attempt
- **THEN** record-batch rejects the batch

### Requirement: Interrupted children recover with a fresh attempt
When one child of a delegation batch is interrupted, the bridge MUST mark that attempt `unknown_outcome` (reason `interrupted_child`) and re-dispatch the unresolved task as a new attempt with a `retry` event referencing the old attempt, while the verified sibling attempt retains its accepted state. Cancellation and provider failure MUST NOT become success.

#### Scenario: Sibling survives interruption
- **WHEN** one of two children is interrupted after the other completed and verified
- **THEN** the interrupted attempt is unknown, a fresh retry attempt is created, and the sibling stays accepted

#### Scenario: Provider failure stays non-success
- **WHEN** a provider failure terminates a child
- **THEN** the attempt records provider_failure/unknown_outcome and never a completion

#### Scenario: Non-completed status never finishes a worker
- **WHEN** an observed child status is anything other than exactly `completed` (cancelled, failed, error, timeout, interrupted, or absent)
- **THEN** the bridge emits unknown_outcome for that attempt and never worker_finished

#### Scenario: Surplus observations fail closed
- **WHEN** the observed hook stream carries more children than the wave declares attempts
- **THEN** the bridge rejects the wave instead of rebinding stale observations from earlier waves

### Requirement: Pinned dependencies install run-locally before start
Hermes dependency setup MUST install the pinned AnySearch revision (v2.1.0, `6ff6aa958ad9747659d669b5e9984f07c896f2aa`) into run-local `HERMES_HOME/skills/anysearch` before Hermes starts, verify revision and payload digest, be idempotent, and fail closed on drift. Global Hermes config MUST NOT be mutated and no host bind mount may substitute for the install.

#### Scenario: Idempotent verified install
- **WHEN** dependency setup runs twice into the same run-local home
- **THEN** the second run reports installed status with the same revision/digest and performs no destructive change

#### Scenario: Drift fails closed
- **WHEN** the installed payload digest differs from the pinned manifest
- **THEN** setup fails closed rather than starting Hermes against the drifted dependency

### Requirement: Hook identity propagation preserves sanitization
The Hermes runtime hook SHALL record delegation lifecycle identity fields (`attempt_id`, `action_id`, `causation_id`, `tool_call_id`, `child_subagent_id`, `child_session_id`, `turn_id`) from allowlisted payload keys and environment fallbacks, mapping `child_subagent_id` to a recorded `agent_id`. Non-identifier values MUST be dropped, and the 1 MiB input bound, event whitelist, and free-text suppression MUST remain unchanged.

#### Scenario: Identity passes through allowlist
- **WHEN** a delegate_task hook payload carries well-formed identity keys
- **THEN** the recorded event contains them (with the agent_id/causation_id mappings) and no task text

#### Scenario: Malformed identity is dropped
- **WHEN** an identity key holds a non-string or non-identifier value
- **THEN** the hook omits it rather than coercing or failing

### Requirement: Live evidence is Docker-isolated and source-bound
The two-child lifecycle/recovery receipt MUST be produced inside a Docker envelope from the official Hermes image with the resolved digest recorded, ephemeral run-local state, dependency setup before start, and no repository mount for provider smoke. A bare-local receipt is not acceptance evidence.

#### Scenario: Receipt carries envelope digests
- **WHEN** the live run completes
- **THEN** the sanitized receipt records image digest, config digest, dependency digest, actual identities, redacted commands, and exit codes sufficient for clean-environment replay
