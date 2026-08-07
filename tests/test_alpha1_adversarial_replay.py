from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_pinned_alpha1_hermes_accepts_a_filler_report_from_clean_checkout(tmp_path: Path) -> None:
    from evaluation.harness.alpha1_adversarial import replay_filler_report

    receipt = replay_filler_report(repository_root=ROOT, work_root=tmp_path)
    baseline = json.loads((ROOT / "evaluation/baselines/alpha1-0.0.1-a1.json").read_text())

    assert receipt["baseline"]["commit"] == "8ab91ea4eb55c98441b5ee6001b80922a56ecdd1"
    assert receipt["host"] == "hermes"
    assert receipt["status"] == "vulnerability_reproduced"
    assert receipt["semantic_predicate"] == "legacy_hermes_completed_heading_padding_reports"
    assert receipt["commands"][-1]["name"] == "complete"
    assert receipt["commands"][-1]["returncode"] == 0
    assert receipt["commands"][-1]["stdout"]
    assert str(tmp_path) not in receipt["commands"][-1]["command"]
    assert str(tmp_path) not in receipt["commands"][-1]["stdout"]
    assert receipt["observed"]["status"] == "complete"
    assert receipt["inputs"]["technical"]["bytes"] >= 1024
    assert receipt["inputs"]["human"]["bytes"] >= 512
    assert receipt["host_package"] == baseline["host_packages"]["hermes"]
    assert receipt["environment"]["implementation"] == sys.implementation.name
    assert receipt["limitations"] == ["baseline reproduction is not fix confirmation"]


def test_recorded_filler_report_receipt_is_redacted_and_not_fix_confirmation() -> None:
    result = json.loads(
        (ROOT / "evaluation/results/alpha1-adversarial-v1/filler-report.json").read_text()
    )

    assert result["status"] == "vulnerability_reproduced"
    assert result["observed"]["status"] == "complete"
    assert result["host_package"]["path"] == "packages/hermes/research-tree"
    assert result["commands"][-1]["name"] == "complete"
    assert "<workspace>" in result["commands"][-1]["stdout"]
    assert "/private/" not in json.dumps(result)
    assert "fix_confirmed" not in json.dumps(result)
