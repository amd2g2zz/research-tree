# Complete Contradiction Lifecycle

## Context

Canonical claims remain immutable RunLedger lineage. The existing slice does not
preserve resolution authority or uniformly revoke downstream state.

## Decisions

- `contradiction-packet` is immutable and records normalized claims, provenance,
  tested scope, exact conflict, invalidated refs, fallback, and digest.
- `contradiction-resolution` is an append-only chain. A valid terminal revision
  authorizes only its selected reconciled claims; `superseded` authorizes none.
  Invalid chains and invalidated historical decisions remain blocked.
- `contradiction-successor-work` records an independent source, method, or
  executable oracle plus the safe fallback. `contradiction-retraction` records
  identity, exact claim set, stale descendants, execution effects, and durable state.
- `ContradictionDetector.detect` is the sole typed boundary. It separates
  non-overlapping applicability before classifying overlapping authority conflicts.
- Coordinator propagation is one ledger batch. Retry is keyed by contradiction
  identity and exact claim set; durable retraction is idempotent after commit.
- Readiness and delivery consume packet, resolution, and retraction lineage and
  name the exact packet and claim IDs when failing closed.

## Testing

Real ledger, coordinator, durable controller, readiness, delivery, and replay
objects cover typed scope, immutable resolution, atomic rollback and retry,
execution effects, post-delivery reopening, rendering, and downstream denial.
