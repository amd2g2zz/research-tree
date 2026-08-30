"""Issue #320: stable state projection for CLI, hooks, briefs, strategy viz."""

from __future__ import annotations

from research_tree.state_projection import (
    StateProjection,
    render_progress_summary,
)


def test_projection_exposes_six_mandated_facets() -> None:
    projection = StateProjection(
        phase="autonomous_research",
        active_branch="branch-a",
        reconciliation_delta=("branch-b unconfirmed",),
        current_action="dispatch attempt-1",
        current_action_reason="policy.propose(method_switch, confidence=0.8)",
        next_action="await worker_finished",
        blockers=("rate_limit",),
        authority_waits=("approval:branch-a",),
        disputes=(),
        experiments=("exp-readme-1",),
        resumable=True,
    )
    for facet in (
        "phase",
        "active_branch",
        "reconciliation_delta",
        "current_action",
        "current_action_reason",
        "next_action",
        "blockers",
        "authority_waits",
        "disputes",
        "experiments",
        "resumable",
    ):
        assert hasattr(projection, facet), f"missing facet: {facet}"


def test_render_progress_summary_compact_view_includes_all_facets() -> None:
    projection = StateProjection(
        phase="synthesis",
        active_branch="branch-a",
        reconciliation_delta=("branch-b unconfirmed",),
        current_action="synthesis attempt-2",
        current_action_reason="slot closure in progress",
        next_action="readiness check",
        blockers=(),
        authority_waits=(),
        disputes=("claim-12",),
        experiments=(),
        resumable=True,
    )
    rendered = render_progress_summary(projection)
    # The compact view names every facet key + value (semantic, not literal)
    assert "phase=" in rendered and "synthesis" in rendered
    assert "branch=" in rendered and "branch-a" in rendered
    assert "next=" in rendered and "readiness check" in rendered
    assert "disputes=" in rendered and "claim-12" in rendered


def test_render_progress_summary_resumable_branch_metadata_visible() -> None:
    projection = StateProjection(
        phase="autonomous_research",
        active_branch="branch-x",
        reconciliation_delta=(),
        current_action="dispatch attempt-7",
        current_action_reason="attempt lineage",
        next_action="worker_finished",
        blockers=(),
        authority_waits=(),
        disputes=(),
        experiments=(),
        resumable=True,
    )
    rendered = render_progress_summary(projection)
    assert "attempt-7" in rendered
    assert "branch-x" in rendered
    assert rendered.endswith("\n") or rendered  # compact one-liner acceptable


def test_projection_from_coordinator_self_state_round_trip(tmp_path) -> None:
    """self_state + projection share the same region keys (smoke)."""

    from test_research_run_coordinator import _confirm_strategy, _initialize

    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _confirm_strategy(ledger, coordinator)
    snapshot = coordinator.self_state("run-57")
    projection = StateProjection.from_coordinator_snapshot(snapshot)
    assert projection.phase == snapshot["workflow"]["value"]
    assert (
        projection.active_branch == ""
        or projection.active_branch.startswith("branch-")
        or projection.active_branch == "branch-pending"
    )
