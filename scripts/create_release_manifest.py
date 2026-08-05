"""Build an immutable, machine-readable alpha2 release evidence manifest."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


HOST_PACKAGE_DIRS = {"codex": Path("packages/codex/research-tree"), "claude-code": Path("packages/claude-code/research-tree"), "hermes": Path("packages/hermes/research-tree")}


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file() and "__pycache__" not in item.parts and not item.name.endswith(".pyc")):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def build_manifest(*, repository: str | Path, source_revision: str, commands: Sequence[Mapping[str, Any]], evaluations: Sequence[Mapping[str, Any]], gates: Sequence[Mapping[str, Any]], limitations: Sequence[str] = (), verifier_identity: str = "research-tree-release-builder-v1", created_at: str | None = None) -> dict[str, Any]:
    root = Path(repository).resolve()
    packages = []
    for host, relative in HOST_PACKAGE_DIRS.items():
        package = root / relative
        packages.append({"host": host, "package_revision": source_revision, "package_digest": _tree_digest(package) if package.is_dir() else "0" * 64, "smoke_result": "not_run"})
    schema_dir = root / "openspec/changes/unify-research-runtime-alpha2/schemas"
    schema_versions = {path.stem: 1 for path in sorted(schema_dir.glob("*.json"))}
    return {"manifest_version": 1, "source_revision": str(source_revision), "created_at": created_at or datetime.now(timezone.utc).isoformat(), "schema_versions": schema_versions, "host_packages": packages, "commands": [dict(item) for item in commands], "evaluations": [dict(item) for item in evaluations], "gates": [dict(item) for item in gates], "limitations": [str(item) for item in limitations], "verifier": {"identity": verifier_identity, "algorithm": "sha256-tree"}}


def write_manifest(path: str | Path, manifest: Mapping[str, Any]) -> Path:
    destination = Path(path).resolve()
    if destination.exists():
        raise FileExistsError(f"release manifest is immutable: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(dict(manifest), ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return destination


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verifier", default="research-tree-release-builder-v1")
    args = parser.parse_args(argv)
    manifest = build_manifest(repository=args.repository, source_revision=args.source_revision, commands=(), evaluations=(), gates=(), verifier_identity=args.verifier)
    print(write_manifest(args.output, manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
