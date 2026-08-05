import json

from research_tree import emit_causal_trace, reconcile_host_events


def test_host_reconciliation_keeps_canonical_attempt_authoritative():
    result = reconcile_host_events(
        canonical_attempts={"a1": {"status": "running"}},
        host_events=[{"event_id": "e1", "attempt_id": "a1", "payload": {"status": "completed"}}, {"event_id": "e1", "attempt_id": "a1", "payload": {"status": "completed"}}],
    )
    assert result["status"] == "reconcile_required"
    assert {item["kind"] for item in result["discrepancies"]} == {"duplicate_host_event", "divergent_outcome"}


def test_causal_trace_contains_safe_ordering_fields(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    (tmp_path / "packages").mkdir()
    (tmp_path / "skill-src").mkdir()
    result = emit_causal_trace(host="codex", phase="research_started", status="started", run_id="run-1", event_id="event-1", sequence=1, actor="coordinator", action="dispatch", project_root=tmp_path)
    value = json.loads((tmp_path / result["path"]).read_text(encoding="utf-8"))
    assert value["sequence"] == 1
    assert value["trace_id"] == "event-1"
    assert value["redaction_class"] == "sanitized"
    assert "prompt" not in value and "tool_input" not in value
