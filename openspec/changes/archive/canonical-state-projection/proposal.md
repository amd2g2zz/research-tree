# Proposal: canonical-state-projection

## Why

issue #320: phase/branch/delta/state fragments across interaction,
alignment graph, coordinator lifecycle, host-visible output. CLI, hooks,
adapters, briefs, strategy visualization need one shared projection.

## What Changes

NEW `src/research_tree/state_projection.py`:
- `StateProjection` frozen dataclass: phase + active_branch +
  reconciliation_delta + current_action + current_action_reason +
  next_action + blockers + authority_waits + disputes + experiments +
  resumable (12 fields covering acceptance bullets 1-7).
- `from_coordinator_snapshot(snapshot)`: builds from coordinator.self_state()
  output (regions + lineage) — single source of truth shared with #324.
- `render_progress_summary(projection)`: compact human-readable one-liner for
  CLI / Human Brief / strategy visualization.

## Impact

- src/research_tree/state_projection.py (new) — no behavior change to existing
  modules.
- All consumers (CLI, hooks, host adapters, briefs, strategy viz) can now
  import the same projection rather than reading coordinator.self_state()
  independently.

## Acceptance ↔ test
| Acceptance | Test |
|---|---|
| phase/branch/delta/action-reason/next/blockers/authority-waits | test_projection_exposes_six_mandated_facets |
| compact view covers all facets + branch values + dispute ids | test_render_progress_summary_compact_view_includes_all_facets |
| attempt lineage (branch + attempt id) visible | test_render_progress_summary_resumable_branch_metadata_visible |
| CLI/hooks/adapters/briefs/strategy viz share one source | test_projection_from_coordinator_self_state_round_trip |
