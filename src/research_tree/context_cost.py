"""Evaluation-only diagnostics for context acquisition cost receipts."""

from __future__ import annotations

from typing import Any, Mapping


class ContextCostDiagnosticError(ValueError):
    """Raised when a receipt cannot support a context-cost diagnostic."""


def _number(receipt: Mapping[str, Any], key: str) -> float:
    value = receipt.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContextCostDiagnosticError(f"receipt {key} must be numeric")
    return float(value)


def _coverage(receipt: Mapping[str, Any]) -> int:
    coverage = receipt.get("evidence_coverage")
    if not isinstance(coverage, Mapping):
        raise ContextCostDiagnosticError("receipt evidence_coverage must be an object")
    value = coverage.get("unique_digest_ranges")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContextCostDiagnosticError("receipt evidence coverage must be a nonnegative integer")
    return value


def evaluate_context_cost(
    baseline_receipt: Mapping[str, Any],
    candidate_receipt: Mapping[str, Any],
    *,
    minimum_duplicate_reduction: float = 0.7,
) -> dict[str, Any]:
    """Compare context cost without assigning semantic quality or completion."""

    if (
        isinstance(minimum_duplicate_reduction, bool)
        or not isinstance(minimum_duplicate_reduction, (int, float))
        or minimum_duplicate_reduction < 0
        or minimum_duplicate_reduction > 1
    ):
        raise ContextCostDiagnosticError("minimum_duplicate_reduction must be a number between zero and one")
    baseline_ratio = _number(baseline_receipt, "duplicate_read_ratio")
    candidate_ratio = _number(candidate_receipt, "duplicate_read_ratio")
    baseline_coverage = _coverage(baseline_receipt)
    candidate_coverage = _coverage(candidate_receipt)
    duplicate_reduction = 0.0 if baseline_ratio == 0 else (baseline_ratio - candidate_ratio) / baseline_ratio
    coverage_retained = candidate_coverage >= baseline_coverage
    material_reduction = duplicate_reduction >= minimum_duplicate_reduction
    return {
        "kind": "context-cost-diagnostic",
        "diagnostic_only": True,
        "semantic_quality": "not_assessed",
        "completion_authority": "none",
        "baseline_duplicate_read_ratio": baseline_ratio,
        "candidate_duplicate_read_ratio": candidate_ratio,
        "duplicate_reduction": duplicate_reduction,
        "minimum_duplicate_reduction": float(minimum_duplicate_reduction),
        "baseline_unique_digest_ranges": baseline_coverage,
        "candidate_unique_digest_ranges": candidate_coverage,
        "coverage_retained": coverage_retained,
        "material_duplicate_reduction": material_reduction,
        "status": "observed" if material_reduction and coverage_retained else "not_met",
    }
