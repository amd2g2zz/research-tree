# ADR-002: Single Completion Authority

Status: Accepted

## Context

Alpha1 adapters, recursive projections, hooks, report gates, and workers could each imply
that research was complete. Their local signals do not prove evidence, delivery, or user
acceptance.

## Decision

Only `ResearchRunCoordinator` may transition canonical lifecycle state, issue or revoke
closure, register readiness and delivery, record exact-revision acceptance, or complete a
run. Other components emit candidate artifacts or versioned events.

## Consequences

Completion is replayable and non-bypassable. Adapters and workers can report progress but
cannot convert local success into canonical success.

## Rejected Alternatives

- Reconcile multiple writable authorities: no deterministic winner exists after divergence.
- Trust worker or report status: syntactic output cannot prove semantic obligations.

## Migration

Legacy completion fields are imported as observations. Host-local state remains read-only
until release gates prove canonical cutover and rollback behavior.
