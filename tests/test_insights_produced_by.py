"""Tests for insight digest produced_by origin labels (issue #440, tasks.md 5.1).

Digest statements must name their producer with a closed-vocabulary origin so
consuming agents can tell agent-synthesized statements from worker/tool
artifacts.
"""

from __future__ import annotations

import pytest

from research_tree.insights import validate_insight_digest


def _digest(produced_by: object = "worker") -> dict[str, object]:
    statement = {
        "finding_pack_id": "finding-1",
        "decision_slot_id": "slot-1",
        "classification": "fact",
        "claim": "the baseline compiles",
        "source_refs": ["anchor-1"],
        "evidence_class": "tool_output",
    }
    if produced_by is not None:
        statement["produced_by"] = produced_by
    return {
        "schema_version": 1,
        "closure": "ready_for_decision_ledger_review",
        "finding_pack_count": 1,
        "producer_version": "v1",
        "digest_id": "digest-1",
        "slot_refs": ["slot-1"],
        "source_refs": ["anchor-1"],
        "classified_statements": [statement],
        "covered_evidence_classes": ["tool_output"],
        "confirmed_facts": [],
        "hypotheses": [],
        "contradictions": [],
        "gaps": [],
        "recommendations": [],
        "limitations": [],
        "previous_digest_ref": None,
        "parent_refs": [],
        "realized_delta": {},
        "recommended_actions": [],
        "evidence_baseline": [],
        "transition_index": 0,
        "confidence": {},
        "calibration": {},
        "changed_beliefs": [],
        "insights": [],
        "next_actions": [],
    }


def test_statement_with_valid_produced_by_accepted() -> None:
    validate_insight_digest(_digest())


@pytest.mark.parametrize("produced_by", ("agent", "worker", "tool", "user", "repository", "generated"))
def test_statement_accepts_every_origin_value(produced_by: str) -> None:
    validate_insight_digest(_digest(produced_by))


def test_statement_without_produced_by_rejected() -> None:
    with pytest.raises(ValueError, match="produced_by"):
        validate_insight_digest(_digest(None))


def test_statement_with_unknown_produced_by_rejected() -> None:
    with pytest.raises(ValueError, match="produced_by"):
        validate_insight_digest(_digest("some-random-string"))
