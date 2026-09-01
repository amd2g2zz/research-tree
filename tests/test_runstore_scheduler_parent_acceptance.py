"""Parent acceptance checks for the #175 RunStore scheduler retirement."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

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
    parent_verification = _group(verification, 78)
    assert parent_verification["state"] == "verified"

    parent_receipt = parent_verification["command_receipt"]
    assert isinstance(parent_receipt, dict)
    assert parent_receipt["command"] == parent["acceptance_command"]
    assert parent_receipt["exit_code"] == 0
    assert parent_receipt["raw_output_ref"] == ".research-tree/verification-runs/issue-175/group-78-output.txt"

    parent_revision = parent_receipt["source_revision"]
    environment_digest = parent_receipt["environment_digest"]
    output_digest = parent_receipt["output_digest"]
    assert isinstance(parent_revision, str)
    assert isinstance(environment_digest, str)
    assert isinstance(output_digest, str)
    assert re.fullmatch(r"[0-9a-f]{40}", parent_revision)
    assert re.fullmatch(r"[0-9a-f]{64}", environment_digest)
    assert re.fullmatch(r"[0-9a-f]{64}", output_digest)
    assert (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", parent_revision, "HEAD"],
            cwd=ROOT,
            check=False,
        ).returncode
        == 0
    )

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
