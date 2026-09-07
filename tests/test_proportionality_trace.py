"""Proportionality-assessment trace tests (issue #498).

The necessity/proportionality check becomes a verifiable trace type: required
on proposal-shaped gaps, presence+schema verified by the engine, content
composed by the prompt layer (layer 1 of the three-layer ladder; the waiver
and compile-time rejection layers already exist).
"""

from __future__ import annotations

import pytest

from research_tree.alignment_graph import _gap_required_traces
from research_tree.turn_contract import (
    DEFAULT_TRACE_REGISTRY,
    INITIAL_TRACE_TYPES,
    ContractTerms,
    CostCap,
    DuplicateTraceTypeError,
    TraceType,
    verify_traces,
)


def assessment_payload(**overrides) -> dict:
    payload = {
        "direction": "over",
        "finding": "String matching does not need a CNN pipeline.",
        "alternative": "A regex or suffix-automaton suffices for the stated scale.",
        "reframing": "Nearest feasible framing: exact matching with documented thresholds.",
    }
    payload.update(overrides)
    return payload


def _terms(required) -> ContractTerms:
    return ContractTerms(
        target_gap="gap.intent.primary",
        required_traces=required,
        cost_cap=CostCap(response_class="discrimination", max_sentences=1),
        taboos=(),
    )


def test_registry_contains_the_proportionality_trace_type() -> None:
    assert "proportionality_assessment" in DEFAULT_TRACE_REGISTRY.names()
    entry = DEFAULT_TRACE_REGISTRY.get("proportionality_assessment")
    assert set(entry.required_fields) == {"direction", "finding", "alternative", "reframing"}
    assert INITIAL_TRACE_TYPES == DEFAULT_TRACE_REGISTRY.names()


def test_duplicate_registration_of_the_trace_is_still_rejected() -> None:
    with pytest.raises(DuplicateTraceTypeError, match="proportionality_assessment"):
        DEFAULT_TRACE_REGISTRY.register(TraceType(name="proportionality_assessment", required_fields=("direction",)))


def test_verification_checks_presence_and_schema_only() -> None:
    satisfied = verify_traces(
        _terms(("option-set", "proportionality_assessment")),
        (
            {"type": "option-set", "payload": {"options": ["A", "B"]}},
            {"type": "proportionality_assessment", "payload": assessment_payload()},
        ),
    )
    assert satisfied == ("option-set", "proportionality_assessment")
    with pytest.raises(Exception, match="alternative"):
        verify_traces(
            _terms(("option-set", "proportionality_assessment")),
            (
                {"type": "option-set", "payload": {"options": ["A", "B"]}},
                {
                    "type": "proportionality_assessment",
                    "payload": {k: v for k, v in assessment_payload().items() if k != "alternative"},
                },
            ),
        )


def test_proposal_shaped_gaps_require_the_assessment() -> None:
    node = {"id": "n1", "status": "open", "human_only": True}
    assert _gap_required_traces(node, reopened=False, cap=_cap()) == (
        "option-set",
        "proportionality_assessment",
    )
    assert _gap_required_traces(node, reopened=False, cap=_cap("generation")) == (
        "possibility-survey",
        "proportionality_assessment",
    )


def test_misunderstood_intent_gaps_do_not_require_the_assessment() -> None:
    node = {"id": "n1", "status": "disputed", "human_only": True}
    assert _gap_required_traces(node, reopened=False, cap=_cap()) == ("guess-statement",)
    assert _gap_required_traces(node, reopened=True, cap=_cap()) == ("guess-statement",)


def _cap(response_class: str = "discrimination") -> CostCap:
    return CostCap(response_class=response_class, max_sentences=1)
