"""Small content-addressed store for evidence and large run artifacts."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
from pathlib import Path
import tempfile
from typing import Any


class CASError(ValueError):
    pass


class CASIntegrityError(CASError):
    pass


class ContentAddressedStore:
    def __init__(self, root: str | Path) -> None:
        self.workspace = Path(root).resolve()
        self.root = self.workspace / ".research-tree" / "cas" / "sha256"
        self.metadata_root = self.workspace / ".research-tree" / "cas" / "metadata"
        self.quarantine_root = self.workspace / ".research-tree" / "cas" / "quarantine"
        self.quarantine_metadata_root = self.quarantine_root / "metadata"
        self.root.mkdir(parents=True, exist_ok=True)
        self.metadata_root.mkdir(parents=True, exist_ok=True)
        self.quarantine_root.mkdir(parents=True, exist_ok=True)
        self.quarantine_metadata_root.mkdir(parents=True, exist_ok=True)

    def _inside_workspace(self, path: Path) -> Path:
        resolved = path.resolve(strict=False)
        try:
            resolved.relative_to(self.workspace)
        except ValueError as exc:
            raise CASError("CAS input must remain inside workspace") from exc
        return resolved

    @staticmethod
    def digest(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def path_for(self, digest: str) -> Path:
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise CASError("digest must be a lowercase SHA-256 hex digest")
        return self.root / digest[:2] / digest

    def put_bytes(
        self,
        data: bytes,
        *,
        media_type: str = "application/octet-stream",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        record = self._record(data, media_type=media_type, metadata=metadata)
        digest = str(record["digest"])
        destination = self.path_for(digest)
        self._write_blob(destination, data)
        record["locator"] = str(destination)
        self._write_metadata(digest, record)
        return record

    def stage_bytes(
        self,
        data: bytes,
        *,
        media_type: str = "application/octet-stream",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        """Write an inert blob that cannot be read until an explicit promote."""

        record = self._record(data, media_type=media_type, metadata=metadata)
        digest = str(record["digest"])
        destination = self.quarantine_root / digest
        self._write_blob(destination, data)
        staged = {**record, "locator": str(destination), "status": "staged"}
        self._write_metadata(digest, staged, root=self.quarantine_metadata_root)
        return staged

    def promote(self, digest: str) -> dict[str, object]:
        staged_path = self.quarantine_root / self.path_for(digest).name
        if not staged_path.is_file():
            raise CASError(f"staged CAS blob is unavailable: {digest}")
        data = staged_path.read_bytes()
        if self.digest(data) != digest:
            raise CASIntegrityError(f"staged CAS blob digest mismatch: {digest}")
        destination = self.path_for(digest)
        self._write_blob(destination, data)
        metadata_path = self.quarantine_metadata_root / f"{digest}.json"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CASIntegrityError(f"staged CAS metadata is unavailable: {digest}") from exc
        committed = {
            **metadata,
            "locator": str(destination),
            "status": "committed",
        }
        self._write_metadata(digest, committed)
        staged_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        return committed

    def quarantine(self, digest: str, *, reason: str) -> dict[str, object]:
        if not isinstance(reason, str) or not reason.strip():
            raise CASError("quarantine reason must be nonempty")
        source = self.path_for(digest)
        if not source.is_file():
            source = self.quarantine_root / digest
        if not source.is_file():
            raise CASError(f"CAS blob is unavailable: {digest}")
        destination = self.quarantine_root / digest
        if source != destination:
            self._write_blob(destination, source.read_bytes())
            source.unlink()
        record = {
            "schema_version": 1,
            "digest": digest,
            "locator": str(destination),
            "size": destination.stat().st_size,
            "status": "quarantined",
            "reason": reason,
        }
        self._write_metadata(digest, record, root=self.quarantine_metadata_root)
        return record

    def _record(
        self,
        data: bytes,
        *,
        media_type: str,
        metadata: dict[str, Any] | None,
    ) -> dict[str, object]:
        if not isinstance(data, bytes):
            raise CASError("CAS content must be bytes")
        if not isinstance(media_type, str) or not media_type.strip() or "/" not in media_type:
            raise CASError("media_type must be a nonempty MIME type")
        if metadata is not None and not isinstance(metadata, dict):
            raise CASError("CAS metadata must be an object")
        digest = self.digest(data)
        return {
            "schema_version": 1,
            "digest": digest,
            "locator": str(self.path_for(digest)),
            "size": len(data),
            "media_type": media_type,
            "metadata": metadata or {},
        }

    @staticmethod
    def _write_blob(destination: Path, data: bytes) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            return
        descriptor, raw_path = tempfile.mkstemp(prefix=".cas-", dir=destination.parent)
        temporary = Path(raw_path)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    def put_file(self, path: str | Path, *, media_type: str | None = None) -> dict[str, object]:
        resolved = self._inside_workspace(Path(path))
        selected_media_type = media_type or mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
        return self.put_bytes(resolved.read_bytes(), media_type=selected_media_type)

    def _metadata_path(self, digest: str) -> Path:
        self.path_for(digest)
        return self.metadata_root / f"{digest}.json"

    def _write_metadata(
        self,
        digest: str,
        value: dict[str, Any],
        *,
        root: Path | None = None,
    ) -> None:
        destination = (root or self.metadata_root) / f"{digest}.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, raw_path = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        temporary = Path(raw_path)
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    def read(self, digest: str) -> bytes:
        path = self.path_for(digest)
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise CASError(f"CAS blob is unavailable: {digest}") from exc
        if self.digest(data) != digest:
            raise CASIntegrityError(f"CAS blob digest mismatch: {digest}")
        return data

    def verify(self, digest: str) -> dict[str, object]:
        data = self.read(digest)
        metadata_path = self._metadata_path(digest)
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CASIntegrityError(f"CAS metadata is unavailable: {digest}") from exc
        if not isinstance(metadata, dict) or metadata.get("digest") != digest:
            raise CASIntegrityError(f"CAS metadata digest mismatch: {digest}")
        if metadata.get("size") != len(data):
            raise CASIntegrityError(f"CAS metadata size mismatch: {digest}")
        return {**metadata, "status": "verified"}
