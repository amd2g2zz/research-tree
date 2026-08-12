from __future__ import annotations

import hashlib

import pytest

from research_tree.coordinator import RESEARCH_RUN_STATE_KIND, ResearchRunCoordinator
from research_tree.debug_trace import CausalTraceError, CausalTraceService
from research_tree.domain import ArtifactRef, canonical_json_bytes
from research_tree.run_ledger import RunLedger
from strategy_support import confirm_strategy


def _append(ledger: RunLedger, artifact_id: str, kind: str, payload: dict, parents=()):
    return ledger.append_artifact(
        "run-63",
        artifact_id,
        kind,
        payload,
        parent_refs=parents,
        expected_revision=ledger.get_revision("run-63"),
    )


def _setup(tmp_path):
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-63")
    handoff = _append(ledger, "handoff-1", "alignment-handoff", {"confirmed": True})
    target = _append(
        ledger,
        "target-1",
        "blueprint-target",
        {"decision_slots": [{"id": "slot-1", "priority": "P0"}]},
        (ArtifactRef("run-63", handoff.id, handoff.revision),),
    )
    coordinator = ResearchRunCoordinator(ledger)
    coordinator.initialize(
        run_id="run-63",
        alignment_handoff=handoff,
        blueprint_target=target,
        expected_revision=ledger.get_revision("run-63"),
    )
    confirm_strategy(ledger, coordinator, "run-63")
    return ledger, coordinator


def _digest(payload: dict) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def test_replay_verifies_exact_cause_chain_and_terminal_digest(tmp_path) -> None:
    ledger, coordinator = _setup(tmp_path)
    terminal = coordinator.state("run-63")

    first = CausalTraceService(ledger).replay("run-63")
    second = CausalTraceService(ledger).replay("run-63")

    assert first == second
    assert first["verified"] is True
    assert first["terminal_state"] == "autonomous_research"
    assert first["state_digest"] == terminal.payload["state_digest"]
    assert [item["sequence"] for item in first["transitions"]] == [1, 2]
    assert first["transitions"][0]["prior_digest"]
    assert first["transitions"][0]["next_digest"]
    assert first["transitions"][0]["causation_id"].startswith("event-")


@pytest.mark.parametrize("failure", ["missing_cause", "digest_mismatch", "fork"])
def test_replay_rejects_ambiguous_or_tampered_state_lineage(tmp_path, failure: str) -> None:
    ledger, coordinator = _setup(tmp_path)
    initial = coordinator.state("run-63")
    body = {
        "state": "handoff_pending",
        "lifecycle_revision": int(initial.payload["lifecycle_revision"]) + 1,
        "unmet_obligations": [],
        "legal_next_actions": ["handoff_confirmed"],
        "previous_state_ref": ArtifactRef("run-63", initial.id, initial.revision).to_dict(),
    }
    body["state_digest"] = "0" * 64 if failure == "digest_mismatch" else _digest(body)
    artifact_id = "forked-state" if failure == "fork" else "run-state"
    _append(
        ledger,
        artifact_id,
        RESEARCH_RUN_STATE_KIND,
        body,
        (ArtifactRef("run-63", initial.id, initial.revision),),
    )

    with pytest.raises(CausalTraceError, match="missing_cause" if failure == "fork" else failure):
        CausalTraceService(ledger).replay("run-63")
