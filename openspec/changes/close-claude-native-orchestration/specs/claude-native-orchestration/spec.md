## ADDED Requirements

### Requirement: Claude child identity is preserved

Claude lifecycle records SHALL preserve opaque project, run, task, attempt,
agent, session, and causation identity without prompts, tool input, transcripts,
secrets, or child summaries.

#### Scenario: SubagentStop identity is incomplete

- **WHEN** a SubagentStop lacks an exact active task/attempt/agent identity
- **THEN** the observation is `unknown_outcome` and cannot complete work

### Requirement: Agent identity binds one active attempt

The adapter SHALL bind the exact host-returned agent identity to the active
canonical attempt before accepting a Claude Finding Pack. The same agent identity
SHALL not bind another attempt.

#### Scenario: Child result is submitted

- **WHEN** a Finding Pack names an attempt whose agent binding is absent or stale
- **THEN** submission fails and the task remains blocked or unknown

### Requirement: Execution modes remain independent

Claude SHALL expose Agent, Workflow, and hybrid capabilities independently.
Agent fallback SHALL be selectable when Workflow is unavailable, but no mode may
be inferred from task-list, hook, workflow status, or report shape.

#### Scenario: Workflow is unavailable

- **WHEN** only real Agent child delegation is available
- **THEN** the mode is Agent and the output does not claim Workflow or hybrid use

### Requirement: Live evidence is mode-specific

Agent closure evidence SHALL include at least two distinct real child identities
and their attempt bindings. Workflow SHALL require persisted workflow/script/run
and phase evidence; hybrid SHALL require both phase and child identity evidence.
Unavailable surfaces SHALL be recorded with the exact probe and version.
