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
            "selector_value": {"path": "src/main.py", "line": 2},
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
            "provenance_group": "repo-main",
            "locator": {"path": "src/main.py"},
        },
    )
    assert resolved["resolved"] is True
    with pytest.raises(EvidenceError, match="selector number"):
        ResolvableEvidenceAnchor.from_mapping(
            {
                **anchor.to_dict(),
                "selector_value": {"path": "src/main.py", "line": 0},
            }
        )


def test_finding_anchor_accepts_canonical_resolvable_evidence_shape() -> None:
    from research_tree.ledger import _normalize_anchor

    normalized = _normalize_anchor(
        {
            "artifact_digest": "a" * 64,
            "artifact_revision": 1,
            "selector_type": "symbol",
            "selector_value": {"path": "src/main.py", "symbol": "run"},
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

    _resolve_strict_evidence(
        [observation],
        [{"content_digest": "a" * 64, "revision": 1, "status": "active"}],
        EvidenceResolver(),
    )


def test_canonical_artifact_mapping_round_trips_to_resolver_contract() -> None:
    from research_tree.evidence import EvidenceArtifact

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
            "provenance_group": "repo-main",
            "applicability": "The selected source revision.",
            "confidence": "high",
            "limitations": ["Static inspection only."],
            "status": "active",
            "extractor_version": "reader-1",
        }
    )
    contract = artifact.to_contract_dict()
    assert contract["content_digest"] == "b" * 64
    assert contract["revision"] == 2
    assert contract["status"] == "active"
