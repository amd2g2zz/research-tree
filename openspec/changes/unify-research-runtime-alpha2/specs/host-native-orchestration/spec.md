## ADDED Requirements

### Requirement: Host-native capabilities are probed and persisted
The system SHALL probe and persist support for native dynamic workflows, dynamic delegation, parallel children, lifecycle hooks, background execution, durable resume, scheduled drain, and structured event transport before selecting a host execution plan.

#### Scenario: A declared capability is unavailable at runtime
- **WHEN** a host advertises dynamic workflows but the probe or first invocation fails
- **THEN** the coordinator records the failure and selects the registered fallback without losing the active action or claiming host parity

### Requirement: Native workflows are non-authoritative projections
A host-native workflow SHALL be created from current coordinator actions and SHALL reference the run revision, strategy revision, action ids, phase ids, child attempt ids, permission profile, and checkpoint contract. It SHALL NOT close a Decision Slot, approve readiness, or complete the run.

#### Scenario: Native workflow finishes all phases
- **WHEN** Claude Code, Codex, or Hermes reports its local workflow complete
- **THEN** the adapter submits produced artifact refs and lifecycle events and the coordinator independently selects the next canonical action

#### Scenario: Strategy changes while a workflow is active
- **WHEN** new evidence invalidates the strategy revision projected into a native workflow
- **THEN** remaining projected phases are cancelled, quarantined, or marked stale and a successor projection is built from the new strategy

### Requirement: Dynamic execution follows research state
The adapter SHALL use supported host-native dynamic workflow features to fan out independent acquisition, fan in typed artifacts, add deepening or validation phases, retry recoverable failures, and resume from durable checkpoints as coordinator decisions change.

#### Scenario: First research phase is relevant but shallow
- **WHEN** post-batch assessment selects deepen or validate
- **THEN** the active native workflow adds or schedules the corresponding phase without requesting routine human approval

### Requirement: A host-neutral fallback preserves semantics
Every native workflow operation SHALL have a registered host-neutral fallback based on coordinator scheduling and Host Events. Capability absence may reduce concurrency or convenience but SHALL NOT remove source capture, checkpoint, evidence, closure, or completion obligations.

#### Scenario: Dynamic workflows are unsupported
- **WHEN** a host probe reports native_dynamic_workflow=false
- **THEN** the coordinator executes equivalent actions through bounded worker dispatch and produces the same canonical artifacts and terminal guards

### Requirement: Native workflow continuity is observable and recoverable
The system SHALL persist native workflow identity, phase and child identities, action refs, capability digest, start/resume/end events, source/checkpoint refs, stale projections, and reconciliation outcomes without storing private prompts or chain-of-thought.

#### Scenario: Host process restarts during a dynamic phase
- **WHEN** the runtime resumes with an unfinished native workflow
- **THEN** reconciliation classifies each child as active, completed, unknown, or stale and resumes from the last durable coordinator checkpoint
