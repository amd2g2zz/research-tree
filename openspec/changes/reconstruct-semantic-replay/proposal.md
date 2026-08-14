# Reconstruct semantic replay

The current causal trace operation checks continuity and stored state digests,
but it does not independently recompute lifecycle state. This change makes
replay derive lifecycle projections from immutable initialization inputs,
lifecycle/correction events, leases, and canonical host events before comparing
the result with materialized state. Materialized `research-run-state` rows are
optional cache data: when absent, replay rebuilds the same projection and
marks that the projection was rebuilt.

The result distinguishes an intact structural chain from a semantically
verified replay and reports the first divergent field without treating a
self-consistent forged projection as authoritative.
