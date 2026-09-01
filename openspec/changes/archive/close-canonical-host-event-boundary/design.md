# Design

## Boundary invariant

`ResearchRunCoordinator.ingest_host_event(s)` is the sole event append path.
The compatibility `ingest_event()` entry point rejects its former generic
arguments and delegates only when a complete envelope is explicitly supplied.
No validation failure calls the ledger, so the run revision and projections
remain unchanged.

## Validation order

1. Parse `HostEvent.from_value()` and verify schema, identifiers, payload
   digest, normalized paths, and event-specific required fields.
2. Require one run, attempt, and expected revision for the complete batch; a
   revision mismatch returns `stale_revision` before mutation.
3. Resolve the exact latest attempt lease. It must retain the attempt identity,
   have `status=active`, and either omit expiry or have a future timezone-aware
   `expires_at`. Declared action/slot bindings cannot contradict the lease's
   work item.
4. Require the next per-attempt sequence. Sequence one may start without a
   cause (or be caused by its attempt); later events require `causation_id` to
   equal the immediately preceding accepted event id, including within a
   batch.
5. For `checkpoint_persisted`, resolve the current analysis checkpoint and
   compare the declared digest with its canonical payload/content hash. For
   `worker_finished`, resolve current same-run/same-attempt committed capture,
   succeeded receipt, checkpoint, finding-pack, and produced-artifact refs.
6. Append each event and its non-authoritative projection through one
   `append_artifact_batch()` transaction. Duplicate event ids replay the
   original event when identity and payload digest agree; changed reuse is a
   conflict.

## Adapter authority

`native_execution_adapter.emit_host_event()` requires an explicit non-negative
`expected_revision` and passes it through unchanged. The local state revision
continues to describe adapter observations only. Hermes already accepts a
canonical revision in its snapshot/CLI path; the shared helper now carries the
same optional `causation_id` field and all package copies are rebuilt.

## Recovery and rollback

The transaction boundary is unchanged and is covered by an injected
`RunLedger._before_commit` failure: neither the event nor its projection is
visible after the crash. Rollback is a Git revert of this change; accepted
immutable event history remains readable and no adapter-local completion route
is restored.
