from __future__ import annotations

import json
from pathlib import Path

from research_tree.openspec_governance import load_governance_inputs, validate_governance


ROOT = Path(__file__).resolve().parents[1]
CHANGE = ROOT / "openspec" / "changes" / "unify-research-runtime-alpha2"
REGISTRIES = CHANGE / "registries"


def registry_groups() -> dict[int, dict[str, object]]:
    payload = json.loads((REGISTRIES / "task-execution-v1.json").read_text(encoding="utf-8"))
    return {item["group"]: item for item in payload["groups"]}


def test_group_14_acceptance_entrypoint_resolves() -> None:
    definition = registry_groups()[14]

    assert definition["acceptance_command"] == ("uv run python scripts/validate_contracts.py")
    assert (ROOT / "scripts" / "validate_contracts.py").is_file()


def test_group_14_owns_only_ratified_contract_outputs() -> None:
    groups = registry_groups()
    group_14 = groups[14]

    assert group_14["depends_on"] == [2, 5]
    assert group_14["outputs"] == ["contract-ratification", "lifecycle-matrix"]
    assert all(14 in groups[group_id]["depends_on"] for group_id in (25, 26, 27))

    tasks = (CHANGE / "tasks.md").read_text(encoding="utf-8")
    group_14_tasks = tasks.split("## 14.", 1)[1].split("## 15.", 1)[0]
    for downstream_output in ("SourceCapture", "NativeWorkflowRun", "SearchPortfolio"):
        assert downstream_output not in group_14_tasks


def test_alpha2_dependency_graph_remains_acyclic() -> None:
    report = validate_governance(
        load_governance_inputs(
            REGISTRIES / "task-execution-v1.json",
            REGISTRIES / "task-verification-v1.json",
            REGISTRIES / "issue-execution-map-v1.json",
            REGISTRIES / "delivery-matrix-v1.json",
        ),
        repository=ROOT,
    )

    assert not [violation for violation in report.violations if violation.code == "dependency_cycle"]
