from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
REGISTRY = ROOT / "openspec/changes/unify-research-runtime-alpha2/registries/repository-paths-v1.json"


def checker():
    spec = importlib.util.spec_from_file_location(
        "check_repository_layout", ROOT / "scripts/check_repository_layout.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_registry(root: Path, entries: list[dict[str, object]]) -> Path:
    if not (root / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    path = root / "registry.json"
    path.write_text(json.dumps({"schema_version": 1, "entries": entries}), encoding="utf-8")
    return path


def report(root: Path, entries: list[dict[str, object]], **kwargs: object) -> dict[str, object]:
    return checker().validate_repository(root, write_registry(root, entries), **kwargs)


def entry(path: str, **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "path": path,
        "asset_class": "authoring_source",
        "owner": "maintainers",
        "mutability": "source",
        "tracked": True,
        "distributed": False,
        "cleanup_safety": "never_delete",
        "canonical_command": "uv run pytest -q",
        "lifecycle": "active",
    }
    value.update(overrides)
    return value


def local_entry(path: str, **overrides: object) -> dict[str, object]:
    value = entry(
        path,
        asset_class="installed_copy",
        owner="codex",
        mutability="generated_or_link",
        tracked=False,
        cleanup_safety="explicit_confirmation",
        canonical_command="research-tree-setup install --host codex --scope project",
        lifecycle="local",
    )
    value.update(overrides)
    return value


def error(code: str, path: str, detail: str) -> dict[str, str]:
    return {"code": code, "path": path, "detail": detail}


def test_current_registry_covers_checkout_and_lifecycle() -> None:
    entries = {item["path"]: item for item in json.loads(REGISTRY.read_text(encoding="utf-8"))["entries"]}

    assert set(entries) >= {
        ".github/",
        ".research-tree-hermes/",
        ".research-tree-native/",
        "src/",
        "tests/",
        "pyproject.toml",
        "README.md",
    }
    assert all(item["lifecycle"] for item in entries.values())
