# ADR-002: Single Completion Authority

Status: Accepted

## Context

Alpha1 recursive projections, host adapters, hooks, worker status, and report
shape checks can each describe a run as complete. None of those local signals
proves canonical evidence closure, readiness, exact delivery lineage, or user
acceptance.

## Decision

`ResearchRunCoordinator` is the only component permitted to transition the
canonical lifecycle, issue or revoke closure, register readiness or delivery,
record exact-revision acceptance, or complete a run. A host, worker, hook, or
report can emit candidate artifacts or versioned events but cannot complete a
run.

## Consequences

Completion is replayable, diagnostic, and non-bypassable. Local activity can
still be useful for scheduling and observability, but it must cross the
coordinator boundary before it affects canonical state.

## Rejected Alternatives

- Reconcile multiple writable authorities: no deterministic winner exists after
  their histories diverge.
- Trust a worker status or report gate: syntactic output cannot prove semantic
  research obligations.

## Migration

Legacy completion fields are imported as historical observations. Host-local
state stays read-only until parity, recovery, and rollback evidence supports a
canonical cutover.
