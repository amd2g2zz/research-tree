from datetime import datetime, timezone
import hashlib

import pytest

from research_tree.content_store import ContentAddressedStore
from research_tree.evidence import (
    EvidenceAnchor,
    EvidenceArtifact,
    EvidenceResolver,
    EvidenceValidationError,
    provenance_group_for,
)


def _artifact(store, data=b"hello", *, media_type="text/plain"):
    content = store.ingest(data, media_type)
    return EvidenceArtifact(
        evidence_id="evidence-one",
        run_id="run-one",
        revision=1,
        media_type=media_type,
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
    )


def test_multimodal_selectors_validate_and_resolve(tmp_path):
    store = ContentAddressedStore(tmp_path)
    artifact = _artifact(store, b"page one\npage two")
    resolver = EvidenceResolver(store, {artifact.content_digest: artifact})
    for selector_type, selector_value in (
        ("line", {"start": 1, "end": 2}),
        ("symbol", {"name": "main"}),
        ("fragment", {"start": 0, "end": 4}),
        ("page_section", {"page": 1, "section": "Summary"}),
        ("image_region", {"x": 1, "y": 2, "width": 3, "height": 4}),
        ("input_revision", {"revision": 2}),
        ("experiment_field", {"field": "accuracy"}),
    ):
        anchor = EvidenceAnchor(
            artifact_digest=artifact.content_digest,
            artifact_revision=1,
            selector_type=selector_type,
            selector_value=selector_value,
            extractor_version="test-1",
            applicability="supports claim",
            confidence="high",
            limitations=(),
        )
        assert resolver.resolve(anchor).digest == artifact.content_digest


def test_changed_or_missing_content_is_rejected(tmp_path):
    store = ContentAddressedStore(tmp_path)
    artifact = _artifact(store)
    resolver = EvidenceResolver(store, {artifact.content_digest: artifact})
    (tmp_path / ".research-tree" / "cas" / "sha256" / artifact.content_digest[:2] / artifact.content_digest).write_bytes(b"tampered")
    with pytest.raises(EvidenceValidationError):
        resolver.resolve(EvidenceAnchor(
            artifact.content_digest, 1, "symbol", {"name": "main"}, "test-1", "x", "high", ()
        ))


def test_invalid_selector_and_digest_are_rejected():
    with pytest.raises(EvidenceValidationError):
        EvidenceAnchor("A" * 64, 1, "line", {"start": 0, "end": 1}, "v", "x", "low", ())


def test_repository_locator_cannot_escape_workspace(tmp_path):
    store = ContentAddressedStore(tmp_path)
    artifact = _artifact(store, b"repo")
    resolver = EvidenceResolver(store, {artifact.content_digest: artifact}, workspace=tmp_path)
    bad = EvidenceArtifact(**{**artifact.__dict__, "locator": {"path": "../outside.py"}})
    resolver = EvidenceResolver(store, {bad.content_digest: bad}, workspace=tmp_path)
    with pytest.raises(EvidenceValidationError):
        resolver.resolve(EvidenceAnchor(bad.content_digest, 1, "fragment", {"start": 0, "end": 1}, "v", "x", "medium", ()))


def test_repository_anchor_requires_the_inspected_revision(tmp_path):
    store = ContentAddressedStore(tmp_path)
    artifact = _artifact(store, b"repo")
    repository_artifact = EvidenceArtifact(**{
        **artifact.__dict__,
        "locator": {"path": "src/app.py"},
        "source_revision": "commit-a",
    })
    resolver = EvidenceResolver(
        store,
        {repository_artifact.content_digest: repository_artifact},
        workspace=tmp_path,
        repository_revisions={"src/app.py": "commit-b"},
    )
    with pytest.raises(EvidenceValidationError, match="inspected revision"):
        resolver.resolve(EvidenceAnchor(artifact.content_digest, 1, "symbol", {"name": "main"}, "test-1", "x", "high", ()))


def test_same_origin_derivatives_share_provenance_group():
    assert provenance_group_for("https://example.test/a?utm_source=x") == provenance_group_for("https://example.test/b")
