from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_repository_has_exactly_one_canonical_completion_edge() -> None:
    from research_tree.authority_audit import audit_completion_authority

    result = audit_completion_authority(ROOT)

    assert result["valid"] is True, result["violations"]
    assert result["completion_edges"] == [
        {
            "from": "awaiting_acceptance",
            "event": "delivery_accepted",
            "to": "completed",
            "actor": "human",
        }
    ]
    assert "src/research_tree/recursive_search.py" in result["checked"]
    assert "scripts/native_execution_adapter.py" in result["checked"]
    assert "scripts/hermes_execution_adapter.py" in result["checked"]
    assert "hooks/research_hook.py" in result["checked"]
    assert any(path.startswith("packages/codex/") for path in result["checked"])
    assert any(path.startswith("packages/claude-code/") for path in result["checked"])
    assert any(path.startswith("packages/hermes/") for path in result["checked"])


def test_authority_audit_detects_proxy_and_sql_completion_bypasses() -> None:
    from research_tree.authority_audit import audit_python_source

    source = '''
state["status"] = "complete"
connection.execute("UPDATE runs SET lifecycle_state='completed'")
coordinator.transition("run-1", event="delivery_accepted", actor="human", expected_revision=3)
'''
    violations = audit_python_source(source, "scripts/unsafe_adapter.py")

    assert {item["code"] for item in violations} == {
        "canonical_sql_bypass",
        "coordinator_transition_bypass",
        "local_run_completion",
    }


def test_task_completion_is_not_misclassified_as_run_completion() -> None:
    from research_tree.authority_audit import audit_python_source

    assert audit_python_source(
        'task["status"] = "completed"\n', "scripts/worker_adapter.py"
    ) == []
