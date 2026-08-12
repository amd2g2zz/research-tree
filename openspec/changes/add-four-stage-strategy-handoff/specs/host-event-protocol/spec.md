## ADDED Requirements

### Requirement: Host projection transports canonical strategy semantics only
Codex, Claude Code, and Hermes adapters SHALL transport the same StrategyProjection semantic payload and digest while keeping host capability and display metadata outside the digest, and SHALL NOT confirm or dispatch on behalf of the requester.

#### Scenario: Native confirmation control is unavailable
- **WHEN** a host cannot provide a structured confirmation control
- **THEN** the adapter uses ordinary contextual conversation or records capability unavailable without weakening the exact-display confirmation gate
