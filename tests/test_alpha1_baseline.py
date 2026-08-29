from __future__ import annotations

import json
from pathlib import Path

import pytest

MANIFEST = Path(__file__).parents[1] / "evaluation" / "cases" / "alpha1-adversarial-v1.json"
ALPHA1_COMMIT = "8ab91ea4eb55c98441b5ee6001b80922a56ecdd1"


def api():
    from research_tree.alpha1_adversarial import (
        BaselineFixtureError,
        evaluate_case,
        evaluate_manifest,
        load_manifest,
        validate_manifest,
    )

    return {
        "BaselineFixtureError": BaselineFixtureError,
        "evaluate_case": evaluate_case,
        "evaluate_manifest": evaluate_manifest,
        "load_manifest": load_manifest,
        "validate_manifest": validate_manifest,
    }


def test_alpha1_manifest_is_pinned_and_only_exposes_public_fixture_material() -> None:
    manifest = api()["load_manifest"](MANIFEST)

    assert manifest["schema_version"] == 1
    assert manifest["id"] == "alpha1-adversarial-v1"
    assert manifest["baseline"]["tag"] == "0.0.1-a1"
    assert manifest["baseline"]["commit"] == ALPHA1_COMMIT
    assert set(manifest["baseline"]["host_packages"]) == {"codex", "claude-code", "hermes"}
    assert len(manifest["cases"]) == 9
    assert {case["host"] for case in manifest["cases"]} == {"codex", "claude-code", "hermes"}
    assert all(case["execution_disposition"] in {"executable", "unavailable"} for case in manifest["cases"])
    assert all(case["execution_disposition"] == "unavailable" for case in manifest["cases"])
    assert all(case["unavailability_reason"] for case in manifest["cases"])
    assert all("oracle_id" in case for case in manifest["cases"])
    assert all("unsafe_outcome" not in case for case in manifest["cases"])
    assert all("fix_confirmed" not in case for case in manifest["cases"])


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda manifest: manifest["baseline"].__setitem__("commit", "abc"), "full commit"),
        (lambda manifest: manifest["cases"][1].__setitem__("id", manifest["cases"][0]["id"]), "unique"),
        (lambda manifest: manifest["cases"][0].__setitem__("host", "unknown"), "host"),
        (lambda manifest: manifest["cases"][0].pop("oracle_id"), "oracle"),
        (
            lambda manifest: manifest["cases"][0].update(
                {"execution_disposition": "executable", "unavailability_reason": None}
            ),
            "command",
        ),
        (lambda manifest: manifest["cases"][0].__setitem__("unsafe_outcome", "leaked"), "public"),
    ],
)
def test_alpha1_manifest_rejects_invalid_or_answer_leaking_cases(mutation, message: str) -> None:
    modules = api()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    mutation(manifest)

    with pytest.raises(modules["BaselineFixtureError"], match=message):
        modules["validate_manifest"](manifest)


def test_alpha1_baseline_classifies_non_reproduction_conservatively() -> None:
    modules = api()
    case = modules["load_manifest"](MANIFEST)["cases"][0]

    reproduced = modules["evaluate_case"](case, observed_unsafe=True)
    assert reproduced["status"] == "vulnerability_reproduced"
    assert reproduced["evidence_refs"] == []

    inconclusive = modules["evaluate_case"](case, observed_unsafe=False)
    assert inconclusive["status"] == "inconclusive"
    assert "reason" in inconclusive

    confirmed = modules["evaluate_case"](
        case,
        observed_unsafe=False,
        evidence_refs=["run:alpha2-candidate:receipt-1"],
    )
    assert confirmed["status"] == "fix_confirmed"
    assert confirmed["evidence_refs"] == ["run:alpha2-candidate:receipt-1"]


def test_alpha1_manifest_receipt_is_deterministic_and_counts_results() -> None:
    modules = api()
    manifest = modules["load_manifest"](MANIFEST)
    observations = {manifest["cases"][0]["id"]: True}

    receipt = modules["evaluate_manifest"](manifest, observations=observations)

    assert receipt["schema_version"] == 1
    assert receipt["baseline"] == manifest["baseline"]
    assert len(receipt["results"]) == len(manifest["cases"])
    assert receipt["counts"] == {
        "vulnerability_reproduced": 1,
        "inconclusive": 8,
        "fix_confirmed": 0,
    }
    assert receipt["results"][0]["oracle_id"] == manifest["cases"][0]["oracle_id"]
