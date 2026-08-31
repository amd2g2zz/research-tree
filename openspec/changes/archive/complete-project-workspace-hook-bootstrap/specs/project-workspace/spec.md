## ADDED Requirements

### Requirement: One writable project authority

The system SHALL create and validate one project/run workspace under
`.research-tree/projects/<project-id>/runs/<run-id>`.  Initialization SHALL
migrate the supported legacy alignment, native, hook, and Hermes roots into
that workspace or fail without leaving a second writable authority.

#### Scenario: Legacy migration

- **WHEN** a legacy run root exists for the requested run
- **THEN** initialization moves it into the project workspace, records the
  migration in the manifest, and removes the legacy writable root

### Requirement: Installed hook proof

The system SHALL render a dependency-free hook launcher in the run workspace
and execute a bounded live probe before reporting lifecycle hooks as available.

#### Scenario: Probe failure

- **WHEN** the installed hook launcher cannot emit a valid run-bound record
- **THEN** the workspace SHALL record `lifecycle_hooks=unavailable`

### Requirement: Host-independent recovery

The system SHALL reopen the same project/run manifest from another supported
host after a process restart without creating a parallel local state root.

#### Scenario: Restart recovery

- **WHEN** one host initializes a run and another host resumes it after restart
- **THEN** both observe the same manifest and run-local event directory
