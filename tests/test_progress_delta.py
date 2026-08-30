"""Issue #329: progress projection is delta-oriented; recoverable failures aggregate.
Issue #387: aggregate_failures returns one group per kind; project_delta routes
decision-relevant groups via DECISION_RELEVANT_AUTHORITIES.
"""

from __future__ import annotations

import pytest

from research_tree.progress_delta import (
    DECISION_RELEVANT_AUTHORITIES,
    FailureRecord,
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
    groups = aggregate_failures(
        [
            FailureRecord(kind="api_timeout", severity="transient", count=1),
            FailureRecord(kind="api_timeout", severity="transient", count=1),
            FailureRecord(kind="api_timeout", severity="transient", count=1),
        ]
    )
    assert len(groups) == 1
    group = groups[0]
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
    assert "changed_decision" in projection["deltas"]


def test_user_expand_failure_group_receives_raw_receipt_refs() -> None:
    failures = [
        FailureRecord(kind="api_timeout", severity="transient", count=1, receipt_ref="receipt-1"),
        FailureRecord(kind="api_timeout", severity="transient", count=1, receipt_ref="receipt-2"),
        FailureRecord(kind="api_timeout", severity="transient", count=1, receipt_ref="receipt-3"),
    ]
    groups = aggregate_failures(failures)
    assert len(groups) == 1
    group = groups[0]
    assert group.receipt_refs == ("receipt-1", "receipt-2", "receipt-3")
    assert group.kind == "api_timeout"


# ---------------------------------------------------------------------------
# Issue #387 — multi-kind aggregation + decision-relevant promotion
# ---------------------------------------------------------------------------


def test_aggregate_failures_returns_one_group_per_kind() -> None:
    """Three different failure kinds must each produce their own ProjectedFailureGroup.

    Regression for: aggregate_failures used `first_kind = next(iter(grouped))`
    which silently dropped all kinds except the first one encountered.
    """
    failures = [
        FailureRecord(kind="api_timeout", severity="transient", count=1),
        FailureRecord(kind="rate_limit", severity="transient", count=2),
        FailureRecord(kind="auth_expired", severity="fatal", count=1),
    ]
    groups = aggregate_failures(failures)
    assert len(groups) == 3
    # Sorted by kind for determinism — assert set membership for clarity.
    kinds = {g.kind for g in groups}
    assert kinds == {"api_timeout", "rate_limit", "auth_expired"}
    counts_by_kind = {g.kind: g.count for g in groups}
    assert counts_by_kind == {"api_timeout": 1, "rate_limit": 2, "auth_expired": 1}


def test_project_delta_promotes_decision_relevant_failures() -> None:
    """Groups whose authority is in DECISION_RELEVANT_AUTHORITIES go to decision_relevant_failures.

    Other groups go to internal_failures. Regression for: project_delta declared
    the two fields but never populated them — they were decorative.
    """
    failures = (
        FailureRecord(kind="api_timeout", severity="transient", count=1, authority=""),
        FailureRecord(
            kind="auth_expired",
            severity="fatal",
            count=1,
            authority="auth_expired",
        ),
    )
    delta = ProgressDelta(
        new_evidence=("evidence-a",),
        failures=failures,
    )
    projection = project_delta(delta)

    kinds_in_decision_relevant = {g.kind for g in projection["decision_relevant_failures"]}
    kinds_in_internal = {g.kind for g in projection["internal_failures"]}

    assert "auth_expired" in kinds_in_decision_relevant
    assert "api_timeout" in kinds_in_internal
    # Sanity: authority is on the group itself (preserved through aggregation).
    auth_group = next(g for g in projection["decision_relevant_failures"] if g.kind == "auth_expired")
    assert auth_group.authority == "auth_expired"


def test_aggregate_failures_empty_raises_value_error() -> None:
    """Empty input is a contract violation — must raise ValueError with the documented message.

    Regression for: contract preservation after the multi-kind refactor.
    """
    with pytest.raises(ValueError, match="aggregate_failures requires at least one entry"):
        aggregate_failures([])


def test_decision_relevant_authorities_constant_is_used_by_routing() -> None:
    """DECISION_RELEVANT_AUTHORITIES is no longer a dead constant — it's the routing key.

    Smoke test: every authority in the frozenset must be routable into
    decision_relevant_failures (and only those authorities are routable there).
    """
    assert DECISION_RELEVANT_AUTHORITIES == frozenset({"budget_exceeded", "auth_expired", "approval_required"})
    # An authority outside the frozenset must NOT route into decision_relevant_failures.
    failures = (FailureRecord(kind="some_kind", severity="transient", count=1, authority="not_a_decision_authority"),)
    delta = ProgressDelta(new_evidence=("e",), failures=failures)
    projection = project_delta(delta)
    assert projection["decision_relevant_failures"] == ()
    assert len(projection["internal_failures"]) == 1
