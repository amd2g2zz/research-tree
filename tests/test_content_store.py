from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from research_tree import (
    ArtifactRef,
    ContentAddressedStore,
    ContentIntegrityError,
    ContentObject,
    LedgerIntegrityError,
    RunLedger,
)


def test_ingest_is_deduplicated_and_reads_verified_bytes(tmp_path: Path) -> None:
    store = ContentAddressedStore(tmp_path)
    first = store.ingest(b"capture", "text/plain")
    second = store.ingest(b"capture", "text/plain")

    assert first.digest == hashlib.sha256(b"capture").hexdigest()
    assert first.locator == second.locator
    assert store.read(first) == b"capture"
    assert len(tuple((tmp_path / ".research-tree" / "cas" / "sha256").glob("*/*"))) == 1


def test_ledger_registers_metadata_and_binds_an_artifact(tmp_path: Path) -> None:
    store = ContentAddressedStore(tmp_path)
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-1")
    artifact = ledger.append_artifact("run-1", "capture", "source-capture", {}, expected_revision=0)
    content = store.ingest(b"bytes", "application/octet-stream")

    registered = ledger.register_content(content)
    ledger.bind_content(ArtifactRef("run-1", artifact.id, artifact.revision), registered)

    assert ledger.get_content(content.digest).locator == content.locator
    assert ledger.resolve_content(ArtifactRef("run-1", artifact.id, artifact.revision), store) == b"bytes"
    assert ledger.register_content(store.ingest(b"bytes", "application/octet-stream")).digest == content.digest


def test_metadata_conflict_and_binding_conflict_are_rejected(tmp_path: Path) -> None:
    store = ContentAddressedStore(tmp_path)
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-1")
    artifact = ledger.append_artifact("run-1", "capture", "source-capture", {}, expected_revision=0)
    content = store.ingest(b"bytes", "text/plain")
    ledger.register_content(content)

    with pytest.raises(LedgerIntegrityError):
        ledger.register_content(
            ContentObject(
                content.digest, "image/png", content.byte_size, content.locator, created_at=content.created_at
            )
        )

    other = store.ingest(b"other", "text/plain")
    ledger.register_content(other)
    ledger.bind_content(ArtifactRef("run-1", artifact.id, artifact.revision), content)
    with pytest.raises(LedgerIntegrityError):
        ledger.bind_content(ArtifactRef("run-1", artifact.id, artifact.revision), other)


def test_tamper_is_detected_on_read(tmp_path: Path) -> None:
    store = ContentAddressedStore(tmp_path)
    content = store.ingest(b"capture", "text/plain")
    path = tmp_path / content.locator
    path.write_bytes(b"tampered")

    with pytest.raises(ContentIntegrityError):
        store.read(content)


def test_orphan_staging_and_published_objects_are_quarantined(tmp_path: Path) -> None:
    store = ContentAddressedStore(tmp_path)
    content = store.ingest(b"keep", "text/plain")
    staging = store.staging_root / "orphan.part"
    staging.parent.mkdir(parents=True, exist_ok=True)
    staging.write_bytes(b"orphan")

    moved = store.quarantine_orphans({content.digest})

    assert hashlib.sha256(b"orphan").hexdigest() in moved
    assert not staging.exists()


def test_digest_input_cannot_escape_workspace(tmp_path: Path) -> None:
    store = ContentAddressedStore(tmp_path)
    with pytest.raises(ContentIntegrityError):
        store.read("../outside")
