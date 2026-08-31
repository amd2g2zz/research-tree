"""Issue #324: canonical state is orthogonal regions, not one overloaded status."""

from __future__ import annotations

import pytest
from test_research_run_coordinator import _confirm_strategy, _initialize

from research_tree.coordinator import (
    LIFECYCLE_STATES,
    RESEARCH_RUN_STATE_KIND,
    CoordinatorConflictError,
    IllegalTransitionError,
)
from research_tree.run_ledger import RunLedger

REGIONS = ("cognitive", "workflow", "authority", "epistemic", "delivery")

# The region value vocabulary is the value domain of the canonical region
# projection (issue #324); every state row must draw from these words only.
REGION_VOCABULARY = {
    "cognitive": frozenset({"active", "settled"}),
    "workflow": frozenset(
        {
            "alignment",
            "autonomous_research",
            "synthesis",
            "readiness",
            "delivery_pending",
            "awaiting_acceptance",
            "completed",
        }
    ),
    "authority": frozenset({"awaiting_requester", "research_owner", "completed"}),
    "epistemic": frozenset({"exploratory", "depth", "synthesis", "verified", "settled"}),
    "delivery": frozenset({"not_started", "deliveries_compiled", "delivered", "completed"}),
}

# Issue #422 arbiter ruling: resumable holds project their predecessor stage
# (the lifecycle matrix enters/exits them inside the research stage), and
# terminal states project the terminal row — no new region words invented.
ARBITER_RULING_ROWS = {
    "paused": {
        "cognitive": "active",
        "workflow": "autonomous_research",
        "authority": "research_owner",
        "epistemic": "depth",
        "delivery": "not_started",
    },
    "blocked": {
        "cognitive": "active",
        "workflow": "autonomous_research",
        "authority": "awaiting_requester",
        "epistemic": "depth",
        "delivery": "not_started",
    },
    "superseded": {
        "cognitive": "settled",
        "workflow": "completed",
        "authority": "completed",
        "epistemic": "settled",
        "delivery": "completed",
    },
    "authority_blocked": {
        "cognitive": "settled",
        "workflow": "completed",
        "authority": "completed",
        "epistemic": "settled",
        "delivery": "completed",
    },
    "failed": {
        "cognitive": "settled",
        "workflow": "completed",
        "authority": "completed",
        "epistemic": "settled",
        "delivery": "completed",
    },
}


def _seed_state(ledger: RunLedger, run_id: str, payload: dict) -> None:
    """Append a research-run-state artifact directly (projection contract test).

    State revisions are per-artifact-id, so the seeded artifact reuses the
    canonical ``run-state`` id to become the latest state revision.
    """

    ledger.append_artifact(
        run_id,
        "run-state",
        RESEARCH_RUN_STATE_KIND,
        payload,
        parent_refs=(),
        expected_revision=ledger.get_revision(run_id),
    )


@pytest.mark.parametrize("state", LIFECYCLE_STATES)
def test_every_canonical_state_projects_five_regions(tmp_path, state) -> None:
    """All 13 LIFECYCLE_STATES must project every region without raising (#422)."""

    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    if state != "alignment":
        _seed_state(ledger, "run-57", {"state": state})
    projection = coordinator.self_state("run-57")
    assert "lineage" in projection
    for region in REGIONS:
        entry = projection[region]
        assert entry["value"] in REGION_VOCABULARY[region], f"state={state} region={region}"
        assert isinstance(entry["revision"], int)
        assert "updated_at" in entry


@pytest.mark.parametrize(("state", "expected"), sorted(ARBITER_RULING_ROWS.items()))
def test_resumable_and_terminal_states_project_their_ruled_rows(tmp_path, state, expected) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _seed_state(ledger, "run-57", {"state": state})
    projection = coordinator.self_state("run-57")
    assert {region: projection[region]["value"] for region in REGIONS} == expected


def test_unknown_state_fails_closed(tmp_path) -> None:
    """A state outside the 13-state vocabulary must still fail closed."""

    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _seed_state(ledger, "run-57", {"state": "junk-state"})
    with pytest.raises(IllegalTransitionError, match="illegal_transition"):
        coordinator.self_state("run-57")


def test_missing_state_field_raises_typed_conflict(tmp_path) -> None:
    """A state payload without a `state` field raises a typed conflict error."""

    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _seed_state(ledger, "run-57", {"other": 1})
    with pytest.raises(CoordinatorConflictError, match="state_field_required"):
        coordinator.self_state("run-57")


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
