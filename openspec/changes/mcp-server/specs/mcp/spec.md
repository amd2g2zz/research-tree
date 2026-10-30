## ADDED Requirements

### Requirement: four projection-only MCP tools

rt.start / rt.status / rt.correct / rt.verdict; no state merge into the harness.

#### Scenario: start opens a task
- **WHEN** rt.start is called with a task id
- **THEN** the machine opens the task and the phase (chat) is returned

#### Scenario: status reports phase and ledger digest
- **WHEN** rt.status is called for a known task
- **THEN** the response carries the phase, ledger event count and version/draft pointers

#### Scenario: corrections route without privilege
- **WHEN** rt.correct carries steering input
- **THEN** the action lands as an engine fact through the same correction path as chat

#### Scenario: verdict exposes deliverable paths
- **WHEN** rt.verdict is called for a committed task
- **THEN** the response carries version, verdict, commit hash and report/底稿 paths

### Requirement: unknown tools are rejected

#### Scenario: unknown tool
- **WHEN** an unregistered tool name is called
- **THEN** the call raises naming the tool
