"""Filesystem repository for mutable research state and frozen snapshots."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from contextlib import contextmanager


def workspace() -> Path:
    return Path(os.environ.get("RESEARCH_WORKSPACE", os.getcwd()))


def drift_dir() -> Path:
    return workspace() / "research_drift"


def state_path() -> Path:
    return drift_dir() / "research_state.json"


def log_path() -> Path:
    return drift_dir() / "drift_log.jsonl"


def lock_path() -> Path:
    return drift_dir() / ".research_state.lock"


def pages_dir() -> Path:
    return drift_dir() / "pages"


def saved_page_path(value: str) -> Path:
    """Resolve an evidence path while confining it to the page store."""
    root = pages_dir().resolve()
    candidate = (workspace() / value).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("accepted evidence local_path must be inside research_drift/pages") from exc
    return candidate


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Replace one file without exposing a partially-written document.

    The temporary file is created in the destination directory so ``os.replace``
    stays on one filesystem. ``mkstemp`` creates it securely and the cleanup
    path preserves the previous document if replacement fails.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path, value: str) -> None:
    _atomic_write_bytes(path, value.encode("utf-8"))


def atomic_write_json(path: Path, data: dict) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


@contextmanager
def _exclusive_lock(path: Path, timeout_seconds: float = 10.0):
    """Hold an advisory cross-process lock without stale lock-file recovery.

    Native file locks are released when a process exits, unlike an ``O_EXCL``
    lock file that can become stale after a crash. The small retry loop keeps
    concurrent host workers from losing a read-modify-write update.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise TimeoutError("timed out waiting for research state lock") from exc
                time.sleep(0.025)
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class JsonResearchRepository:
    """Persists the domain state without interpreting its graph semantics."""

    def load_data(self) -> dict:
        path = state_path()
        if not path.is_file():
            raise FileNotFoundError("research state missing; run engine init")
        return json.loads(path.read_text(encoding="utf-8"))

    def save_data(self, data: dict) -> None:
        atomic_write_json(state_path(), data)

    @contextmanager
    def locked(self):
        with _exclusive_lock(lock_path()):
            yield

    def append_event(self, record: dict) -> None:
        drift_dir().mkdir(parents=True, exist_ok=True)
        with log_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def write_snapshot(self, snapshot_id: str, data: dict, frozen_at: str) -> dict:
        path = workspace() / "research_snapshots" / snapshot_id
        path.mkdir(parents=True, exist_ok=False)
        frozen = dict(data)
        frozen["snapshot_id"] = snapshot_id
        frozen["frozen_at"] = frozen_at
        state_file = path / "research_state.json"
        atomic_write_json(state_file, frozen)
        manifest = {
            "snapshot_id": snapshot_id,
            "frozen_at": frozen_at,
            "state_sha256": hashlib.sha256(state_file.read_bytes()).hexdigest(),
            "evidence_count": len(data["evidence"]),
            "cognition_count": len(data["cognitions"]),
        }
        atomic_write_json(path / "manifest.json", manifest)
        return manifest


def default_repository() -> JsonResearchRepository:
    return JsonResearchRepository()
