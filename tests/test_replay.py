from __future__ import annotations

from dataclasses import replace
import hashlib
from unittest.mock import patch

import pytest

from research_tree.coordinator import RESEARCH_RUN_STATE_KIND, ResearchRunCoordinator
from research_tree.debug_trace import CausalTraceError, CausalTraceService
from research_tree.domain import ArtifactRef, canonical_json_bytes
from research_tree.run_ledger import RunLedger
from strategy_support import confirm_strategy
from test_feedback_rounds import correction_context
from test_research_run_coordinator import _register_canonical_completion_inputs


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
    assert first["replay_mode"] == "semantic"
    assert first["chain_intact"] is True
    assert first["recomputed_digest"] == first["stored_digest"]
    assert first["earliest_divergence"] is None


def test_replay_reports_illegal_transition_with_a_self_consistent_state_digest(tmp_path) -> None:
    ledger, coordinator = _setup(tmp_path)
    current = coordinator.state("run-63")
    event_ref = ArtifactRef("run-63", "forged-event", 1)
    event_payload = {
        "event_id": "forged-event",
        "idempotency_key": "forged-event-key",
        "event": "handoff_confirmed",
        "from": current.payload["state"],
        "to": "completed",
        "actor": "human",
        "payload": {},
    }
    state_payload = {
        "state": "completed",
        "lifecycle_revision": int(current.payload["lifecycle_revision"]) + 1,
        "unmet_obligations": [],
        "legal_next_actions": ["export_audit"],
        "transition_payload": {},
        "previous_state_ref": ArtifactRef("run-63", current.id, current.revision).to_dict(),
    }
    state_payload["state_digest"] = _digest(state_payload)
    ledger.append_artifact_batch(
        "run-63",
        (
            ("forged-event", "lifecycle-event", event_payload, (ArtifactRef("run-63", current.id, current.revision),)),
            (
                "run-state",
                RESEARCH_RUN_STATE_KIND,
                state_payload,
                (ArtifactRef("run-63", current.id, current.revision), event_ref),
            ),
        ),
        expected_revision=ledger.get_revision("run-63"),
    )

    replay = CausalTraceService(ledger).replay("run-63")

    assert replay["chain_intact"] is True
    assert replay["verified"] is False
    assert replay["earliest_divergence"]["reason"] == "illegal_transition"


def test_replay_recomputes_a_valid_completion_record(tmp_path) -> None:
    ledger, coordinator = _setup(tmp_path)
    target = next(item for item in ledger.load_run("run-63").artifacts if item.kind == "blueprint-target")
    _register_canonical_completion_inputs(ledger, "run-63", target)
    coordinator.transition("run-63", "batch_checkpoint", "coordinator", expected_revision=ledger.get_revision("run-63"))
    coordinator.transition("run-63", "all_slots_closed", "coordinator", expected_revision=ledger.get_revision("run-63"))
    coordinator.transition("run-63", "readiness_passed", "coordinator", expected_revision=ledger.get_revision("run-63"))
    coordinator.transition(
        "run-63", "deliveries_compiled", "coordinator", expected_revision=ledger.get_revision("run-63")
    )
    coordinator.transition("run-63", "delivery_accepted", "human", expected_revision=ledger.get_revision("run-63"))

    replay = CausalTraceService(ledger).replay("run-63")

    assert replay["verified"] is True
    assert replay["terminal_state"] == "completed"
    assert replay["recomputed_digest"] == replay["stored_digest"]
    assert replay["earliest_divergence"] is None
    snapshot = ledger.load_run("run-63")
    stripped = replace(
        snapshot,
        artifacts=tuple(item for item in snapshot.artifacts if item.kind != RESEARCH_RUN_STATE_KIND),
    )
    with patch.object(ledger, "load_run", return_value=stripped):
        rebuilt = CausalTraceService(ledger).replay("run-63")
    assert rebuilt["verified"] is True
    assert rebuilt["semantic_digest"] == replay["semantic_digest"]
    ledger.append_artifact(
        "run-63",
        "technical-1",
        "technical-research-package",
        {"status": "compiled", "replacement": True},
        expected_revision=ledger.get_revision("run-63"),
    )
    stale = CausalTraceService(ledger).replay("run-63")
    assert stale["verified"] is False
    assert stale["earliest_divergence"]["reason"] == "completion_inputs_divergence"


def test_replay_rebuilds_from_immutable_inputs_without_materialized_states(tmp_path) -> None:
    ledger, _ = _setup(tmp_path)
    service = CausalTraceService(ledger)
    stored = service.replay("run-63")
    snapshot = ledger.load_run("run-63")
    stripped = replace(
        snapshot,
        artifacts=tuple(item for item in snapshot.artifacts if item.kind != RESEARCH_RUN_STATE_KIND),
    )

    with patch.object(ledger, "load_run", return_value=stripped):
        rebuilt = service.replay("run-63")

    assert rebuilt["projection_rebuilt"] is True
    assert rebuilt["verified"] is True
    assert rebuilt["semantic_digest"] == stored["semantic_digest"]
    assert rebuilt["terminal_state"] == stored["terminal_state"]


def test_replay_recomputes_correction_quarantine_state(tmp_path) -> None:
    ledger, coordinator, _, _, correction = correction_context(tmp_path)
    coordinator.apply_correction(correction, expected_revision=ledger.get_revision(correction.run_id))

    replay = CausalTraceService(ledger).replay(correction.run_id)

    assert replay["verified"] is True
    assert replay["terminal_state"] == "alignment"
    assert replay["transitions"][0]["action"] == "correction"
    assert replay["earliest_divergence"] is None


def test_replay_recomputes_contradiction_quarantine_state(tmp_path) -> None:
    from test_canonical_contradictions import _claim_payload

    ledger, coordinator, state, _, _ = correction_context(tmp_path)
    first = ledger.append_artifact(
        "run-correction",
        "finding-replay-a",
        "finding-pack",
        {"claims": [_claim_payload(claim_id="claim-replay-a", polarity="positive")]},
        parent_refs=(ArtifactRef(state.round_id, state.id, state.revision),),
        expected_revision=ledger.get_revision("run-correction"),
    )
    second = ledger.append_artifact(
        "run-correction",
        "finding-replay-b",
        "finding-pack",
        {"claims": [_claim_payload(claim_id="claim-replay-b", polarity="negative")]},
        parent_refs=(ArtifactRef(first.round_id, first.id, first.revision),),
        expected_revision=ledger.get_revision("run-correction"),
    )
    coordinator.apply_contradiction(
        run_id="run-correction",
        contradiction_id="contradiction-replay",
        finding_refs=(
            ArtifactRef(first.round_id, first.id, first.revision),
            ArtifactRef(second.round_id, second.id, second.revision),
        ),
        reason="The evidence directly conflicts.",
        expected_revision=ledger.get_revision("run-correction"),
    )

    replay = CausalTraceService(ledger).replay("run-correction")

    assert replay["verified"] is True
    assert replay["terminal_state"] == "alignment"
    assert replay["transitions"][0]["action"] == "contradiction"
    assert replay["earliest_divergence"] is None


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
