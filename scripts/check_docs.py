"""Validate documentation authority, terminology, links, and generated copies."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_REGISTRY = Path("openspec/changes/unify-research-runtime-alpha2/registries/documentation-authority-v1.json")
REQUIRED_FIELDS = (
    "path",
    "class",
    "authority",
    "audience",
    "owner",
    "lifecycle",
    "canonical_edit",
    "update_trigger",
    "superseded_by",
    "validation_rule",
)
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^]]*\]\(([^)]+)\)")


def _error(code: str, path: str, detail: str) -> dict[str, str]:
    return {"code": code, "path": path, "detail": detail}


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _match_entry(relative: str, entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    matches = [
        item
        for item in entries
        if relative == item["path"].rstrip("/") or relative.startswith(item["path"].rstrip("/") + "/")
    ]
    return max(matches, key=lambda item: len(item["path"])) if matches else None


def _validate_registry(registry: Any) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    if not isinstance(registry, dict) or not isinstance(registry.get("entries"), list):
        return [], [_error("invalid-registry", "entries", "registry requires an entries array")]
    entries: list[dict[str, Any]] = []
    for index, entry in enumerate(registry["entries"]):
        if not isinstance(entry, dict):
            errors.append(_error("invalid-registry", f"entries[{index}]", "entry must be an object"))
            continue
        for field in REQUIRED_FIELDS:
            if field not in entry:
                errors.append(_error("invalid-registry", f"entries[{index}].{field}", "field is required"))
        if isinstance(entry.get("path"), str) and entry["path"]:
            entries.append(entry)
        else:
            errors.append(_error("invalid-registry", f"entries[{index}].path", "path must be non-empty"))
        if entry.get("lifecycle") in {"historical", "superseded"} and not entry.get("superseded_by"):
            errors.append(
                _error("invalid-registry", f"entries[{index}].superseded_by", "historical entries require a successor")
            )
    paths = [item["path"] for item in entries]
    if len(paths) != len(set(paths)):
        errors.append(_error("invalid-registry", "entries", "paths must be unique"))
    return entries, errors


def _is_external(target: str) -> bool:
    return target.startswith(("#", "http://", "https://", "mailto:", "tel:"))


def _check_links(path: Path, root: Path, errors: list[dict[str, str]]) -> None:
    text = path.read_text(encoding="utf-8")
    for target in MARKDOWN_LINK.findall(text):
        destination = target.split("#", 1)[0].strip().strip("<>")
        if not destination or _is_external(destination):
            continue
        candidate = (path.parent / destination).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            errors.append(_error("broken-link", _relative(path, root), f"link escapes repository: {target}"))
            continue
        if not candidate.exists():
            errors.append(_error("broken-link", _relative(path, root), f"missing target: {target}"))


def _check_package_provenance(repository: Path, errors: list[dict[str, str]]) -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_skill_packages.py", "--check"],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        detail = (
            (result.stderr or result.stdout).strip().splitlines()[-1]
            if (result.stderr or result.stdout).strip()
            else "package check failed"
        )
        errors.append(_error("stale-generated-copy", "packages/", detail))


def validate_repository(repository: Path, registry_path: Path, *, check_packages: bool = False) -> dict[str, Any]:
    repository = repository.resolve()
    errors: list[dict[str, str]] = []
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"status": "invalid", "errors": [_error("invalid-registry", str(registry_path), str(exc))]}
    entries, registry_errors = _validate_registry(registry)
    errors.extend(registry_errors)
    forbidden_terms = [term for term in registry.get("forbidden_active_terms", []) if isinstance(term, str)]
    for path in sorted(repository.rglob("*.md")):
        relative = _relative(path, repository)
        if any(part in {".git", ".venv", ".pytest_cache", "build", "dist"} for part in path.parts):
            continue
        entry = _match_entry(relative, entries)
        if entry is None:
            errors.append(_error("undocumented-root", relative, "no documentation authority entry"))
            continue
        if re.search(r"(?:session[-_ ]?log|report)", path.name, re.IGNORECASE) and entry["class"] not in {
            "operational",
            "evaluation",
            "historical",
        }:
            errors.append(
                _error("misplaced-session-log", relative, "report or session log is outside an allowed class")
            )
        if entry.get("lifecycle") not in {"historical", "superseded"} and not entry.get("legacy_compatibility"):
            text = path.read_text(encoding="utf-8")
            for term in forbidden_terms:
                if term in text:
                    errors.append(_error("legacy-term", relative, f"retired active term: {term}"))
        _check_links(path, repository, errors)
    if check_packages and any(item.get("validation_rule") == "package-build-check" for item in entries):
        _check_package_provenance(repository, errors)
    errors.sort(key=lambda item: (item["path"], item["code"], item["detail"]))
    return {"status": "invalid" if errors else "valid", "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--skip-package-check", action="store_true")
    args = parser.parse_args()
    repository = args.repo.resolve()
    registry = (args.registry or repository / DEFAULT_REGISTRY).resolve()
    report = validate_repository(repository, registry, check_packages=not args.skip_package_check)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
