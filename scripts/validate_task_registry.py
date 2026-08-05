"""Validate the alpha2 task execution registry as an executable contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
from typing import Any, Mapping


REGISTRY = Path("openspec/changes/unify-research-runtime-alpha2/registries/task-execution-v1.json")


def validate(root: Path) -> dict[str, Any]:
    path = root / REGISTRY
    value = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    rule = value.get("task_rule")
    groups = value.get("groups")
    if not isinstance(rule, Mapping) or not isinstance(groups, list):
        return {"schema_version": 1, "valid": False, "errors": ["task_rule and groups are required"]}
    required = rule.get("required_fields")
    if not isinstance(required, list) or not required:
        errors.append("task_rule.required_fields must be nonempty")
        required = []
    by_id: dict[int, Mapping[str, Any]] = {}
    for index, group in enumerate(groups):
        label = f"groups[{index}]"
        if not isinstance(group, Mapping):
            errors.append(f"{label} must be an object")
            continue
        missing = sorted(set(required) - set(group))
        if missing:
            errors.append(f"{label} missing fields: {missing}")
        group_id = group.get("group")
        if isinstance(group_id, bool) or not isinstance(group_id, int) or group_id < 1:
            errors.append(f"{label}.group must be a positive integer")
            continue
        if group_id in by_id:
            errors.append(f"duplicate group: {group_id}")
        by_id[group_id] = group
        for field in ("outputs", "evidence_refs"):
            items = group.get(field)
            if not isinstance(items, list) or not items or not all(isinstance(item, str) and item.strip() for item in items):
                errors.append(f"group {group_id} {field} must be a nonempty string array")
        for ref in group.get("evidence_refs", []):
            if isinstance(ref, str) and not (root / ref).exists():
                errors.append(f"group {group_id} evidence ref does not resolve: {ref}")
        command = group.get("acceptance_command")
        if not isinstance(command, str) or not command.strip():
            errors.append(f"group {group_id} acceptance_command is required")
        else:
            for token in shlex.split(command, posix=True):
                if token.endswith(".py") and not (root / token).exists():
                    errors.append(f"group {group_id} command path does not resolve: {token}")
    expected = set(range(1, len(by_id) + 1))
    if set(by_id) != expected:
        errors.append(f"group ids must be contiguous: expected={sorted(expected)}, actual={sorted(by_id)}")
    for group_id, group in by_id.items():
        depends_on = group.get("depends_on")
        if not isinstance(depends_on, list) or any(isinstance(item, bool) or not isinstance(item, int) for item in depends_on):
            errors.append(f"group {group_id} depends_on must be an integer array")
            continue
        unknown = sorted(set(depends_on) - set(by_id))
        if unknown:
            errors.append(f"group {group_id} has unknown dependencies: {unknown}")
        if group_id in depends_on:
            errors.append(f"group {group_id} cannot depend on itself")
    _check_cycles(by_id, errors)
    return {"schema_version": 1, "registry": REGISTRY.as_posix(), "group_count": len(by_id), "valid": not errors, "errors": errors}


def _check_cycles(groups: Mapping[int, Mapping[str, Any]], errors: list[str]) -> None:
    visiting: set[int] = set()
    visited: set[int] = set()

    def visit(group_id: int) -> None:
        if group_id in visiting:
            errors.append(f"dependency cycle includes group {group_id}")
            return
        if group_id in visited:
            return
        visiting.add(group_id)
        for dependency in groups[group_id].get("depends_on", []):
            if dependency in groups:
                visit(dependency)
        visiting.remove(group_id)
        visited.add(group_id)

    for group_id in groups:
        visit(group_id)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    args = parser.parse_args()
    result = validate(args.root.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
