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
