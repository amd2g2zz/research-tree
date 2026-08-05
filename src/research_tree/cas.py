"""Small content-addressed store for evidence and large run artifacts."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile


class CASError(ValueError):
    pass


class CASIntegrityError(CASError):
    pass


class ContentAddressedStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve() / ".research-tree" / "cas" / "sha256"
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def digest(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def path_for(self, digest: str) -> Path:
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise CASError("digest must be a lowercase SHA-256 hex digest")
        return self.root / digest[:2] / digest

    def put_bytes(self, data: bytes) -> dict[str, object]:
        if not isinstance(data, bytes):
            raise CASError("CAS content must be bytes")
        digest = self.digest(data)
        destination = self.path_for(digest)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
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
        return {"digest": digest, "locator": str(destination), "size": len(data)}

    def put_file(self, path: str | Path) -> dict[str, object]:
        return self.put_bytes(Path(path).read_bytes())

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
        return {"digest": digest, "size": len(data), "status": "verified"}
