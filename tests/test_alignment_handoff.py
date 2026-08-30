from __future__ import annotations

from pathlib import Path

import pytest

from research_tree.alignment_protocol import AlignmentMessageError, AlignmentProtocol
from research_tree.run_ledger import RunLedger


def _ready_service(tmp_path: Path) -> tuple[AlignmentProtocol, dict[str, object]]:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-handoff")
    service = AlignmentProtocol(ledger, "run-handoff")
    ledger.append_artifact(
        "run-handoff",
        "evidence-anchor",
        "alignment-evidence",
        {"source": "test-fixture"},
        parent_refs=(),
        expected_revision=ledger.get_revision("run-handoff"),
    )
    basis_ref = [
        {
            "round_id": "run-handoff",
            "artifact_id": "evidence-anchor",
            "revision": 1,
        }
    ]
    planned = service.plan(
        [
            {
                "action_id": "confirm-1",
                "kind": "confirmation",
                "field": "strategy",
                "objective": "Confirm the bounded strategy.",
                "trigger_refs": ["belief:strategy"],
                "closure_oracle": "The displayed strategy remains current.",
                "method_boundary": "alignment only",
            }
        ]
    )
    for field in (
        "outcome",
        "intended_use",
        "scope",
        "non_goals",
        "delivery",
        "authority",
        "safety",
        "success_oracle",
        "feasibility",
        "strategy",
    ):
        service.record_belief(
            belief_id=f"belief-{field.replace('_', '-')}",
            actor="human",
            field=field,
            statement=f"Confirmed {field}.",
            confidence="high",
            basis_refs=basis_ref,
        )
    service.message(
        mirror="The bounded strategy is ready for your decision.",
        evidence_refs=["belief:strategy"],
        consequence="Confirmation permits autonomous research.",
        prompt=None,
        action_id="confirm-1",
    )
    return service, planned


def test_readiness_is_field_level_and_generic_confirmation_cannot_handoff(tmp_path: Path) -> None:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-handoff")
    service = AlignmentProtocol(ledger, "run-handoff")
    readiness = service.readiness()
    assert readiness["ready"] is False
    assert readiness["fields"]["outcome"] in {"unknown", "fail"}


def test_current_context_confirmation_is_idempotent_and_lineage_bound(tmp_path: Path) -> None:
    service, planned = _ready_service(tmp_path)
    message = service._latest("alignment-message")[0].payload

    handoff = service.confirm(
        "I confirm the stated outcome, scope, delivery, authority, and success strategy.",
        expected_digest=message["belief_digest"],
    )
    assert handoff["confirmed"] is True
    assert handoff["action_ref"]["artifact_id"] == planned["action"]["action_id"]
    assert (
        service.confirm(
            "I confirm the stated outcome, scope, delivery, authority, and success strategy.",
            expected_digest=message["belief_digest"],
        )
        == handoff
    )


def test_alignment_change_invalidates_displayed_confirmation_digest(tmp_path: Path) -> None:
    service, _ = _ready_service(tmp_path)
    message = service._latest("alignment-message")[0].payload
    service.record_belief(
        belief_id="belief-correction",
        actor="human",
        field="scope",
        statement="The scope is narrower than the displayed strategy.",
        confidence="high",
        supersedes=(),
    )

    with pytest.raises(AlignmentMessageError, match="stale"):
        service.confirm("I confirm the displayed strategy.", expected_digest=message["belief_digest"])
