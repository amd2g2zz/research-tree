# Proposal: turn-record-self-heal

## Why

issue #529 (confirmed): the fail-closed continuity gate (#497/#509) is correct
against drift and self-answering but has no recovery path. A missing or
stale turn record blocks the next alignment turn even though the alignment
graph's append-only event log still holds the ground truth of what happened.
After compaction or a lost write the run stalls with no way back except
manual surgery on the record file.

## What Changes

1. **Baseline reconstruction before blocking** (alignment_turn_record.py):
   on a continuity-gate failure (`missing_turn_record` / `stale_turn_record`),
   the store attempts a reconstruction from the alignment-graph event log —
   read-only SQLite access to the run's `response_recorded` events (same
   store the graph and the hook already read; the graph is never written).
   One recovery record is synthesized: grounded mirror from the latest graph
   state, delta from the event, `recorded_at` from the event, and the marker
   `reconstructed: true` (schema-additive field).
2. **Degraded mode, never silently pristine**: a successful reconstruction
   continues the run — the healed gate verdict carries `degraded: true` plus
   a named `recovery` section, the grounding names `reconstructed: true`, and
   the refresh receipt reports `reconstructed_count` / `degraded` whenever the
   record file holds reconstructed records.
3. **Fail-closed unchanged**: an empty, unreadable, or contradictory event log
   (or a corrupt record file, or a log whose turn axis contradicts the
   record file) blocks exactly as today — the gate's failure reasons and
   messages are pinned.
4. **Marker enforced in schema**: `reconstructed` is validated like every
   record field — present implies the record IS reconstructed (any value
   other than boolean `true` is a schema error), authored records omit it,
   and only the reconstruction path writes it. Reconstructed records can
   never masquerade as authored ones.

## Impact

- src/research_tree/alignment_turn_record.py: additive reconstruction path in
  the store/gate region + the schema marker. Read-only import of
  `alignment_graph.database_path` (lazy, cycle-safe; the graph module is not
  modified and never written).
- tests/test_turn_record_self_heal.py: new scenarios.
- No canonical generation inputs (skill-src, packages, lifecycle_hook,
  turn_contract) are touched; parity stays green.
