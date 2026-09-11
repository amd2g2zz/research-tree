# Proposal: discipline-telemetry

## Why

issue #525 (user feedback, 2026-09): compliance decay. When reminded, the
agent follows the working discipline, then drifts back within a few turns —
known LLM long-context instruction decay that stronger SKILL wording cannot
fix. The prescription is mechanical, external, never-forgetting observation:
the hook measures what #527 (agent turn budget) and #514 (turn shape) already
emit, remembers violations per run, and escalates through a graduated
response ladder instead of one-shot blocking. Today the hook observes prompts
but never counts agent-side output shape, and there is no memory of
violation history — so "comply, relapse" is invisible to the system.

## What Changes

1. Violation stream (new `src/research_tree/discipline.py`): an append-only
   JSONL store per run — one record per named violation
   (`{turn_index, dimension, measured, cap, source}`), dimensions drawn from
   a canonical vocabulary (`questions` / `chars` / `record` / `other`),
   persisted beside the turn record under the run's `discipline/` directory.
   Query: a sliding-window violation rate over the last
   `DISCIPLINE_WINDOW_TURNS` turns.
2. Hook measurement seam (lifecycle_hook.py, additive): on PostToolUse/Stop,
   the hook reads what the event stream already emits — the #527
   `turn_budget_violations` entries persisted in the alignment event log and
   the #514 `turn_shape` verdicts (plus #497 empty-delta compliance)
   persisted in the turn-record file — and appends unseen violations to the
   stream. No measurement logic is duplicated. The hook receipt gains a
   `discipline` section (rate, recent violations, response marker).
3. Graduated response ladder (named thresholds, pinned by tests):
   rate below `DISCIPLINE_REMINDER_RATE` → receipt-only (current behavior);
   at/above → a `discipline_reminder` injection entry in the hook result
   (the structured payload #530's tail-injection channel carries — single
   line, fixed slot, bounded per the #530 cache-friendly constraint);
   sustained high (at/above `DISCIPLINE_RELOAD_RATE`) → a
   `discipline_reload` entry that requests the SKILL discipline section
   reload; extreme sustained (at/above `DISCIPLINE_BLOCK_RATE`) → a
   `discipline_block` verdict a next-turn gate check honors.
4. Fail-open observation, fail-closed only at the top step: telemetry
   absent → no measurements, no false violations, gate allows; only the
   block step is fail-closed.

## Impact

- src/research_tree/discipline.py: new module (stream store, rate query,
  ladder, gate check).
- src/research_tree/lifecycle_hook.py: additive seams only — one optional
  import chain (standalone-packaged execution degrades to no telemetry,
  like #497), one collection helper consuming emitted records, one observe
  branch on PostToolUse/Stop; the existing #503/#509/#511 logic is
  untouched.
- src/research_tree/__init__.py: exports for the new module.
- tests/test_discipline_telemetry.py: new scenario tests.
- openspec/changes/discipline-telemetry/: this change.
- packages regenerated only for the embedded lifecycle_hook.py copy
  (generated-only commit).
- Does NOT touch alignment_graph.py, turn_contract.py,
  alignment_turn_record.py, tree_state.py, recursive_search.py, ledger.py,
  decision_map.py, skill-src/**, references/**.
- Feeds (follow-up, outside this change's files): the adaptive-stance
  controller can read the violation-rate signal via the exported rate query.
