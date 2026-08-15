from __future__ import annotations

import ast
import importlib.util
import json
import re
import subprocess
from pathlib import Path

import research_tree


ROOT = Path(__file__).resolve().parents[1]
RETIRED_SYMBOLS = (
    "InvalidOpenSpecExportError",
    "OpenSpecExport",
    "OpenSpecExportError",
    "OpenSpecExporter",
)


def _imports_retired_module(node: ast.AST) -> bool:
    if isinstance(node, ast.Import):
        return any(alias.name == "research_tree.openspec" for alias in node.names)
    if not isinstance(node, ast.ImportFrom):
        return False
    if node.module in {"openspec", "research_tree.openspec"}:
        return True
    if node.module in {None, "research_tree"}:
        return any(alias.name == "openspec" for alias in node.names)
    return False


def test_runstore_openspec_exporter_is_not_published_or_importable() -> None:
    assert all(not hasattr(research_tree, symbol) for symbol in RETIRED_SYMBOLS)
    assert all(symbol not in research_tree.__all__ for symbol in RETIRED_SYMBOLS)
    assert importlib.util.find_spec("research_tree.openspec") is None


def test_retired_exporter_source_and_legacy_consumers_are_absent() -> None:
    runtime_root = ROOT / "src" / "research_tree"

    assert not (runtime_root / "openspec.py").exists()
    assert not (ROOT / "tests" / "test_openspec_export.py").exists()
    assert not (ROOT / "tests" / "test_e2e_blueprint.py").exists()
    for source_path in runtime_root.glob("*.py"):
        module = ast.parse(source_path.read_text(encoding="utf-8"))
        assert not any(_imports_retired_module(node) for node in ast.walk(module)), source_path

    assert hasattr(research_tree, "CanonicalFindingPackCompiler")
    assert hasattr(research_tree, "RunLedger")


def test_active_authority_registers_only_the_removal_slice() -> None:
    umbrella = ROOT / "openspec" / "changes" / "unify-research-runtime-alpha2"
    registry_root = umbrella / "registries"
    execution = json.loads((registry_root / "task-execution-v1.json").read_text(encoding="utf-8"))
    verification = json.loads((registry_root / "task-verification-v1.json").read_text(encoding="utf-8"))
    verified_groups = {item["group"] for item in verification["groups"] if item["state"] == "verified"}
    active_sources = (
        ROOT / "PRODUCT.md",
        ROOT / "README.md",
        ROOT / "docs" / "方案设计.md",
        ROOT / "docs" / "需求理解.md",
        ROOT / "references" / "blueprint-generation-research.md",
        umbrella / "proposal.md",
        umbrella / "design.md",
        umbrella / "tasks.md",
        umbrella / "schemas" / "README.md",
        umbrella / "specs" / "adaptive-research-execution" / "spec.md",
        registry_root / "issue-execution-map-v1.json",
        registry_root / "delivery-matrix-v1.json",
    )
    active_text = "\n".join(
        (
            *(source_path.read_text(encoding="utf-8") for source_path in active_sources),
            json.dumps(
                [item for item in execution["groups"] if item["group"] not in verified_groups],
                sort_keys=True,
            ),
        )
    )
    issue_map = json.loads((registry_root / "issue-execution-map-v1.json").read_text(encoding="utf-8"))
    matrix = json.loads((registry_root / "delivery-matrix-v1.json").read_text(encoding="utf-8"))

    retired_claims = (
        "InvalidOpenSpecExportError",
        "OpenSpecExport",
        "OpenSpecExporter",
        "OpenSpec export",
        "OpenSpec exporter",
        "src/research_tree/openspec.py",
        "tests/test_openspec_export.py",
        "tests/test_e2e_blueprint.py",
    )
    group = next(item for item in execution["groups"] if item["group"] == 82)
    verification_record = next(item for item in verification["groups"] if item["group"] == 82)
    issue = next(item for item in issue_map["issues"] if item["issue"] == 176)
    capability = next(
        item for item in matrix["capability_rows"] if item["capability"] == "runstore-openspec-export-removal"
    )

    assert all(claim not in active_text for claim in retired_claims)
    assert group["depends_on"] == [81]
    assert group["outputs"] == ["runstore-openspec-export-removal"]
    assert verification_record["state"] == "verified"
    assert verification_record["evidence_refs"] == [
        "local://.research-tree/verification-runs/issue-176/group-82-receipt.json"
    ]
    receipt = verification_record["command_receipt"]
    assert isinstance(receipt, dict)
    assert receipt["command"] == group["acceptance_command"]
    assert receipt["exit_code"] == 0
    assert receipt["raw_output_ref"] == ".research-tree/verification-runs/issue-176/group-82-output.txt"
    for digest in (receipt["environment_digest"], receipt["output_digest"]):
        assert isinstance(digest, str)
        assert re.fullmatch(r"[0-9a-f]{64}", digest)
    source_revision = receipt["source_revision"]
    assert isinstance(source_revision, str)
    assert re.fullmatch(r"[0-9a-f]{40}", source_revision)
    assert (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", source_revision, "HEAD"],
            cwd=ROOT,
            check=False,
        ).returncode
        == 0
    )
    assert verification_record["rollback"] == group["rollback"]
    assert issue == {
        "issue": 176,
        "primary_group": 82,
        "supporting_groups": [81],
        "capabilities": ["runstore-openspec-export-removal"],
        "openspec_change": "remove-runstore-openspec-exporter",
    }
    assert capability == {
        "capability": "runstore-openspec-export-removal",
        "source_modules": ["src/research_tree/__init__.py", "tests/test_runstore_openspec_export_removal.py"],
        "public_surface": [],
        "task_groups": [82],
        "github_issue": "#176",
        "owner": "runtime",
    }


def test_generated_packages_do_not_advertise_the_retired_exporter() -> None:
    package_text = "\n".join(
        package_path.read_text(encoding="utf-8", errors="ignore")
        for package_path in (ROOT / "packages").rglob("*")
        if package_path.is_file()
    )

    retired_claims = (
        "InvalidOpenSpecExportError",
        "OpenSpecExport",
        "OpenSpecExporter",
        "OpenSpec Exporter",
        "OpenSpec exporter",
        "explicit request --> OpenSpec exporter",
    )

    assert all(claim not in package_text for claim in retired_claims)
