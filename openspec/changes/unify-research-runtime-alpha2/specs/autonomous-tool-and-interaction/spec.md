## ADDED Requirements

### Requirement: Heterogeneous inputs enter a typed context inventory

The runtime SHALL ingest user text, repositories, source files, documents, images, URLs, and experiment outputs as typed input records with locator, permission, media type, digest, acquisition status, parser status, and limitations before they can influence a Decision Slot.

#### Scenario: Image evidence cannot be parsed

- **WHEN** an image is available but the configured extractor fails
- **THEN** the input remains visible with `unparsed` status and a bounded alternate extraction action
- **AND** no visual claim is treated as verified

#### Scenario: User gives only a vague sentence

- **WHEN** intake has insufficient detail to define a safe strategy
- **THEN** the agent records hypotheses and blind spots, performs bounded reconnaissance where agent-verifiable, and asks one open question rather than finalizing a brief

### Requirement: Every action declares capability and permission boundaries

Each Work Item and HostEvent SHALL carry a permission profile naming allowed read roots, write roots, network/search capability, code-execution capability, secret policy, tool timeout, and safety tier. Adapters MUST reject a dispatch that exceeds the confirmed envelope.

#### Scenario: A worker needs public documentation

- **WHEN** a research action encounters an unknown API or tool behavior
- **THEN** it may use an allowed documentation/search capability, record the source and failure history, and continue with an alternate method before raising a blocker

#### Scenario: An action requests an out-of-bound write

- **WHEN** a worker attempts to write outside its declared artifact workspace
- **THEN** the host denies the action, emits a sanitized policy violation event, and leaves the canonical run non-complete

### Requirement: Self-directed uncertainty handling is a bounded loop

After handoff, an agent SHALL handle uncertainty through the ordered loop `inspect -> search/learn -> try alternate method -> validate -> record blocker or request authority`, with each iteration bound to a Work Item, attempt, evidence reference, and stop reason.

#### Scenario: First tool fails

- **WHEN** a tool returns an error or empty result
- **THEN** the agent records the failure, searches permitted documentation or local references, selects a distinct method, and retries within the attempt policy

#### Scenario: All permitted methods fail

- **WHEN** the bounded method set is exhausted
- **THEN** the agent records an evidence-backed blocker, residual uncertainty, attempted methods, and the next human-authority decision; it does not claim ignorance as completion

### Requirement: Alignment communication uses an internal strategy state

Before every user-facing alignment turn, the runtime SHALL persist the pending action, current belief digest, unresolved gaps, evidence basis, expected information gain, cognitive-load estimate, and reason for selecting the next prompt. It SHALL emit at most one open prompt and SHALL not ask a batch of independent questions.

#### Scenario: Several gaps are open

- **WHEN** more than one unresolved gap is present
- **THEN** the planner ranks them by decision consequence and expected ambiguity reduction
- **AND** it keeps the remaining gaps internal until a later turn

#### Scenario: User answer changes a premise

- **WHEN** a response contradicts the displayed belief digest
- **THEN** the runtime appends a new belief revision, invalidates affected strategy projections, and recalculates the next action

### Requirement: Handoff and autonomy envelopes are explicit

The handoff artifact SHALL record the confirmed objective, scope, non-goals, authority boundary, safety boundary, delivery contract, success oracles, unresolved assumptions, escalation conditions, and strategy digest. Autonomous execution MAY change methods and hypotheses but MUST NOT change those hard fields without feedback lineage.

#### Scenario: Agent discovers a better research direction

- **WHEN** a new direction is within the confirmed objective and improves an open closure deficit
- **THEN** the agent may grow a local action branch and records the triggering evidence

#### Scenario: Agent wants to change the objective

- **WHEN** a proposed action changes scope, authority, safety, or success definition
- **THEN** execution pauses at an authority boundary and requests a successor-round decision

### Requirement: Stop, growth, pruning, and penalty decisions are inspectable

Every frontier decision SHALL record parent reference, trigger evidence, expected gain components, realized delta vector, branch complexity, depth, penalty components, mandatory flag, pruning reason if any, and the selected closure or continuation oracle. A scalar score alone is insufficient.

#### Scenario: First research transition has no prior evidence

- **WHEN** the initial baseline is established
- **THEN** realized evidence delta is exactly zero and baseline provenance is recorded

#### Scenario: Frontier is empty but closure is incomplete

- **WHEN** all optional branches are pruned or deferred while a mandatory deficit remains
- **THEN** the runtime emits `frontier_exhausted_with_obligation` and selects a method switch, recovery, or authority boundary

### Requirement: Operational limits pause rather than terminate research

The runtime SHALL model wall-clock, context, concurrency, provider, tool, and storage limits as resumable checkpoints with explicit reason, owner, expiry, and resume action. Monetary cost SHALL NOT be a completion condition.

#### Scenario: Context compaction is required

- **WHEN** the host context approaches its configured limit
- **THEN** the runtime persists a compacted digest and resumes from canonical state without silently dropping unresolved obligations
