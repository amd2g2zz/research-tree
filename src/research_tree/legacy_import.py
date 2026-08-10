"""Idempotent, low-trust import of Alpha1 filesystem rounds."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from .domain import ArtifactRef, LineageEvent, RoundSnapshot, canonical_json_bytes, validate_identifier
from .run_ledger import LedgerConflictError, LedgerError, LedgerIntegrityError, RunLedger
from .storage import RunStore


class LegacyImportError(LedgerError):
    """A legacy source cannot be imported without trusting unsupported state."""


@dataclass(frozen=True)
class LegacyImportReceipt:
    source_digest: str
    source_locator: str
    run_id: str | None
    disposition: str
    detail_json: str
    created_at: str

    def __post_init__(self) -> None:
        if len(self.source_digest) != 64 or any(c not in "0123456789abcdef" for c in self.source_digest):
            raise LegacyImportError("source_digest must be a lowercase SHA-256 digest")
        if self.disposition not in {"imported", "legacy_unverified", "quarantined", "conflict", "already_imported"}:
            raise LegacyImportError("invalid legacy import disposition")
        if self.run_id is not None:
            validate_identifier(self.run_id, "run_id")


@dataclass(frozen=True)
class LegacyImportResult:
    receipt: LegacyImportReceipt
    snapshot: RoundSnapshot | None


class LegacyRunStoreImporter:
    """Read legacy files without modifying them or inheriting their authority."""

    def __init__(self, legacy_root: str | Path, ledger: RunLedger) -> None:
        self.legacy_root = Path(legacy_root).resolve(strict=False)
        self.ledger = ledger

    def import_round(self, round_id: str, *, dry_run: bool = False) -> LegacyImportResult:
        round_id = validate_identifier(round_id, "round_id")
        source_dir = self.legacy_root / "rounds" / round_id
        source_digest = self._source_digest(source_dir)
        source_locator = source_dir.relative_to(self.legacy_root).as_posix() if source_dir.is_relative_to(self.legacy_root) else str(source_dir)
        existing = self.ledger.get_import_receipt(source_digest)
        if existing is not None:
            return LegacyImportResult(
                LegacyImportReceipt(source_digest, existing.source_locator, existing.run_id, "already_imported", existing.detail_json, existing.created_at),
                None,
            )
        try:
            snapshot = RunStore(self.legacy_root).load_round(round_id)
        except Exception as error:
            receipt = self._receipt(source_digest, source_locator, None, "quarantined", {"error": type(error).__name__, "message": str(error)})
            self.ledger.record_import_receipt(receipt)
            return LegacyImportResult(receipt, None)
        if dry_run:
            receipt = self._receipt(source_digest, source_locator, snapshot.record.id, "legacy_unverified", self._detail(snapshot))
            return LegacyImportResult(receipt, snapshot)
        try:
            self.ledger.create_run(snapshot.record.id)
        except LedgerConflictError as error:
            receipt = self._receipt(source_digest, source_locator, snapshot.record.id, "conflict", {"error": "run_id_collision", "message": str(error)})
            self.ledger.record_import_receipt(receipt)
            return LegacyImportResult(receipt, snapshot)
        mapping: dict[ArtifactRef, ArtifactRef] = {}
        try:
            expected_revision = 0
            for artifact in snapshot.artifacts:
                parents: list[ArtifactRef] = []
                for parent in artifact.parent_refs:
                    if parent not in mapping:
                        raise LegacyImportError(f"parent is outside imported round: {parent}")
                    parents.append(mapping[parent])
                imported = self.ledger.append_artifact(
                    snapshot.record.id,
                    artifact.id,
                    f"legacy-{artifact.kind}",
                    {"legacy_disposition": "legacy_unverified", "source_artifact": artifact.to_dict()},
                    parent_refs=parents,
                    expected_revision=expected_revision,
                )
                expected_revision = self.ledger.get_revision(snapshot.record.id)
                mapping[ArtifactRef(snapshot.record.id, artifact.id, artifact.revision)] = ArtifactRef(snapshot.record.id, imported.id, imported.revision)
            for event in snapshot.lineage_events:
                mapped_ref = mapping.get(event.artifact_ref) if event.artifact_ref is not None else None
                self.ledger.append_event(
                    snapshot.record.id,
                    LineageEvent(
                        id=f"legacy-{event.id}",
                        round_id=snapshot.record.id,
                        kind=f"legacy-{event.kind}",
                        created_at=event.created_at,
                        artifact_ref=mapped_ref,
                        parent_round_id=event.parent_round_id,
                    ),
                    expected_revision=self.ledger.get_revision(snapshot.record.id),
                )
            receipt = self._receipt(source_digest, source_locator, snapshot.record.id, "imported", self._detail(snapshot))
            self.ledger.record_import_receipt(receipt)
            return LegacyImportResult(receipt, snapshot)
        except Exception as error:
            receipt = self._receipt(source_digest, source_locator, snapshot.record.id, "quarantined", {"error": type(error).__name__, "message": str(error)})
            self.ledger.record_import_receipt(receipt)
            return LegacyImportResult(receipt, snapshot)

    @staticmethod
    def _detail(snapshot: RoundSnapshot) -> dict[str, Any]:
        return {
            "legacy_round": snapshot.record.to_dict(),
            "artifact_count": len(snapshot.artifacts),
            "event_count": len(snapshot.lineage_events),
            "trust": "historical-only; closure, validation, and delivery claims require revalidation",
        }

    @staticmethod
    def _receipt(source_digest: str, source_locator: str, run_id: str | None, disposition: str, detail: dict[str, Any]) -> LegacyImportReceipt:
        return LegacyImportReceipt(source_digest, source_locator, run_id, disposition, json.dumps(detail, sort_keys=True), datetime.now(timezone.utc).isoformat())

    @staticmethod
    def _source_digest(source_dir: Path) -> str:
        if not source_dir.exists() or not source_dir.is_dir():
            raise LegacyImportError(f"legacy round does not exist: {source_dir}")
        entries: list[dict[str, Any]] = []
        for path in sorted(source_dir.rglob("*"), key=lambda item: item.as_posix()):
            if path.is_symlink() or not path.is_file():
                continue
            raw = path.read_bytes()
            entries.append({"path": path.relative_to(source_dir).as_posix(), "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)})
        return hashlib.sha256(canonical_json_bytes(entries)).hexdigest()
