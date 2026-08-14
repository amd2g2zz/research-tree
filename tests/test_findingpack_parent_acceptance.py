"""Parent acceptance checks for the #171 Finding Pack consumer migrations."""

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


def test_parent_group_binds_reachable_canonical_findingpack_children() -> None:
    execution = _registry("task-execution-v1.json")
    verification = _registry("task-verification-v1.json")
    issue_map = _registry("issue-execution-map-v1.json")
    matrix = _registry("delivery-matrix-v1.json")

    parent = _group(execution, 81)
    assert parent["depends_on"] == [79, 80]
    assert parent["outputs"] == ["canonical-findingpack-parent-acceptance", "group-81-receipt"]
    assert _group(verification, 81)["state"] in {"planned", "verified"}

    for child in (79, 80):
        child_verification = _group(verification, child)
        assert child_verification["state"] == "verified"
        receipt = child_verification["command_receipt"]
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
    issue = next(item for item in issues if item["issue"] == 171)
    assert issue == {
        "issue": 171,
        "primary_group": 81,
        "supporting_groups": [79, 80],
        "capabilities": ["canonical-findingpack-parent-acceptance"],
        "openspec_change": "accept-canonical-findingpack-parent-acceptance",
    }

    rows = matrix["capability_rows"]
    assert isinstance(rows, list)
    capability = next(item for item in rows if item["capability"] == "canonical-findingpack-parent-acceptance")
    assert capability == {
        "capability": "canonical-findingpack-parent-acceptance",
        "source_modules": ["tests/test_findingpack_parent_acceptance.py"],
        "public_surface": [],
        "task_groups": [81],
        "github_issue": "#171",
        "owner": "runtime",
    }
