from __future__ import annotations

import pytest

from research_tree.growth import (
    BRANCH_TURN_LIMITS,
    BranchHandoff,
    BranchState,
    GrowthError,
    branch_turn_limit_exceeded,
    compute_readiness_delta,
    per_branch_turn_limit,
    seal_branch,
)


def branch(
    branch_id: str,
    *,
    status: str = "active",
    node_count: int = 1,
    revision: int = 1,
    turns: int = 0,
) -> BranchState:
    return BranchState.create(
        branch_id=branch_id,
        status=status,
        node_count=node_count,
        revision=revision,
        last_delta_at="2026-08-30T00:00:00+00:00",
        per_branch_turn_count=turns,
    )


def test_growth_increases_node_count_is_not_readiness_violation() -> None:
    before = (branch("b-1", node_count=2),)
    after = (branch("b-1", node_count=7, revision=2), branch("b-2", node_count=3))

    delta = compute_readiness_delta(before, after, {})

    assert delta.is_progress is True
    assert delta.delta_count >= 2
    assert "model" in delta.kinds
    assert delta.violations == ()


def test_readiness_is_delta_driven() -> None:
    unresolved = (branch("b-1", node_count=40),)

    stalled = compute_readiness_delta(unresolved, unresolved, {})
    moved = compute_readiness_delta(unresolved, unresolved, {"b-1": ("blocker",)})

    assert stalled.is_progress is False
    assert stalled.delta_count == 0
    assert moved.is_progress is True
    assert moved.kinds == ("blocker",)
    # Unresolved node counts never enter the readiness verdict.
    assert moved.violations == ()


def test_single_branch_handoff_does_not_close_siblings() -> None:
    branches = (branch("b-1"), branch("b-2"), branch("b-3"))
    handoff = BranchHandoff.create(
        branch_id="b-2",
        outcome="resolved",
        lineage_refs=("finding-9",),
        delta_summary="scope resolved from independent source",
    )

    sealed = seal_branch(branches, handoff)

    by_id = {item.branch_id: item for item in sealed}
    assert by_id["b-2"].status == "handed_off"
    assert [item.branch_id for item in sealed if item.status == "active"] == ["b-1", "b-3"]


def test_per_branch_turn_limit_independent_of_siblings() -> None:
    exhausted = branch("b-1", turns=BRANCH_TURN_LIMITS["active"])
    fresh = branch("b-2", turns=0)

    assert per_branch_turn_limit(exhausted) == BRANCH_TURN_LIMITS["active"]
    assert branch_turn_limit_exceeded(exhausted) is True
    assert branch_turn_limit_exceeded(fresh) is False
    assert per_branch_turn_limit(branch("b-3", status="stalled")) < BRANCH_TURN_LIMITS["active"]


def test_branch_handoff_carries_per_branch_outcome_and_lineage() -> None:
    handoff = BranchHandoff.create(
        branch_id="b-1",
        outcome="branch",
        lineage_refs=("node-1", "node-2"),
        delta_summary="new root discovered",
    )

    payload = handoff.to_dict()

    assert payload["branch_id"] == "b-1"
    assert payload["outcome"] == "branch"
    assert payload["lineage_refs"] == ["node-1", "node-2"]
    assert payload["delta_summary"] == "new root discovered"
    with pytest.raises(GrowthError):
        BranchHandoff.create(branch_id="b-1", outcome="finished", lineage_refs=(), delta_summary="x")


def test_vague_intent_with_discoveries_progresses() -> None:
    current = (branch("b-1", node_count=1),)
    progressed = 0
    for cycle in range(5):
        grown = (
            *(
                item.with_growth(node_count=item.node_count + 2, last_delta_at=f"2026-08-30T00:0{cycle}:00+00:00")
                for item in current
            ),
            branch(f"b-new-{cycle}", node_count=1),
        )
        delta = compute_readiness_delta(current, grown, {"b-1": ("evidence",)})
        assert delta.violations == ()
        progressed += delta.delta_count
        current = grown

    assert progressed >= 5
    assert len(current) == 6


def test_existing_callers_unaffected_when_opt_in_flag_absent(tmp_path) -> None:
    from research_tree.alignment_protocol import AlignmentProtocol
    from research_tree.run_ledger import RunLedger

    ledger = RunLedger(tmp_path)
    ledger.create_run("run-318")
    service = AlignmentProtocol(ledger, "run-318")

    baseline = service.readiness()

    assert set(baseline) == {"ready", "fields", "reasons", "digest", "belief_refs"}
    assert baseline["ready"] is False

    growth = service.growth_aware_readiness(
        branches_before=(branch("b-1"),),
        branches_after=(branch("b-1", node_count=4, revision=2),),
        evidence_deltas={"b-1": ("evidence",)},
    )

    assert growth["digest"] == baseline["digest"]
    assert growth["growth_aware"] is True
    assert growth["readiness_delta"]["is_progress"] is True
