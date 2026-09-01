# Design

`CausalTraceService.replay` keeps the existing structural checks for duplicate
or missing lifecycle revisions, state digests, previous-state references, and
event causes. It then rebuilds the initial state from the immutable
alignment-handoff and blueprint-target parents, applies the checked-in
lifecycle matrix to each lifecycle event, and applies correction events with
their quarantine bindings.

Canonical HostEvent envelopes are independently parsed and checked for their
semantic digest, expected ledger revision, lease projection, sequence,
causation, and durable completion references. Host observations that predate
the typed envelope are retained as non-authoritative diagnostics and are not
reported as canonical replay inputs.

Replay input order comes from the append-only lineage event stream rather than
filesystem or database row order. If materialized lifecycle state rows are
absent, deterministic synthetic state references are used only for the
reconstructed trace; no synthetic data is written to the ledger.

The output includes `chain_intact`, `replay_mode`, `projection_rebuilt`, `stored_digest`,
`recomputed_digest`, `semantic_digest`, unresolved obligations, legal next
actions, and `earliest_divergence`. A valid chain with a forged but
self-consistent state is therefore observable as `chain_intact: true` and
`verified: false`.
