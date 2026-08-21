## ADDED Requirements

### Requirement: Codex child identities bind through observed hooks
The adapter SHALL accept a Codex child `agent_id` binding only when that identity appears in the project's observed hook event stream for the run, the task attempt is running, and the identity is not already bound. Caller-invented identities MUST be rejected.

#### Scenario: Observed Codex identity binds
- **WHEN** a Codex SubagentStart hook observation carries a well-formed agent identity for a running attempt
- **THEN** bind-agent records the binding with session/causation identifiers

#### Scenario: Unobserved identity is rejected
- **WHEN** a caller supplies an agent identity absent from the observed hook stream
- **THEN** binding fails closed with a stable error

#### Scenario: Identity reuse is rejected
- **WHEN** an agent identity already bound to one attempt is offered for another
- **THEN** the rebinding is rejected without mutating either attempt

### Requirement: Codex hook events preserve bindable identities
The lifecycle hook SHALL extract allowlist-sanitized child identities (`agent_id`, `session_id`, `turn_id`, `causation_id`) from Codex `SubagentStart`/`SubagentStop` payloads, record `binding_status` candidacies, and never serialize free text from those payloads.

#### Scenario: SubagentStart identity recorded
- **WHEN** a Codex SubagentStart payload carries well-formed identity keys
- **THEN** the hook record contains them plus a binding candidacy status and no task text

#### Scenario: Malformed identity dropped
- **WHEN** an identity key holds a non-string or oversized value
- **THEN** the hook omits it rather than coercing

### Requirement: Parent interruption resolves as unknown with fresh retries
When the Codex parent session stops with active attempts, the adapter MUST mark those attempts `unknown_outcome`, preserve verified siblings, and re-dispatch unresolved work with a fresh attempt ID via a `retry` event. Stop and cancellation MUST NOT become success.

#### Scenario: Stop with active attempts
- **WHEN** the parent Stop hook fires while attempts are running
- **THEN** each active attempt records unknown_outcome and no completion

#### Scenario: Retry uses a fresh attempt
- **WHEN** unresolved work is re-dispatched
- **THEN** the retry event references the old attempt via retry_of and carries a new attempt ID

### Requirement: Live collaboration receipt is source-bound and isolated
The two-task in-session collaboration receipt MUST record actual child IDs, distinct Finding Packs, hook sequence, ledger rows, and host/package/model/environment fingerprints, produced in a Docker envelope or under an explicitly reviewed isolation deviation.

#### Scenario: Receipt carries real identities
- **WHEN** the live collaboration run completes
- **THEN** the sanitized receipt distinguishes two actual child identities and their bound attempts

#### Scenario: Unbindable surface stops the lane
- **WHEN** the capability probe confirms no bindable child ID exists on the active surface
- **THEN** a blocker receipt is posted, the issue stays open, and no delivery PR is created
