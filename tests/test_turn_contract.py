"""Two-layer contract seam (issue #501, ADR-008).

Covers the contract-terms schema (target_gap / required_traces / cost_cap /
taboos), the frozen append-only trace-type registry (six initial types,
duplicate registration rejected), and the verify_traces primitive that fails
closed naming the exact missing term — presence and schema checks only,
never content quality.
"""

from __future__ import annotations

import pytest

from research_tree.turn_contract import (
    DEFAULT_TRACE_REGISTRY,
    ContractTerms,
    ContractTermsError,
    CostCap,
    DuplicateTraceTypeError,
    MissingTraceError,
    TraceRecordError,
    TraceType,
    TraceTypeRegistry,
    verify_traces,
)

INITIAL_TRACE_TYPES = (
    "concept-card",
    "counterargument",
    "evidence-delta",
    "guess-statement",
    "option-set",
    "possibility-survey",
)

NODE_GAP = "gap.intent.primary"
OPTION_SET_TRACE = {"type": "option-set", "payload": {"options": ["persistent-tree", "event-sourced"]}}
SURVEY_TRACE = {"type": "possibility-survey", "payload": {"possibilities": ["A", "B", "C"]}}


def _terms(**overrides: object) -> ContractTerms:
    values: dict[str, object] = {
        "target_gap": NODE_GAP,
        "required_traces": ("option-set",),
        "cost_cap": CostCap(response_class="discrimination", max_sentences=1),
        "taboos": ("gap.answered-1",),
    }
    values.update(overrides)
    return ContractTerms(**values)  # type: ignore[arg-type]


def _terms_dict(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "target_gap": NODE_GAP,
        "required_traces": ["option-set"],
        "cost_cap": {"response_class": "discrimination", "max_sentences": 1},
        "taboos": ["gap.answered-1"],
    }
    payload.update(overrides)
    return payload


# --- 1. Trace-type registry (tasks 1.1, 1.2) ---------------------------------


def test_default_registry_seeds_exactly_the_six_initial_types() -> None:
    assert DEFAULT_TRACE_REGISTRY.names() == INITIAL_TRACE_TYPES


def test_registering_duplicate_trace_type_is_rejected_and_names_it() -> None:
    duplicate = TraceType(name="option-set", required_fields=("options",))
    with pytest.raises(DuplicateTraceTypeError, match="option-set"):
        DEFAULT_TRACE_REGISTRY.register(duplicate)


def test_register_duplicate_inside_constructor_is_rejected() -> None:
    repeated = TraceType(name="counterargument", required_fields=("counterargument",))
    with pytest.raises(DuplicateTraceTypeError, match="counterargument"):
        TraceTypeRegistry((repeated, repeated))


def test_register_returns_new_registry_and_leaves_original_frozen() -> None:
    extra = TraceType(name="proportionality_assessment", required_fields=("direction",))
    extended = DEFAULT_TRACE_REGISTRY.register(extra)
    assert "proportionality_assessment" in extended.names()
    assert extended.names() == tuple(sorted([*INITIAL_TRACE_TYPES, "proportionality_assessment"]))
    assert DEFAULT_TRACE_REGISTRY.names() == INITIAL_TRACE_TYPES


# --- 2. Contract-terms schema (tasks 2.1-2.4) --------------------------------


def test_contract_terms_round_trip() -> None:
    terms = _terms()
    restored = ContractTerms.from_dict(terms.to_dict())
    assert restored == terms
    assert restored.to_dict()["schema_version"] == 1


def test_missing_field_is_rejected_and_named() -> None:
    payload = _terms_dict()
    del payload["required_traces"]
    with pytest.raises(ContractTermsError, match="required_traces"):
        ContractTerms.from_dict(payload)


def test_unknown_field_is_rejected_and_named() -> None:
    with pytest.raises(ContractTermsError, match="next_action"):
        ContractTerms.from_dict(_terms_dict(next_action="teach"))


def test_target_gap_must_be_an_alignment_graph_node_reference() -> None:
    with pytest.raises(ContractTermsError, match="target_gap"):
        _terms(target_gap="teach the user about storage engines")


def test_taboo_entries_must_be_unique_node_references() -> None:
    with pytest.raises(ContractTermsError, match="taboos"):
        _terms(taboos=("gap.a", "gap.a"))
    with pytest.raises(ContractTermsError, match="taboos"):
        _terms(taboos=("not a node id!",))


def test_required_traces_must_be_registered_and_unique() -> None:
    with pytest.raises(ContractTermsError, match="teach-the-user"):
        _terms(required_traces=("teach-the-user",))
    with pytest.raises(ContractTermsError, match="option-set"):
        _terms(required_traces=("option-set", "option-set"))


def test_cost_cap_rejects_unknown_response_class() -> None:
    with pytest.raises(ContractTermsError, match="response_class"):
        CostCap(response_class="persuasion", max_sentences=1)


def test_discrimination_cost_cap_is_exactly_one_sentence() -> None:
    with pytest.raises(ContractTermsError, match="max_sentences"):
        CostCap(response_class="discrimination", max_sentences=3)
    with pytest.raises(ContractTermsError, match="max_sentences"):
        CostCap(response_class="discrimination", max_sentences=None)


def test_generation_cost_cap_allows_free_text_or_positive_bound() -> None:
    assert CostCap(response_class="generation", max_sentences=None).to_dict() == {
        "response_class": "generation",
        "max_sentences": None,
    }
    with pytest.raises(ContractTermsError, match="max_sentences"):
        CostCap(response_class="generation", max_sentences=0)


# --- 3. verify_traces (tasks 3.1-3.3) ----------------------------------------


def test_missing_required_trace_fails_naming_the_exact_term() -> None:
    terms = _terms(required_traces=("possibility-survey", "option-set"))
    with pytest.raises(MissingTraceError, match="possibility-survey"):
        verify_traces(terms, [OPTION_SET_TRACE])


def test_unregistered_recorded_trace_type_fails_naming_it() -> None:
    with pytest.raises(TraceRecordError, match="teach-the-user"):
        verify_traces(_terms(), [{"type": "teach-the-user", "payload": {}}])


def test_recorded_trace_missing_declared_field_fails_naming_the_field() -> None:
    with pytest.raises(TraceRecordError, match="options"):
        verify_traces(_terms(), [{"type": "option-set", "payload": {"question": "which one?"}}])


def test_malformed_trace_record_fails_naming_the_shape() -> None:
    with pytest.raises(TraceRecordError, match="payload"):
        verify_traces(_terms(), [{"type": "option-set"}])


def test_satisfied_contract_verifies_and_returns_required_traces() -> None:
    terms = _terms(required_traces=("option-set", "possibility-survey"))
    satisfied = verify_traces(terms, [SURVEY_TRACE, OPTION_SET_TRACE])
    assert satisfied == ("option-set", "possibility-survey")


def test_verification_never_judges_payload_content() -> None:
    """ADR-008: the engine verifies that a trace exists, never what it says."""
    nonsense = {"type": "option-set", "payload": {"options": "随便什么文本都行，引擎不看内容"}}
    assert verify_traces(_terms(), [nonsense]) == ("option-set",)


def test_unrequired_registered_traces_may_accompany_the_turn() -> None:
    extra = {"type": "guess-statement", "payload": {"guess": "the user wants replayability"}}
    assert verify_traces(_terms(), [OPTION_SET_TRACE, extra]) == ("option-set",)
