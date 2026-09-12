"""Transformation-trace tests (issue #499).

Three verifiable increments, none of them quote-ratio policing (the rejected
design): the registry grows the mid-research user-update trace types
(``digest-first``, ``viewpoint-hints`` reusing the material_alternatives /
trade_off schema shape), Finding Pack ingestion carries an optional but
strictly-validated ``transformation`` record, and the #493 turn-shape ratio
slot gains its documented semantics (composer-reported until #500 wires the
required digest-first trace for user-facing mid-research updates).
"""

from __future__ import annotations

import pytest

from research_tree.turn_contract import (
    DEFAULT_TRACE_REGISTRY,
    INITIAL_TRACE_TYPES,
    ContractTerms,
    CostCap,
    verify_traces,
)


def test_registry_carries_the_mid_research_update_trace_types() -> None:
    assert "digest-first" in DEFAULT_TRACE_REGISTRY.names()
    assert "viewpoint-hints" in DEFAULT_TRACE_REGISTRY.names()
    assert set(DEFAULT_TRACE_REGISTRY.get("digest-first").required_fields) == {
        "point",
        "decision_relevance",
        "source_pointer",
    }
    assert "alternatives" in DEFAULT_TRACE_REGISTRY.get("viewpoint-hints").required_fields
    assert INITIAL_TRACE_TYPES == DEFAULT_TRACE_REGISTRY.names()


def test_digest_first_trace_verifies_against_required_terms() -> None:
    terms = ContractTerms(
        target_gap="gap.mid.research",
        required_traces=("digest-first",),
        cost_cap=CostCap(response_class="discrimination", max_sentences=1),
        taboos=(),
    )
    satisfied = verify_traces(
        terms,
        (
            {
                "type": "digest-first",
                "payload": {
                    "point": "Engine X caps context at 200k tokens.",
                    "decision_relevance": "Bounds the viable retrieval designs.",
                    "source_pointer": "source:engine-x-design-doc",
                },
            },
        ),
    )
    assert satisfied == ("digest-first",)


def test_viewpoint_hints_trace_reuses_the_trade_off_schema_shape() -> None:
    terms = ContractTerms(
        target_gap="gap.mid.research",
        required_traces=("viewpoint-hints",),
        cost_cap=CostCap(response_class="generation", max_sentences=3),
        taboos=(),
    )
    satisfied = verify_traces(
        terms,
        (
            {
                "type": "viewpoint-hints",
                "payload": {
                    "alternatives": [
                        {"position": "Event-sourced state", "trade_off": "Durable but heavier recovery"},
                        {"position": "Snapshot state", "trade_off": "Simple but lossy"},
                    ],
                },
            },
        ),
    )
    assert satisfied == ("viewpoint-hints",)
    with pytest.raises(Exception, match="alternatives"):
        verify_traces(terms, ({"type": "viewpoint-hints", "payload": {}},))


def test_finding_pack_transformation_record_is_validated_and_persisted(tmp_path) -> None:
    """Ingestion carries the optional-but-strict transformation record (#499)."""

    import pytest
    from canonical_finding_fixture import canonical_context

    from research_tree import CanonicalFindingPackCompiler, InvalidFindingPackError

    ledger, resolver, _record, _model, _brief, _target, work, _a, _b, _evidence, anchor = canonical_context(
        tmp_path, include_decision=False
    )
    compiler = CanonicalFindingPackCompiler(ledger, resolver)
    pack_kwargs = {
        "round_id": "round-canonical",
        "finding_id": "finding-transformed",
        "work_item": work,
        "observations": [
            {
                "claim_id": "claim-transformed",
                "claim": "The compared source supports the boundary.",
                "anchor": anchor.to_dict(),
                "applicability": "the fixture boundary",
                "confidence": "high",
                "limitation": "fixture evidence only",
            }
        ],
        "option_effects": [{"option": "isolated-worker", "effect": "supports", "claim_ids": ["claim-transformed"]}],
        "implementation_implications": ["Keep the boundary."],
        "remaining_uncertainties": [],
        "expected_revision": ledger.get_revision("round-canonical"),
    }
    with pytest.raises(InvalidFindingPackError, match="ratio"):
        compiler.compile(**pack_kwargs, transformation={"ratio": "high"})
    compiled = compiler.compile(**pack_kwargs, transformation={"ratio": 0.75})
    assert compiled.payload["transformation"] == {"ratio": 0.75}
