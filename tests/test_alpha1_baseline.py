from __future__ import annotations

from pathlib import Path


MANIFEST = Path(__file__).parents[1] / "evaluation" / "cases" / "alpha1-adversarial-v1.json"


def test_alpha1_manifest_is_pinned_and_worker_visible_material_is_public_only() -> None:
    from evaluation.harness.alpha1_adversarial import load_manifest

    manifest = load_manifest(MANIFEST)
    assert manifest["baseline"]["tag"] == "0.0.1-a1"
    assert len(manifest["baseline"]["commit"]) == 40
    assert len(manifest["cases"]) == 9
    assert all("oracle_id" in case for case in manifest["cases"])
    assert all("unsafe_outcome" not in case for case in manifest["cases"])


def test_alpha1_baseline_classifies_reproduction_and_does_not_claim_fix() -> None:
    from evaluation.harness.alpha1_adversarial import evaluate_case, load_manifest

    manifest = load_manifest(MANIFEST)
    reproduced = evaluate_case(manifest["cases"][0], observed_unsafe=True)
    assert reproduced["status"] == "vulnerability_reproduced"
    inconclusive = evaluate_case(manifest["cases"][0], observed_unsafe=False)
    assert inconclusive["status"] == "inconclusive"
    confirmed = evaluate_case(
        manifest["cases"][0], observed_unsafe=False, fix_evidence=["candidate-run-1"]
    )
    assert confirmed["status"] == "fix_confirmed"
