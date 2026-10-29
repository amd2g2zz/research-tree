# design — dual-store-graph-projection

## Layout

Two new modules, two additive extensions:

- `graph_events.py` — vocabulary + validation only (no kuzu, no sqlite imports).
- `graph_store.py` — Kùzu projection: DDL, idempotent apply, rebuild, snapshot, lineage.
- `run_ledger.py` — schema v8: `graph_events(seq INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id NULLABLE, event_type, payload_json, prev_hash, content_hash, created_at)`;
  chain: `content_hash = sha256(prev_hash ‖ canonical_json(record-without-hashes))`,
  genesis prev = 64×"0"; `verify_graph_chain()` detects seq gaps and hash mismatches.
- `coordinator.py` — optional `graph_store=` kwarg; dual-write = log first (authority),
  projection second; projection failure raises `GraphProjectionError` (fail-closed,
  recovery = `resync_graph()` rebuild from log).

## Event vocabulary (state-carrying upserts + additive edges)

`claim.upsert` · `claim.kill_edge` · `stage.upsert` · `stage.depends_on` ·
`stage.contains` · `evidence.upsert` · `evidence.attach` · `artifact.upsert` ·
`artifact.link` · `version.commit` · `fork.edge`

Node identity: single-column PK (`id`) — Kùzu requires single-column primary keys
(W0 smoke verified). `version.commit` ids are `"<task_id>:<v>"` shaped upstream; the
log does not enforce the shape, the projection does not assume it.

## impact_scope

- `RunLedger` (additive), `ResearchRunCoordinator` (additive optional kwarg)
- new: `graph_events`, `graph_store`
- tests: `test_graph_events.py`, `test_graph_store.py`, `test_coordinator_graph.py`
- `pyproject.toml` / `uv.lock` (kuzu runtime dep)

## rejected_designs

- Reusing per-run `LineageEvent` (no global order, revision-locked semantics).
- Delta-only events (replay order-dependence, weaker idempotency).
- Mandatory projection in the coordinator constructor (breaks v1 callers for no T0 need).
- Storing node state in both SQLite tables and the graph now: claim/stage tables are
  #547's scope; this change ships the event log + projection seam only, so #547 wires
  CRUD into `append_graph_event` instead of inventing a second write path later.
- Top-level `import kuzu` in `graph_store.py`: the wheel CLI contract
  (test_cli installs with `--no-deps`; deployment form ① portable skill, any host)
  requires booting without the graph engine. kuzu stays a declared runtime dependency
  (normal installs get it); the import happens lazily at connection time, so graph
  use without kuzu fails loudly exactly where the graph is needed.

## Verification anchors

- Dual-store consistency: same write lands in log and projection; drift is repairable
  by `resync_graph()` (event-log replay == live graph — the T0 acceptance).
- Tamper-evidence: row mutation / row deletion both detected (`verify_graph_chain`).
- Idempotency: replaying any event twice leaves `snapshot_state` unchanged.
