from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_pinned_alpha1_hermes_accepts_a_filler_report_from_clean_checkout(tmp_path: Path) -> None:
    from evaluation.harness.alpha1_adversarial import replay_filler_report

    receipt = replay_filler_report(repository_root=ROOT, work_root=tmp_path)

    assert receipt["baseline"]["commit"] == "8ab91ea4eb55c98441b5ee6001b80922a56ecdd1"
    assert receipt["host"] == "hermes"
    assert receipt["status"] == "vulnerability_reproduced"
    assert receipt["semantic_predicate"] == "legacy_hermes_completed_heading_padding_reports"
    assert receipt["commands"][-1]["returncode"] == 0
    assert receipt["observed"]["status"] == "complete"
    assert receipt["inputs"]["technical"]["bytes"] >= 1024
    assert receipt["inputs"]["human"]["bytes"] >= 512
    assert receipt["host_package"]["path"] == "packages/hermes/research-tree"
    assert len(receipt["host_package"]["sha256"]) == 64
    assert receipt["limitations"] == ["baseline reproduction is not fix confirmation"]
