from __future__ import annotations

from pathlib import Path

import pytest


def test_cas_is_content_addressed_and_detects_tampering(tmp_path: Path) -> None:
    from research_tree.cas import ContentAddressedStore, CASIntegrityError

    cas = ContentAddressedStore(tmp_path)
    stored = cas.put_bytes(b"evidence")
    assert stored["digest"] == cas.digest(b"evidence")
    assert cas.read(stored["digest"]) == b"evidence"
    path = cas.path_for(stored["digest"])
    path.write_bytes(b"tampered")
    with pytest.raises(CASIntegrityError):
        cas.read(stored["digest"])


def test_evidence_anchor_requires_exact_selector_and_oracle_binds_digest() -> None:
    from research_tree.evidence import EvidenceAnchor, EvidenceArtifact
    from research_tree.oracles import OracleRun, OracleSpec

    anchor = EvidenceAnchor.from_mapping({"kind": "repository", "ref": "src/main.py", "selector": {"line": 12}})
    artifact = EvidenceArtifact.create(
        evidence_id="evidence-main", run_id="run-evidence", artifact_digest="a" * 64,
        media_type="text/plain", provenance_group="repo-main", acquisition={"revision": "abc"},
        anchors=[anchor.to_dict()],
    )
    oracle = OracleSpec.create("oracle-build", "repository", "python -m compileall", expected="pass")
    result = OracleRun.create(
        "oracle-run", oracle, attempt_id="attempt-1", input_refs=[artifact.ref()],
        verdict="pass", environment_digest="b" * 64, result={"status": "pass"},
    )
    assert result.input_refs == (artifact.ref(),)
    assert result.verdict == "pass"


def test_slot_closure_requires_independent_evidence_and_passed_oracle() -> None:
    from research_tree.closure import SlotClosureAssessment

    assessment = SlotClosureAssessment.assess(
        slot_id="slot-a",
        evidence=[
            {"evidence_id": "e1", "provenance_group": "source-a", "classes": ["repository"]},
            {"evidence_id": "e2", "provenance_group": "source-b", "classes": ["experiment"]},
        ],
        oracle_runs=[{"oracle_run_id": "o1", "verdict": "pass"}],
        contradictions=[],
        required_classes=["repository", "experiment"],
    )
    assert assessment.status == "closed"
    assert assessment.token_digest


def test_resolvable_anchor_binds_digest_revision_selector_and_cas(tmp_path: Path) -> None:
    from research_tree.cas import ContentAddressedStore
    from research_tree.evidence import EvidenceError, EvidenceResolver, ResolvableEvidenceAnchor

    cas = ContentAddressedStore(tmp_path)
    stored = cas.put_bytes(b"line one\nline two\n", media_type="text/plain")
    anchor = ResolvableEvidenceAnchor.from_mapping(
        {
            "artifact_digest": stored["digest"],
            "artifact_revision": 1,
            "selector_type": "line",
            "selector_value": {"repository_revision": "commit-a", "path": "src/main.py", "line": 2},
            "extractor_version": "source-reader-1",
            "applicability": "The inspected function body.",
            "confidence": "high",
            "limitations": ["Single revision inspected."],
        }
    )
    resolved = EvidenceResolver(cas=cas, workspace=tmp_path).resolve(
        anchor,
        {
            "evidence_id": "evidence-main",
            "revision": 1,
            "content_digest": stored["digest"],
            "status": "active",
            "source_revision": "commit-a",
            "provenance_group": "repo-main",
            "locator": {"path": "src/main.py"},
        },
    )
    assert resolved["resolved"] is True
    with pytest.raises(EvidenceError, match="digest"):
        EvidenceResolver(workspace=tmp_path).resolve(
            anchor,
            {
                "revision": 1,
                "content_digest": "0" * 64,
                "status": "active",
                "source_revision": "commit-a",
                "locator": {"path": "src/main.py"},
            },
        )
    fragment = ResolvableEvidenceAnchor.from_mapping(
        {
            **anchor.to_dict(),
            "selector_type": "fragment",
            "selector_value": {"fragment": "line two"},
        }
    )
    with pytest.raises(EvidenceError, match="escapes workspace"):
        EvidenceResolver(workspace=tmp_path).resolve(
            fragment,
            {
                "revision": 1,
                "content_digest": stored["digest"],
                "status": "active",
                "locator": {"path": "../outside.txt"},
            },
        )
    with pytest.raises(EvidenceError, match="selector number"):
        ResolvableEvidenceAnchor.from_mapping(
            {
                **anchor.to_dict(),
                "selector_value": {"repository_revision": "commit-a", "path": "src/main.py", "line": 0},
            }
        )


def test_finding_anchor_accepts_canonical_resolvable_evidence_shape() -> None:
    from research_tree.ledger import _normalize_anchor

    normalized = _normalize_anchor(
        {
            "artifact_digest": "a" * 64,
            "artifact_revision": 1,
            "selector_type": "symbol",
            "selector_value": {"repository_revision": "commit-a", "path": "src/main.py", "symbol": "run"},
            "extractor_version": "source-reader-1",
            "applicability": "The selected symbol.",
            "confidence": "medium",
            "limitations": ["No dynamic execution."],
        },
        "observation",
        {"source", "repository", "input", "experiment", "evidence"},
        ValueError,
    )
    assert normalized["kind"] == "evidence"
    assert normalized["evidence"]["artifact_digest"] == "a" * 64


def test_strict_evidence_requires_one_matching_artifact() -> None:
    from research_tree.evidence import EvidenceResolver
    from research_tree.ledger import InvalidFindingPackError, _resolve_strict_evidence

    observation = {
        "anchor": {
            "kind": "evidence",
            "ref": "a" * 64,
            "evidence": {
                "artifact_digest": "a" * 64,
                "artifact_revision": 1,
                "selector_type": "fragment",
                "selector_value": {"fragment": "claim"},
                "extractor_version": "reader-1",
                "applicability": "The extracted claim.",
                "confidence": "high",
                "limitations": [],
            },
        }
    }
    with pytest.raises(InvalidFindingPackError, match="exactly one"):
        _resolve_strict_evidence([observation], [], EvidenceResolver())

    with pytest.raises(InvalidFindingPackError, match="resolvable Evidence Artifact"):
        _resolve_strict_evidence(
            [{"anchor": {"kind": "source", "ref": "https://example.invalid"}}],
            [],
            EvidenceResolver(),
        )

    _resolve_strict_evidence(
        [observation],
        [{"content_digest": "a" * 64, "revision": 1, "status": "active"}],
        EvidenceResolver(),
    )


def test_canonical_artifact_mapping_round_trips_to_resolver_contract() -> None:
    from research_tree.evidence import EvidenceArtifact, provenance_group_for

    provenance_origin = "repository:https://example.invalid/project"
    provenance_group = provenance_group_for(provenance_origin, "repository_checkout")

    artifact = EvidenceArtifact.from_mapping(
        {
            "evidence_id": "evidence-main",
            "run_id": "run-evidence",
            "revision": 2,
            "media_type": "text/plain",
            "locator": {"path": "src/main.py"},
            "content_digest": "b" * 64,
            "size_bytes": 12,
            "acquired_at": "2026-08-05T00:00:00Z",
            "acquisition_method": "repository_checkout",
            "provenance_origin": provenance_origin,
            "provenance_group": provenance_group,
            "applicability": "The selected source revision.",
            "confidence": "high",
            "limitations": ["Static inspection only."],
            "status": "active",
            "extractor_version": "reader-1",
            "source_revision": "commit-a",
        }
    )
    contract = artifact.to_contract_dict()
    assert contract["content_digest"] == "b" * 64
    assert contract["revision"] == 2
    assert contract["status"] == "active"
    assert contract["provenance_group"] == provenance_group


def test_repository_anchor_must_match_the_inspected_source_revision(tmp_path: Path) -> None:
    from research_tree.evidence import EvidenceError, EvidenceResolver, ResolvableEvidenceAnchor

    anchor = ResolvableEvidenceAnchor.from_mapping(
        {
            "artifact_digest": "c" * 64,
            "artifact_revision": 1,
            "selector_type": "symbol",
            "selector_value": {
                "repository_revision": "commit-a",
                "path": "src/main.py",
                "symbol": "run",
            },
            "extractor_version": "source-reader-1",
            "applicability": "The inspected symbol.",
            "confidence": "high",
            "limitations": [],
        }
    )
    with pytest.raises(EvidenceError, match="repository revision"):
        EvidenceResolver(workspace=tmp_path).resolve(
            anchor,
            {
                "content_digest": "c" * 64,
                "revision": 1,
                "status": "active",
                "source_revision": "commit-b",
                "locator": {"path": "src/main.py"},
            },
        )


@pytest.mark.parametrize(
    ("selector_type", "selector_value"),
    [
        ("page_section", {"page": 2, "section": "Architecture"}),
        ("image_region", {"x": 1, "y": 2, "width": 10, "height": 12}),
        ("input_revision", {"input_id": "input-brief", "revision": 3}),
        ("experiment_field", {"run_id": "experiment-1", "field": "result.status"}),
    ],
)
def test_multimodal_selectors_are_exact_and_bounded(selector_type, selector_value) -> None:
    from research_tree.evidence import ResolvableEvidenceAnchor

    anchor = ResolvableEvidenceAnchor.from_mapping(
        {
            "artifact_digest": "d" * 64,
            "artifact_revision": 1,
            "selector_type": selector_type,
            "selector_value": selector_value,
            "extractor_version": "extractor-1",
            "applicability": "Exact selected region.",
            "confidence": "medium",
            "limitations": [],
        }
    )
    assert anchor.selector_value == selector_value


def test_evidence_parent_lineage_requires_the_exact_persisted_artifact_revision() -> None:
    from research_tree import ArtifactRevision
    from research_tree.ledger import InvalidFindingPackError, _resolve_evidence_parent_refs

    mapping = {
        "evidence_id": "evidence-main",
        "run_id": "round-evidence",
        "revision": 1,
        "content_digest": "e" * 64,
    }
    stored = ArtifactRevision.create(
        artifact_id="evidence-main",
        round_id="round-evidence",
        revision=1,
        kind="evidence-artifact",
        payload=mapping,
        parent_refs=(),
    )
    refs = _resolve_evidence_parent_refs(
        [stored], [mapping], round_id="round-evidence", allow_legacy=False
    )
    assert [ref.to_dict() for ref in refs] == [
        {"round_id": "round-evidence", "artifact_id": "evidence-main", "revision": 1}
    ]
    with pytest.raises(InvalidFindingPackError, match="exact persisted Evidence Artifact"):
        _resolve_evidence_parent_refs(
            [stored], [{**mapping, "content_digest": "f" * 64}],
            round_id="round-evidence", allow_legacy=False,
        )


def test_derivative_sources_share_one_computed_provenance_group() -> None:
    from research_tree.evidence import EvidenceArtifact, EvidenceError, provenance_group_for

    origin = "vendor-announcement:release-42"
    group = provenance_group_for(origin, "web_snapshot")

    def artifact(locator):
        return {
            "evidence_id": "evidence-derivative",
            "run_id": "run-evidence",
            "revision": 1,
            "media_type": "text/html",
            "locator": {"url": locator},
            "content_digest": "1" * 64,
            "size_bytes": 10,
            "acquired_at": "2026-08-05T00:00:00Z",
            "acquisition_method": "web_snapshot",
            "provenance_origin": origin,
            "provenance_group": group,
            "applicability": "The vendor release claim.",
            "confidence": "medium",
            "limitations": ["Derivative publication."],
            "status": "active",
            "extractor_version": "reader-1",
        }

    first = EvidenceArtifact.from_mapping(artifact("https://mirror-a.invalid/post"))
    second = EvidenceArtifact.from_mapping(artifact("https://mirror-b.invalid/post"))
    assert first.provenance_group == second.provenance_group == group
    with pytest.raises(EvidenceError, match="provenance_group"):
        EvidenceArtifact.from_mapping({**artifact("https://mirror-c.invalid/post"), "provenance_group": "fake-independent"})
