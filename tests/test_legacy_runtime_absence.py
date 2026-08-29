from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import research_tree

ROOT = Path(__file__).resolve().parents[1]
LEGACY_SYMBOLS = {
    "BlueprintTargetCompiler",
    "DecisionLedgerCompiler",
    "DeliveryCompiler",
    "FeedbackRoundService",
    "FindingPackCompiler",
    "InputIntakeService",
    "IntentModelCompiler",
    "ReadinessVerifier",
    "RunStore",
    "WorkItemCompiler",
    "WorkItemPlanner",
    "WorkItemStatusService",
    "WorkingBriefCompiler",
}
ACTIVE_DOCUMENTS = (
    ROOT / "README.md",
    ROOT / "references" / "research-tree-architecture.md",
    ROOT / "docs" / "adr" / "ADR-001-runtime-foundation.md",
    ROOT / "packages" / "codex" / "research-tree" / "references" / "research-tree-architecture.md",
    ROOT
    / "packages"
    / "claude-code"
    / "research-tree"
    / "skills"
    / "research-tree"
    / "references"
    / "research-tree-architecture.md",
    ROOT / "packages" / "hermes" / "research-tree" / "references" / "research-tree-architecture.md",
)


def _code_symbols(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names.update(node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute))
    names.update(
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    )
    return names


def test_legacy_runtime_symbols_are_absent_from_live_code_and_exports() -> None:
    live_modules = (*sorted((ROOT / "src" / "research_tree").glob("*.py")), *sorted((ROOT / "tests").glob("*.py")))

    assert all(not hasattr(research_tree, symbol) for symbol in LEGACY_SYMBOLS)
    assert importlib.util.find_spec("research_tree.application") is None
    assert importlib.util.find_spec("research_tree.storage") is None
    assert all(not (_code_symbols(path) & LEGACY_SYMBOLS) for path in live_modules)


def test_active_documentation_and_generated_references_do_not_advertise_legacy_runtime() -> None:
    assert all(path.exists() for path in ACTIVE_DOCUMENTS)

    for path in ACTIVE_DOCUMENTS:
        content = path.read_text(encoding="utf-8")
        assert all(symbol not in content for symbol in LEGACY_SYMBOLS)
