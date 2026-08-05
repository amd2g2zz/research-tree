from __future__ import annotations

from pathlib import Path

from scripts.generate_delivery_matrix import generate


def test_delivery_matrix_links_correction_requirement_to_issue_evidence() -> None:
    change = (
        Path(__file__).parents[1]
        / "openspec"
        / "changes"
        / "unify-research-runtime-alpha2"
    )
    matrix = generate(change)
    rows = {row["requirement_id"]: row for row in matrix["rows"]}
    correction = rows[
        "mutual-alignment/corrections-transactionally-invalidate-dependent-state"
    ]
    assert correction["github_issue"] == "#73"
    assert correction["status"] == "in_progress"
    assert correction["integration_tests"] == [
        "tests/test_alpha2_correction_integration.py"
    ]
    assert correction["evidence_artifact"] == (
        "evaluation/harness/fixtures/correction_invalidation_trace.json"
    )
