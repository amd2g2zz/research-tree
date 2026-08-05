# ADR-005: Host Adapters as Event Translators

Status: Accepted

## Context

Codex, Claude Code, and Hermes expose different delegation, question, hook, and lifecycle
surfaces. Encoding product state separately in each adapter causes semantic drift.

## Decision

Host adapters translate native activity into the versioned HostEvent protocol and project
coordinator decisions back to host actions. They own no closure, readiness, delivery, or
completion state. Hooks are fail-open observability and wake-up mechanisms only.

## Consequences

Host capabilities can differ without changing product semantics. Provider failures and
unknown attempts remain visible and recoverable in the canonical ledger.

## Rejected Alternatives

- One shared prompt for every host: it ignores native lifecycle and persistence features.
- Host-local completion state: equivalent executions can produce conflicting outcomes.

## Migration

Native and Hermes checkpoints become read-only import projections. Cutover requires parity,
provider-failure, stale-event, duplicate-event, and restart reconciliation evidence.
