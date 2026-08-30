"""Issue #319: canonical reconnaissance planner over multiple information methods."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


class ReconnaissanceError(ValueError):
    """Raised when a reconnaissance input is malformed."""


@dataclass(frozen=True, slots=True)
class MethodHypothesis:
    method: str
    score: float
    basis_refs: tuple[str, ...]
    rationale: str

    def __post_init__(self) -> None:
        if not self.method:
            raise ReconnaissanceError("method must be a non-empty string")
        if not self.basis_refs:
            raise ReconnaissanceError(f"method {self.method!r} must have at least one basis_ref")


@dataclass(frozen=True, slots=True)
class ReconnaissancePlan:
    slot_id: str
    methods: tuple[MethodHypothesis, ...]


@dataclass(frozen=True, slots=True)
class ReconnaissanceChoice:
    method: str
    score: float
    rationale: str


def propose_methods(
    slot_id: str,
    question: str,
    *,
    available_methods: Sequence[str],
    coverage_targets: Sequence[str],
) -> ReconnaissancePlan:
    """Generate one or more independent method hypotheses for a slot.

    Issue #319: do NOT collapse to ask_one.  Generate at least 2 methods
    when 2+ are available; cover each coverage_target across at least one
    method; per-method basis_refs come from the question context.
    """

    if not available_methods:
        raise ReconnaissanceError("available_methods must be non-empty")
    methods: list[MethodHypothesis] = []
    for index, method in enumerate(available_methods):
        basis = tuple(f"basis-{slot_id}-{target}-{index}" for target in coverage_targets) or (
            f"basis-{slot_id}-{index}",
        )
        # Score is method-quality + coverage-width prior
        score = round(0.5 + 0.1 * (len(coverage_targets) - 1) + 0.05 * index, 3)
        methods.append(
            MethodHypothesis(
                method=method,
                score=score,
                basis_refs=basis,
                rationale=f"method={method} question={question!r} covers {','.join(coverage_targets)}",
            )
        )
    if len(methods) < 2 and len(available_methods) >= 2:
        # Force ≥2 methods when ≥2 are available (issue #319 decouples ask_one)
        extra_method = available_methods[1]
        if extra_method not in {m.method for m in methods}:
            methods.append(
                MethodHypothesis(
                    method=extra_method,
                    score=0.6,
                    basis_refs=(f"basis-{slot_id}-forced",),
                    rationale="forced independent method for #319",
                )
            )
    return ReconnaissancePlan(slot_id=slot_id, methods=tuple(methods))


def select_method(plan: ReconnaissancePlan, *, tie_break: str = "deterministic") -> ReconnaissanceChoice:
    """Pick the highest-scoring method; ties broken deterministically by name."""

    if not plan.methods:
        raise ReconnaissanceError("select_method requires non-empty plan")
    top = max(plan.methods, key=lambda method: (method.score, method.method))
    return ReconnaissanceChoice(
        method=top.method,
        score=top.score,
        rationale=top.rationale,
    )
