## Context

Durable interaction state has two projections of pending work: the reducer-owned semantic `agent.pending_actions` tuple and the persisted action-status map used for crash recovery. Corrections change the first projection today but not the second.

## Goals / Non-Goals

**Goals:**

- Reconcile persisted action statuses with reducer successor state in the same revisioned `submit` mutation.
- Preserve unrelated action statuses exactly, including their `started` value.
- Make correction invalidation survive checkpoint recovery and repeated submission of the same event ID.

**Non-Goals:**

- Adding another action authority, completion state machine, host adapter, or contradiction-propagation path.
- Changing reducer invalidation rules or deleting auditable episodes/checkpoints.

## Decisions

- `submit` always reduces the event first, computes the action IDs that disappeared from semantic `agent.pending_actions` during that transition, and removes only those IDs from `prior.pending_actions`.
- Reconciliation is transition-scoped, not global semantic-set authorization: tracked execution IDs that never appeared in semantic state, and action IDs not invalidated by this transition, retain their observed status exactly.
- Recovery restores checkpoint state, first intersects checkpoint statuses with statuses still present durably, and replays post-checkpoint correction transitions through the reducer. Each replay removes only the action IDs invalidated by that correction before converting checkpointed `started` statuses to `unknown`.
- Repeated event IDs do not create a restore path. Current-revision replay is deterministic, and a stale submission is rejected without publication.

## Risks / Trade-offs

- [Rollback to an older checkpoint loses post-checkpoint semantic work] -> correction invalidation remains a safety boundary and cannot be rolled back into durable action authority.
- [A damaged episode prevents replay] -> recovery fails closed rather than inferring authorization.
