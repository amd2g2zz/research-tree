# ADR-001: Run-Scoped Local Runtime

## Decision

Adopt the RT-001 design recorded in [方案设计](../方案设计.md): Python 3.11+,
an explicit `RunStore` root, versioned JSON artifact envelopes, append-only
lineage events, and `pytest` exercised through a locked `uv` environment.

## Rationale

The product contracts need immutable lineage and reproducible local state now.
They do not yet justify a network service, database, or a broad runtime
framework. The chosen boundary isolates future modules from storage while
keeping artifacts inspectable and tests deterministic from a clean checkout.

## Rejected alternatives

- A global `research_state.json`: cannot isolate concurrent or recursive rounds.
- A mutable document per round: cannot preserve artifact revisions.
- A full server/database first: adds operational choices before the product's
  domain behavior has been validated.
