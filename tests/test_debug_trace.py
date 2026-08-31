from __future__ import annotations

import json
from pathlib import Path

import pytest
from strategy_support import confirm_strategy

from research_tree.coordinator import ResearchRunCoordinator
from research_tree.debug_trace import (
    CausalTraceError,
    CausalTraceService,
    DebugTraceError,
    emit_trace,
    main,
    summarize_traces,
)
from research_tree.domain import ArtifactRef
from research_tree.run_ledger import RunLedger


def project(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    (tmp_path / "packages").mkdir()
    (tmp_path / "skill-src").mkdir()
    return tmp_path


def canonical_run(tmp_path: Path):
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-63")
    handoff = ledger.append_artifact(
        "run-63", "handoff-1", "alignment-handoff", {"confirmed": True}, expected_revision=0
    )
    target = ledger.append_artifact(
        "run-63",
        "target-1",
        "blueprint-target",
        {"decision_slots": [{"id": "slot-1", "priority": "P0"}]},
        parent_refs=(ArtifactRef("run-63", handoff.id, handoff.revision),),
        expected_revision=1,
    )
    coordinator = ResearchRunCoordinator(ledger)
    coordinator.initialize(
        run_id="run-63",
        alignment_handoff=handoff,
        blueprint_target=target,
        expected_revision=2,
    )
    confirm_strategy(ledger, coordinator, "run-63")
    return ledger, coordinator


def test_trace_emits_only_structured_sanitized_fields(tmp_path: Path) -> None:
    root = project(tmp_path)
    result = emit_trace(
        host="codex",
        phase="alignment_blocked",
        status="blocked",
        codes=("missing-success-oracle", "awaiting-authority"),
        run_id="run-1",
        project_root=root,
    )

    record = json.loads((root / result["path"]).read_text(encoding="utf-8"))
    assert record == {
        "schema": 1,
        "source": "research-tree-debug",
        "recorded_at": record["recorded_at"],
        "host": "codex",
        "phase": "alignment_blocked",
        "status": "blocked",
        "codes": ["missing-success-oracle", "awaiting-authority"],
        "run_id": "run-1",
    }
    assert "prompt" not in record
    assert "tool_input" not in record


def test_trace_summary_is_bounded_and_counts_transitions(tmp_path: Path) -> None:
    root = project(tmp_path)
    emit_trace(
        host="claude",
        phase="intake",
        status="started",
        project_root=root,
    )
    emit_trace(
        host="claude",
        phase="alignment_checkpoint",
        status="completed",
        project_root=root,
    )

    summary = summarize_traces(project_root=root, limit=1)
    assert summary["event_count"] == 2
    assert summary["by_phase"] == {"alignment_checkpoint": 1, "intake": 1}
    assert summary["by_status"] == {"completed": 1, "started": 1}
    assert len(summary["recent"]) == 1
    assert summary["recent"][0]["phase"] == "alignment_checkpoint"


def test_trace_accepts_alignment_turn_without_transcript_fields(tmp_path: Path) -> None:
    root = project(tmp_path)
    result = emit_trace(
        host="hermes",
        phase="alignment_turn",
        status="completed",
        codes=("model-delta",),
        project_root=root,
    )

    record = json.loads((root / result["path"]).read_text(encoding="utf-8"))
    assert record["phase"] == "alignment_turn"
    assert record["codes"] == ["model-delta"]
    assert "response" not in record
    assert "prompt" not in record


def test_trace_rejects_free_form_codes_and_invalid_limits(tmp_path: Path) -> None:
    root = project(tmp_path)
    with pytest.raises(DebugTraceError, match="debug code"):
        emit_trace(
            host="hermes",
            phase="worker_blocked",
            status="blocked",
            codes=("contains user prompt",),
            project_root=root,
        )
    with pytest.raises(DebugTraceError, match="limit"):
        summarize_traces(project_root=root, limit=0)


def test_explain_run_and_action_use_canonical_evidence(tmp_path: Path) -> None:
    ledger, coordinator = canonical_run(tmp_path)
    state = coordinator.state("run-63")
    action = ledger.append_artifact(
        "run-63",
        "action-1",
        "research-action",
        {
            "action_id": "action-1",
            "inputs": {"slot_id": "slot-1"},
            "score_components": {"expected_delta": 0.7, "cost": 0.2},
            "outcome": "selected",
            "reason": "p0_deficit",
        },
        parent_refs=(ArtifactRef("run-63", state.id, state.revision),),
        expected_revision=ledger.get_revision("run-63"),
    )
    service = CausalTraceService(ledger)

    explained = service.explain_run("run-63")
    why = service.why_action("run-63", "action-1")

    assert explained["state"] == "autonomous_research"
    assert explained["verified"] is True
    assert {item["obligation"] for item in explained["evidence_gaps"]} >= {
        "p0_closure_tokens",
        "insight_ref",
        "readiness_ref",
        "evaluation_ref",
        "technical_delivery_ref",
        "human_delivery_ref",
        "acceptance_ref",
    }
    assert why["artifact_ref"] == ArtifactRef("run-63", action.id, action.revision).to_dict()
    assert why["score_components"] == {"cost": 0.2, "expected_delta": 0.7}
    assert why["reason"] == "p0_deficit"


def test_host_reconciliation_is_bounded_read_only_and_non_authoritative(tmp_path: Path) -> None:
    ledger, coordinator = canonical_run(tmp_path)
    before_revision = ledger.get_revision("run-63")
    before_state = coordinator.state("run-63")
    observations = [
        {"event_id": "host-1", "attempt_id": "attempt-1", "status": "complete", "sequence": 1},
        {"event_id": "host-1", "attempt_id": "attempt-1", "status": "complete", "sequence": 1},
        {"event_id": "host-2", "attempt_id": "attempt-2", "status": "unknown", "sequence": 2},
    ]

    result = CausalTraceService(ledger).reconcile_host("run-63", observations)

    assert result["completion_authority"] == "coordinator_only"
    assert result["duplicate_event_ids"] == ["host-1"]
    assert {item["classification"] for item in result["observations"]} == {"missing", "uncertain"}
    assert ledger.get_revision("run-63") == before_revision
    assert coordinator.state("run-63") == before_state

    with pytest.raises(CausalTraceError, match="sensitive"):
        CausalTraceService(ledger).reconcile_host(
            "run-63",
            [{"event_id": "host-3", "attempt_id": "attempt-3", "status": "failed", "token": "secret"}],
        )


def test_replay_cli_reads_the_canonical_workspace(tmp_path: Path, capsys) -> None:
    canonical_run(tmp_path)

    assert main(["replay", "--run-id", "run-63", "--project-root", str(tmp_path)]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["verified"] is True
    assert output["terminal_state"] == "autonomous_research"
    assert [item["sequence"] for item in output["transitions"]] == [1, 2]


def test_host_failure_trace_allows_categories_but_rejects_free_text(tmp_path: Path) -> None:
    ledger, coordinator = canonical_run(tmp_path)
    state = coordinator.state("run-63")
    ledger.append_artifact(
        "run-63",
        "provider-event-1",
        "host-event",
        {
            "event_id": "provider-event-1",
            "kind": "provider_failure",
            "attempt_id": "attempt-1",
            "sequence": 1,
            "actor": "hermes",
            "payload": {"category": "rate_limit", "code": "provider-429", "raw_detail": "do not export"},
        },
        parent_refs=(ArtifactRef("run-63", state.id, state.revision),),
        expected_revision=ledger.get_revision("run-63"),
    )

    trace = CausalTraceService(ledger).explain_run("run-63")["host_events"]

    assert trace[0]["diagnostic"] == {"category": "rate_limit", "code": "provider-429"}
    assert "do not export" not in json.dumps(trace)

    ledger.append_artifact(
        "run-63",
        "provider-event-2",
        "host-event",
        {
            "event_id": "provider-event-2",
            "kind": "provider_failure",
            "attempt_id": "attempt-1",
            "sequence": 2,
            "actor": "hermes",
            "payload": {"category": "free form provider failure with user content"},
        },
        parent_refs=(ArtifactRef("run-63", state.id, state.revision),),
        expected_revision=ledger.get_revision("run-63"),
    )
    with pytest.raises(CausalTraceError, match="bounded diagnostic"):
        CausalTraceService(ledger).explain_run("run-63")
