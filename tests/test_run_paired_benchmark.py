from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).parents[1]


def runner_module():
    path = ROOT / "evaluation/harness/run_paired_benchmark.py"
    spec = importlib.util.spec_from_file_location("run_paired_benchmark", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def benchmark_test_module():
    path = ROOT / "tests/test_paired_benchmark.py"
    spec = importlib.util.spec_from_file_location("paired_benchmark_test_data", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_runner_reports_unavailable_without_claiming_a_completed_benchmark(capsys: pytest.CaptureFixture[str]) -> None:
    runner = runner_module()

    assert runner.main(["--expect-status", "unavailable"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "unavailable"
    assert result["human_evidence_status"] == "unavailable"


def test_runner_only_accepts_evaluator_owned_inputs_and_outputs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = runner_module()
    fixture = benchmark_test_module()
    manifest = fixture.sealed_manifest()
    measurements = fixture.records(manifest)
    manifest_path = tmp_path / "manifest.json"
    records_path = tmp_path / "records.json"
    review_key_path = tmp_path / "review-attestation.key"
    output_path = tmp_path / "result.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    records_path.write_text(json.dumps(measurements), encoding="utf-8")
    review_key_path.write_bytes(fixture.REVIEW_KEY + b"\n")

    assert (
        runner.main(
            [
                "--manifest",
                str(manifest_path),
                "--records",
                str(records_path),
                "--review-attestation-key-file",
                str(review_key_path),
                "--output",
                str(output_path),
                "--expect-status",
                "analyzed",
            ]
        )
        == 0
    )
    result = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["status"] == "analyzed"
    assert "transcript" not in output_path.read_text(encoding="utf-8")
    assert json.loads(capsys.readouterr().out)["status"] == "analyzed"


def test_runner_refuses_tracked_evaluation_paths(tmp_path: Path) -> None:
    runner = runner_module()
    tracked_path = ROOT / "evaluation" / "results" / "not-an-input.json"

    with pytest.raises(ValueError, match="outside the tracked repository"):
        runner._require_evaluator_owned(tracked_path, "sealed manifest")
    assert runner._is_evaluator_owned(tmp_path / "external.json") is True


def test_runner_requires_an_external_review_attestation_key(tmp_path: Path) -> None:
    runner = runner_module()
    fixture = benchmark_test_module()
    manifest = fixture.sealed_manifest()
    measurements = fixture.records(manifest)
    manifest_path = tmp_path / "manifest.json"
    records_path = tmp_path / "records.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    records_path.write_text(json.dumps(measurements), encoding="utf-8")

    with pytest.raises(ValueError, match="attestation key"):
        runner.run(manifest_path, records_path)

    tracked_key = ROOT / "review-attestation.key"
    with pytest.raises(ValueError, match="outside the tracked repository"):
        runner._require_evaluator_owned(tracked_key, "review attestation key")
