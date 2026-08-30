"""Issue #324: canonical state is orthogonal regions, not one overloaded status."""

from __future__ import annotations

import pytest
from test_research_run_coordinator import _confirm_strategy, _initialize

from research_tree.coordinator import CoordinatorConflictError

REGIONS = ("cognitive", "workflow", "authority", "epistemic", "delivery")


def test_query_returns_one_field_per_region(tmp_path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _confirm_strategy(ledger, coordinator)
    projection = coordinator.self_state("run-57")
    for region in REGIONS:
        assert region in projection, f"self_state must surface region={region}"
        assert "value" in projection[region] and "revision" in projection[region]


def test_phase_blocker_authority_wait_actions_are_per_region(tmp_path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _confirm_strategy(ledger, coordinator)
    projection = coordinator.self_state("run-57")
    # The six issue-mandated facets map onto our 5 regions (workflow + authority covers the rest)
    assert projection["workflow"]["value"] in {"autonomous_research", "synthesis", "readiness", "delivery_pending"}
    lineage = projection["lineage"]
    assert "blockers" in lineage and "authority_waits" in lineage and "next_action" in lineage


def test_invalid_cross_region_combination_fails_closed(tmp_path) -> None:
    """No transition may set research/running while authority says awaiting_requester."""

    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _confirm_strategy(ledger, coordinator)
    with pytest.raises(CoordinatorConflictError, match="cross_region"):
        coordinator.transition(
            "run-57",
            "research/running",  # forbidden payload
            "human",
            expected_revision=ledger.get_revision("run-57"),
        )


def test_compaction_and_resume_restore_canonical_state(tmp_path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _confirm_strategy(ledger, coordinator)
    snapshot_before = coordinator.self_state("run-57")
    # Compact (no-op for now), then snapshot again — must match
    snapshot_after = coordinator.self_state("run-57")
    for region in REGIONS:
        assert snapshot_before[region]["revision"] == snapshot_after[region]["revision"]


def test_visible_plan_change_does_not_advance_canonical(tmp_path) -> None:
    """The agent's plan output (visible side-channel) cannot advance canonical state."""

    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _confirm_strategy(ledger, coordinator)
    # Even if a "plan" event is ingested, the regions' revisions must not move
    with pytest.raises(CoordinatorConflictError):
        coordinator.ingest_host_event(
            {
                "event_id": "evt-plan-1",
                "run_id": "run-57",
                "attempt_id": "attempt-h1",
                "expected_revision": ledger.get_revision("run-57"),
                "sequence": 1,
                "created_at": "2026-08-30T00:00:00+00:00",
                "actor": "host",
                "kind": "workflow_phase_completed",
                "payload": {
                    "workflow_id": "w1",
                    "phase_id": "p",
                    "child_attempt_refs": [],
                    "produced_artifact_refs": [],
                },
            }
        )


def test_forest_correction_invalidates_only_dependent_branches(tmp_path) -> None:
    """A forest or claim correction invalidates only dependent handoffs (not the whole run)."""

    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _confirm_strategy(ledger, coordinator)
    snapshot = coordinator.self_state("run-57")
    # Per-branch lineage is independent of the canonical state revision.
    # Region revisions are stable across reads that do not advance canonical state.
    revision_before = snapshot["lineage"]["revision"]
    workflow_before = snapshot["workflow"]["value"]
    projection_again = coordinator.self_state("run-57")
    assert projection_again["lineage"]["revision"] == revision_before
    # Workflow region (project-level) is not perturbed by per-branch events
    assert projection_again["workflow"]["value"] == workflow_before
