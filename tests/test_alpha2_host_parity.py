from research_tree import canonical_event_digest, emit_native_event, sanitize_provider_failure


def test_equivalent_codex_and_claude_events_have_same_semantic_digest():
    payload = {"terminal_status": "verified", "artifact_refs": ["finding-f-1"]}
    codex = emit_native_event(host="codex", event_id="codex-event", event_type="worker_finished", run_id="run-1", round_id="round-1", expected_revision=2, attempt_id="attempt-1", payload=payload)
    claude = emit_native_event(host="claude-code", event_id="claude-event", event_type="worker_finished", run_id="run-1", round_id="round-1", expected_revision=2, attempt_id="attempt-1", payload=payload)
    assert canonical_event_digest([codex]) == canonical_event_digest([claude])


def test_provider_failure_keeps_safe_metadata_only():
    failure = sanitize_provider_failure(provider="gateway", model="glm", category="context_limit", opaque_code="ctx-001", attempt_id="attempt-1", gateway_log_ref="log:abc")
    assert "raw" not in failure
    assert failure["gateway_log_ref"] == "log:abc"
