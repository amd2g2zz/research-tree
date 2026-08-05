"""Non-destructive, digest-addressed migration inventory and cutover helpers."""

from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any, Iterable


class MigrationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MigrationEntry:
    source: str
    destination: str
    source_digest: str
    disposition: str
    collision: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MigrationManager:
    """Plan and apply copies within a workspace without deleting user data."""

    def __init__(self, workspace: str | Path, *, manifest_name: str = "migration-manifest.json") -> None:
        self.workspace = Path(workspace).resolve()
        self.state_dir = self.workspace / ".research-tree"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.state_dir / manifest_name

    def _inside(self, path: Path) -> Path:
        resolved = path.resolve(strict=False)
        try:
            resolved.relative_to(self.workspace)
        except ValueError as exc:
            raise MigrationError("migration path escapes workspace") from exc
        return resolved

    @staticmethod
    def _digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def inventory(self, sources: Iterable[str | Path], *, destination_root: str | Path = ".research-tree/imported") -> dict[str, Any]:
        destination_root_path = self._inside(self.workspace / destination_root)
        entries: list[MigrationEntry] = []
        for raw in sources:
            source = self._inside(self.workspace / raw if not Path(raw).is_absolute() else Path(raw))
            if not source.is_file():
                raise MigrationError(f"source is not a file: {raw}")
            relative = source.relative_to(self.workspace)
            destination = self._inside(destination_root_path / relative.name)
            digest = self._digest(source)
            collision = destination.exists() and self._digest(destination) != digest
            disposition = "collision" if collision else ("already_imported" if destination.exists() else "planned")
            entries.append(MigrationEntry(relative.as_posix(), destination.relative_to(self.workspace).as_posix(), digest, disposition, collision))
        return {"schema_version": 1, "workspace": str(self.workspace), "entries": [entry.to_dict() for entry in entries], "source_count": len(entries)}

    def dry_run(self, sources: Iterable[str | Path], *, destination_root: str | Path = ".research-tree/imported") -> dict[str, Any]:
        plan = self.inventory(sources, destination_root=destination_root)
        plan["mode"] = "dry-run"
        return plan

    def apply(self, sources: Iterable[str | Path], *, destination_root: str | Path = ".research-tree/imported", confirmation: str | None = None) -> dict[str, Any]:
        plan = self.inventory(sources, destination_root=destination_root)
        if any(item["collision"] for item in plan["entries"]):
            raise MigrationError("migration has collisions; resolve them before apply")
        if confirmation != "CONFIRM-MIGRATION":
            raise MigrationError("operator confirmation is required")
        for item in plan["entries"]:
            source = self._inside(self.workspace / item["source"])
            destination = self._inside(self.workspace / item["destination"])
            if item["disposition"] == "already_imported":
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        plan["mode"] = "applied"
        self.manifest_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        return plan

    def status(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            return {"status": "not_started", "manifest": None}
        return {"status": "applied", "manifest": json.loads(self.manifest_path.read_text(encoding="utf-8"))}

    def verify(self) -> dict[str, Any]:
        status = self.status()
        if status["status"] != "applied":
            raise MigrationError("no applied migration manifest")
        failures = []
        for item in status["manifest"]["entries"]:
            path = self._inside(self.workspace / item["destination"])
            if not path.is_file() or self._digest(path) != item["source_digest"]:
                failures.append(item["destination"])
        return {"status": "verified" if not failures else "failed", "failures": failures}

    def rollback(self) -> dict[str, Any]:
        status = self.status()
        if status["status"] != "applied":
            return {"status": "not_started", "removed": []}
        removed = []
        for item in status["manifest"]["entries"]:
            destination = self._inside(self.workspace / item["destination"])
            if destination.is_file() and self._digest(destination) == item["source_digest"]:
                destination.unlink()
                removed.append(item["destination"])
        self.manifest_path.unlink(missing_ok=True)
        return {"status": "rolled_back", "removed": removed}
