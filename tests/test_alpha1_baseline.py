from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evaluation" / "baselines" / "alpha1-adversarial-v1.json"

EXPECTED_DEFECTS = {
    "forged-validation",
    "missing-evidence",
    "filler-report",
    "empty-frontier",
    "active-contradiction",
    "repeated-reconnaissance",
    "adapter-only-completion",
    "provider-failure",
    "crash-recovery",
}


def test_alpha1_adversarial_manifest_is_complete_and_truthful() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert manifest["schema_version"] == 1
    assert manifest["baseline"] == {
        "tag": "0.0.1-a1",
        "commit": "8ab91ea4eb55c98441b5ee6001b80922a56ecdd1",
    }
    cases = {case["case_id"]: case for case in manifest["cases"]}
    assert set(cases) == EXPECTED_DEFECTS
    assert len(cases) == len(EXPECTED_DEFECTS)

    executable = [case for case in cases.values() if case["status"] == "executable"]
    pending = [case for case in cases.values() if case["status"] == "pending"]
    assert {case["case_id"] for case in executable} == {
        "filler-report",
        "forged-validation",
    }
    assert len(pending) == 7

    for case in executable:
        for key in ("fixture", "harness", "receipt", "semantic_predicate"):
            assert case[key]
        for relative in (case["fixture"], case["harness"], case["receipt"]):
            assert (ROOT / relative).is_file(), relative
        receipt = json.loads((ROOT / case["receipt"]).read_text(encoding="utf-8"))
        assert receipt["case_id"] == case["case_id"]
        assert receipt["status"] == "vulnerability_reproduced"
        assert receipt["semantic_predicate"] == case["semantic_predicate"]
        assert "fix_confirmed" not in json.dumps(receipt)

    for case in pending:
        assert case["reason"]
        assert "receipt" not in case
