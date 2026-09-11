# Design: turn-record-self-heal

## Approach

Self-heal lives in the store/gate region of `alignment_turn_record.py` — the
continuity gate stays fail-closed and gains exactly one recovery attempt
between the failure and the block. The alignment graph is read-only ground
truth: the reconstruction reads its append-only `response_recorded` event log
and never writes to the graph.

## Reconstruction trigger and rules

`check_continuity(next_turn)` attempts reconstruction only for the two
failures a lost write can produce:

- `missing_turn_record` — the record file is absent or empty while
  `next_turn > 1`;
- `stale_turn_record` — the latest persisted index is behind `next_turn - 1`.

`invalid_turn_record` (corrupt record file) never heals: appending one line
cannot make a corrupt file parse again, so today's block is unchanged.

The reconstruction succeeds only when every rule holds; any violation is a
contradictory history and raises the original gate error unchanged:

1. The graph database is readable through a read-only SQLite connection
   (`file:...?mode=ro`, the hook's `_budget_violations_from_events`
   pattern). Missing database, `sqlite3.Error`, or zero `response_recorded`
   events → reconstruction impossible.
2. Every event row parses as JSON with mapping `details_json` and
   `state_json`. Any corrupt row → block (pinned).
3. The event turn axis (each event's `state_json.controller.turn`) is
   exactly `1..N` in sequence order. Non-monotonic or gapped axes are a
   contradictory log → block.
4. The latest log turn `T` must extend the record file, not contradict it:
   `T >= next_turn - 1` and (stale case) `T >` latest persisted index.
5. The synthesized fields validate against the record schema (mirror, gap,
   delta, user_move). A synthesis that cannot produce a valid record →
   block.

## Recovery record synthesis

One baseline record at the log's latest turn `T`:

- `turn_index = T`; `recorded_at` from the event row's `created_at`.
- **mirror** — grounded in the event's materialized graph state: node/edge
  counts, open-gap count, and the latest recorded response
  (`node_id`, `outcome`).
- **gap** — the recorded node is the consequential gap under discussion: its
  statement from the state, else the node id.
- **delta** — summary names the recorded outcome on the node;
  `nodes = [node_id]` when it matches the node-id pattern.
- **user_move** — the event's `user_move` when it is a seam response class,
  else `generation` (the permissive default; the marker carries the
  epistemic caveat).
- **traces** — the event's traces that validate against the seam registry;
  none survive validation → empty (never fabricated).
- **contract_terms** — `None` (terms cannot be faithfully reconstructed; the
  marker states the provenance, and the policy seam already fails open on a
  terms-less latest record).

## Schema marker (never masquerade)

- `reconstructed` is a schema-additive, optional record field.
- Read rule (`from_dict`): when present it must be boolean `true`; any other
  value is a `TurnRecordError`. Absence means authored.
- Write rule: only the new `AlignmentTurnRecordStore.reconstruct(...)` writes
  the marker; `append` keeps authoring records without it, and authored
  `to_dict` payloads stay byte-identical to schema 2 today.
- `SCHEMA_VERSION` stays 2 (additive optional field, like `turn_shape`).

## Degraded mode surface

- Healed gate verdict: `degraded: true`, `recovery: {"turn_index": T,
  "source": "alignment_event_log"}`, and `grounding.reconstructed: true`.
- Any later verdict grounded on a reconstructed latest record also reports
  `degraded: true` + the grounding marker — continuity repaired is never
  reported as pristine.
- `refresh_validation` verdict and the `turn-records.state.json` receipt gain
  `reconstructed_count` (N) and `degraded: true` when the file holds
  reconstructed records; both keys are absent otherwise, so every existing
  exact-shape receipt assertion stays green.

## Graph database resolution

Resolved through the graph's canonical helper
(`alignment_graph.database_path`) when the run root matches the canonical
workspace layout, imported lazily (function-level) because
`alignment_graph → lifecycle_hook → alignment_turn_record` forbids a
module-level import; the canonical adjacency (the db lives in the same
`alignment/` directory as the record file — the helper's own layout) is the
fallback. The graph module is not modified.

## impact_scope

- `AlignmentTurnRecordStore.check_continuity` (additive recovery path),
  `AlignmentTurnRecordStore.reconstruct` (new), `AlignmentTurnRecord`
  (additive field), `AlignmentTurnRecord.from_dict` / `to_dict` (marker
  rules), `refresh_validation` (additive receipt keys).
- Callers (verified via GitNexus impact + text search): lifecycle_hook reads
  `latest()` / `records()` / `refresh_validation` — additive keys only;
  `check_continuity` has no src callers (the turn composer's public
  observation surface + tests). Existing exact-shape assertions in
  test_alignment_turn_record.py / test_lifecycle_hook_turn_record.py /
  test_turn_shape_gate.py are preserved for non-reconstructed records.
