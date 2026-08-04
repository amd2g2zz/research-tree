from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_tree.debug_trace import DebugTraceError, emit_trace, summarize_traces


def project(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    (tmp_path / "packages").mkdir()
    (tmp_path / "skill-src").mkdir()
    return tmp_path


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
