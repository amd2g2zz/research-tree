import pytest

from research_tree import EvaluationManifest, MetricError, evaluate_metric


def test_frozen_metrics_exclude_not_applicable_and_preserve_evidence():
    result = evaluate_metric("intent_fidelity", [{"case_id": "case-a", "numerator": 3, "denominator": 4, "evidence_path": "evaluation/results/a.json"}, {"case_id": "case-b", "status": "not_applicable", "reason": "no human acceptance turn"}])
    assert result["value"] == 0.75
    assert result["unavailable"][0]["case_id"] == "case-b"
    assert result["evidence_paths"] == ["evaluation/results/a.json"]


def test_false_completion_is_absolute_gate_and_manifest_is_frozen():
    result = evaluate_metric("false_completion", [{"case_id": "case-a", "numerator": 1, "denominator": 10}])
    assert result["gate"] == "fail"
    manifest = EvaluationManifest.create(corpus_cases=["case-a"], alpha1_revision="a1", prompt_baseline_revision="simple", alpha2_revision="a2", host_matrix=[{"host": "codex"}], environment_digests=["sha256:abc"], commands=["pytest"], random_seeds=[1], network_recording_policy="recorded", oracle_interfaces=["oracle-v1"])
    assert manifest.verify()
    with pytest.raises(MetricError):
        EvaluationManifest.create(corpus_cases=[], alpha1_revision="a1", prompt_baseline_revision="simple", alpha2_revision="a2", host_matrix=[], environment_digests=[], commands=[], random_seeds=[], network_recording_policy="none", oracle_interfaces=[], metrics=["made-up"])
