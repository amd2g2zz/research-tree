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
    assert all(14 in groups[group_id]["depends_on"] for group_id in (25, 26))

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


def test_current_only_setup_contract_replaces_archived_refresh_behavior() -> None:
    archive = ROOT / "openspec/changes/archive/2026-08-13-verify-cross-host-skill-activation"
    active_change = ROOT / "openspec/changes/verify-cross-host-skill-activation"
    issue_map = json.loads((REGISTRIES / "issue-execution-map-v1.json").read_text(encoding="utf-8"))
    verification = json.loads((REGISTRIES / "task-verification-v1.json").read_text(encoding="utf-8"))
    umbrella_spec = (CHANGE / "specs/skill-activation-integrity/spec.md").read_text(encoding="utf-8")
    umbrella_tasks = (CHANGE / "tasks.md").read_text(encoding="utf-8")

    assert archive.is_dir()
    assert not active_change.exists()
    assert next(item for item in issue_map["issues"] if item["issue"] == 71)["openspec_change"] == (
        "archive/2026-08-13-verify-cross-host-skill-activation"
    )
    group_32 = next(item for item in verification["groups"] if item["group"] == 32)
    assert group_32["evidence_refs"] == ["ci://delivery-governance/delivery-gate"]
    assert group_32["command_receipt"]["raw_output_ref"] == (
        "ci://delivery-governance/delivery-gate"
    )
    assert "`unsupported`" in umbrella_spec
    assert "`stale_link`" not in umbrella_spec
    assert "refresh flag" not in umbrella_spec
    assert "stale-link refresh protocol" in umbrella_tasks


def test_migrated_groups_use_ci_locators_without_tracked_output_paths() -> None:
    verification = json.loads(
        (REGISTRIES / "task-verification-v1.json").read_text(encoding="utf-8")
    )
    records = {item["group"]: item for item in verification["groups"]}

    for group in range(1, 10):
        record = records[group]
        assert record["evidence_refs"] == ["ci://delivery-governance/delivery-gate"]
        assert record["command_receipt"]["raw_output_ref"] == (
            "ci://delivery-governance/delivery-gate"
        )
        assert all(
            "openspec/changes/" not in reference
            for reference in record["evidence_refs"]
        )
