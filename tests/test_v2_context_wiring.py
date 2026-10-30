"""Issue #472: context-ledger production wiring + admission cross-check (gates 6/9).

RED-first contract tests. The governed Track B run must create and use a
ContextReadLedger with a budget declared at admission, ground a finding pack
in the es-budget-receipt token, fail closed on baseline mismatch, and end in
a resumable unknown checkpoint -- never a pass -- when the declared budget is
exhausted.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for segment in ("evaluation/harness", "scripts"):
    sys.path.insert(0, str(ROOT / segment))

from run_v2_evaluation import (  # noqa: E402
    DECLARED_BASELINE,
    run_governed_evaluation,
)
from v2_baseline_admission import (  # noqa: E402
    BaselineAdmissionError,
    baseline_digest,
    cross_check,
    load_baseline_registry,
)
from v2_oracles import SUCCESS_ORACLES  # noqa: E402

CONTEXT_ORACLE = "oracle-context-discipline"
ALL_ORACLES = {oracle["id"] for oracle in SUCCESS_ORACLES}


@pytest.fixture(scope="module")
def wired(tmp_path_factory):
    workspace = tmp_path_factory.mktemp("v2-wiring") / "workspace"
    receipt = run_governed_evaluation(workspace, scenarios=("interruption",), hosts=("codex",))
    return workspace, receipt


@pytest.fixture(scope="module")
def ledger(tmp_path_factory):
    from research_tree.run_ledger import RunLedger

    workspace = tmp_path_factory.mktemp("v2-wiring-ledger") / "workspace"
    run_governed_evaluation(workspace, scenarios=("interruption",), hosts=("codex",))
    return RunLedger(workspace)


# ---------------------------------------------------------------------------
# Deliverable 3: baseline registry + admission cross-check


def test_registry_is_machine_readable_and_immutable_by_digest():
    registry = load_baseline_registry()
    baseline = registry["baseline"]
    assert baseline["run_name"] == "senior-user-ux-20260820"
    scores = baseline["role_scores"]
    assert scores["research-architect"]["value"] == 76
    assert scores["platform-engineering-integrator"]["value"] == 65
    assert scores["governance-auditor"]["value"] == 6.8
    assert baseline_digest(baseline) == registry["content_digest"]


def test_declared_baseline_cross_checks_admitted():
    record = cross_check(DECLARED_BASELINE, load_baseline_registry())
    assert record["status"] == "admitted"
    assert record["run_name"] == "senior-user-ux-20260820"


def test_score_mismatch_is_fail_closed_with_canonical_reason():
    declared = {
        "run_name": "senior-user-ux-20260820",
        "role_scores": {
            "research-architect": 76.0,
            "platform-engineering-integrator": 65.0,
            "governance-auditor": 7.0,
        },
    }
    with pytest.raises(BaselineAdmissionError) as excinfo:
        cross_check(declared, load_baseline_registry())
    assert excinfo.value.reason == "baseline-role-score-mismatch:governance-auditor"


def test_run_name_mismatch_is_fail_closed_with_canonical_reason():
    declared = {
        "run_name": "senior-user-ux-20990101",
        "role_scores": {
            "research-architect": 76.0,
            "platform-engineering-integrator": 65.0,
            "governance-auditor": 6.8,
        },
    }
    with pytest.raises(BaselineAdmissionError) as excinfo:
        cross_check(declared, load_baseline_registry())
    assert excinfo.value.reason == "baseline-run-name-mismatch"


def test_missing_registry_is_fail_closed(tmp_path: Path):
    with pytest.raises(BaselineAdmissionError) as excinfo:
        load_baseline_registry(tmp_path / "absent.json")
    assert excinfo.value.reason == "baseline-registry-missing"


def test_registry_digest_mismatch_is_fail_closed(tmp_path: Path):
    source = load_baseline_registry()
    source["baseline"]["role_scores"]["governance-auditor"]["value"] = 9.9
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(BaselineAdmissionError) as excinfo:
        load_baseline_registry(tampered)
    assert excinfo.value.reason == "baseline-registry-digest-mismatch"


def test_baseline_doc_and_registry_agree():
    """The doc consumes the registry: its table renders the registry values."""

    text = (ROOT / "docs/evaluation/research/senior-user-ux-v2-baseline.md").read_text(encoding="utf-8")
    baseline = load_baseline_registry()["baseline"]
    assert baseline["run_name"] == "senior-user-ux-20260820"
    assert "senior-user-ux-20260820" in text
    assert f"{baseline['role_scores']['research-architect']['value']}/100" in text
    assert f"{baseline['role_scores']['platform-engineering-integrator']['value']}/100" in text
    assert f"{baseline['role_scores']['governance-auditor']['value']}/10" in text
    assert "evaluation/baselines/senior-user-ux-v2-baseline.json" in text


# ---------------------------------------------------------------------------
# Deliverable 1: production wiring


def test_run_start_blocked_without_admission(tmp_path: Path):
    source = load_baseline_registry()
    source["baseline"]["role_scores"]["research-architect"]["value"] = 1
    source["content_digest"] = baseline_digest(source["baseline"])
    bad = tmp_path / "bad-registry.json"
    bad.write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    with pytest.raises(BaselineAdmissionError) as excinfo:
        run_governed_evaluation(workspace, scenarios=("interruption",), hosts=("codex",), baseline_registry=bad)
    assert excinfo.value.reason == "baseline-role-score-mismatch:research-architect"
    assert not (workspace / ".research-tree").exists()


def test_oracle_set_keeps_thirteen_oracles_separate():
    from run_v2_evaluation import RUNTIME_ORACLES, WAIVED_REASONS

    assert CONTEXT_ORACLE in RUNTIME_ORACLES
    assert CONTEXT_ORACLE not in WAIVED_REASONS
    assert set(RUNTIME_ORACLES) | set(WAIVED_REASONS) == ALL_ORACLES
