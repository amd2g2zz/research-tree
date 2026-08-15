from __future__ import annotations

from datetime import datetime, timezone

import pytest

from research_tree import ArtifactRef, ContentAddressedStore, RunLedger
from research_tree.evidence import (
    EvidenceAnchor,
    EvidenceArtifact,
    EvidenceRepository,
    EvidenceResolver,
    EvidenceValidationError,
)


def _environment(tmp_path, data: bytes = b"page one\npage two"):
    ledger = RunLedger(tmp_path / "ledger")
    ledger.initialize()
    ledger.create_run("run-one")
    store = ContentAddressedStore(tmp_path / "content")
    content = store.ingest(data, "text/plain")
    artifact = EvidenceArtifact(
        evidence_id="evidence-one",
        run_id="run-one",
        revision=1,
        media_type="text/plain",
        locator={"uri": "https://example.test/a"},
        content_digest=content.digest,
        size_bytes=content.byte_size,
        acquired_at=datetime.now(timezone.utc).isoformat(),
        acquisition_method="http",
        provenance_group="example-origin",
        applicability="primary source",
        confidence="high",
        limitations=(),
        status="active",
        extractor_version="test-1",
        evidence_class="source",
        metadata={
            "symbols": ["main"],
            "page_count": 1,
            "sections": ["Summary"],
            "width": 4,
            "height": 6,
            "input_revisions": [2],
            "fields": ["accuracy"],
        },
    )
    reference = EvidenceRepository(ledger, store).record(
        artifact,
        content,
        expected_run_revision=0,
    )
    resolver = EvidenceResolver.from_ledger(ledger, store, workspace=tmp_path)
    return ledger, store, artifact, content, reference, resolver


def _anchor(
    reference: ArtifactRef, digest: str, selector_type: str, selector_value: dict[str, object]
) -> EvidenceAnchor:
    return EvidenceAnchor(
        artifact_ref=reference,
        artifact_digest=digest,
        artifact_revision=reference.revision,
        selector_type=selector_type,
        selector_value=selector_value,
        extractor_version="test-1",
        applicability="supports claim",
        confidence="high",
        limitations=(),
    )


def test_multimodal_selectors_validate_and_resolve_from_ledger(tmp_path) -> None:
    _ledger, _store, _artifact, content, reference, resolver = _environment(tmp_path)

    for selector_type, selector_value in (
        ("line", {"start": 1, "end": 2}),
        ("symbol", {"name": "main"}),
        ("fragment", {"start": 0, "end": 4}),
        ("page_section", {"page": 1, "section": "Summary"}),
        ("image_region", {"x": 1, "y": 2, "width": 3, "height": 4}),
        ("input_revision", {"revision": 2}),
        ("experiment_field", {"field": "accuracy"}),
    ):
        assert (
            resolver.resolve(_anchor(reference, content.digest, selector_type, selector_value)).digest == content.digest
        )


def test_changed_or_missing_content_is_rejected_from_ledger(tmp_path) -> None:
    _ledger, store, _artifact, content, reference, resolver = _environment(tmp_path)
    content_path = tmp_path / "content" / ".research-tree" / "cas" / "sha256" / content.digest[:2] / content.digest
    content_path.write_bytes(b"tampered")

    with pytest.raises(EvidenceValidationError):
        resolver.resolve(_anchor(reference, content.digest, "symbol", {"name": "main"}))
    assert store.workspace == (tmp_path / "content").resolve()


def test_invalid_selector_and_digest_are_rejected() -> None:
    with pytest.raises(EvidenceValidationError):
        EvidenceAnchor(
            artifact_ref=ArtifactRef("run-one", "evidence-one", 1),
            artifact_digest="A" * 64,
            artifact_revision=1,
            selector_type="line",
            selector_value={"start": 0, "end": 1},
            extractor_version="test-1",
            applicability="supports claim",
            confidence="high",
            limitations=(),
        )


def test_repository_locator_cannot_escape_workspace(tmp_path) -> None:
    ledger, store, artifact, content, _reference, _resolver = _environment(tmp_path)
    escaped = EvidenceArtifact(
        **{**artifact.__dict__, "evidence_id": "evidence-escaped", "locator": {"path": "../outside.py"}}
    )
    reference = EvidenceRepository(ledger, store).record(
        escaped,
        content,
        expected_run_revision=ledger.get_revision("run-one"),
    )
    resolver = EvidenceResolver.from_ledger(ledger, store, workspace=tmp_path)

    with pytest.raises(EvidenceValidationError, match="escapes workspace"):
        resolver.resolve(_anchor(reference, content.digest, "fragment", {"start": 0, "end": 1}))


def test_repository_anchor_requires_the_inspected_revision(tmp_path) -> None:
    ledger, store, artifact, content, _reference, _resolver = _environment(tmp_path)
    repository_artifact = EvidenceArtifact(
        **{
            **artifact.__dict__,
            "evidence_id": "evidence-repository",
            "locator": {"path": "src/app.py"},
            "source_revision": "commit-a",
        }
    )
    reference = EvidenceRepository(ledger, store).record(
        repository_artifact,
        content,
        expected_run_revision=ledger.get_revision("run-one"),
    )
    resolver = EvidenceResolver.from_ledger(
        ledger,
        store,
        workspace=tmp_path,
        repository_revisions={"src/app.py": "commit-b"},
    )

    with pytest.raises(EvidenceValidationError, match="inspected revision"):
        resolver.resolve(_anchor(reference, content.digest, "symbol", {"name": "main"}))


def test_evidence_derives_provenance_from_upstream_or_content_identity(tmp_path) -> None:
    _ledger, _store, artifact, _content, _reference, _resolver = _environment(tmp_path)
    upstream = EvidenceArtifact(
        **{
            **artifact.__dict__,
            "metadata": {**artifact.metadata, "canonical_upstream_id": "official-release-2"},
        }
    )

    assert upstream.provenance_descriptor.cluster_id == "official-release-2"
    assert artifact.provenance_descriptor.cluster_id == artifact.content_digest
