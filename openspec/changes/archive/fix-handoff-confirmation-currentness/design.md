## Context

`AlignmentGraphStore.confirm` records a digest before mutating the strategy
status, while `compile_handoff` rebuilds context from current graph nodes. The
two digest fields can consequently differ even without a later mutation, and
the adapter accepts the result without checking their relationship.

## Goals / Non-Goals

**Goals:**

- Treat the confirmation digest as a graph-currentness token.
- Preserve the prior confirmation record while exposing a deterministic stale
  reason after any subsequent graph mutation.
- Ensure source and generated Codex, Claude, and Hermes adapters reject an
  internally stale handoff.

**Non-Goals:**

- Retrospectively revoke a handoff artifact already dispatched into an
  independent canonical run.
- Change the coordinator completion manifold or the user-facing strategy text.

## Decisions

- `confirm` accepts the current graph only after normalizing the accepted
  strategy state, then stores that final graph digest and confirmation revision.
- `merge` and `record` invalidate an autonomous confirmation before committing
  their graph/response event. The controller returns to alignment phase and
  retains a structured stale handoff record for diagnosis.
- `compile_handoff` rejects stale controller state and rejects any digest
  mismatch before materializing Decision Slots or execution context.
- Native and Hermes adapters reject a supplied handoff unless it carries equal,
  well-formed confirmation and compiled graph digests, preventing malformed
  artifacts from entering host execution or creating project authority.

## Risks / Trade-offs

- A no-op post-confirmation merge requires reconfirmation. This is intentional:
  the controller cannot prove intent-preserving equivalence across arbitrary
  graph updates, so it fails closed.
- A valid artifact compiled before a later correction remains an immutable
  historical artifact. Canonical run-level correction invalidation remains the
  responsibility of the coordinator.
