from copy import deepcopy

import pytest


def api():
    from research_tree import InvalidReleaseManifest, ReleaseManifest, evaluate_release

    return InvalidReleaseManifest, ReleaseManifest, evaluate_release


def case(host: str = "codex", **changes):
    value = {
        "case_id": f"case-{host}",
        "case_version": "1",
        "host": host,
        "execution_disposition": "passed",
        "source_revision": "a" * 40,
        "environment_digest": "b" * 64,
        "package_digest": "c" * 64,
        "command": "independent-runner --case public",
        "public_artifact_refs": [f"artifact:{host}:result"],
        "opaque_oracle_id": f"oracle-{host}",
        "oracle_verdict_digest": "d" * 64,
        "evaluator_id": f"independent-{host}",
        "producer_id": f"worker-{host}",
        "false_completion_count": 0,
        "p0_total": 2,
        "p0_resolved": 2,
        "evidence_refs_resolved": True,
        "closure_refs_resolved": True,
        "recovery_preserved": True,
        "semantic_delivery_consistent": True,
        "canonical_outcome_digest": "e" * 64,
        "quality": {
            "intent_fidelity": 0.9,
            "unsupported_claim_control": 1.0,
            "contradiction_handling": 0.8,
            "depth": 0.85,
            "implementation_success": 1.0,
            "rediscovery_control": 0.8,
            "professional_usefulness": 0.9,
        },
        "comparison": {
            "alpha2_implementation_success": 1.0,
            "alpha1_implementation_success": 0.5,
            "simpler_prompt_implementation_success": 0.4,
        },
        "review_refs": [f"review:{host}:blinded"],
        "limitations": ["Provider-specific latency is not compared."],
    }
    value.update(changes)
    return value


def manifest(**changes):
    value = {
        "schema_version": 1,
        "manifest_id": "alpha2-candidate-1",
        "source_revision": "f" * 40,
        "required_hosts": ["codex", "claude-code", "hermes"],
        "cases": [case(host) for host in ("codex", "claude-code", "hermes")],
        "quality_thresholds": {
            "intent_fidelity": 0.7,
            "unsupported_claim_control": 0.9,
            "contradiction_handling": 0.7,
            "depth": 0.7,
            "implementation_success": 0.8,
            "rediscovery_control": 0.6,
            "professional_usefulness": 0.7,
        },
        "independent_implementation_refs": ["implementation:runner:1"],
        "blinded_review_refs": ["review:panel:1"],
        "limitations": ["Live provider variability remains external."],
    }
    value.update(changes)
    return value


def test_release_manifest_passes_only_with_all_integrity_gates() -> None:
    _, ReleaseManifest, evaluate_release = api()
    decision = evaluate_release(ReleaseManifest.from_mapping(manifest()))

    assert decision.status == "pass"
    assert all(gate.status == "pass" for gate in decision.integrity_gates)
    assert set(decision.quality_diagnostics) == set(manifest()["quality_thresholds"])


@pytest.mark.parametrize(
    ("change", "gate"),
    [
        ({"false_completion_count": 1}, "zero_false_completion"),
        ({"p0_resolved": 1}, "p0_resolution"),
        ({"evidence_refs_resolved": False}, "evidence_and_closure"),
        ({"recovery_preserved": False}, "recovery"),
        ({"semantic_delivery_consistent": False}, "semantic_delivery"),
    ],
)
def test_non_negotiable_gate_cannot_be_offset_by_high_quality(change, gate) -> None:
    _, ReleaseManifest, evaluate_release = api()
    value = manifest()
    value["cases"][0].update(change)

    decision = evaluate_release(ReleaseManifest.from_mapping(value))

    assert decision.status == "fail"
    assert next(item for item in decision.integrity_gates if item.name == gate).status == "fail"
    assert min(decision.quality_diagnostics.values()) >= 0.8


def test_unavailable_host_and_parity_drift_fail_honestly() -> None:
    _, ReleaseManifest, evaluate_release = api()
    unavailable = manifest()
    unavailable["cases"][2].update(
        execution_disposition="unavailable",
        oracle_verdict_digest=None,
        public_artifact_refs=[],
        limitations=["Hermes executable is unavailable."],
    )
    decision = evaluate_release(ReleaseManifest.from_mapping(unavailable))
    assert next(item for item in decision.integrity_gates if item.name == "required_host_parity").status == "fail"

    drift = manifest()
    drift["cases"][1]["canonical_outcome_digest"] = "0" * 64
    decision = evaluate_release(ReleaseManifest.from_mapping(drift))
    assert next(item for item in decision.integrity_gates if item.name == "required_host_parity").status == "fail"


def test_manifest_rejects_hidden_material_self_review_and_missing_binding() -> None:
    InvalidReleaseManifest, ReleaseManifest, _ = api()
    leaking = manifest()
    leaking["cases"][0]["reference_patch"] = "diff --git a/secret"
    with pytest.raises(InvalidReleaseManifest, match="hidden"):
        ReleaseManifest.from_mapping(leaking)

    self_review = manifest()
    self_review["cases"][0]["evaluator_id"] = self_review["cases"][0]["producer_id"]
    with pytest.raises(InvalidReleaseManifest, match="independent"):
        ReleaseManifest.from_mapping(self_review)

    missing = deepcopy(manifest())
    del missing["cases"][0]["environment_digest"]
    with pytest.raises(InvalidReleaseManifest, match="fields"):
        ReleaseManifest.from_mapping(missing)


def test_proxy_counts_are_not_release_authority() -> None:
    _, ReleaseManifest, evaluate_release = api()
    value = manifest()
    value["cases"][0]["false_completion_count"] = 1
    value["proxy_metrics"] = {"source_count": 1000, "report_bytes": 1_000_000}

    decision = evaluate_release(ReleaseManifest.from_mapping(value))

    assert decision.status == "fail"
    assert "proxy_metrics" not in decision.to_dict()


def test_quality_threshold_and_independent_improvement_are_release_gates() -> None:
    _, ReleaseManifest, evaluate_release = api()
    shallow = manifest()
    shallow["cases"][0]["quality"]["depth"] = 0.4
    decision = evaluate_release(ReleaseManifest.from_mapping(shallow))
    assert next(item for item in decision.integrity_gates if item.name == "quality_thresholds").status == "fail"

    no_improvement = manifest()
    no_improvement["cases"][0]["comparison"]["alpha1_implementation_success"] = 1.0
    decision = evaluate_release(ReleaseManifest.from_mapping(no_improvement))
    assert (
        next(item for item in decision.integrity_gates if item.name == "independent_implementation_improvement").status
        == "fail"
    )
