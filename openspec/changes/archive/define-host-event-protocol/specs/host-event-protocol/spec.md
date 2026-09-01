## ADDED Requirements

### Requirement: Host events are strict, typed, and digest-bound

The runtime SHALL validate a versioned HostEvent envelope containing event id,
kind, run/round/slot/action/attempt bindings, expected revision, sequence,
actor, created time, payload, and payload digest. Event-specific payload
requirements SHALL be enforced beyond generic JSON shape, and unsupported
versions or digest mismatches SHALL be rejected.

#### Scenario: Payload digest is forged
- **WHEN** an event payload does not match its declared digest
- **THEN** validation rejects it without appending an event or changing run state

### Requirement: Host ingestion is replayable and non-authoritative

Accepted events SHALL be appended atomically with a non-terminal attempt or
reconciliation projection. Exact duplicate `(run_id,event_id,payload_digest)`
ingestion SHALL return the original result; changed reuse, stale revision,
unknown attempt, and out-of-order sequence SHALL be rejected or quarantined
without lifecycle mutation. Host events SHALL never issue closure, readiness,
delivery, acceptance, or completion authority.

#### Scenario: Equivalent event is replayed
- **WHEN** an identical event is ingested twice
- **THEN** the second call is idempotent and no second projection or transition is appended

### Requirement: Native adapters are thin equivalent translators

Codex and Claude adapters SHALL emit equivalent host-neutral envelopes for
equivalent traces and SHALL NOT persist local completion, report-gate, task
count, wave, or empty-work success state. Generated packages SHALL derive the
shared helper from one authoring source.

#### Scenario: Report file exists without canonical closure
- **WHEN** an adapter observes a report with sufficient bytes/headings
- **THEN** it emits an observation event and the coordinator remains non-terminal

### Requirement: Invalid events have bounded disposition

Invalid, unsupported, orphaned, or stale events SHALL produce a stable rejection
or explicit quarantine disposition that records the reason without advancing
canonical lifecycle or completion state. A crash after validation but before
commit SHALL leave no partially accepted event.

#### Scenario: Crash occurs during append
- **WHEN** the process fails before the event/projection transaction commits
- **THEN** replay sees neither half of the accepted pair and can retry safely
