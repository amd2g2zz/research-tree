from __future__ import annotations

from pathlib import Path

import pytest

from research_tree.alignment_protocol import AlignmentProtocolError, AlignmentProtocol
from research_tree.run_ledger import RunLedger


def test_message_rejects_more_than_one_prompt(tmp_path: Path) -> None:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-message")
    service = AlignmentProtocol(ledger, "run-message")
    service.plan(
        [
            {
                "action_id": "question-1",
                "kind": "question",
                "field": "scope",
                "objective": "Choose a scope.",
                "human_exclusive": True,
                "researchable": False,
                "trigger_refs": ["brief-1"],
                "closure_oracle": "requester confirms scope",
                "method_boundary": "conversation",
            }
        ]
    )
    with pytest.raises(AlignmentProtocolError, match="one open prompt"):
        service.message(
            mirror="Scope is unresolved.",
            evidence_refs=[],
            consequence="Scope changes the result.",
            prompt=["What is the scope?", "What is the delivery?"],
            action_id="question-1",
        )
