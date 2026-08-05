from __future__ import annotations

from pathlib import Path


def test_alpha2_task_registry_is_executable_and_acyclic() -> None:
    from scripts.validate_task_registry import validate

    result = validate(Path(__file__).parents[1])
    assert result["valid"], result["errors"]
    assert result["group_count"] == 24
