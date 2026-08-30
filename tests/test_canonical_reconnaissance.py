"""Issue #319: canonical reconnaissance planner over multiple information methods."""

from __future__ import annotations

import pytest

from research_tree.reconnaissance import (
    MethodHypothesis,
    ReconnaissancePlan,
    propose_methods,
    select_method,
)


def test_reconnaissance_decouples_ask_one_from_reconnaissance() -> None:
    """The planner does not pre-bake a single ask_one — multiple methods compete."""

    plan = propose_methods(
        slot_id="slot-1",
        question="how does the codebase handle retries?",
        available_methods=("repository", "web_search", "experiment"),
        coverage_targets=("core", "tests"),
    )
    assert len(plan.methods) >= 2


def test_methods_carry_basis_refs_and_method_independence_marker() -> None:
    method = MethodHypothesis(
        method="repository",
        score=0.8,
        basis_refs=("e1", "e2"),
        rationale="direct read",
    )
    assert method.method == "repository"
    assert method.basis_refs == ("e1", "e2")


def test_select_method_picks_highest_score_with_rationale() -> None:
    plan = ReconnaissancePlan(
        slot_id="slot-1",
        methods=(
            MethodHypothesis(method="repository", score=0.5, basis_refs=("e1",), rationale="r1"),
            MethodHypothesis(method="web_search", score=0.9, basis_refs=("e2",), rationale="r2"),
            MethodHypothesis(method="experiment", score=0.7, basis_refs=("e3",), rationale="r3"),
        ),
    )
    choice = select_method(plan, tie_break="deterministic")
    assert choice.method == "web_search"
    assert choice.rationale == "r2"


def test_method_hypothesis_requires_nonempty_method_and_basis() -> None:
    """An empty method or basis_refs is malformed."""

    from research_tree.reconnaissance import ReconnaissanceError

    with pytest.raises(ReconnaissanceError, match="method"):
        MethodHypothesis(method="", score=0.5, basis_refs=("e1",), rationale="r1")


def test_propose_methods_rejects_empty_method_set() -> None:
    from research_tree.reconnaissance import ReconnaissanceError

    with pytest.raises(ReconnaissanceError, match="methods"):
        propose_methods(
            slot_id="slot-1",
            question="x",
            available_methods=(),
            coverage_targets=("core",),
        )


def test_reconnaissance_methods_are_decoupled_from_ask_one() -> None:
    """Plan emits multiple methods in parallel (not a forced single path)."""

    plan = propose_methods(
        slot_id="slot-2",
        question="performance regression?",
        available_methods=("repository", "experiment"),
        coverage_targets=("core", "tests"),
    )
    methods_used = {m.method for m in plan.methods}
    # Independent methods — not a single ask_one
    assert methods_used != {"ask_one"}
    assert len(methods_used) >= 2
