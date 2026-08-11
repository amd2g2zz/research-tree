from __future__ import annotations

from pathlib import Path

from research_tree.alignment_protocol import AlignmentProtocol
from research_tree.run_ledger import RunLedger


def test_human_and_agent_beliefs_are_retained_separately(tmp_path: Path) -> None:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-beliefs")
    service = AlignmentProtocol(ledger, "run-beliefs")
    human = service.record_belief(
        belief_id="human-scope",
        actor="human",
        field="scope",
        statement="Only the persistence boundary is in scope.",
        confidence="high",
        human_only=True,
    )
    agent = service.record_belief(
        belief_id="agent-scope",
        actor="agent",
        field="scope",
        statement="The adapter boundary is also relevant.",
        confidence="medium",
        supersedes=(),
    )
    assert human["actor"] == "human"
    assert agent["actor"] == "agent"
    assert human["belief_id"] != agent["belief_id"]
