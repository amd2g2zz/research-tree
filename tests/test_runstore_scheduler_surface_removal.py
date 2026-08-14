from __future__ import annotations

import ast
import json
from pathlib import Path

import research_tree


def test_runstore_scheduler_symbols_are_not_published_from_root_package() -> None:
    retired_symbols = (
        "AdaptivePortfolioScheduler",
        "InvalidPortfolioError",
        "PortfolioError",
        "WORK_PORTFOLIO_KIND",
        "validate_portfolio_payload",
    )

    assert all(not hasattr(research_tree, symbol) for symbol in retired_symbols)
    assert all(symbol not in research_tree.__all__ for symbol in retired_symbols)


def test_scheduler_source_is_absent_without_runtime_imports() -> None:
    root = Path(__file__).resolve().parents[1]
    runtime_sources = (root / "src" / "research_tree").glob("*.py")

    assert not (root / "src" / "research_tree" / "scheduler.py").exists()
    for source in runtime_sources:
        imports = [
            node
            for node in ast.walk(ast.parse(source.read_text(encoding="utf-8")))
            if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        assert not any(
            isinstance(node, ast.Import)
            and any(alias.name == "research_tree.scheduler" for alias in node.names)
            or isinstance(node, ast.ImportFrom)
            and (
                node.module == "scheduler"
                or node.module == "research_tree.scheduler"
                or node.module == "research_tree"
                and any(alias.name == "scheduler" for alias in node.names)
                or node.module is None
                and any(alias.name == "scheduler" for alias in node.names)
            )
            for node in imports
        )


def test_active_authority_does_not_advertise_the_retired_scheduler() -> None:
    root = Path(__file__).resolve().parents[1]
    umbrella = root / "openspec" / "changes" / "unify-research-runtime-alpha2"
    registry_root = umbrella / "registries"
    active_sources = (
        root / "PRODUCT.md",
        root / "docs" / "方案设计.md",
        root / "docs" / "需求理解.md",
        root / "references" / "blueprint-generation-research.md",
        umbrella / "proposal.md",
        umbrella / "tasks.md",
        umbrella / "schemas" / "README.md",
        umbrella / "specs" / "worker-orchestration" / "spec.md",
        registry_root / "task-execution-v1.json",
        registry_root / "task-verification-v1.json",
        registry_root / "issue-execution-map-v1.json",
        registry_root / "delivery-matrix-v1.json",
    )
    active_text = "\n".join(path.read_text(encoding="utf-8") for path in active_sources)
    delivery_matrix = json.loads((registry_root / "delivery-matrix-v1.json").read_text(encoding="utf-8"))
    task_execution = json.loads((registry_root / "task-execution-v1.json").read_text(encoding="utf-8"))
    task_verification = json.loads((registry_root / "task-verification-v1.json").read_text(encoding="utf-8"))
    issue_map = json.loads((registry_root / "issue-execution-map-v1.json").read_text(encoding="utf-8"))

    retired_claims = (
        "AdaptivePortfolioScheduler",
        "Adaptive Portfolio Scheduler",
        "portfolio scheduler",
        "work-portfolio",
        "scheduler.py",
        "tests/test_scheduler.py",
    )

    assert all(claim not in active_text for claim in retired_claims)
    assert all(
        "src/research_tree/scheduler.py" not in row["source_modules"] for row in delivery_matrix["capability_rows"]
    )
    group = next(item for item in task_execution["groups"] if item["group"] == 62)
    verification = next(item for item in task_verification["groups"] if item["group"] == 62)
    issue = next(item for item in issue_map["issues"] if item["issue"] == 178)

    assert group["depends_on"] == [54, 55]
    assert group["outputs"] == ["public-runstore-scheduler-surface-removal"]
    assert verification["state"] == "verified"
    assert verification["command_receipt"]["source_revision"] == "c647ef52901cbf30d04fecc6080c78854dc822fd"
    assert verification["command_receipt"]["raw_output_ref"] == "ci://delivery-governance/delivery-gate"
    assert issue["primary_group"] == 62
    assert issue["capabilities"] == ["public-runstore-scheduler-surface-removal"]
    assert not (root / "tests" / "test_scheduler.py").exists()
    assert not (root / "docs" / "specs" / "RT-010.md").exists()


def test_generated_packages_do_not_advertise_the_retired_scheduler() -> None:
    root = Path(__file__).resolve().parents[1]
    package_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore") for path in (root / "packages").rglob("*") if path.is_file()
    )

    retired_claims = (
        "AdaptivePortfolioScheduler",
        "InvalidPortfolioError",
        "PortfolioError",
        "WORK_PORTFOLIO_KIND",
        "validate_portfolio_payload",
        "research_tree.scheduler",
        "scheduler.py",
        "work-portfolio",
    )

    assert all(claim not in package_text for claim in retired_claims)


def test_scheduler_source_purge_has_its_own_planned_group() -> None:
    root = Path(__file__).resolve().parents[1]
    registry_root = root / "openspec" / "changes" / "unify-research-runtime-alpha2" / "registries"
    execution = json.loads((registry_root / "task-execution-v1.json").read_text(encoding="utf-8"))
    verification = json.loads((registry_root / "task-verification-v1.json").read_text(encoding="utf-8"))
    issue_map = json.loads((registry_root / "issue-execution-map-v1.json").read_text(encoding="utf-8"))
    matrix = json.loads((registry_root / "delivery-matrix-v1.json").read_text(encoding="utf-8"))

    group = next(item for item in execution["groups"] if item["group"] == 76)
    verification_record = next(item for item in verification["groups"] if item["group"] == 76)
    issue = next(item for item in issue_map["issues"] if item["issue"] == 179)
    capability = next(
        item
        for item in matrix["capability_rows"]
        if item["capability"] == "unreachable-runstore-scheduler-source-removal"
    )

    assert group["depends_on"] == [62]
    assert group["outputs"] == ["unreachable-runstore-scheduler-source-removal", "group-76-receipt"]
    assert verification_record["state"] == "planned"
    assert issue == {
        "issue": 179,
        "primary_group": 76,
        "supporting_groups": [62],
        "capabilities": ["unreachable-runstore-scheduler-source-removal"],
        "openspec_change": "purge-unreachable-runstore-scheduler-source",
    }
    assert capability["task_groups"] == [76]
