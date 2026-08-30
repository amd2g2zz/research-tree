"""Issue #334: best-of-N candidate answers for high-impact decisions.

A P0 slot closed by a single method/candidate without a recorded
single-candidate degradation is a closure violation.  The runtime
generates, scores, and selects among candidates with full rationale;
Human Brief surfaces the comparison count + winning rationale.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True, slots=True)
class Candidate:
    """One candidate answer for a Decision Slot closure."""

    id: str
    kind: str
    method: str
    score: float
    basis_refs: tuple[str, ...]
    rationale: str


@dataclass(frozen=True, slots=True)
class CandidatePool:
    """A pool of candidates with optional method-independence requirement."""

    candidates: tuple[Candidate, ...]
    require_method_independence: bool = True

    def __post_init__(self) -> None:
        if not self.candidates:
            raise ValueError("candidates pool must be non-empty")
        if self.require_method_independence:
            methods = {candidate.method for candidate in self.candidates}
            if len(methods) < len(self.candidates):
                raise ValueError("independence violated: duplicate method in pool")


@dataclass(frozen=True, slots=True)
class CandidateSelection:
    """The selected candidate + audit metadata persisted per Decision Slot."""

    selected_candidate_id: str
    selected_method: str
    score: float
    rationale: str
    candidate_count: int
    tie_break: str
    method_independence: str

    def persistence_payload(self) -> dict[str, object]:
        return {
            "selected_id": self.selected_candidate_id,
            "selected_method": self.selected_method,
            "score": self.score,
            "rationale": self.rationale,
            "candidate_count": self.candidate_count,
            "tie_break": self.tie_break,
            "method_independence": self.method_independence,
        }

    def human_brief_summary(self) -> str:
        return (
            f"{self.candidate_count} candidates were compared; "
            f"this one won because {self.method_independence} selection "
            f"chose method={self.selected_method} "
            f"(rationale: {self.rationale})."
        )


def select_candidate(pool: CandidatePool, *, tie_break: str = "deterministic") -> CandidateSelection:
    """Pick the highest-scoring candidate; ties broken deterministically."""

    if not pool.candidates:
        raise ValueError("select_candidate requires non-empty pool")
    top = max(pool.candidates, key=lambda candidate: (candidate.score, candidate.id))
    independence = "declared" if pool.require_method_independence else "not_declared"
    return CandidateSelection(
        selected_candidate_id=top.id,
        selected_method=top.method,
        score=top.score,
        rationale=top.rationale,
        candidate_count=len(pool.candidates),
        tie_break=tie_break,
        method_independence=independence,
    )


@dataclass(frozen=True, slots=True)
class SlotClosureResult:
    """Result of closing a Decision Slot, possibly with single-candidate degradation."""

    selected_candidate_id: str
    degradation_recorded: bool


def close_p0_slot_with_single_candidate(
    slot_id: str,
    priority: str,
    candidates: Sequence[Candidate],
    *,
    degradation_recorded: bool = False,
) -> SlotClosureResult:
    """Close a Decision Slot, enforcing best-of-N for P0 slots."""

    if not candidates:
        raise ValueError("candidates must be non-empty")
    if priority == "P0" and len(candidates) < 2 and not degradation_recorded:
        raise ValueError(
            f"single_candidate_degradation_required_for_P0_slot:{slot_id}: "
            "must record degradation or supply >=2 candidates"
        )
    return SlotClosureResult(
        selected_candidate_id=candidates[0].id,
        degradation_recorded=degradation_recorded,
    )
