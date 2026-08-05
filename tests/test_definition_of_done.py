from scripts.check_definition_of_done import check_task


def test_definition_of_done_rejects_partial_task_record():
    result = check_task({"task_id": "15.1", "code": ["src/a.py"], "focused_tests": ["tests/a.py"]})
    assert result["valid"] is False
    assert "regression" in " ".join(result["errors"])


def test_definition_of_done_accepts_evidence_bearing_task_record():
    result = check_task({"task_id": "15.1", "code": ["src/a.py"], "focused_tests": ["tests/a.py"], "regression": ["253 passed"], "documentation": ["README.md"], "migration_notes": ["none: new module"], "evidence_refs": ["evaluation/results/run.json"], "acceptance": {"command": "uv run pytest -q", "status": "passed"}})
    assert result["valid"] is True
