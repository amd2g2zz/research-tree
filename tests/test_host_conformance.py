from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "evaluation" / "cases" / "host-conformance-v1.json"
RUNNER = ROOT / "evaluation" / "harness" / "run_host_conformance.py"


def test_frozen_case_loads_and_is_deterministic() -> None:
    sys.path.insert(0, str(ROOT / "evaluation" / "harness"))
    from host_conformance import load_case

    case = load_case(CASE)
    assert case["id"] == "host-conformance-v1"
    assert len(case["leaves"]) == 2
    assert "contradiction_detected" in " ".join(case["expected_canonical_sequence"])


def test_projected_identity_oracle_fails_when_accepted() -> None:
    sys.path.insert(0, str(ROOT / "evaluation" / "harness"))
    from host_conformance import check_negative_oracle

    case = json.loads(CASE.read_text(encoding="utf-8"))
    assert check_negative_oracle(case, {"kind": "projected-identity"}) == "passed"
    assert "failed" in check_negative_oracle(case, {"kind": "projected-identity", "identity": "worker-1"})


def test_synthetic_finding_and_capability_oracles() -> None:
    sys.path.insert(0, str(ROOT / "evaluation" / "harness"))
    from host_conformance import check_negative_oracle

    case = json.loads(CASE.read_text(encoding="utf-8"))
    assert "failed" in check_negative_oracle(case, {"kind": "synthetic-finding"})
    assert check_negative_oracle(case, {"kind": "synthetic-finding", "anchor": "src"}) == "passed"
    assert check_negative_oracle(case, {"kind": "capability-string"}) == "passed"
    assert "failed" in check_negative_oracle(case, {"kind": "capability-string", "executed": True})


def test_sequence_comparison_detects_missing_contradiction_and_validation() -> None:
    sys.path.insert(0, str(ROOT / "evaluation" / "harness"))
    from host_conformance import compare_sequences

    expected = ["attempt_started:leaf-a", "contradiction_detected:", "retry:leaf-a", "validation:accepted"]
    observed_missing = ["attempt_started:leaf-a", "worker_finished:leaf-a", "worker_finished:leaf-b"]
    divergences = compare_sequences(expected, observed_missing)
    assert any("contradiction_detected" in d for d in divergences)
    assert any("validation" in d for d in divergences)


def test_replay_divergence_fails_closed() -> None:
    sys.path.insert(0, str(ROOT / "evaluation" / "harness"))
    from host_conformance import check_replay

    recorded = {
        "accepted_attempts": ["a1"],
        "unresolved_work": [],
        "event_sequence": ["start", "finish"],
        "attempt_ids": ["a1"],
    }
    same = {
        "accepted_attempts": ["a1"],
        "unresolved_work": [],
        "event_sequence": ["start", "finish"],
        "attempt_ids": ["a1"],
    }
    assert check_replay(recorded, same)["status"] == "passed"
    divergent = dict(same, unresolved_work=["a2"])
    assert check_replay(recorded, divergent)["status"] == "failed"


def test_runner_blocks_without_observation_and_passes_conforming_observation(tmp_path: Path) -> None:
    result_path = tmp_path / "result.json"
    blocked = subprocess.run(
        [sys.executable, str(RUNNER), "--case", str(CASE), "--mode", "codex", "--result", str(result_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert blocked.returncode == 1
    assert json.loads(result_path.read_text(encoding="utf-8"))["status"] == "blocked"

    observation = {
        "events": [
            "attempt_started:leaf-a",
            "attempt_started:leaf-b",
            "worker_finished:leaf-a",
            "worker_finished:leaf-b",
            "contradiction_detected:",
            "retry:leaf-a",
            "worker_finished:leaf-a-retry",
            "validation:accepted",
        ],
        "identities": ["call-alpha", "call-beta"],
        "oracle_submissions": [
            {"kind": "projected-identity"},
            {"kind": "synthetic-finding", "anchor": "src"},
            {"kind": "capability-string"},
        ],
        "faults": [{"kind": "process_kill", "resulted_in_completion": False}],
        "envelope": {"kind": "deviation-accepted", "digest": "sha256:0" * 8, "deviation": None},
    }
    obs_path = tmp_path / "obs.json"
    obs_path.write_text(json.dumps(observation), encoding="utf-8")
    passed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--case",
            str(CASE),
            "--mode",
            "codex",
            "--observation",
            str(obs_path),
            "--result",
            str(result_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert passed.returncode == 0, passed.stderr
    assert json.loads(result_path.read_text(encoding="utf-8"))["status"] == "passed"
