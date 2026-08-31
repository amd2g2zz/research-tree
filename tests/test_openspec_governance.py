from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from openspec_governance import load_governance_inputs, validate_governance  # noqa: E402

CHANGE = ROOT / "openspec" / "changes" / "unify-research-runtime-alpha2"
REGISTRIES = CHANGE / "registries"


def registry_groups() -> dict[int, dict[str, object]]:
    payload = json.loads((REGISTRIES / "task-execution-v1.json").read_text(encoding="utf-8"))
    return {item["group"]: item for item in payload["groups"]}


def write_registry_fixtures(
    tmp_path: Path,
    *,
    acceptance_command: str,
    receipt_command: str | None = None,
    state: str = "verified",
) -> tuple[Path, Path, Path, Path]:
    group_path = tmp_path / "groups.json"
    group_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "groups": [
                    {
                        "group": 1,
                        "depends_on": [],
                        "owner": "runtime",
                        "outputs": ["output-1"],
                        "acceptance_command": acceptance_command,
                        "rollback": "disable feature",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    verification_record: dict[str, object] = {"group": 1, "state": state}
    if receipt_command is not None:
        verification_record.update(
            {
                "evidence_refs": ["evidence-1"],
                "command_receipt": {
                    "command": receipt_command,
                    "exit_code": 0,
                    "environment_digest": "a" * 64,
                    "output_digest": "b" * 64,
                    "source_revision": "c" * 40,
                    "raw_output_ref": "evidence/output-1.txt",
                    "recorded_at": "2026-08-10T00:00:00+00:00",
                },
                "rollback": "disable feature",
            }
        )
    verification_path = tmp_path / "verification.json"
    verification_path.write_text(
        json.dumps({"schema_version": 1, "groups": [verification_record]}),
        encoding="utf-8",
    )
    issues_path = tmp_path / "issues.json"
    issues_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "issues": [
                    {
                        "issue": 53,
                        "primary_group": 1,
                        "supporting_groups": [],
                        "capabilities": ["durable-runtime"],
                        "openspec_change": "fixture-change",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    capabilities_path = tmp_path / "capabilities.json"
    capabilities_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "capability_rows": [{"capability": "durable-runtime", "github_issue": "#53", "task_groups": [1]}],
            }
        ),
        encoding="utf-8",
    )
    return group_path, verification_path, issues_path, capabilities_path


def missing_tests_entrypoint_violations(report: object) -> list[object]:
    return [violation for violation in report.violations if violation.code == "missing_tests_entrypoint"]  # type: ignore[attr-defined]


def test_command_pair_referencing_absent_tests_path_is_rejected(tmp_path: Path) -> None:
    command = "uv run pytest -q tests/test_absent_suite.py"

    report = validate_governance(
        load_governance_inputs(*write_registry_fixtures(tmp_path, acceptance_command=command, receipt_command=command)),
        repository=tmp_path,
    )

    violations = missing_tests_entrypoint_violations(report)
    assert len(violations) == 1
    assert violations[0].subject == 1
    assert violations[0].message == (
        "task group 1 command references missing tests/ entrypoint: tests/test_absent_suite.py"
    )


def test_command_pair_with_existing_tests_path_stays_valid(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_present_suite.py").write_text("", encoding="utf-8")
    command = "uv run pytest -q tests/test_present_suite.py"

    report = validate_governance(
        load_governance_inputs(*write_registry_fixtures(tmp_path, acceptance_command=command, receipt_command=command)),
        repository=tmp_path,
    )

    assert missing_tests_entrypoint_violations(report) == []
    assert report.valid is True


def test_planned_command_with_absent_tests_path_is_rejected(tmp_path: Path) -> None:
    command = "uv run pytest -q tests/test_future_absent_suite.py"

    report = validate_governance(
        load_governance_inputs(*write_registry_fixtures(tmp_path, acceptance_command=command, state="planned")),
        repository=tmp_path,
    )

    violations = missing_tests_entrypoint_violations(report)
    assert len(violations) == 1
    assert violations[0].subject == 1
    assert "tests/test_future_absent_suite.py" in violations[0].message


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
    assert group_32["command_receipt"]["raw_output_ref"] == ("ci://delivery-governance/delivery-gate")
    assert "`unsupported`" in umbrella_spec
    assert "`stale_link`" not in umbrella_spec
    assert "refresh flag" not in umbrella_spec
    assert "stale-link refresh protocol" in umbrella_tasks


def test_migrated_groups_use_ci_locators_without_tracked_output_paths() -> None:
    verification = json.loads((REGISTRIES / "task-verification-v1.json").read_text(encoding="utf-8"))
    records = {item["group"]: item for item in verification["groups"]}

    for group in range(1, 10):
        record = records[group]
        assert record["evidence_refs"] == ["ci://delivery-governance/delivery-gate"]
        assert record["command_receipt"]["raw_output_ref"] == ("ci://delivery-governance/delivery-gate")
        assert all("openspec/changes/" not in reference for reference in record["evidence_refs"])
