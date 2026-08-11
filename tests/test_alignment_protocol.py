from __future__ import annotations

from pathlib import Path

import pytest

from research_tree.alignment_protocol import (
    AlignmentConflictError,
    AlignmentProtocol,
    AlignmentProtocolError,
)
from research_tree.run_ledger import RunLedger


def protocol(tmp_path: Path) -> AlignmentProtocol:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-59")
    return AlignmentProtocol(ledger, "run-59")


def candidate(
    action_id: str,
    *,
    kind: str = "reconnaissance",
    human_exclusive: bool = False,
    researchable: bool = True,
    impact: int = 5,
) -> dict[str, object]:
    return {
        "action_id": action_id,
        "kind": kind,
        "field": "scope",
        "objective": "Resolve the current scope uncertainty.",
        "belief_refs": [],
        "evidence_refs": [],
        "impact": impact,
        "human_exclusive": human_exclusive,
        "researchable": researchable,
        "expected_ambiguity_reduction": 0.8,
        "decision_consequence": 5,
        "cognitive_load": 1,
        "repetition": 0,
        "closure_oracle": "The scope is supported by an independent source.",
        "method_boundary": "repository and public documentation only",
        "trigger_refs": ["brief-1"],
    }


def test_researchable_ambiguity_is_selected_before_requester_question(tmp_path: Path) -> None:
    service = protocol(tmp_path)

    planned = service.plan([candidate("recon-1")], seed=11)

    assert planned["action"]["kind"] == "reconnaissance"
    assert planned["attempt"]["status"] == "pending"
    assert planned["action"]["trigger_refs"] == ["brief-1"]


def test_planning_replay_returns_the_same_pending_attempt(tmp_path: Path) -> None:
    service = protocol(tmp_path)
    options = [candidate("recon-1")]

    first = service.plan(options, seed=3)
    replay = service.plan(options, seed=3)

    assert replay == first
    assert service.ledger.get_revision("run-59") == 2


def test_requester_only_candidate_becomes_one_open_question(tmp_path: Path) -> None:
    service = protocol(tmp_path)

    planned = service.plan([candidate("question-1", kind="question", human_exclusive=True, researchable=False)])

    assert planned["action"]["kind"] == "question"
    assert planned["action"]["human_exclusive"] is True
    with pytest.raises(AlignmentProtocolError, match="human-only"):
        service.record_belief(
            belief_id="agent-approval",
            actor="agent",
            field="authority",
            statement="Requester approved.",
            confidence="high",
            human_only=True,
        )


def test_response_must_bind_to_current_pending_action(tmp_path: Path) -> None:
    service = protocol(tmp_path)
    planned = service.plan([candidate("recon-1")])

    with pytest.raises(AlignmentConflictError, match="pending action"):
        service.respond(
            response_id="response-1",
            action_id="other-action",
            attempt_id=planned["attempt"]["attempt_id"],
            outcome="answered",
        )

    consumed = service.respond(
        response_id="response-1",
        action_id="recon-1",
        attempt_id=planned["attempt"]["attempt_id"],
        outcome="answered",
        evidence_refs=["capture-1"],
    )
    assert consumed["attempt"]["status"] == "consumed"
    assert (
        service.respond(
            response_id="response-1",
            action_id="recon-1",
            attempt_id=planned["attempt"]["attempt_id"],
            outcome="answered",
            evidence_refs=["capture-1"],
        )
        == consumed
    )


def test_message_is_bounded_and_confirmation_requires_current_digest(tmp_path: Path) -> None:
    service = protocol(tmp_path)
    planned = service.plan([candidate("question-1", kind="question", human_exclusive=True, researchable=False)])

    message = service.message(
        mirror="The current scope is still requester-controlled.",
        evidence_refs=["capture-1"],
        consequence="The answer determines the research boundary.",
        prompt="Which scope should the run use?",
        action_id="question-1",
    )
    assert message["belief_digest"] == message["response_binding"]["expected_digest"]
    assert message["selected_action_id"] == planned["action"]["action_id"]

    with pytest.raises(AlignmentProtocolError, match="generic acknowledgement"):
        service.confirm("okay", expected_digest=message["belief_digest"])
    with pytest.raises(AlignmentProtocolError, match="stale"):
        service.confirm("I accept the displayed scope.", expected_digest="0" * 64)


def test_feedback_classifies_material_change_as_successor_and_method_change_as_replan(
    tmp_path: Path,
) -> None:
    service = protocol(tmp_path)

    successor = service.record_feedback(
        feedback_id="feedback-1",
        kind="success_change",
        message="The success definition changed.",
        materiality="material",
        affected_fields=["success_definition"],
    )
    replan = service.record_feedback(
        feedback_id="feedback-2",
        kind="depth_request",
        message="Go deeper on the same question.",
        materiality="informational",
        affected_fields=["depth"],
    )

    assert successor["classification"] == "successor_request"
    assert replan["classification"] == "same_round_replan"


@pytest.mark.parametrize(
    ("scenario", "kind", "human_exclusive", "researchable"),
    [
        ("vague-brief", "reconnaissance", False, True),
        ("impossible-goal", "disagreement", False, True),
        ("wrong-human-premise", "disagreement", True, False),
        ("wrong-agent-premise", "disagreement", False, True),
        ("repeated-planning", "reconnaissance", False, True),
        ("generic-acknowledgement", "question", True, False),
    ],
)
def test_black_box_briefs_keep_actions_bounded_and_digest_bound(
    tmp_path: Path,
    scenario: str,
    kind: str,
    human_exclusive: bool,
    researchable: bool,
) -> None:
    service = protocol(tmp_path)
    option = candidate(
        f"{scenario}-action",
        kind=kind,
        human_exclusive=human_exclusive,
        researchable=researchable,
    )
    planned = service.plan([option], seed=5)
    assert planned["action"]["kind"] == kind
    if scenario == "repeated-planning":
        assert service.plan([option], seed=5) == planned
    if scenario == "generic-acknowledgement":
        message = service.message(
            mirror="The request remains requester-controlled.",
            evidence_refs=[],
            consequence="The answer changes the research boundary.",
            prompt=None,
        )
        with pytest.raises(AlignmentProtocolError, match="generic acknowledgement"):
            service.confirm("okay", expected_digest=message["belief_digest"])
