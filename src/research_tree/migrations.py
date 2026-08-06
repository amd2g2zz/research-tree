"""Non-destructive, digest-addressed migration inventory and cutover helpers."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any, Iterable

from .domain import thaw_json
from .sqlite_ledger import SQLiteLedgerError, SQLiteRunLedger
from .storage import RunStore


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


class LegacyRunStoreImporter:
    """Idempotently import immutable alpha1 rounds without trusting closure state."""

    def __init__(self, source_root: str | Path, destination_workspace: str | Path) -> None:
        self.source_root = Path(source_root).resolve()
        self.store = RunStore(self.source_root)
        self.ledger = SQLiteRunLedger(destination_workspace)
        with self.ledger._connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS legacy_imports(source_digest TEXT PRIMARY KEY,source_root TEXT NOT NULL,round_id TEXT NOT NULL,artifact_count INTEGER NOT NULL,imported_at TEXT NOT NULL)")

    def _source_digest(self, round_id: str) -> str:
        root = self.source_root / "rounds" / round_id
        digest = hashlib.sha256()
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            digest.update(path.relative_to(root).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
        return digest.hexdigest()

    def import_round(self, round_id: str) -> dict[str, Any]:
        snapshot = self.store.load_round(round_id)
        source_digest = self._source_digest(round_id)
        with self.ledger._connect() as connection:
            prior = connection.execute("SELECT artifact_count FROM legacy_imports WHERE source_digest=?", (source_digest,)).fetchone()
        if prior is not None:
            return {"status": "already_imported", "round_id": round_id, "source_digest": source_digest, "artifact_count": prior["artifact_count"]}
        try:
            self.ledger.run(round_id)
        except SQLiteLedgerError as exc:
            if exc.code != "run_not_found":
                raise
            self.ledger.create_run(
                round_id,
                task_identity={"legacy_source": str(self.source_root)},
                parent_run_id=snapshot.record.parent_round_id,
            )
        pending = list(snapshot.artifacts)
        imported = 0
        while pending:
            remaining = []
            progressed = False
            for artifact in pending:
                try:
                    self.ledger.append_artifact(run_id=round_id, artifact_id=artifact.id, kind=artifact.kind, payload=thaw_json(artifact.payload), actor_kind="migration", actor_id="alpha1-importer", status="legacy_unverified", parent_refs=[{"run_id": ref.round_id, "artifact_id": ref.artifact_id, "revision": ref.revision} for ref in artifact.parent_refs], expected_revision=artifact.revision - 1, created_at=artifact.created_at)
                    imported += 1
                    progressed = True
                except SQLiteLedgerError as exc:
                    if exc.code == "dangling_parent":
                        remaining.append(artifact)
                    elif exc.code in {"stale_revision", "artifact_conflict"}:
                        resolved = self.ledger.resolve(round_id, artifact.id, artifact.revision)
                        if resolved["status"] != "legacy_unverified":
                            raise MigrationError("legacy import collides with canonical artifact") from exc
                    else:
                        raise
            if remaining and not progressed:
                raise MigrationError("legacy lineage cannot be resolved")
            pending = remaining
        with self.ledger._connect() as connection:
            connection.execute("INSERT INTO legacy_imports VALUES(?,?,?,?,?)", (source_digest, str(self.source_root), round_id, imported, datetime.now(timezone.utc).isoformat()))
        return {"status": "imported", "round_id": round_id, "source_digest": source_digest, "artifact_count": imported, "closure_disposition": "legacy_unverified"}
