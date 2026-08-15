from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from research_tree import (
    ArtifactRef,
    ContentAddressedStore,
    EvidenceAnchor,
    EvidenceArtifact,
    EvidenceRepository,
    EvidenceValidationError,
    RunLedger,
)


def _artifact(*, run_id: str, evidence_id: str, digest: str, size: int, locator: str) -> EvidenceArtifact:
    return EvidenceArtifact(
        evidence_id=evidence_id,
        run_id=run_id,
        revision=1,
        media_type="text/plain",
        locator={"uri": locator},
        content_digest=digest,
        size_bytes=size,
        acquired_at=datetime.now(timezone.utc).isoformat(),
        acquisition_method="test-capture",
        provenance_group=locator,
        applicability="supports the bounded claim",
        confidence="high",
        limitations=(),
        status="active",
        extractor_version="reader-1",
        evidence_class="source",
        metadata={"capture_scope": "fixture"},
    )


def _ledger_and_store(tmp_path: Path) -> tuple[RunLedger, ContentAddressedStore]:
    ledger = RunLedger(tmp_path)
    ledger.initialize()
    ledger.create_run("run-evidence")
    return ledger, ContentAddressedStore(tmp_path)


def test_canonical_evidence_round_trips_with_exact_artifact_ref_after_restart(tmp_path: Path) -> None:
    ledger, store = _ledger_and_store(tmp_path)
    content = store.ingest(b"primary source", "text/plain")
    artifact = _artifact(
        run_id="run-evidence",
        evidence_id="source-one",
        digest=content.digest,
        size=content.byte_size,
        locator="https://example.test/one",
    )

    reference = EvidenceRepository(ledger, store).record(
        artifact,
        content,
        expected_run_revision=0,
    )
    anchor = EvidenceAnchor(
        artifact_digest=content.digest,
        artifact_revision=1,
        selector_type="line",
        selector_value={"start": 1, "end": 1},
        extractor_version="reader-1",
        applicability="supports the bounded claim",
        confidence="high",
        limitations=(),
        artifact_ref=reference,
    )

    persisted = RunLedger(tmp_path).get_artifact(reference)
    restored = EvidenceArtifact.from_revision(reference, persisted)

    assert reference == ArtifactRef("run-evidence", "source-one", 1)
    assert restored.to_dict() == artifact.to_dict()
    assert EvidenceAnchor.from_dict(anchor.to_dict()) == anchor
    assert anchor.is_strict is True


def test_same_content_keeps_distinct_canonical_provenance(tmp_path: Path) -> None:
    ledger, store = _ledger_and_store(tmp_path)
    content = store.ingest(b"identical bytes", "text/plain")
    repository = EvidenceRepository(ledger, store)

    first = repository.record(
        _artifact(
            run_id="run-evidence",
            evidence_id="source-one",
            digest=content.digest,
            size=content.byte_size,
            locator="https://a.example.test/source",
        ),
        content,
        expected_run_revision=0,
    )
    second = repository.record(
        _artifact(
            run_id="run-evidence",
            evidence_id="source-two",
            digest=content.digest,
            size=content.byte_size,
            locator="https://b.example.test/source",
        ),
        content,
        expected_run_revision=1,
    )

    reopened = RunLedger(tmp_path)
    assert first != second
    assert EvidenceArtifact.from_revision(first, reopened.get_artifact(first)).locator["uri"] == "https://a.example.test/source"
    assert EvidenceArtifact.from_revision(second, reopened.get_artifact(second)).locator["uri"] == "https://b.example.test/source"


def test_repository_rejects_implicit_class_or_cas_metadata_mismatch(tmp_path: Path) -> None:
    ledger, store = _ledger_and_store(tmp_path)
    content = store.ingest(b"primary source", "text/plain")
    artifact = _artifact(
        run_id="run-evidence",
        evidence_id="source-one",
        digest=content.digest,
        size=content.byte_size,
        locator="https://example.test/one",
    )

    with pytest.raises(EvidenceValidationError, match="evidence_class"):
        EvidenceRepository(ledger, store).record(
            EvidenceArtifact(**{**artifact.__dict__, "evidence_class": "legacy_unspecified"}),
            content,
            expected_run_revision=0,
        )
    with pytest.raises(EvidenceValidationError, match="does not match CAS"):
        EvidenceRepository(ledger, store).record(
            EvidenceArtifact(**{**artifact.__dict__, "size_bytes": content.byte_size + 1}),
            content,
            expected_run_revision=0,
        )
    assert ledger.get_revision("run-evidence") == 0


def test_canonical_artifact_rejects_non_textual_locator_or_optional_metadata() -> None:
    base = {
        "evidence_id": "source-one",
        "run_id": "run-evidence",
        "revision": 1,
        "media_type": "text/plain",
        "locator": {"uri": "https://example.test/one"},
        "content_digest": "0" * 64,
        "size_bytes": 0,
        "acquired_at": "2026-01-01T00:00:00+00:00",
        "acquisition_method": "test-capture",
        "provenance_group": "example.test",
        "applicability": "fixture",
        "confidence": "high",
        "limitations": (),
        "status": "active",
        "extractor_version": "reader-1",
        "evidence_class": "source",
    }

    with pytest.raises(EvidenceValidationError, match="locator\\[uri\\]"):
        EvidenceArtifact(**{**base, "locator": {"uri": 1}})
    with pytest.raises(EvidenceValidationError, match="source_revision"):
        EvidenceArtifact(**{**base, "source_revision": 1})
    with pytest.raises(EvidenceValidationError, match="license_note"):
        EvidenceArtifact(**{**base, "license_note": 1})
