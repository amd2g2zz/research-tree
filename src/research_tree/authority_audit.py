"""Static completion-authority audit for alpha2 runtime surfaces."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Iterable


_RUN_OBJECT_NAMES = frozenset(
    {"state", "result", "run", "record", "projection", "checkpoint", "summary"}
)
_TERMINAL_VALUES = frozenset({"complete", "completed"})


def _constant_string(node: ast.AST | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _subscript_key(node: ast.Subscript) -> str | None:
    return _constant_string(node.slice)


class _AuthorityVisitor(ast.NodeVisitor):
    def __init__(self, relative_path: str, *, allow_coordinator_api: bool) -> None:
        self.relative_path = relative_path
        self.allow_coordinator_api = allow_coordinator_api
        self.violations: list[dict[str, Any]] = []

    def _add(self, node: ast.AST, code: str, message: str) -> None:
        self.violations.append(
            {
                "path": self.relative_path,
                "line": getattr(node, "lineno", 0),
                "code": code,
                "message": message,
            }
        )

    def _check_assignment(self, target: ast.AST, value: ast.AST | None) -> None:
        terminal = _constant_string(value)
        if terminal not in _TERMINAL_VALUES:
            return
        if isinstance(target, ast.Subscript):
            owner = target.value.id if isinstance(target.value, ast.Name) else None
            key = _subscript_key(target)
            if owner in _RUN_OBJECT_NAMES and key in {"status", "lifecycle_state", "complete"}:
                self._add(
                    target,
                    "local_run_completion",
                    f"{owner}[{key!r}] cannot set canonical-looking status {terminal!r}",
                )
        elif isinstance(target, ast.Attribute) and target.attr in {"status", "lifecycle_state"}:
            self._add(
                target,
                "local_run_completion",
                f"attribute {target.attr!r} cannot be assigned {terminal!r} outside the coordinator",
            )

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._check_assignment(target, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._check_assignment(node.target, node.value)
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        for key_node, value_node in zip(node.keys, node.values):
            key = _constant_string(key_node)
            value = _constant_string(value_node)
            if key in {"lifecycle_state", "canonical_status"} and value in _TERMINAL_VALUES:
                self._add(
                    node,
                    "embedded_run_completion",
                    f"non-coordinator mapping declares {key}={value!r}",
                )
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            normalized = " ".join(node.value.casefold().split())
            if "update runs set lifecycle_state" in normalized:
                self._add(
                    node,
                    "canonical_sql_bypass",
                    "only ResearchRunCoordinator may update runs.lifecycle_state",
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if not self.allow_coordinator_api and isinstance(node.func, ast.Attribute):
            owner = node.func.value.id if isinstance(node.func.value, ast.Name) else None
            if owner in {"coordinator", "run_coordinator"} and node.func.attr == "accept":
                self._add(
                    node,
                    "coordinator_accept_bypass",
                    "host and compatibility surfaces may not accept delivery",
                )
            if owner in {"coordinator", "run_coordinator"} and node.func.attr == "transition":
                event = next(
                    (_constant_string(item.value) for item in node.keywords if item.arg == "event"),
                    None,
                )
                if event == "delivery_accepted":
                    self._add(
                        node,
                        "coordinator_transition_bypass",
                        "delivery_accepted may enter through the canonical CLI/API only",
                    )
        self.generic_visit(node)


def audit_python_source(
    source: str,
    relative_path: str,
    *,
    allow_coordinator_api: bool = False,
) -> list[dict[str, Any]]:
    """Return completion-authority violations in one Python source."""

    try:
        tree = ast.parse(source, filename=relative_path)
    except SyntaxError as error:
        return [
            {
                "path": relative_path,
                "line": error.lineno or 0,
                "code": "syntax_error",
                "message": str(error),
            }
        ]
    visitor = _AuthorityVisitor(
        relative_path, allow_coordinator_api=allow_coordinator_api
    )
    visitor.visit(tree)
    return visitor.violations


def _completion_edges(source: str) -> list[dict[str, str]]:
    tree = ast.parse(source, filename="src/research_tree/coordinator.py")
    for statement in tree.body:
        if not isinstance(statement, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "TRANSITIONS" for target in statement.targets):
            continue
        if not isinstance(statement.value, ast.Dict):
            break
        edges: list[dict[str, str]] = []
        for key_node, value_node in zip(statement.value.keys, statement.value.values):
            if not isinstance(key_node, ast.Tuple) or not isinstance(value_node, ast.Tuple):
                continue
            key = [_constant_string(item) for item in key_node.elts]
            value = [_constant_string(item) for item in value_node.elts]
            if len(key) == 2 and len(value) == 2 and value[0] == "completed":
                edges.append(
                    {
                        "from": key[0] or "",
                        "event": key[1] or "",
                        "to": value[0] or "",
                        "actor": value[1] or "",
                    }
                )
        return edges
    return []


def _audited_files(root: Path) -> Iterable[Path]:
    yield from sorted((root / "src" / "research_tree").glob("*.py"))
    yield from sorted((root / "scripts").glob("*.py"))
    if (root / "hooks").is_dir():
        yield from sorted((root / "hooks").rglob("*.py"))
    if (root / "packages").is_dir():
        yield from sorted((root / "packages").glob("*/research-tree/scripts/*.py"))


def audit_completion_authority(root: str | Path) -> dict[str, Any]:
    """Audit source and generated packages for a single completion authority."""

    repository = Path(root).resolve()
    coordinator_path = repository / "src" / "research_tree" / "coordinator.py"
    violations: list[dict[str, Any]] = []
    checked: list[str] = []
    if not coordinator_path.is_file():
        violations.append(
            {
                "path": "src/research_tree/coordinator.py",
                "line": 0,
                "code": "coordinator_missing",
                "message": "canonical completion authority source is missing",
            }
        )
        edges: list[dict[str, str]] = []
    else:
        coordinator_source = coordinator_path.read_text(encoding="utf-8")
        edges = _completion_edges(coordinator_source)
        if edges != [
            {
                "from": "awaiting_acceptance",
                "event": "delivery_accepted",
                "to": "completed",
                "actor": "human",
            }
        ]:
            violations.append(
                {
                    "path": "src/research_tree/coordinator.py",
                    "line": 0,
                    "code": "completion_edge_mismatch",
                    "message": "completed must have exactly one human delivery_accepted edge",
                }
            )

    seen: set[Path] = set()
    for path in _audited_files(repository):
        resolved = path.resolve()
        if resolved in seen or resolved == coordinator_path.resolve():
            continue
        seen.add(resolved)
        relative = path.relative_to(repository).as_posix()
        if relative == "src/research_tree/authority_audit.py":
            continue
        checked.append(relative)
        violations.extend(
            audit_python_source(
                path.read_text(encoding="utf-8"),
                relative,
                allow_coordinator_api=relative == "src/research_tree/cli.py",
            )
        )
    violations.sort(key=lambda item: (item["path"], item["line"], item["code"]))
    return {
        "schema": 1,
        "valid": not violations,
        "authority": "src/research_tree/coordinator.py",
        "completion_edges": edges,
        "checked": checked,
        "violations": violations,
    }
