"""Parent acceptance checks for the #152 closure-quality children."""

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


def test_parent_group_binds_reachable_evidence_children() -> None:
    execution = _registry("task-execution-v1.json")
    verification = _registry("task-verification-v1.json")
    issue_map = _registry("issue-execution-map-v1.json")
    matrix = _registry("delivery-matrix-v1.json")

    parent = _group(execution, 39)
    assert parent["depends_on"] == [46, 47]
    assert parent["outputs"] == ["evidence-graph-closure-quality-acceptance"]
    parent_receipt = _group(verification, 39)
    assert parent_receipt["state"] == "verified"
    assert parent_receipt["command_receipt"]["source_revision"] == "6cc7bed7ed5ac21f58b420a2cf2097feb5d388a4"

    for child in (46, 47):
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
    row = next(item for item in issues if item["issue"] == 152)
    assert row["primary_group"] == 39

    rows = matrix["capability_rows"]
    assert isinstance(rows, list)
    capability = next(item for item in rows if item["capability"] == "evidence-graph-closure-quality-acceptance")
    assert capability["task_groups"] == [39]
