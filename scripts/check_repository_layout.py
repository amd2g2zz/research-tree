#!/usr/bin/env python3
"""Validate the repository path authority and clean-checkout boundary read-only."""

from __future__ import annotations

import argparse
from fnmatch import fnmatchcase
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any


DEFAULT_REGISTRY = Path("openspec/changes/unify-research-runtime-alpha2/registries/repository-paths-v1.json")
DEFAULT_SCHEMA = Path("openspec/changes/unify-research-runtime-alpha2/schemas/path-registry-v1.json")
GENERATED_DISTRIBUTIONS = {"packages/", ".claude-plugin/"}
PACKAGE_BUILD_COMMAND = "uv run python scripts/build_skill_packages.py"
INSTALLED_ROOTS = {".agents/", ".claude/", ".codex/"}
RUNTIME_ROOTS = {
    ".research-tree/",
    ".research-tree-alignment/",
    ".research-tree-debug/",
    ".research-tree-hermes/",
    ".research-tree-hooks/",
    ".research-tree-native/",
}


def _error(code: str, path: str, detail: str) -> dict[str, str]:
    return {"code": code, "path": path, "detail": detail}


def _root_name(path: str) -> str:
    return path.rstrip("/").split("/", 1)[0]


def _normalized_path(path: str) -> str:
    return path.replace("\\", "/").rstrip("/")


def _exact_ignore_rule(path: str) -> str:
    return f"{_normalized_path(path)}/" if path.endswith("/") else _normalized_path(path)


def _tracked_paths(repository: Path) -> set[str]:
    result = subprocess.run(["git", "ls-files", "-z"], cwd=repository, capture_output=True, check=False)
    if result.returncode:
        return set()
    return {path.decode("utf-8", errors="surrogateescape") for path in result.stdout.split(b"\0") if path}


def _checkout_roots(repository: Path) -> set[str]:
    return {path.name for path in repository.iterdir() if path.name != ".git"}


def _read_ignore_rules(repository: Path) -> set[str]:
    path = repository / ".gitignore"
    if not path.is_file():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#") and not line.lstrip().startswith("!")
    }


def _schema_error(path: Path, detail: str) -> tuple[None, list[dict[str, str]]]:
    return None, [_error("invalid-schema", str(path), detail)]


def _load_schema(path: Path) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _schema_error(path, str(exc))
    if not isinstance(schema, dict):
        return _schema_error(path, "schema must be an object")
    root_properties = schema.get("properties")
    definitions = schema.get("$defs")
    if not isinstance(root_properties, dict) or not isinstance(definitions, dict):
        return _schema_error(path, "schema must define root properties and definitions")
    entries_schema = root_properties.get("entries")
    entry_schema = definitions.get("entry")
    if not isinstance(entries_schema, dict) or not isinstance(entry_schema, dict):
        return _schema_error(path, "schema must define entries and entry")
    if entries_schema.get("items", {}).get("$ref") != "#/$defs/entry":
        return _schema_error(path, "entries must reference the entry definition")
    if not isinstance(entry_schema.get("properties"), dict) or not isinstance(entry_schema.get("required"), list):
        return _schema_error(path, "entry definition must declare properties and required fields")
    return schema, []


def _value_matches_type(value: object, declared: object) -> bool:
    types = declared if isinstance(declared, list) else [declared]
    for item in types:
        if item == "string" and isinstance(value, str):
            return True
        if item == "boolean" and isinstance(value, bool):
            return True
        if item == "array" and isinstance(value, list):
            return True
        if item == "object" and isinstance(value, dict):
            return True
        if item == "null" and value is None:
            return True
    return False


def _type_detail(field: str, declared: object) -> str:
    types = declared if isinstance(declared, list) else [declared]
    readable = ["null" if item == "null" else f"a {item}" for item in types]
    if len(readable) == 1:
        return f"{field} must be {readable[0]}"
    return f"{field} must be {' or '.join(readable)}"


def _condition_matches(item: dict[str, Any], condition: object) -> bool:
    if not isinstance(condition, dict):
        return False
    properties = condition.get("properties")
    if not isinstance(properties, dict):
        return False
    for field, constraint in properties.items():
        if not isinstance(constraint, dict) or "const" not in constraint:
            return False
        value = item.get(field)
        if value != constraint["const"] or type(value) is not type(constraint["const"]):
            return False
    return True


def _load_registry(
    path: Path,
    schema_path: Path | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    schema_path = schema_path or Path(__file__).resolve().parents[1] / DEFAULT_SCHEMA
    schema, schema_errors = _load_schema(schema_path)
    if schema is None:
        return [], schema_errors
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [], [_error("invalid-registry", str(path), str(exc))]
    if not isinstance(payload, dict):
        return [], [_error("invalid-registry", "registry", "registry must be an object")]
    root_properties = schema["properties"]
    entry_schema = schema["$defs"]["entry"]
    entry_properties = entry_schema["properties"]
    root_required = schema.get("required", [])
    required_fields = entry_schema["required"]
    errors: list[dict[str, str]] = []
    if schema.get("additionalProperties") is False:
        for field in sorted(set(payload) - set(root_properties)):
            errors.append(_error("invalid-registry", field, "field is not allowed"))
    for field in root_required:
        if field not in payload:
            errors.append(_error("invalid-registry", field, "field is required"))
    schema_version = root_properties.get("schema_version", {})
    expected_version = schema_version.get("const") if isinstance(schema_version, dict) else None
    if (
        "schema_version" not in payload
        or payload.get("schema_version") != expected_version
        or type(payload.get("schema_version")) is not type(expected_version)
    ):
        return [], [_error("invalid-registry", "schema_version", "registry requires schema_version 1")]
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list):
        errors.append(_error("invalid-registry", "entries", "registry requires an entries array"))
        return [], errors
    entries_schema = root_properties["entries"]
    minimum_entries = entries_schema.get("minItems") if isinstance(entries_schema, dict) else None
    if isinstance(minimum_entries, int) and len(raw_entries) < minimum_entries:
        errors.append(_error("invalid-registry", "entries", "registry requires at least one entry"))
    entries: list[dict[str, Any]] = []
    for index, item in enumerate(raw_entries):
        if not isinstance(item, dict):
            errors.append(_error("invalid-registry", f"entries[{index}]", "entry must be an object"))
            continue
        entries.append(item)
        if entry_schema.get("additionalProperties") is False:
            for field in sorted(set(item) - set(entry_properties)):
                errors.append(_error("invalid-registry", f"entries[{index}].{field}", "field is not allowed"))
        for field in required_fields:
            if field not in item:
                errors.append(_error("invalid-registry", f"entries[{index}].{field}", "field is required"))
        for field, constraints in entry_properties.items():
            if field not in item or not isinstance(constraints, dict):
                continue
            value = item[field]
            if "type" in constraints and not _value_matches_type(value, constraints["type"]):
                errors.append(
                    _error("invalid-registry", f"entries[{index}].{field}", _type_detail(field, constraints["type"]))
                )
                continue
            if isinstance(value, str) and constraints.get("minLength") and not value:
                errors.append(_error("invalid-registry", f"entries[{index}].{field}", f"{field} must be non-empty"))
            if "enum" in constraints and value not in constraints["enum"]:
                errors.append(
                    _error(
                        "invalid-registry",
                        f"entries[{index}].{field}",
                        f"unsupported {field.replace('_', ' ')}",
                    )
                )
        dependent_required = entry_schema.get("dependentRequired", {})
        if isinstance(dependent_required, dict):
            for field, dependencies in dependent_required.items():
                if field in item and isinstance(dependencies, list) and any(name not in item for name in dependencies):
                    errors.append(
                        _error(
                            "invalid-registry", f"entries[{index}]", "migration target and disposition must be paired"
                        )
                    )
                    break
        for condition in entry_schema.get("allOf", []):
            if not isinstance(condition, dict) or not _condition_matches(item, condition.get("if")):
                continue
            then = condition.get("then")
            required = then.get("required") if isinstance(then, dict) else None
            if isinstance(required, list) and any(field not in item for field in required):
                errors.append(
                    _error(
                        "invalid-registry",
                        f"entries[{index}].{required[0]}",
                        "operator-migrated paths require a target and disposition",
                    )
                )
    paths = [item.get("path") for item in entries if isinstance(item.get("path"), str)]
    if len(paths) != len(set(paths)):
        errors.append(_error("invalid-registry", "entries", "paths must be unique"))
    return entries, errors


def _entry_contains_tracked_path(entry: dict[str, Any], tracked_path: str) -> bool:
    path = str(entry.get("path", ""))
    normalized = _normalized_path(path)
    if "*" in normalized:
        return fnmatchcase(_root_name(tracked_path), _root_name(normalized))
    if path.endswith("/"):
        return tracked_path.startswith(f"{normalized}/")
    return tracked_path == normalized


def _entry_matches_root(entry: dict[str, Any], root: str) -> bool:
    return fnmatchcase(root, _root_name(str(entry.get("path", ""))))


def _read_registry(registry_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    return _load_registry(registry_path)


def _boundary_errors(repository: Path, entries: list[dict[str, Any]]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    by_path = {str(entry.get("path", "")): entry for entry in entries}
    for path in sorted(GENERATED_DISTRIBUTIONS):
        entry = by_path.get(path)
        if entry is None:
            if (repository / _normalized_path(path)).exists():
                errors.append(
                    _error("missing-generated-boundary", path, "generated distribution root is not registered")
                )
            continue
        if entry.get("asset_class") != "generated_distribution" or entry.get("mutability") != "rebuildable":
            errors.append(
                _error(
                    "invalid-package-boundary",
                    path,
                    f"{path} must be generated_distribution and rebuildable",
                )
            )
        if entry.get("canonical_command") != PACKAGE_BUILD_COMMAND:
            errors.append(
                _error(
                    "invalid-package-command",
                    path,
                    f"{path} must use {PACKAGE_BUILD_COMMAND}",
                )
            )
    for path in sorted(INSTALLED_ROOTS):
        entry = by_path.get(path)
        if entry is None:
            if (repository / _normalized_path(path)).exists():
                errors.append(_error("missing-installed-boundary", path, "installed-copy root is not registered"))
            continue
        if entry.get("asset_class") != "installed_copy" or entry.get("mutability") != "generated_or_link":
            errors.append(
                _error(
                    "invalid-installed-boundary",
                    path,
                    f"{path} must be installed_copy and generated_or_link",
                )
            )
    for path in sorted(RUNTIME_ROOTS):
        entry = by_path.get(path)
        if entry is None:
            if (repository / _normalized_path(path)).exists():
                errors.append(_error("missing-runtime-boundary", path, "runtime root is not registered"))
            continue
        if entry.get("asset_class") != "runtime_state":
            errors.append(_error("invalid-runtime-boundary", path, f"{path} must be runtime_state"))
    return errors


def validate_repository(
    repository: Path,
    registry_path: Path,
    *,
    tracked_roots: set[str] | None = None,
    checkout_roots: set[str] | None = None,
    tracked_paths: set[str] | None = None,
) -> dict[str, Any]:
    """Return a stable report without mutating repository or registered paths."""

    repository = repository.resolve()
    entries, errors = _read_registry(registry_path)
    paths = (
        tracked_paths if tracked_paths is not None else (_tracked_paths(repository) if tracked_roots is None else set())
    )
    tracked_policy_known = tracked_paths is not None or tracked_roots is None
    roots = tracked_roots if tracked_roots is not None else {_root_name(path) for path in paths}
    observed_roots = (
        checkout_roots
        if checkout_roots is not None
        else (_checkout_roots(repository) if tracked_roots is None else set(roots))
    )
    for root in sorted(root for root in roots if not any(_entry_matches_root(entry, root) for entry in entries)):
        errors.append(_error("unregistered-tracked-root", root, "add a registry entry for this checkout root"))
    for root in sorted(
        root for root in observed_roots - roots if not any(_entry_matches_root(entry, root) for entry in entries)
    ):
        errors.append(_error("unregistered-checkout-root", root, "add a registry entry or relocate this path"))

    for entry in entries:
        path = str(entry.get("path", ""))
        matching_paths = [tracked_path for tracked_path in paths if _entry_contains_tracked_path(entry, tracked_path)]
        if tracked_policy_known and entry.get("tracked") is False and matching_paths:
            errors.append(
                _error("tracked-policy-mismatch", path, "registry marks this path untracked but Git contains it")
            )
        if tracked_policy_known and entry.get("tracked") is True and not matching_paths:
            errors.append(
                _error("tracked-policy-mismatch", path, "registry marks this path tracked but Git has no files")
            )

    errors.extend(_boundary_errors(repository, entries))

    ignore_rules = _read_ignore_rules(repository)
    protected_local_paths: list[str] = []
    for entry in entries:
        path = str(entry.get("path", ""))
        root = _root_name(path)
        if entry.get("tracked") is False:
            expected_rule = _exact_ignore_rule(path)
            if expected_rule not in ignore_rules:
                errors.append(
                    _error(
                        "missing-ignore-rule",
                        path,
                        "registered untracked root requires an exact .gitignore rule",
                    )
                )
            if (repository / _normalized_path(path)).exists():
                protected_local_paths.append(path)

    runtime_entry = next((entry for entry in entries if entry.get("path") == ".research-tree/"), None)
    if runtime_entry is not None:
        for authoring_root in entries:
            if authoring_root.get("asset_class") != "authoring_source":
                continue
            root_path = str(authoring_root.get("path", ""))
            if not root_path.endswith("/"):
                continue
            misplaced = repository / _normalized_path(root_path) / ".research-tree"
            if misplaced.exists():
                errors.append(
                    _error(
                        "misplaced-runtime-output",
                        f"{_normalized_path(root_path)}/.research-tree/",
                        "runtime state belongs in .research-tree/ via research-tree run-status",
                    )
                )

    errors.sort(key=lambda item: (item["path"], item["code"], item["detail"]))
    return {
        "status": "invalid" if errors else "valid",
        "errors": errors,
        "protected_local_paths": sorted(protected_local_paths),
    }


def migration_plan(repository: Path, registry_path: Path) -> dict[str, Any]:
    """Report operator-migrated path collisions without reading or moving content."""

    repository = repository.resolve()
    entries, errors = _read_registry(registry_path)
    items: list[dict[str, Any]] = []
    for entry in entries:
        if "migration_target" not in entry:
            continue
        source = str(entry.get("path", ""))
        destination = entry.get("migration_target")
        disposition = entry.get("migration_disposition")
        if not isinstance(destination, str) or not isinstance(disposition, str):
            errors.append(
                _error("invalid-migration-policy", source, "operator-migrated path requires target and disposition")
            )
            continue
        if not (repository / _normalized_path(source)).exists():
            continue
        items.append(
            {
                "source": source,
                "destination": destination,
                "disposition": disposition,
                "collision": (
                    _normalized_path(source) != _normalized_path(destination)
                    and (repository / _normalized_path(destination)).exists()
                ),
            }
        )
    items.sort(key=lambda item: item["source"])
    token_data = json.dumps(items, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "status": "invalid"
        if errors
        else ("collision_detected" if any(item["collision"] for item in items) else "planned"),
        "errors": sorted(errors, key=lambda item: (item["path"], item["code"], item["detail"])),
        "items": items,
        "confirmation_token": sha256(token_data).hexdigest() if items else None,
        "moves_performed": 0,
    }


def _git_status(repository: Path) -> str:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else ""


def workflow_probe(repository: Path) -> dict[str, Any]:
    """Exercise supported commands in a temporary project without mutating checkout state."""

    repository = repository.resolve()
    before = _git_status(repository)
    errors: list[dict[str, str]] = []
    with TemporaryDirectory(prefix="research-tree-layout-") as temporary:
        project = Path(temporary) / "project"
        home = Path(temporary) / "home"
        package_check = subprocess.run(
            [sys.executable, "scripts/build_skill_packages.py", "--check"],
            cwd=repository,
            capture_output=True,
            text=True,
            check=False,
        )
        if package_check.returncode:
            errors.append(_error("package-check-failed", "packages/", "build_skill_packages.py --check failed"))
        tests = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/test_skill_packages.py",
                "tests/test_migration.py",
            ],
            cwd=repository,
            capture_output=True,
            text=True,
            check=False,
        )
        if tests.returncode:
            errors.append(_error("workflow-tests-failed", "tests/", "supported package and migration tests failed"))
        install = subprocess.run(
            [
                sys.executable,
                "-m",
                "research_tree.skill_setup",
                "install",
                "--host",
                "codex",
                "--scope",
                "project",
                "--source",
                str(repository),
                "--project-root",
                str(project),
                "--home",
                str(home),
                "--mode",
                "copy",
            ],
            cwd=repository,
            capture_output=True,
            text=True,
            check=False,
        )
        installed_skill = project / ".agents" / "skills" / "research-tree" / "SKILL.md"
        if install.returncode or not installed_skill.is_file():
            errors.append(_error("install-probe-failed", ".agents/", "project-scoped Codex install failed"))
        sample = subprocess.run(
            [sys.executable, "-m", "research_tree.migration_cli", "--workspace", str(project), "inventory"],
            cwd=repository,
            capture_output=True,
            text=True,
            check=False,
        )
        if sample.returncode:
            errors.append(_error("sample-run-failed", ".research-tree/", "migration inventory failed"))
    after = _git_status(repository)
    if after != before:
        errors.append(_error("checkout-mutated", ".", "supported workflow changed checkout status"))
    errors.sort(key=lambda item: (item["path"], item["code"], item["detail"]))
    return {
        "status": "invalid" if errors else "valid",
        "errors": errors,
        "installed_project_roots": [".agents"],
        "sample_run": "migration_inventory",
        "repository_status_unchanged": after == before,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--migration-plan", action="store_true")
    parser.add_argument("--workflow-probe", action="store_true")
    args = parser.parse_args()
    repository = args.repo.resolve()
    registry = (args.registry or repository / DEFAULT_REGISTRY).resolve()
    if args.migration_plan:
        report = migration_plan(repository, registry)
    elif args.workflow_probe:
        report = workflow_probe(repository)
    else:
        report = validate_repository(repository, registry)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] in {"valid", "planned"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
