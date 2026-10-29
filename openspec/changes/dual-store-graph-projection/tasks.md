# dual-store-graph-projection — tasks

- [ ] 1. `graph_events.py`: vocabulary + per-type payload validation (RED first)
- [ ] 2. `RunLedger` v8: `graph_events` table, hash-chained `append_graph_event`,
      `graph_events(since_seq)`, `verify_graph_chain` (RED first)
- [ ] 3. `graph_store.py`: Kùzu DDL, idempotent apply, rebuild, snapshot_state,
      fork lineage queries (RED first)
- [ ] 4. `ResearchRunCoordinator`: optional graph store, dual-write append,
      resync self-heal (RED first)
- [ ] 5. Replay acceptance: rebuild-from-log-alone == live graph (CI test)
- [ ] 6. Full local gates (pytest, ruff, impact-scope audit) + PR
