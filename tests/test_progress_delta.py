"""Issue #329: progress projection is delta-oriented; recoverable failures aggregate."""

from __future__ import annotations

from research_tree.progress_delta import (
    ProgressDelta,
    aggregate_failures,
    project_delta,
)


def test_visible_progress_derived_from_canonical_delta_only() -> None:
    delta = ProgressDelta(
        new_evidence=("evidence-a",),
        changed_model=(),
        changed_decision=(),
        changed_phase=("autonomous_research",),
        new_blocker=(),
        changed_authority=(),
        changed_next_action=(),
    )
    projection = project_delta(delta)
    assert "new_evidence" in projection["deltas"]
    assert projection["phase"] == "autonomous_research"


def test_repeated_unchanged_context_collapses() -> None:
    delta_a = ProgressDelta(new_evidence=("evidence-a",), changed_phase=("autonomous_research",))
    delta_b = ProgressDelta(new_evidence=(), changed_phase=())
    # Same canonical snapshot → no second projection
    projection_a = project_delta(delta_a)
    projection_b = project_delta(delta_b)
    assert projection_b["deltas"] == ()
    # First one stays
    assert "new_evidence" in projection_a["deltas"]


def test_recoverable_tool_failures_aggregate_with_count() -> None:
    group = aggregate_failures(
        [
            ("api_timeout", "transient", 1),
            ("api_timeout", "transient", 1),
            ("api_timeout", "transient", 1),
        ]
    )
    assert group.kind == "api_timeout"
    assert group.count == 3
    assert group.severity == "transient"
    assert group.first_seen and group.last_seen


def test_user_visible_progress_only_for_decision_relevant_signals() -> None:
    delta = ProgressDelta(
        new_evidence=(),
        changed_model=(),
        changed_decision=(),
        changed_phase=(),
        new_blocker=("auth-expired",),
        changed_authority=(),
        changed_next_action=(),
    )
    projection = project_delta(delta)
    assert "new_blocker" in projection["deltas"]
    # Recoverable internal failures are not surfaced unless they change scope/authority/cost
    assert projection["internal_failures"] == ()


def test_recoverable_failure_scope_change_promotes_to_user_visible() -> None:
    delta = ProgressDelta(
        new_evidence=(),
        changed_model=(),
        changed_decision=("decision-1",),
        changed_phase=(),
        new_blocker=(),
        changed_authority=("budget_exceeded",),
        changed_next_action=(),
    )
    projection = project_delta(delta)
    assert "changed_authority" in projection["deltas"]
    assert "decision_relevant_failure" in projection["deltas"] or "changed_decision" in projection["deltas"]


def test_user_expand_failure_group_receives_raw_receipt_refs() -> None:
    failures = [
        ("api_timeout", "transient", 1, "receipt-1"),
        ("api_timeout", "transient", 1, "receipt-2"),
        ("api_timeout", "transient", 1, "receipt-3"),
    ]
    group = aggregate_failures(failures)
    assert group.receipt_refs == ("receipt-1", "receipt-2", "receipt-3")
    assert group.kind == "api_timeout"
