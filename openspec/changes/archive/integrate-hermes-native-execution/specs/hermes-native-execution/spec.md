## ADDED Requirements

### Requirement: Hermes observations use the canonical HostEvent protocol
The system SHALL translate Hermes delegation, lifecycle, provider failure, retry, and reconciliation observations into versioned digest-bound HostEvents with canonical run, action, attempt, revision, sequence, and actor lineage.

#### Scenario: Equivalent Hermes trace is deterministic
- **WHEN** the same canonical action and sanitized Hermes trace are translated more than once
- **THEN** the emitted semantic event ids and payload digests are identical and exact replay is idempotent

#### Scenario: Changed event reuse conflicts
- **WHEN** Hermes reuses an event id with a different sanitized payload or lineage
- **THEN** canonical ingestion rejects the conflict without lifecycle mutation

### Requirement: Provider diagnostics are bounded and sanitized
The system MUST persist only normalized provider/model identifiers, retry category, opaque error code, attempt number, and workspace-relative gateway-log reference from provider failures.

#### Scenario: Safe provider failure is retained
- **WHEN** a provider failure contains only whitelisted bounded fields and a normalized workspace-relative log reference
- **THEN** the translator emits a provider_failure HostEvent containing those fields

#### Scenario: Raw or unsafe diagnostics are rejected
- **WHEN** a provider observation contains raw messages, prompts, tokens, credentials, absolute paths, traversal, or unbounded diagnostic fields
- **THEN** the translator rejects or omits those fields and does not persist them as canonical evidence

### Requirement: Restart reconciles canonical attempts before retry
The system SHALL reconstruct active Hermes work from the canonical ledger and MUST record an unresolved running attempt as unknown outcome before dispatching a retry or coordinator-authorized method switch.

#### Scenario: Interrupted child becomes unknown before retry
- **WHEN** Hermes restarts with a canonical attempt that has dispatch/start evidence but no terminal observation
- **THEN** an unknown_outcome event is accepted before a retry event or replacement attempt is created

#### Scenario: Crash leaves no partial accepted prefix
- **WHEN** fault injection interrupts unknown-outcome and retry composition
- **THEN** replay produces either the complete ordered canonical event set or no newly accepted prefix

#### Scenario: Retry remains inside confirmed authority
- **WHEN** a retry or method switch is requested for an action not issued by the coordinator or outside the confirmed authority envelope
- **THEN** the request is rejected without creating a new attempt

### Requirement: Hermes goals Kanban and hooks are non-authoritative projections
The system SHALL project coordinator actions into replaceable Hermes goal/Kanban records with canonical ids and acceptance criteria, and MUST treat hooks as sanitized fail-open observability signals only.

#### Scenario: Projection can be rebuilt
- **WHEN** local Hermes goal/Kanban state is missing or stale after restart
- **THEN** it is reconstructed from canonical actions and attempts without changing canonical lifecycle state

#### Scenario: Host signals cannot complete research
- **WHEN** a hook succeeds or fails, a child exits, a card is done, the queue is empty, or local reports satisfy shape checks
- **THEN** no slot closure, readiness, delivery, acceptance, or run completion obligation is satisfied

### Requirement: Hermes converges with other hosts on canonical outcomes
For the same action, attempt, and sanitized observation fixture, Hermes and native host translators SHALL yield the same canonical Decision Ledger outcome even when provider retry timing differs.

#### Scenario: Cross-host retry fixture converges
- **WHEN** equivalent Codex/Claude and Hermes fixtures contain one retryable failure followed by accepted evidence
- **THEN** their canonical action/attempt terminal state and evidence lineage are equivalent while host-specific metadata remains observational

#### Scenario: Long-horizon retry resumes without human authority
- **WHEN** a retryable provider failure interrupts a confirmed long-horizon action
- **THEN** the coordinator can resume the bounded action after unknown-outcome reconciliation without human intervention or local completion claims
