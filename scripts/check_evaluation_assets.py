"""Validate the repository's governed evaluation asset boundaries."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


DEFAULT_REGISTRY = Path("openspec/changes/unify-research-runtime-alpha2/registries/evaluation-paths-v1.json")
_LEGACY_PREFIX = "evaluation/experiences/"


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _error(code: str, path: str, detail: str) -> dict[str, str]:
    return {"code": code, "path": path, "detail": detail}


def _walk_values(value: Any, prefix: str = ""):
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{prefix}.{key}" if prefix else key
            yield child_path, key, child
            yield from _walk_values(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_values(child, f"{prefix}[{index}]")


def _contains_forbidden(value: Any, keys: set[str]) -> str | None:
    for path, key, child in _walk_values(value):
        lowered = key.lower()
        if lowered in keys:
            return path
        if isinstance(child, str) and any(
            marker in child.lower() for marker in ("-----begin private", "diff --git", "api_key=", "credential=")
        ):
            return path
    return None


def _load_json(path: Path, errors: list[dict[str, str]], relative: str) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(_error("invalid-json", relative, str(exc)))
        return None


def _case_ids(repo: Path, errors: list[dict[str, str]]) -> set[str]:
    ids: set[str] = set()
    cases_root = repo / "evaluation" / "cases"
    if not cases_root.exists():
        return ids
    for path in sorted(cases_root.glob("*.json")):
        data = _load_json(path, errors, _relative(path, repo))
        if not isinstance(data, dict):
            continue
        if isinstance(data.get("id"), str):
            ids.add(data["id"])
        if isinstance(data.get("cases"), list):
            for case in data["cases"]:
                if isinstance(case, dict) and isinstance(case.get("id"), str):
                    ids.add(case["id"])
    return ids


def _validate_case(relative: str, data: Any, errors: list[dict[str, str]], forbidden: set[str]) -> None:
    leak = _contains_forbidden(data, forbidden)
    if leak:
        errors.append(_error("hidden-material", relative, f"forbidden public field at {leak}"))
    if not isinstance(data, dict):
        errors.append(_error("invalid-case", relative, "case manifest must be an object"))
        return
    cases = data.get("cases")
    if not isinstance(cases, list):
        return
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str):
            errors.append(_error("invalid-case", relative, "every case must have a stable id"))
            continue
        if case["id"] in seen:
            errors.append(_error("invalid-case", relative, f"duplicate case id {case['id']}"))
        seen.add(case["id"])


def validate_repository(repository: Path, registry_path: Path) -> dict[str, Any]:
    repository = repository.resolve()
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    entries = registry.get("entries", [])
    forbidden = {key.lower() for key in registry.get("forbidden_public_keys", [])}
    errors: list[dict[str, str]] = []
    seen_ids = _case_ids(repository, errors)
    legacy_candidates: list[str] = []
    for entry in entries:
        path = entry["path"].rstrip("/")
        if entry.get("class") == "legacy-experience-input" and (repository / path).exists():
            legacy_candidates.append(entry["path"])

    forbidden_root = repository / "evals"
    if forbidden_root.exists():
        for path in sorted(p for p in forbidden_root.rglob("*") if p.is_file()):
            errors.append(
                _error("misplaced-path", _relative(path, repository), "evals/ is retired and has no active role")
            )

    for entry in entries:
        if not entry.get("tracked") or entry.get("class") in {"legacy-experience-input", "retired-ambiguous-root"}:
            continue
        root = repository / entry["path"].rstrip("/")
        if not root.exists():
            continue
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            relative = _relative(path, repository)
            try:
                size = path.stat().st_size
            except OSError as exc:
                errors.append(_error("unreadable-asset", relative, str(exc)))
                continue
            limit = entry.get("max_bytes", registry.get("limits", {}).get("tracked_asset_bytes"))
            if entry.get("class") in {"redacted-release-evidence", "registered-baseline", "blinded-review"}:
                class_limit = registry.get("limits", {}).get("tracked_result_bytes", limit)
                limit = min(candidate for candidate in (limit, class_limit) if candidate is not None)
            if limit is not None and size > limit:
                errors.append(_error("oversized-asset", relative, f"tracked asset exceeds {limit} bytes"))
            if path.suffix.lower() == ".json":
                data = _load_json(path, errors, relative)
                if data is not None:
                    if entry.get("class") in {"versioned-case", "public-fixture", "benchmark-protocol"}:
                        _validate_case(relative, data, errors, forbidden)
                    if entry.get("class") in {"redacted-release-evidence", "registered-baseline", "blinded-review"}:
                        leak = _contains_forbidden(data, forbidden)
                        if leak:
                            errors.append(_error("hidden-material", relative, f"forbidden field at {leak}"))
                        required = set(registry.get("provenance_required", []))
                        missing = sorted(key for key in required if key not in data)
                        if missing:
                            errors.append(_error("missing-provenance", relative, ", ".join(missing)))
                        case_id = data.get("case_id")
                        if isinstance(case_id, str) and case_id not in seen_ids:
                            errors.append(_error("dangling-reference", relative, f"unknown case id {case_id}"))
    errors.sort(key=lambda item: (item["path"], item["code"], item["detail"]))
    return {
        "status": "invalid" if errors else "valid",
        "errors": errors,
        "legacy_candidates": sorted(legacy_candidates),
    }


def run_public_alpha1(repository: Path, registry_path: Path) -> dict[str, Any]:
    report = validate_repository(repository, registry_path)
    manifest = repository / "evaluation" / "cases" / "alpha1-adversarial-v1.json"
    if not manifest.exists():
        return {
            "status": "unavailable",
            "manifest": "evaluation/cases/alpha1-adversarial-v1.json",
            "errors": report["errors"],
        }
    payload = manifest.read_bytes()
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    if report["errors"]:
        return {
            "status": "invalid",
            "manifest": _relative(manifest, repository),
            "manifest_digest": digest,
            "errors": report["errors"],
        }
    return {
        "status": "validated",
        "manifest": _relative(manifest, repository),
        "manifest_digest": digest,
        "case_count": len(json.loads(payload)["cases"]),
        "errors": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--public-alpha1", action="store_true")
    args = parser.parse_args()
    repository = args.repo.resolve()
    registry = (args.registry or repository / DEFAULT_REGISTRY).resolve()
    result = (
        run_public_alpha1(repository, registry) if args.public_alpha1 else validate_repository(repository, registry)
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") in {"valid", "validated"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
