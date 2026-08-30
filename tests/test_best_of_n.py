"""Issue #334: best-of-N candidate answers for high-impact decisions."""

from __future__ import annotations

import pytest

from research_tree.best_of_n import (
    Candidate,
    CandidatePool,
    close_p0_slot_with_single_candidate,
    select_candidate,
)


def test_p0_slot_closed_with_single_candidate_without_record_raises() -> None:
    candidates = [
        Candidate(id="c1", kind="method", method="repository", score=0.9, basis_refs=("e1",), rationale="direct")
    ]
    with pytest.raises(ValueError, match="single_candidate"):
        close_p0_slot_with_single_candidate(
            slot_id="slot-1",
            priority="P0",
            candidates=candidates,
        )


def test_p0_slot_closed_with_single_candidate_when_recorded_succeeds() -> None:
    candidates = [
        Candidate(id="c1", kind="method", method="repository", score=0.9, basis_refs=("e1",), rationale="direct")
    ]
    result = close_p0_slot_with_single_candidate(
        slot_id="slot-1",
        priority="P0",
        candidates=candidates,
        degradation_recorded=True,
    )
    assert result.selected_candidate_id == "c1"
    assert result.degradation_recorded is True


def test_non_p0_slot_allows_single_candidate() -> None:
    candidates = [
        Candidate(id="c1", kind="method", method="repository", score=0.9, basis_refs=("e1",), rationale="direct")
    ]
    result = close_p0_slot_with_single_candidate(
        slot_id="slot-1",
        priority="P2",
        candidates=candidates,
    )
    assert result.selected_candidate_id == "c1"


def test_select_candidate_picks_highest_score_with_rationale() -> None:
    pool = CandidatePool(
        candidates=[
            Candidate(id="c1", kind="method", method="A", score=0.5, basis_refs=("e1",), rationale="r1"),
            Candidate(id="c2", kind="method", method="B", score=0.9, basis_refs=("e2",), rationale="r2"),
            Candidate(id="c3", kind="method", method="C", score=0.7, basis_refs=("e3",), rationale="r3"),
        ]
    )
    result = select_candidate(pool, tie_break="deterministic")
    assert result.selected_candidate_id == "c2"
    assert result.rationale == "r2"


def test_candidate_pool_requires_diversity_when_independence_declared() -> None:
    candidates = [
        Candidate(id="c1", kind="method", method="A", score=0.9, basis_refs=("e1",), rationale="r1"),
        Candidate(id="c2", kind="method", method="A", score=0.8, basis_refs=("e1",), rationale="r2"),
    ]
    with pytest.raises(ValueError, match="independence"):
        CandidatePool(candidates=candidates, require_method_independence=True)


def test_select_candidate_records_persistence_payload() -> None:
    pool = CandidatePool(
        candidates=[
            Candidate(id="c1", kind="method", method="A", score=0.9, basis_refs=("e1",), rationale="r1"),
            Candidate(id="c2", kind="method", method="B", score=0.8, basis_refs=("e2",), rationale="r2"),
        ]
    )
    result = select_candidate(pool, tie_break="deterministic")
    payload = result.persistence_payload()
    assert payload["candidate_count"] == 2
    assert payload["selected_id"] == "c1"
    assert payload["score"] == 0.9
    assert payload["method_independence"] == "declared"


def test_human_brief_summary_records_n_and_reason() -> None:
    pool = CandidatePool(
        candidates=[
            Candidate(id="c1", kind="method", method="A", score=0.9, basis_refs=("e1",), rationale="r1"),
            Candidate(id="c2", kind="method", method="B", score=0.8, basis_refs=("e2",), rationale="r2"),
        ]
    )
    result = select_candidate(pool, tie_break="deterministic")
    summary = result.human_brief_summary()
    assert "2 candidates were compared" in summary
    assert "A" in summary and "r1" in summary
