from __future__ import annotations

import json
from pathlib import Path

import research_tree
import pytest

from research_tree import ContentAddressedStore, InvalidFindingPackError
from research_tree.evidence import (
    EvidenceAnchor,
    EvidenceArtifact,
    EvidenceResolver,
    EvidenceValidationError,
)
from legacy_runstore_fixture import compile_finding, context, finding_payload


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_SCHEMA = (
    ROOT / "openspec" / "changes" / "unify-research-runtime-alpha2" / "schemas" / "evidence-artifact-v1.json"
)


def _artifact_fields(**overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "evidence_id": "evidence-one",
        "run_id": "run-one",
        "revision": 1,
        "media_type": "text/plain",
        "locator": {"uri": "https://example.test/source"},
        "content_digest": "0" * 64,
        "size_bytes": 0,
        "acquired_at": "2026-01-01T00:00:00+00:00",
        "acquisition_method": "test-capture",
        "provenance_group": "https://example.test",
        "applicability": "fixture evidence",
        "confidence": "high",
        "limitations": (),
        "status": "active",
        "extractor_version": "fixture-reader-v1",
        "evidence_class": "source",
        "metadata": {},
    }
    fields.update(overrides)
    return fields


def _legacy_anchor_payload() -> dict[str, object]:
    return {
        "artifact_digest": "0" * 64,
        "artifact_revision": 1,
        "selector_type": "symbol",
        "selector_value": {"name": "main"},
        "extractor_version": "fixture-reader-v1",
        "applicability": "legacy import",
        "confidence": "low",
        "limitations": ["unresolved provenance"],
        "legacy_unverified": True,
    }


def test_legacy_anchor_payload_has_no_compatibility_reader() -> None:
    payload = _legacy_anchor_payload()

    with pytest.raises(EvidenceValidationError, match="unexpected fields"):
        EvidenceAnchor.from_dict(payload)
    with pytest.raises(TypeError, match="allow_legacy"):
        EvidenceAnchor.from_dict(payload, allow_legacy=True)  # type: ignore[call-arg]


def test_anchor_requires_an_exact_artifact_reference() -> None:
    with pytest.raises(TypeError, match="artifact_ref"):
        EvidenceAnchor(
            artifact_digest="0" * 64,
            artifact_revision=1,
            selector_type="symbol",
            selector_value={"name": "main"},
            extractor_version="fixture-reader-v1",
            applicability="fixture evidence",
            confidence="high",
            limitations=(),
        )


def test_artifact_rejects_legacy_status_and_implicit_evidence_class() -> None:
    with pytest.raises(EvidenceValidationError, match="invalid status"):
        EvidenceArtifact(**_artifact_fields(status="legacy_unverified"))

    fields = _artifact_fields()
    fields.pop("evidence_class")
    with pytest.raises(TypeError, match="evidence_class"):
        EvidenceArtifact(**fields)


def test_resolver_has_no_artifact_map_constructor(tmp_path) -> None:
    store = ContentAddressedStore(tmp_path)

    with pytest.raises(TypeError, match="positional"):
        EvidenceResolver(store, {})


def test_retained_compiler_rejects_legacy_typed_evidence_anchor(tmp_path) -> None:
    modules, store, round_record, _model, _brief, _target, _finding, _decision = context(
        tmp_path,
        include_decision=False,
    )
    work = next(artifact for artifact in store.load_round(round_record.id).artifacts if artifact.id == "work-isolation")
    payload = finding_payload(
        "isolated-worker",
        "supports",
        "Legacy typed evidence cannot establish a finding.",
    )
    payload["observations"][0]["anchor"] = _legacy_anchor_payload()

    with pytest.raises(InvalidFindingPackError, match="unexpected fields"):
        compile_finding(modules, store, round_record, work, "finding-legacy-anchor", **payload)


def test_legacy_provenance_helper_is_not_public() -> None:
    assert not hasattr(research_tree, "provenance_group_for")


def test_active_evidence_schema_and_public_surface_admit_no_legacy_form() -> None:
    schema = json.loads(EVIDENCE_SCHEMA.read_text(encoding="utf-8"))

    assert "legacy_unverified" not in schema["properties"]["status"]["enum"]
    assert "allow_legacy" not in (ROOT / "src" / "research_tree" / "evidence.py").read_text(encoding="utf-8")
    assert "provenance_group_for" not in (ROOT / "src" / "research_tree" / "__init__.py").read_text(encoding="utf-8")
