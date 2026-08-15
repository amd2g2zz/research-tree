from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from research_tree.openspec_governance import (
    GovernanceViolation,
    load_governance_inputs,
    main,
    validate_governance,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_ROOT = ROOT / "openspec" / "changes" / "unify-research-runtime-alpha2" / "registries"


def write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def inputs(
    tmp_path: Path,
    *,
    groups: list[dict[str, object]],
    verification: list[dict[str, object]],
    issues: list[dict[str, object]],
    capabilities: list[dict[str, object]],
) -> tuple[Path, Path, Path, Path]:
    return (
        write_json(tmp_path / "groups.json", {"schema_version": 1, "groups": groups}),
        write_json(
            tmp_path / "verification.json",
            {"schema_version": 1, "groups": verification},
        ),
        write_json(tmp_path / "issues.json", {"schema_version": 1, "issues": issues}),
        write_json(
            tmp_path / "capabilities.json",
            {"schema_version": 1, "capability_rows": capabilities},
        ),
    )


def group(group_id: int, depends_on: list[int] | None = None) -> dict[str, object]:
    return {
        "group": group_id,
        "depends_on": depends_on or [],
        "owner": "runtime",
        "outputs": [f"output-{group_id}"],
        "acceptance_command": f"uv run check-{group_id}",
        "rollback": "disable feature",
    }


def record(group_id: int, state: str, **extra: object) -> dict[str, object]:
    return {"group": group_id, "state": state, **extra}


def verified_record(group_id: int) -> dict[str, object]:
    return record(
        group_id,
        "verified",
        evidence_refs=[f"evidence-{group_id}"],
        command_receipt={
            "command": f"uv run check-{group_id}",
            "exit_code": 0,
            "environment_digest": "a" * 64,
            "output_digest": "b" * 64,
            "source_revision": "c" * 40,
            "raw_output_ref": f"evidence/output-{group_id}.txt",
            "recorded_at": "2026-08-10T00:00:00+00:00",
        },
        rollback="disable feature",
    )


def issue(issue_id: int, primary_group: int, capability: str) -> dict[str, object]:
    return {
        "issue": issue_id,
        "primary_group": primary_group,
        "supporting_groups": [],
        "capabilities": [capability],
        "openspec_change": f"issue-{issue_id}-change",
    }


def capability(name: str, issue_id: int, groups: list[int]) -> dict[str, object]:
    return {
        "capability": name,
        "github_issue": f"#{issue_id}",
        "task_groups": groups,
    }


def validate(
    tmp_path: Path,
    *,
    groups: list[dict[str, object]],
    verification: list[dict[str, object]],
    issues: list[dict[str, object]],
    capabilities: list[dict[str, object]],
):
    paths = inputs(
        tmp_path,
        groups=groups,
        verification=verification,
        issues=issues,
        capabilities=capabilities,
    )
    return validate_governance(load_governance_inputs(*paths))


def codes(report) -> set[str]:
    return {violation.code for violation in report.violations}


def test_valid_nonverified_plan_is_structurally_valid_but_not_release_ready(
    tmp_path: Path,
) -> None:
    report = validate(
        tmp_path,
        groups=[group(1)],
        verification=[record(1, "planned")],
        issues=[issue(53, 1, "durable-runtime")],
        capabilities=[capability("durable-runtime", 53, [1])],
    )

    assert report.valid is True
    assert report.release_ready is False
    assert report.unverified_groups == (1,)
    assert report.violations == ()


def test_verified_group_requires_evidence_receipt_and_rollback(tmp_path: Path) -> None:
    report = validate(
        tmp_path,
        groups=[group(1)],
        verification=[record(1, "verified")],
        issues=[issue(53, 1, "durable-runtime")],
        capabilities=[capability("durable-runtime", 53, [1])],
    )

    assert report.valid is False
    assert "verified_record_incomplete" in codes(report)


def test_verified_group_rejects_a_substituted_or_source_less_command_receipt(tmp_path: Path) -> None:
    forged = verified_record(1)
    forged["command_receipt"] = {
        **forged["command_receipt"],  # type: ignore[index]
        "command": "true",
    }
    report = validate(
        tmp_path,
        groups=[group(1)],
        verification=[forged],
        issues=[issue(53, 1, "ledger")],
        capabilities=[capability("ledger", 53, [1])],
    )
    assert "verified_record_incomplete" in codes(report)

    missing_source = verified_record(1)
    del missing_source["command_receipt"]["source_revision"]  # type: ignore[index]
    report = validate(
        tmp_path,
        groups=[group(1)],
        verification=[missing_source],
        issues=[issue(53, 1, "ledger")],
        capabilities=[capability("ledger", 53, [1])],
    )
    assert "verified_record_incomplete" in codes(report)


def test_verified_group_requires_repository_relative_python_entrypoint(
    tmp_path: Path,
) -> None:
    definition = group(1)
    definition["acceptance_command"] = "uv run python scripts/missing.py"
    receipt = verified_record(1)
    receipt["command_receipt"]["command"] = definition["acceptance_command"]  # type: ignore[index]

    report = validate_governance(
        load_governance_inputs(
            *inputs(
                tmp_path,
                groups=[definition],
                verification=[receipt],
                issues=[issue(53, 1, "ledger")],
                capabilities=[capability("ledger", 53, [1])],
            )
        ),
        repository=tmp_path,
    )

    assert "missing_acceptance_entrypoint" in codes(report)


def test_verified_group_allows_a_retired_entrypoint_preserved_at_source_revision(
    tmp_path: Path,
) -> None:
    script = tmp_path / "scripts" / "retired.py"
    script.parent.mkdir()
    script.write_text("print('retired')\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "scripts/retired.py"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Research Tree Test",
            "-c",
            "user.email=research-tree@example.invalid",
            "commit",
            "-qm",
            "record retired entrypoint",
        ],
        cwd=tmp_path,
        check=True,
    )
    source_revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    script.unlink()

    definition = group(1)
    definition["acceptance_command"] = "uv run python scripts/retired.py"
    receipt = verified_record(1)
    receipt["command_receipt"] = {
        **receipt["command_receipt"],  # type: ignore[index]
        "command": definition["acceptance_command"],
        "source_revision": source_revision,
    }

    report = validate_governance(
        load_governance_inputs(
            *inputs(
                tmp_path,
                groups=[definition],
                verification=[receipt],
                issues=[issue(53, 1, "ledger")],
                capabilities=[capability("ledger", 53, [1])],
            )
        ),
        repository=tmp_path,
    )

    assert report.valid is True
    assert "missing_acceptance_entrypoint" not in codes(report)


def test_verified_group_rejects_entrypoint_from_nonancestor_source_revision(
    tmp_path: Path,
) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Research Tree Test",
            "-c",
            "user.email=research-tree@example.invalid",
            "commit",
            "-qm",
            "record base",
        ],
        cwd=tmp_path,
        check=True,
    )
    base_branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(["git", "switch", "-qc", "retired"], cwd=tmp_path, check=True)
    script = tmp_path / "scripts" / "retired.py"
    script.parent.mkdir()
    script.write_text("print('retired')\n", encoding="utf-8")
    subprocess.run(["git", "add", "scripts/retired.py"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Research Tree Test",
            "-c",
            "user.email=research-tree@example.invalid",
            "commit",
            "-qm",
            "record unrelated retired entrypoint",
        ],
        cwd=tmp_path,
        check=True,
    )
    source_revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(["git", "switch", "-q", base_branch], cwd=tmp_path, check=True)

    definition = group(1)
    definition["acceptance_command"] = "uv run python scripts/retired.py"
    receipt = verified_record(1)
    receipt["command_receipt"] = {
        **receipt["command_receipt"],  # type: ignore[index]
        "command": definition["acceptance_command"],
        "source_revision": source_revision,
    }

    report = validate_governance(
        load_governance_inputs(
            *inputs(
                tmp_path,
                groups=[definition],
                verification=[receipt],
                issues=[issue(53, 1, "ledger")],
                capabilities=[capability("ledger", 53, [1])],
            )
        ),
        repository=tmp_path,
    )

    assert report.valid is False
    assert "missing_acceptance_entrypoint" in codes(report)


def test_planned_group_allows_future_acceptance_entrypoint(tmp_path: Path) -> None:
    definition = group(1)
    definition["acceptance_command"] = "uv run python scripts/future.py"

    report = validate_governance(
        load_governance_inputs(
            *inputs(
                tmp_path,
                groups=[definition],
                verification=[record(1, "planned")],
                issues=[issue(53, 1, "ledger")],
                capabilities=[capability("ledger", 53, [1])],
            )
        ),
        repository=tmp_path,
    )

    assert report.valid is True
    assert "missing_acceptance_entrypoint" not in codes(report)


def test_verified_group_rejects_direct_and_transitive_incomplete_dependencies(
    tmp_path: Path,
) -> None:
    report = validate(
        tmp_path,
        groups=[group(1), group(2, [1]), group(3, [2])],
        verification=[record(1, "blocked"), verified_record(2), verified_record(3)],
        issues=[
            issue(53, 1, "ledger"),
            issue(54, 2, "evidence"),
            issue(56, 3, "closure"),
        ],
        capabilities=[
            capability("ledger", 53, [1]),
            capability("evidence", 54, [2]),
            capability("closure", 56, [3]),
        ],
    )

    violations = {
        violation.subject: violation for violation in report.violations if violation.code == "unverified_dependency"
    }
    assert violations[2].path == (2, 1)
    assert violations[3].path == (3, 2, 1)
    assert violations[3].observed_state == "blocked"


def test_cycle_missing_group_duplicate_issue_and_owner_mismatch_are_all_reported(
    tmp_path: Path,
) -> None:
    report = validate(
        tmp_path,
        groups=[group(1, [2]), group(2, [1])],
        verification=[record(1, "planned"), record(2, "planned")],
        issues=[
            issue(53, 1, "ledger"),
            issue(54, 1, "evidence"),
        ],
        capabilities=[
            capability("ledger", 53, [1, 25]),
            capability("evidence", 53, [2]),
        ],
    )

    assert {
        "dependency_cycle",
        "missing_task_group",
        "duplicate_primary_group_owner",
        "capability_owner_mismatch",
    }.issubset(codes(report))


def test_unavailable_state_is_valid_history_but_never_release_ready(tmp_path: Path) -> None:
    report = validate(
        tmp_path,
        groups=[group(1)],
        verification=[record(1, "unavailable", blocker="host CLI unavailable")],
        issues=[issue(71, 1, "activation-integrity")],
        capabilities=[capability("activation-integrity", 71, [1])],
    )

    assert report.valid is True
    assert report.release_ready is False
    assert report.unavailable_groups == (1,)


def test_loader_rejects_unknown_lifecycle_state(tmp_path: Path) -> None:
    paths = inputs(
        tmp_path,
        groups=[group(1)],
        verification=[record(1, "done")],
        issues=[issue(53, 1, "ledger")],
        capabilities=[capability("ledger", 53, [1])],
    )

    with pytest.raises(ValueError, match="unknown lifecycle state"):
        load_governance_inputs(*paths)


def test_report_is_deterministic_and_uses_structured_violations(tmp_path: Path) -> None:
    report = validate(
        tmp_path,
        groups=[group(2, [1]), group(1)],
        verification=[record(2, "planned"), record(1, "planned")],
        issues=[issue(54, 2, "evidence"), issue(53, 1, "ledger")],
        capabilities=[capability("evidence", 54, [2]), capability("ledger", 53, [1])],
    )

    assert (
        report.as_dict()
        == validate(
            tmp_path,
            groups=[group(1), group(2, [1])],
            verification=[record(1, "planned"), record(2, "planned")],
            issues=[issue(53, 1, "ledger"), issue(54, 2, "evidence")],
            capabilities=[capability("ledger", 53, [1]), capability("evidence", 54, [2])],
        ).as_dict()
    )
    assert all(isinstance(item, GovernanceViolation) for item in report.violations)


def test_alpha2_registry_has_resolvable_ownership_and_noncyclic_boundaries() -> None:
    report = validate_governance(
        load_governance_inputs(
            REGISTRY_ROOT / "task-execution-v1.json",
            REGISTRY_ROOT / "task-verification-v1.json",
            REGISTRY_ROOT / "issue-execution-map-v1.json",
            REGISTRY_ROOT / "delivery-matrix-v1.json",
        )
    )

    assert report.valid is True
    assert report.release_ready is False
    assert report.verified_groups == (
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        11,
        12,
        14,
        16,
        20,
        23,
        25,
        26,
        27,
        28,
        29,
        31,
        32,
        33,
        35,
        36,
        39,
        40,
        42,
        43,
        44,
        45,
        46,
        47,
        48,
        54,
        55,
        57,
        59,
        60,
        61,
        62,
        63,
        74,
        75,
        76,
        77,
        78,
        79,
        80,
        81,
        82,
        83,
    )
    assert report.unverified_groups == (
        *(
            group
            for group in range(6, 33)
            if group not in {6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 20, 23, 25, 26, 27, 28, 29, 31, 32}
        ),
        84,
    )


def test_cli_emits_deterministic_real_registry_report(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--repo", str(ROOT)]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is True
    assert payload["release_ready"] is False
    assert payload["verified_groups"] == [
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        11,
        12,
        14,
        16,
        20,
        23,
        25,
        26,
        27,
        28,
        29,
        31,
        32,
        33,
        35,
        36,
        39,
        40,
        42,
        43,
        44,
        45,
        46,
        47,
        48,
        54,
        55,
        57,
        59,
        60,
        61,
        62,
        63,
        74,
        75,
        76,
        77,
        78,
        79,
        80,
        81,
        82,
        83,
    ]
    assert payload["unverified_groups"] == [
        *(
            group
            for group in range(6, 33)
            if group not in {6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 20, 23, 25, 26, 27, 28, 29, 31, 32}
        ),
        84,
    ]


def test_cli_returns_nonzero_for_semantic_violation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths = inputs(
        tmp_path,
        groups=[group(1)],
        verification=[record(1, "verified")],
        issues=[issue(53, 1, "ledger")],
        capabilities=[capability("ledger", 53, [1])],
    )

    assert (
        main(
            [
                "--task-registry",
                str(paths[0]),
                "--verification",
                str(paths[1]),
                "--issue-map",
                str(paths[2]),
                "--delivery-matrix",
                str(paths[3]),
            ]
        )
        == 1
    )
    assert "verified_record_incomplete" in capsys.readouterr().out


def test_cli_require_release_ready_rejects_valid_but_unverified_plan(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--repo", str(ROOT), "--require-release-ready"]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is True
    assert payload["release_ready"] is False
