"""Workspace-scoped, content-addressed storage for large research artifacts."""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


class ContentStoreError(Exception):
    """Base class for content-store failures."""


class ContentIntegrityError(ContentStoreError):
    """Stored bytes or metadata do not match their digest."""


class ContentPathError(ContentStoreError):
    """A locator escapes the workspace or is not a regular file."""


@dataclass(frozen=True)
class ContentObject:
    digest: str
    media_type: str
    byte_size: int
    locator: str
    availability: str = "available"
    created_at: str = ""

    def __post_init__(self) -> None:
        if len(self.digest) != 64 or any(char not in "0123456789abcdef" for char in self.digest):
            raise ContentIntegrityError("digest must be a lowercase SHA-256 hex string")
        if not self.media_type.strip():
            raise ContentIntegrityError("media_type must not be empty")
        if self.byte_size < 0:
            raise ContentIntegrityError("byte_size must not be negative")
        if self.availability not in {"available", "quarantined", "unavailable"}:
            raise ContentIntegrityError("invalid content availability")
        if self.created_at:
            try:
                datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
            except ValueError as error:
                raise ContentIntegrityError("created_at must be an ISO-8601 timestamp") from error


class ContentAddressedStore:
    """Publish immutable bytes and expose only digest-verified reads."""

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).resolve()
        self.root = self.workspace / ".research-tree"
        self.cas_root = self.root / "cas" / "sha256"
        self.staging_root = self.root / "staging"
        self.quarantine_root = self.root / "quarantine"
        self._before_publish: Callable[[], None] = lambda: None

    def ingest(self, data: bytes, media_type: str) -> ContentObject:
        if not isinstance(data, bytes):
            raise TypeError("CAS ingest requires bytes")
        if not isinstance(media_type, str) or not media_type.strip():
            raise ContentIntegrityError("media_type must not be empty")
        digest = hashlib.sha256(data).hexdigest()
        destination = self._object_path(digest)
        self.staging_root.mkdir(parents=True, exist_ok=True)
        temporary = self.staging_root / f"{uuid.uuid4().hex}.part"
        try:
            with temporary.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if self._digest(temporary) != digest or temporary.stat().st_size != len(data):
                raise ContentIntegrityError("staged bytes failed digest verification")
            self._before_publish()
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                self._verify_path(destination, digest, len(data))
            else:
                try:
                    os.link(temporary, destination)
                except FileExistsError:
                    self._verify_path(destination, digest, len(data))
            return ContentObject(
                digest=digest,
                media_type=media_type.strip(),
                byte_size=len(data),
                locator=self._locator(destination),
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def read(self, content: ContentObject | str) -> bytes:
        digest = content.digest if isinstance(content, ContentObject) else content
        path = self._object_path(digest)
        self._verify_path(path, digest, None if not isinstance(content, ContentObject) else content.byte_size)
        return path.read_bytes()

    def quarantine_orphans(self, referenced_digests: set[str]) -> tuple[str, ...]:
        """Move unreferenced staged/published objects out of canonical reads."""
        self.quarantine_root.mkdir(parents=True, exist_ok=True)
        moved: list[str] = []
        for path in self._candidate_files():
            digest = self._digest(path) if path.parent.name == "staging" else path.name
            if digest in referenced_digests:
                continue
            target = self.quarantine_root / f"{digest}.{uuid.uuid4().hex}.orphan"
            os.replace(path, target)
            moved.append(digest)
        return tuple(sorted(moved))

    def _candidate_files(self) -> tuple[Path, ...]:
        candidates = [path for path in self.staging_root.glob("*.part") if path.is_file()]
        if self.cas_root.exists():
            candidates.extend(path for path in self.cas_root.glob("*/*") if path.is_file())
        return tuple(candidates)

    def _object_path(self, digest: str) -> Path:
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ContentIntegrityError("digest must be a lowercase SHA-256 hex string")
        path = self.cas_root / digest[:2] / digest
        self._assert_within_workspace(path)
        return path

    def _locator(self, path: Path) -> str:
        self._assert_within_workspace(path)
        return path.relative_to(self.workspace).as_posix()

    def _assert_within_workspace(self, path: Path) -> None:
        try:
            path.resolve(strict=False).relative_to(self.workspace)
        except ValueError as error:
            raise ContentPathError("content locator escapes workspace") from error

    @staticmethod
    def _digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _verify_path(self, path: Path, digest: str, expected_size: int | None) -> None:
        self._assert_within_workspace(path)
        if path.is_symlink() or not path.is_file():
            raise ContentPathError("CAS locator is not a regular file")
        actual_size = path.stat().st_size
        if expected_size is not None and actual_size != expected_size:
            raise ContentIntegrityError(f"CAS byte-size mismatch: {digest}")
        if self._digest(path) != digest:
            raise ContentIntegrityError(f"CAS digest mismatch: {digest}")
