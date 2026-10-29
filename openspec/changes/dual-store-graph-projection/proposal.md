# dual-store-graph-projection

## Why

Issue #546 (T0 row 1, roadmap docs/product/04-roadmap-v1.md). v2.0 needs an object graph
carrying claims / stages / evidence / artifacts / versions with **fork lineage as a
first-class graph query**. The trust guarantees (replayable research history; "any
conclusion ≤3 clicks to raw evidence") require the graph to be a **replayable
projection** of the append-only event stream, not hand-maintained state.

Two stores, one truth:

- SQLite (`RunLedger`) stays the sole authority: a new workspace-global `graph_events`
  table is an append-only, **hash-chained** event log (tamper-evident, dense global seq).
- Kùzu (`graph_store.GraphStore`) is a projection: `rebuild(events)` reproduces the
  identical state from the log alone; a replay test lands in CI.

## What changes

- New `graph_events.py`: typed event vocabulary (11 event types covering claim/stage/
  evidence/artifact/version/fork facts) + payload validation (dataclass-free, strict,
  per-type). No kuzu import — usable from both the ledger and the projection.
- New `graph_store.py`: Kùzu schema (5 node tables, 6 rel tables incl. `FORKED_FROM`),
  idempotent `apply_event`, full `rebuild`, `snapshot_state` (deterministic, for
  equality tests), fork lineage queries both directions.
- `RunLedger` (schema v7 → v8, additive): `graph_events` table + `append_graph_event`
  (BEGIN IMMEDIATE serialized chain append) + `graph_events(since_seq)` +
  `verify_graph_chain()` (gap + hash-mismatch detection).
- `ResearchRunCoordinator` (additive): optional `graph_store=` constructor kwarg;
  `append_graph_event` dual-writes log-then-projection (projection failure raises
  `GraphProjectionError`, recovery = `resync_graph()`); `graph_events` passthrough;
  `resync_graph()` rebuilds the projection from the log alone.
- `pyproject.toml`: first runtime dependency `kuzu>=0.11,<0.12`.

## impact_scope

- `RunLedger` (additive: SCHEMA_VERSION 8, new table, three new methods — no existing
  signature changes), `ResearchRunCoordinator` (additive: optional kwarg + three new
  methods — no existing signature changes)
- new: `graph_events` (vocabulary + validation), `graph_store` (Kùzu projection)
- GitNexus impact (2026-10-29, dev @ 03ccece): `RunLedger` upstream = **HIGH**
  (28 impacted, 19 direct) — additive-only mitigation + full suite as regression
  guard; `ResearchRunCoordinator` upstream = MEDIUM (17 impacted, 6 direct).
  HIGH warning is restated in the PR description per AGENTS.md.

## rejected_designs

- **Per-run `LineageEvent` reuse for graph facts**: those carry run-revision
  expectations and lifecycle semantics; the projection needs a workspace-global total
  order and a tamper-evident chain — a dedicated log is simpler and does not perturb
  the v1 revision protocol.
- **Delta-only events** (posterior_change etc.): state-carrying upserts make replay
  idempotent and rebuild equality trivially checkable; deltas would make every replay
  test order-dependent.
- **GraphStore inside coordinator as mandatory**: v1 callers construct coordinators
  without a graph; the projection is opt-in until T1 surfaces it (#559 canvas).
