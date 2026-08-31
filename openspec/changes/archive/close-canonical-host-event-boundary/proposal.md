# Close the Canonical HostEvent Boundary

## Why

Issue #151 identified a P1 Alpha2 regression at the only boundary that can
turn host observations into canonical run lineage. `ingest_event()` accepted
an arbitrary payload and wrote a lone `host-event` artifact, while
`ingest_host_events()` performed the typed envelope, lease, revision, sequence,
and projection work. Native adapters also copied their local JSON revision into
the event envelope, creating a second revision authority.

## What Changes

- Make the legacy generic ingestion signature a non-writing compatibility
  wrapper that accepts only a complete `HostEvent` envelope.
- Bind every accepted event to the current active, unexpired attempt lease,
  current ledger revision, optional action/slot lineage, and a causal
  predecessor for every sequence after the first.
- Validate exact current SourceCapture, AcquisitionReceipt, AnalysisCheckpoint,
  Finding Pack, and produced-artifact references before `worker_finished`; the
  existing ledger batch remains the atomic event/projection commit.
- Add checkpoint digest validation and stable rejection reasons for inactive,
  expired, orphan, stale, out-of-order, causal, and incomplete events.
- Require native adapters to receive canonical expected revision explicitly;
  local observation revision is never copied into a HostEvent.
- Extend the dependency-free protocol and rebuild Codex, Claude, and Hermes
  package copies from the same authoring source.

## Non-goals

- Synchronizing or deleting local adapter observation counters.
- Granting host events completion, readiness, closure, delivery, or acceptance
  authority.
- Replacing the transactional `RunLedger.append_artifact_batch()` boundary.

## Impact

The affected implementation surface is `src/research_tree/coordinator.py`,
`src/research_tree/host_events.py`, `src/research_tree/native_workflows.py`,
the native and Hermes protocol adapters, generated package copies, and focused
coordinator/adapter/package tests. No new database table or public completion
authority is introduced.
