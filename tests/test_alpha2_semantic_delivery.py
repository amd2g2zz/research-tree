import pytest

from research_tree import AcceptanceError, validate_semantic_deliveries


def _technical():
    return {"kind": "technical-research-package", "document": {name: {"evidence_refs": ["e-1"]} for name in sorted(__import__("research_tree.acceptance", fromlist=["TECHNICAL_SECTIONS"]).TECHNICAL_SECTIONS)}}


def _human():
    return {"kind": "human-research-report", "document": {name: "supported reasoning" for name in sorted(__import__("research_tree.acceptance", fromlist=["HUMAN_SECTIONS"]).HUMAN_SECTIONS)}}


def test_semantic_delivery_requires_both_professional_surfaces():
    result = validate_semantic_deliveries(_technical(), _human())
    assert result["status"] == "semantically_ready"


def test_semantic_delivery_rejects_legacy_kind_and_orphan_claims():
    legacy = _human() | {"kind": "human-brief"}
    with pytest.raises(AcceptanceError):
        validate_semantic_deliveries(_technical(), legacy)
    technical = _technical()
    technical["document"]["findings"] = [{"claim": "unsupported"}]
    with pytest.raises(AcceptanceError):
        validate_semantic_deliveries(technical, _human())
