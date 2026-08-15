## ADDED Requirements

### Requirement: Project scoped workspace owns run artifacts

The system SHALL create and validate one project-local workspace beneath
`.research-tree/projects/<project-id>/` for every declared project/run pair.
The workspace descriptor SHALL expose only paths beneath that project root.

#### Scenario: A second host resumes an existing run

- **WHEN** a caller initializes an existing `project_id` and `run_id`
- **THEN** it receives the same workspace descriptor and does not create a
  parallel state root

### Requirement: Hook bootstrap preserves unrelated project configuration

The system SHALL atomically merge its marked hook entries into project-local
Codex and Claude configuration, preserving unrelated keys and hooks. It SHALL
create Hermes configuration only inside the selected run workspace.

#### Scenario: Bootstrap is repeated after an interrupted host write

- **WHEN** one host configuration write fails while bootstrap runs
- **THEN** all prior project configuration bytes are restored and the next
  bootstrap can apply one copy of each owned hook entry

### Requirement: Lifecycle records use the workspace descriptor

The system SHALL write lifecycle records carrying a valid project/run/session
descriptor only below that run's event directory.

#### Scenario: Events from concurrent projects arrive

- **WHEN** hooks report two distinct valid project/run descriptors
- **THEN** their sanitized event records are stored in distinct project run
  trees and neither record can name the other tree
