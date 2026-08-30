"""Issue #330: Human Brief adds organizational operating-model projection."""

from __future__ import annotations

from research_tree.operating_model import (
    OperatingModelProjection,
    RoleAssignment,
    SLATier,
    build_operating_model,
)


def test_operating_model_captures_required_fields() -> None:
    """Per issue #330: role capacity, owner assignments, SLA, escalation time,
    concurrent-project limits, meeting replacement, adoption metrics."""

    model = OperatingModelProjection(
        roles=(
            RoleAssignment(role="research_lead", owner="alice", capacity=2.0, unit="FTE"),
            RoleAssignment(role="domain_expert", owner="bob", capacity=1.0, unit="FTE"),
        ),
        sla=SLATier(tier="standard", target_response="24h", escalation_after="72h"),
        concurrent_project_limit=3,
        meeting_replacement_per_week=2.0,
        adoption_metrics={"weekly_run_count": 0, "median_satisfaction": 0.0, "knowledge_reuse_pct": 0.0},
    )
    for field in ("roles", "sla", "concurrent_project_limit", "meeting_replacement_per_week", "adoption_metrics"):
        assert hasattr(model, field), f"operating model missing field: {field}"


def test_build_operating_model_yields_structured_record_from_inputs() -> None:
    roles = (RoleAssignment(role="research_lead", owner="alice", capacity=2.0, unit="FTE"),)
    sla = SLATier(tier="standard", target_response="24h", escalation_after="72h")
    model = build_operating_model(
        roles=roles,
        sla=sla,
        concurrent_project_limit=3,
        meeting_replacement_per_week=2.0,
    )
    assert model.roles == roles
    assert model.sla == sla
    assert model.concurrent_project_limit == 3
    assert model.meeting_replacement_per_week == 2.0


def test_operating_model_serializes_to_dict() -> None:
    model = build_operating_model(
        roles=(RoleAssignment(role="r", owner="o", capacity=1.0, unit="FTE"),),
        sla=SLATier(tier="standard", target_response="24h", escalation_after="72h"),
        concurrent_project_limit=1,
        meeting_replacement_per_week=1.0,
    )
    snapshot = model.to_dict()
    assert snapshot["roles"][0]["role"] == "r"
    assert snapshot["sla"]["tier"] == "standard"
    assert snapshot["concurrent_project_limit"] == 1


def test_operating_model_carries_zero_defaults_for_initial_deployment() -> None:
    """For a fresh installation, adoption metrics start at zero (not fabricated)."""

    model = build_operating_model(
        roles=(),
        sla=SLATier(tier="none", target_response="n/a", escalation_after="n/a"),
        concurrent_project_limit=0,
        meeting_replacement_per_week=0.0,
    )
    assert model.adoption_metrics == {"weekly_run_count": 0, "median_satisfaction": 0.0, "knowledge_reuse_pct": 0.0}


def test_role_assignment_serializes_with_all_fields() -> None:
    role = RoleAssignment(role="research_lead", owner="alice", capacity=2.0, unit="FTE")
    assert role.to_dict() == {"role": "research_lead", "owner": "alice", "capacity": 2.0, "unit": "FTE"}
