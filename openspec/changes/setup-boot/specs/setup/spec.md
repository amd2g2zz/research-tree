## ADDED Requirements

### Requirement: rt setup is idempotent and reports what it did

#### Scenario: fresh machine provisions to a working boot
- **WHEN** runSetup runs on a fresh workspace
- **THEN** the .research-tree root exists (ledger migrations applied) and the report says "created"

#### Scenario: second run is a no-op
- **WHEN** runSetup runs twice
- **THEN** the second run reports "already-initialized"

### Requirement: provisioning is named, pinned and confirmed

Provider CLI installs/updates are reported per provider; global installs and credential writes require the explicit confirm gate.

#### Scenario: provider status is named with guidance
- **WHEN** a provider CLI is missing its API key
- **THEN** the report names the provider with status "missing-api-key" and its install guidance

#### Scenario: global installs are gated
- **WHEN** a provider needs a global install
- **THEN** the confirm gate runs first and the confirmed_actions log reflects the outcome

### Requirement: doctor reports boot readiness with named guidance

#### Scenario: per-provider availability
- **WHEN** doctor runs with a missing provider CLI
- **THEN** that provider is named "missing" with install guidance (not a generic failure)

#### Scenario: overall readiness
- **WHEN** every check passes (providers/storage/mcp/pi)
- **THEN** overall is "ready"; any failure is "attention-required"

#### Scenario: storage and mcp states
- **WHEN** the workspace is initialized and the MCP server is mountable
- **THEN** storage is "writable" and mcp is "mountable"
