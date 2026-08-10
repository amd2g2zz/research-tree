from __future__ import annotations

from pathlib import Path

import pytest

from research_tree import (
    ArtifactRef,
    ContentAddressedStore,
    ContentIntegrityError,
    ContentObject,
    LedgerConflictError,
    LedgerIntegrityError,
    RunLedger,
)


def _ledger_and_store(tmp_path: Path) -> tuple[RunLedger, ContentAddressedStore]:
    ledger = RunLedger(tmp_path)
    ledger.initialize()
    ledger.create_run("run-binding")
    return ledger, ContentAddressedStore(tmp_path)


def _append(
    ledger: RunLedger,
    store: ContentAddressedStore,
    content: ContentObject,
    *,
    artifact_id: str = "capture-one",
    payload: dict[str, object] | None = None,
    expected_revision: int = 0,
    expected_artifact_revision: int | None = 1,
):
    return ledger.append_artifact_with_content(
        "run-binding",
        artifact_id,
        "source-capture",
        payload or {"provenance": "capture-a"},
        content,
        store,
        expected_revision=expected_revision,
        expected_artifact_revision=expected_artifact_revision,
    )


def test_atomic_append_publishes_artifact_binding_and_event_after_restart(tmp_path: Path) -> None:
    ledger, store = _ledger_and_store(tmp_path)
    content = store.ingest(b"captured bytes", "text/plain")

    artifact = _append(ledger, store, content)
    reference = ArtifactRef("run-binding", artifact.id, artifact.revision)

    assert ledger.get_revision("run-binding") == 1
    assert ledger.get_artifact(reference).payload["provenance"] == "capture-a"
    assert ledger.get_bound_content(reference).digest == content.digest
    assert ledger.resolve_content(reference, store) == b"captured bytes"
    snapshot = ledger.load_run("run-binding")
    assert snapshot.lineage_events[-1].kind == "artifact-content-appended"
    assert snapshot.lineage_events[-1].artifact_ref == reference

    reopened = RunLedger(tmp_path)
    assert reopened.get_artifact(reference).content_hash == artifact.content_hash
    assert reopened.get_bound_content(reference).digest == content.digest
    assert reopened.resolve_content(reference, ContentAddressedStore(tmp_path)) == b"captured bytes"


def test_equal_bytes_keep_distinct_artifact_identity_and_provenance(tmp_path: Path) -> None:
    ledger, store = _ledger_and_store(tmp_path)
    content = store.ingest(b"same capture", "text/plain")

    first = _append(
        ledger,
        store,
        content,
        artifact_id="capture-one",
        payload={"provenance": "source-a"},
    )
    second = _append(
        ledger,
        store,
        content,
        artifact_id="capture-two",
        payload={"provenance": "source-b"},
        expected_revision=1,
    )

    first_ref = ArtifactRef("run-binding", first.id, first.revision)
    second_ref = ArtifactRef("run-binding", second.id, second.revision)
    reopened = RunLedger(tmp_path)
    assert first_ref != second_ref
    assert reopened.get_artifact(first_ref).payload["provenance"] == "source-a"
    assert reopened.get_artifact(second_ref).payload["provenance"] == "source-b"
    assert reopened.get_bound_content(first_ref).digest == content.digest
    assert reopened.get_bound_content(second_ref).digest == content.digest


def test_stale_run_or_artifact_revision_leaves_no_partial_publication(tmp_path: Path) -> None:
    ledger, store = _ledger_and_store(tmp_path)
    content = store.ingest(b"captured bytes", "text/plain")
    first = _append(ledger, store, content)

    with pytest.raises(LedgerConflictError, match="stale run revision"):
        _append(
            ledger,
            store,
            content,
            artifact_id="capture-stale-run",
            expected_revision=0,
        )
    with pytest.raises(LedgerConflictError, match="stale artifact revision"):
        _append(
            ledger,
            store,
            content,
            artifact_id=first.id,
            expected_revision=1,
            expected_artifact_revision=1,
        )

    snapshot = ledger.load_run("run-binding")
    assert ledger.get_revision("run-binding") == 1
    assert [artifact.id for artifact in snapshot.artifacts] == ["capture-one"]
    assert ledger.get_bound_content(ArtifactRef("run-binding", first.id, first.revision)).digest == content.digest


def test_tampered_or_unavailable_content_cannot_publish_authoritative_rows(tmp_path: Path) -> None:
    ledger, store = _ledger_and_store(tmp_path)
    content = store.ingest(b"captured bytes", "text/plain")
    (tmp_path / content.locator).write_bytes(b"tampered")

    with pytest.raises(ContentIntegrityError):
        _append(ledger, store, content)

    unavailable = ContentObject(
        content.digest,
        content.media_type,
        content.byte_size,
        content.locator,
        availability="unavailable",
        created_at=content.created_at,
    )
    with pytest.raises(LedgerIntegrityError, match="available"):
        _append(ledger, store, unavailable)

    assert ledger.get_revision("run-binding") == 0
    assert ledger.load_run("run-binding").artifacts == ()
    with pytest.raises(LedgerIntegrityError, match="content does not exist"):
        ledger.get_content(content.digest)


def test_precommit_failure_rolls_back_artifact_content_binding_and_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger, store = _ledger_and_store(tmp_path)
    content = store.ingest(b"captured bytes", "text/plain")

    def fail_before_commit() -> None:
        raise RuntimeError("injected commit failure")

    monkeypatch.setattr(ledger, "_before_commit", fail_before_commit)
    with pytest.raises(RuntimeError, match="injected commit failure"):
        _append(ledger, store, content)

    reopened = RunLedger(tmp_path)
    assert reopened.get_revision("run-binding") == 0
    assert reopened.load_run("run-binding").artifacts == ()
    assert [event.kind for event in reopened.load_run("run-binding").lineage_events] == ["run-created"]
    with pytest.raises(LedgerIntegrityError, match="content does not exist"):
        reopened.get_content(content.digest)
