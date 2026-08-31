## ADDED Requirements

### Requirement: Capability probes are honest, persisted, and deterministic
The system SHALL validate and digest explicit runtime observations for native dynamic workflows, dynamic delegation, parallel children, lifecycle hooks, background execution, durable resume, scheduled drain, and structured event transport before selecting an execution plan. Unknown, partial, denied, failed, and unavailable observations SHALL NOT be treated as available and SHALL select a registered bounded fallback.

#### Scenario: Advertised capability is absent or denied
- **WHEN** a host registry advertises a conditional surface but its runtime probe reports unavailable, partial, denied, failed, or unknown
- **THEN** the plan records that exact state and selects the host-neutral fallback without claiming parity

#### Scenario: Capability fails after a successful probe
- **WHEN** first invocation contradicts an available probe result
- **THEN** the adapter records a failure observation with a new digest and rebuilds the projection using its registered fallback

### Requirement: Native workflows are bounded non-authoritative projections
The system SHALL project canonical actions into a NativeWorkflowRun containing stable workflow and script identity, run and strategy revisions, action and phase identities, child attempt identities, permission profile, capability digest, checkpoint contract, explicit phase/child bounds, and fallback id. The projection MUST declare itself non-authoritative and MUST NOT close a Decision Slot, approve readiness, accept delivery, or complete the run.

#### Scenario: Host-local workflow reports completion
- **WHEN** a Claude workflow, Codex plan, or Hermes task/Kanban/goal surface has no remaining local work
- **THEN** the adapter emits observations and artifact refs with `complete=false` and leaves canonical completion to the coordinator evidence gates

#### Scenario: Projection exceeds a configured bound
- **WHEN** a workflow would exceed its maximum phases or child attempts
- **THEN** projection fails deterministically and persists a resumable recovery disposition instead of silently adding work

### Requirement: Host adapters preserve native execution semantics
The system SHALL map Claude Code dynamic phases and contradiction replans, Codex concurrent dependency-ready tasks and wait/completion observations, and Hermes batched delegation, restart recovery, and optional goal/Kanban/hook/scheduled-drain mirrors to the shared projection and HostEvent contracts. Missing host surfaces SHALL reduce convenience or concurrency only, not canonical obligations.

#### Scenario: Equivalent ready wave runs on three hosts
- **WHEN** Claude Code, Codex, and Hermes receive semantically equivalent canonical actions and capability observations
- **THEN** each projection retains the same action, checkpoint, evidence, and completion obligations while exposing only the native surfaces actually available on that host

#### Scenario: Hermes optional lifecycle surface is missing
- **WHEN** delegation is available but goals, Kanban, hooks, or scheduled drain are unavailable
- **THEN** Hermes uses bounded delegation plus checkpoint-backed recovery and records explicit fallbacks for each missing optional surface

### Requirement: Dynamic replan and resume preserve durable lineage
The system SHALL preserve workflow and script identity across a same-run replan or resume, increment projection revision, retain checkpoint refs, mark unfinished work from superseded strategy revisions stale, and append bounded successor phases bound to the current strategy.

#### Scenario: Claude phase discovers a contradiction
- **WHEN** accepted evidence invalidates the strategy revision during a Claude dynamic phase
- **THEN** unfinished projected phases become stale and the successor projection retains workflow/script identity and the contradiction event reference

#### Scenario: Host process restarts during delegated work
- **WHEN** Codex or Hermes resumes an unfinished workflow after restart
- **THEN** reconciliation uses the last durable checkpoint to classify each child as active, completed, unknown, or stale before any retry

### Requirement: Native lifecycle observations use canonical HostEvents
The system SHALL translate workflow start, resume, phase completion, checkpoint persistence, provider failure, cancellation or unknown outcome, retry request, and reconciliation into digest-bound HostEvents with required workflow, phase, child, capability, strategy, checkpoint, and successor fields. Raw prompts, chain-of-thought, credentials, and unsafe provider diagnostics MUST NOT be stored.

#### Scenario: Provider fails during a dynamic phase
- **WHEN** a provider failure, cancellation, crash, namespace limit, or permission limit interrupts a child attempt
- **THEN** a deterministic non-success HostEvent leaves durable recovery state and the coordinator selects retry, fallback, or replan within authority

#### Scenario: Host state conflicts with canonical state
- **WHEN** a resumed host reports a child completed but the canonical ledger lacks its required checkpoint or evidence refs
- **THEN** reconciliation records the conflict as unknown or stale and refuses completion

### Requirement: Native and fallback paths preserve canonical parity
The system SHALL prove that semantically equivalent native and fallback execution traces produce equivalent canonical action obligations, artifact refs, recovery classifications, and coordinator-only completion guards.

#### Scenario: Native workflow support is unavailable
- **WHEN** `native_dynamic_workflow` is not available for a host
- **THEN** `coordinator-dispatch-v1` executes the bounded actions and produces the same required checkpoint, evidence, and completion-gate semantics
