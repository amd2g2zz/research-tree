## ADDED Requirements

### Requirement: the legal transition walk is enforced

CHAT→(confirm)DECOMPOSE→(sign)RESEARCH⟲→CONVERGED→(freeze)COMMITTED→CHAT(继承对齐); every transition is a task.transition event.

#### Scenario: full chain walk with v0 commit
- **WHEN** a task walks chat→decompose→research→converged and freezeTask commits
- **THEN** the version exists (v0, verdict) and the machine lands in chat (inherit-and-realign); the event stream holds the full transition sequence including the birth

#### Scenario: version+1 continuation
- **WHEN** the walk repeats after inherit-and-realign with an advanced working set
- **THEN** v1 commits (per-task monotonic v)

### Requirement: illegal transitions fail closed without mutating state

#### Scenario: off-matrix transitions rejected
- **WHEN** any signal not in the current phase's matrix fires
- **THEN** an illegal-transition error is raised and the phase is unchanged

#### Scenario: research requires a confirmed decomposition and a signed plan
- **WHEN** sign fires without a confirmed decomposition or an attached run plan
- **THEN** the sign gate rejects and the phase stays decompose

#### Scenario: freeze has no bypass
- **WHEN** freezeTask is called outside converged
- **THEN** it raises (freeze gate) and no version is created

### Requirement: mid-chain decomposition re-entry keeps the ledger

research → chat (user-recalled) preserves ledger rows; the task can re-enter research through a new confirmed decomposition.

#### Scenario: re-entry keeps state
- **WHEN** research returns to chat and a claim was upserted mid-research
- **THEN** the claim is still present and research re-entry succeeds via a new confirmed decomposition

### Requirement: the early-termination hard gate pauses research fail-closed

A refuted make-or-break pauses; continuation is blocked until the user resolves 埋了/继续挖.

#### Scenario: pause blocks continuation
- **WHEN** raiseEarlyTermination fires in research
- **THEN** the phase is paused and research signals are refused

#### Scenario: bury converges, continue resumes
- **WHEN** the user resolves
- **THEN** bury lands converged; continue resumes research

### Requirement: fork produces an inherited child task

#### Scenario: fork transition
- **WHEN** forkTask runs from a committed version
- **THEN** the child task exists with the inherited v0 snapshot, chat phase, and recorded lineage

### Requirement: state is event-sourced

#### Scenario: rehydrate from transition events
- **WHEN** a machine is rebuilt from the event stream alone
- **THEN** phases match the original machine's phases

### Requirement: the run plan is data with mechanical advancement

#### Scenario: plan validation
- **WHEN** a plan has an over-cap budget or an unknown yaw mode
- **THEN** parse/validate reject it naming the field

#### Scenario: step advancement
- **WHEN** the interpreter advances and completes a stage
- **THEN** step status reflects pending→advanced→complete
