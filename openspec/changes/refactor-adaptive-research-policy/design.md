# Design

`AdaptiveResearchPolicy` is a pure, seeded reader of normalized Slot deficits, verified evidence, digest signals, prior outcomes, and versioned configuration. It returns typed proposals, dispositions, and a replay trace; it never persists, dispatches, acquires, leases, or mutates lifecycle state. `ResearchRunCoordinator` remains authoritative.

The immutable delta covers evidence-class coverage, provenance independence, contradiction, oracle state, implementation uncertainty, and Slot closure with references/contributions; repeated state is zero/no-progress. Version, canonical input, configuration, and seed determine ranking; mandatory P0 actions survive pruning and unverified worker suggestions are rejected.

Digest synthesis validates lineage and emits classified statements, gaps, contradictions, limitations, confidence, parent/digest refs, and delta as an input projection. Recursive search is read-only: local signals cannot close a Slot, accept delivery, or complete a run. Rollback retains history and never restores writable legacy completion; alignment, host, invalidation, capture, and portfolio authority remain out of scope.
