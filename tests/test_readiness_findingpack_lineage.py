from __future__ import annotations

import ast
from pathlib import Path


def _tree(name: str) -> ast.Module:
    return ast.parse(Path(__file__).with_name(name).read_text(encoding="utf-8"))


def _names(tree: ast.AST) -> set[str]:
    return (
        {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        | {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        | {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    )


def _imported_names(tree: ast.AST) -> set[str]:
    return {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }


def test_readiness_consumers_have_no_legacy_fixture_or_state_copy_path() -> None:
    readiness_tree = _tree("test_readiness.py")
    readiness_names = _names(readiness_tree) | _imported_names(readiness_tree)

    assert "legacy_runstore_fixture" not in readiness_names
    assert (
        not {
            "FindingPackCompiler",
            "DecisionLedgerCompiler",
            "RunStore",
            "load_round",
            "ReadinessVerifier",
        }
        & readiness_names
    )
    assert "CanonicalReadinessVerifier" in readiness_names

    strict_tree = _tree("test_strict_evidence_decision_boundary.py")
    strict_names = _names(strict_tree) | _imported_names(strict_tree)

    assert "greenfield_package" not in strict_names
    assert "_migrate_run_store" not in strict_names
    assert "load_round" not in strict_names

    legacy_compiler_calls = [
        node
        for node in ast.walk(strict_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "FindingPackCompiler"
    ]
    assert len(legacy_compiler_calls) == 1
