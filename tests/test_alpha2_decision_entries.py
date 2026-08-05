from __future__ import annotations

from copy import deepcopy

import pytest


def _ref(artifact_id: str, digest_character: str) -> dict[str, object]:
    return {
        "run_id": "run-1",
        "artifact_id": artifact_id,
        "revision": 1,
        "content_hash": digest_character * 64,
    }


def _context():
    target = {
        "target_id": "blueprint-target",
        "run_id": "run-1",
        "slots": [
            {
                "slot_id": "slot-1",
                "priority": "P0",
                "options": ["option-a", "option-b"],
                "status": "open",
            }
        ],
    }
    finding_ref = _ref("finding-1", "2")
    finding = {
        "finding_id": "finding-1",
        "run_id": "run-1",
        "decision_slot_id": "slot-1",
        "observations": [
            {
                "observation_id": "observation-1",
                "class": "fact",
                "claim": "Option A has the required boundary.",
            }
        ],
        "option_effects": [
            {
                "option": "option-a",
                "effect": "supports",
                "observation_ids": ["observation-1"],
            }
        ],
    }
    insight = {
        "digest_id": "insight-1",
        "slot_refs": ["slot-1"],
        "statements": [
            {
                "id": "finding-1-statement-0",
                "class": "fact",
                "text": "Option A has the required boundary.",
                "evidence_refs": ["evidence:source@1"],
                "confidence": "high",
            }
        ],
        "contradictions": [],
        "gaps": [],
        "recommended_actions": [],
    }
    payload = {
        "decision_id": "decision-1",
        "run_id": "run-1",
        "blueprint_target_ref": _ref("blueprint-target", "1"),
        "decision_slot_id": "slot-1",
        "finding_pack_refs": [finding_ref],
        "insight_digest_ref": _ref("insight-1", "3"),
        "status": "selected",
        "selected_option": "option-a",
        "alternatives": [
            {
                "option": "option-b",
                "disposition": "rejected",
                "reason": "The accepted Finding Pack does not support option B.",
            }
        ],
        "evidence_basis": [
            {
                "finding_pack_ref": finding_ref,
                "observation_ids": ["observation-1"],
            }
        ],
        "rationale": "The accepted evidence supports option A.",
        "design_consequence": "Use option A at the canonical boundary.",
        "repository_touchpoints": [],
        "validation": {
            "oracle_run_refs": [],
            "status": "pending",
            "limitations": ["The integration oracle remains pending."],
        },
        "change_tasks": [],
        "assumptions": [],
        "fallback": "Retain the existing boundary.",
        "reversal_condition": "Independent evidence invalidates option A.",
        "revision_reason": "Initial evidence-backed decision.",
        "previous_decision_ref": None,
        "producer_version": "decision-v1",
        "limitations": ["The integration oracle remains pending."],
    }
    return payload, target, {"finding-1": finding}, insight


def test_decision_entry_accepts_exact_supported_slot_decision():
    from research_tree.decision_entries import validate_decision_entry_payload

    payload, target, findings, insight = _context()

    normalized = validate_decision_entry_payload(
        payload,
        run_id="run-1",
        blueprint_target=target,
        finding_packs=findings,
        insight_digest=insight,
    )

    assert normalized == payload


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda payload: (
                payload.update(selected_option="option-b"),
                payload["alternatives"][0].update(option="option-a"),
            ),
            "selected option has no supporting observation",
        ),
        (
            lambda payload: payload["evidence_basis"][0].update(
                observation_ids=["observation-missing"]
            ),
            "evidence basis references an unknown observation",
        ),
        (
            lambda payload: payload.update(alternatives=[]),
            "alternatives must dispose every non-selected option",
        ),
    ],
)
def test_decision_entry_rejects_untraceable_selection(mutation, message):
    from research_tree.decision_entries import (
        DecisionEntryContractError,
        validate_decision_entry_payload,
    )

    payload, target, findings, insight = _context()
    invalid = deepcopy(payload)
    mutation(invalid)

    with pytest.raises(DecisionEntryContractError, match=message):
        validate_decision_entry_payload(
            invalid,
            run_id="run-1",
            blueprint_target=target,
            finding_packs=findings,
            insight_digest=insight,
        )


def test_blocked_decision_requires_no_selected_option_and_keeps_fallback():
    from research_tree.decision_entries import validate_decision_entry_payload

    payload, target, _findings, insight = _context()
    payload.update(
        status="blocked",
        selected_option=None,
        finding_pack_refs=[],
        evidence_basis=[],
        alternatives=[
            {
                "option": "option-a",
                "disposition": "deferred",
                "reason": "The required environment is unavailable.",
            },
            {
                "option": "option-b",
                "disposition": "deferred",
                "reason": "The required environment is unavailable.",
            },
        ],
    )

    normalized = validate_decision_entry_payload(
        payload,
        run_id="run-1",
        blueprint_target=target,
        finding_packs={},
        insight_digest=insight,
    )

    assert normalized["status"] == "blocked"
    assert normalized["fallback"] == "Retain the existing boundary."
