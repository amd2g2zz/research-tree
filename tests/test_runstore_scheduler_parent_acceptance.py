"""Parent acceptance checks for the #175 RunStore scheduler retirement."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
REGISTRIES = ROOT / "openspec" / "changes" / "unify-research-runtime-alpha2" / "registries"


def _registry(name: str) -> dict[str, object]:
    return json.loads((REGISTRIES / name).read_text(encoding="utf-8"))


def _group(payload: dict[str, object], group_id: int) -> dict[str, object]:
    groups = payload["groups"]
    assert isinstance(groups, list)
    return next(item for item in groups if item["group"] == group_id)


def test_parent_group_binds_reachable_scheduler_retirement_children() -> None:
    execution = _registry("task-execution-v1.json")
    verification = _registry("task-verification-v1.json")
    issue_map = _registry("issue-execution-map-v1.json")
    matrix = _registry("delivery-matrix-v1.json")

    parent = _group(execution, 78)
    assert parent["depends_on"] == [62, 76]
    assert parent["outputs"] == ["runstore-scheduler-retirement-acceptance", "group-78-receipt"]
    assert _group(verification, 78)["state"] in {"planned", "verified"}

    for child in (62, 76):
        receipt = _group(verification, child)["command_receipt"]
        assert isinstance(receipt, dict)
        revision = receipt["source_revision"]
        assert isinstance(revision, str)
        assert (
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", revision, "HEAD"],
                cwd=ROOT,
                check=False,
            ).returncode
            == 0
        )

    issues = issue_map["issues"]
    assert isinstance(issues, list)
    issue = next(item for item in issues if item["issue"] == 175)
    assert issue == {
        "issue": 175,
        "primary_group": 78,
        "supporting_groups": [62, 76],
        "capabilities": ["runstore-scheduler-retirement-acceptance"],
        "openspec_change": "accept-runstore-scheduler-retirement",
    }

    rows = matrix["capability_rows"]
    assert isinstance(rows, list)
    capability = next(item for item in rows if item["capability"] == "runstore-scheduler-retirement-acceptance")
    assert capability == {
        "capability": "runstore-scheduler-retirement-acceptance",
        "source_modules": ["tests/test_runstore_scheduler_parent_acceptance.py"],
        "public_surface": [],
        "task_groups": [78],
        "github_issue": "#175",
        "owner": "runtime",
    }

    assert not (ROOT / "src" / "research_tree" / "scheduler.py").exists()
    assert not (ROOT / "docs" / "specs" / "RT-010.md").exists()
