from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from test_readiness import complete_conditional_package, package_context

from research_tree.domain import thaw_json


def api():
    from research_tree import (
        CanonicalReadinessVerifier,
        InvalidReadinessError,
        IsolatedVerificationResult,
        VerificationFailure,
        readiness_for_delivery,
    )

    return {
        "IsolatedVerificationResult": IsolatedVerificationResult,
        "InvalidReadinessError": InvalidReadinessError,
        "CanonicalReadinessVerifier": CanonicalReadinessVerifier,
        "VerificationFailure": VerificationFailure,
        "readiness_for_delivery": readiness_for_delivery,
    }


@dataclass
class CapturingAdapter:
    result_factory: object
    request: object | None = None

    def run(self, request):
        self.request = request
        return self.result_factory(request)


def safe_isolation(*, repository_mutated: bool = False, host_secrets_exposed: bool = False):
    return {
        "host_secrets_exposed": host_secrets_exposed,
        "repository_mutated": repository_mutated,
        "isolated_working_copy": True,
        "network_access": "disabled",
    }


def result_for(api_modules, request, *, status: str, failure=None, isolation=None):
    command_names = (
        ("spike",) if request.check_kind == "targeted_spike" else ("build", "hidden_acceptance", "regression")
    )
    return api_modules["IsolatedVerificationResult"](
        check_kind=request.check_kind,
        status=status,
        commands=tuple({"name": name, "command": f"fake-{name}"} for name in command_names),
        results=tuple(
            {
                "name": name,
                "status": "pass" if status == "pass" else "fail",
                "summary": f"Deterministic {name} result.",
            }
            for name in command_names
        ),
        isolation=safe_isolation() if isolation is None else isolation,
        failure=failure,
    )


def verify(api_modules, fixture_modules, store, round_record, package, *, root: Path, tier: str, adapter=None):
    return api_modules["CanonicalReadinessVerifier"](
        store,
        fixture_modules["resolver"],
    ).verify(
        round_id=round_record.id,
        readiness_id=f"readiness-risk-{tier}",
        technical_package=package,
        repository_roots={"input-repository": root},
        risk_tier=tier,
        verification_adapter=adapter,
        expected_revision=store.get_revision(round_record.id),
    )


def test_default_policy_records_each_execution_check_as_skipped(tmp_path: Path) -> None:
    api_modules = api()
    (
        fixture_modules,
        store,
        round_record,
        _model,
        _brief,
        _target,
        _finding,
        _decision,
        package,
    ) = package_context(tmp_path)

    record = verify(
        api_modules,
        fixture_modules,
        store,
        round_record,
        package,
        root=tmp_path / "repository",
        tier="default",
    )

    evidence = record.payload["risk_verification"]
    assert evidence["policy"]["execution_check"] is None
    assert evidence["executed_checks"] == ()
    assert {item["check"] for item in evidence["skipped_checks"]} == {
        "targeted_spike",
        "independent_implementation_run",
    }
    assert api_modules["readiness_for_delivery"](record)["risk_tier"] == "default"


def test_rt008_readiness_records_remain_readable_without_rt011_fields(tmp_path: Path) -> None:
    api_modules = api()
    (
        fixture_modules,
        store,
        round_record,
        _model,
        _brief,
        _target,
        _finding,
        _decision,
        package,
    ) = package_context(tmp_path)
    record = verify(
        api_modules,
        fixture_modules,
        store,
        round_record,
        package,
        root=tmp_path / "repository",
        tier="default",
    )
    legacy_payload = thaw_json(record.payload)
    legacy_payload.pop("risk_verification")
    for diagnostic in legacy_payload["diagnostics"]:
        diagnostic.pop("failure_category")
    legacy = store.append_artifact(
        round_record.id,
        record.id,
        record.kind,
        legacy_payload,
        parent_refs=record.parent_refs,
        expected_revision=store.get_revision(round_record.id),
    )

    assert api_modules["readiness_for_delivery"](legacy) == legacy.payload["delivery_readiness"]


def test_medium_spike_gets_a_sanitized_request_and_persists_evidence(tmp_path: Path) -> None:
    api_modules = api()
    fixture_modules, store, round_record, package = complete_conditional_package(tmp_path)
    adapter = CapturingAdapter(lambda request: result_for(api_modules, request, status="pass"))

    record = verify(
        api_modules,
        fixture_modules,
        store,
        round_record,
        package,
        root=tmp_path / "repository",
        tier="medium",
        adapter=adapter,
    )

    request = adapter.request
    assert request is not None
    assert request.check_kind == "targeted_spike"
    assert not hasattr(request, "repository_roots")
    assert "repository_root" not in request.baselines[0]
    assert "origin_locator" not in request.baselines[0]
    assert "read_scope" not in request.baselines[0]
    assert request.technical_package["ref"]["artifact_id"] == package.id
    evidence = record.payload["risk_verification"]
    assert evidence["executed_checks"][0]["check"] == "targeted_spike"
    assert evidence["executed_checks"][0]["commands"] == ({"name": "spike", "command": "fake-spike"},)
    assert evidence["executed_checks"][0]["isolation"] == safe_isolation()


def test_high_risk_passing_run_records_exact_versions_commands_and_results(tmp_path: Path) -> None:
    api_modules = api()
    fixture_modules, store, round_record, package = complete_conditional_package(tmp_path)
    adapter = CapturingAdapter(lambda request: result_for(api_modules, request, status="pass"))

    record = verify(
        api_modules,
        fixture_modules,
        store,
        round_record,
        package,
        root=tmp_path / "repository",
        tier="high",
        adapter=adapter,
    )

    evidence = record.payload["risk_verification"]
    executed = evidence["executed_checks"][0]
    assert executed["check"] == "independent_implementation_run"
    assert executed["status"] == "pass"
    assert {item["name"] for item in executed["commands"]} == {
        "build",
        "hidden_acceptance",
        "regression",
    }
    assert {item["name"] for item in executed["results"]} == {
        "build",
        "hidden_acceptance",
        "regression",
    }
    assert evidence["technical_package"] == {
        "ref": {
            "round_id": round_record.id,
            "artifact_id": package.id,
            "revision": package.revision,
        },
        "content_hash": package.content_hash,
    }
    assert evidence["baselines"][0]["revision"]["sha256"]
    assert api_modules["readiness_for_delivery"](record)["gates"]["implementation_readiness"] == "pass"


def test_high_policy_marks_a_missing_independent_run_as_a_same_round_failure(tmp_path: Path) -> None:
    api_modules = api()
    fixture_modules, store, round_record, package = complete_conditional_package(tmp_path)

    record = verify(
        api_modules,
        fixture_modules,
        store,
        round_record,
        package,
        root=tmp_path / "repository",
        tier="high",
    )

    evidence = record.payload["risk_verification"]
    assert evidence["executed_checks"] == ()
    assert evidence["skipped_checks"][1]["check"] == "independent_implementation_run"
    assert evidence["same_round_follow_ups"][0]["decision_slot_id"] == "slot-isolation"
    assert api_modules["readiness_for_delivery"](record)["gates"]["implementation_readiness"] == "fail"


def test_high_risk_rejects_incomplete_execution_evidence_before_persisting(tmp_path: Path) -> None:
    api_modules = api()
    fixture_modules, store, round_record, package = complete_conditional_package(tmp_path)
    adapter = CapturingAdapter(
        lambda request: api_modules["IsolatedVerificationResult"](
            check_kind=request.check_kind,
            status="pass",
            commands=({"name": "build", "command": "fake-build"},),
            results=(
                {
                    "name": "build",
                    "status": "pass",
                    "summary": "Only one required check was recorded.",
                },
            ),
            isolation=safe_isolation(),
        )
    )

    with pytest.raises(api_modules["InvalidReadinessError"], match="hidden_acceptance"):
        verify(
            api_modules,
            fixture_modules,
            store,
            round_record,
            package,
            root=tmp_path / "repository",
            tier="high",
            adapter=adapter,
        )

    assert not [
        artifact for artifact in store.load_run(round_record.id).artifacts if artifact.kind == "readiness-record"
    ]


def test_risk_evidence_cannot_name_a_different_technical_package(tmp_path: Path) -> None:
    api_modules = api()
    fixture_modules, store, round_record, package = complete_conditional_package(tmp_path)
    adapter = CapturingAdapter(lambda request: result_for(api_modules, request, status="pass"))
    record = verify(
        api_modules,
        fixture_modules,
        store,
        round_record,
        package,
        root=tmp_path / "repository",
        tier="high",
        adapter=adapter,
    )
    corrupted_payload = thaw_json(record.payload)
    corrupted_payload["risk_verification"]["technical_package"]["ref"]["artifact_id"] = "wrong-package"
    corrupted = store.append_artifact(
        round_record.id,
        record.id,
        record.kind,
        corrupted_payload,
        parent_refs=record.parent_refs,
        expected_revision=store.get_revision(round_record.id),
    )

    with pytest.raises(api_modules["InvalidReadinessError"], match="technical package ref"):
        api_modules["readiness_for_delivery"](corrupted)


def test_high_risk_failure_is_classified_and_returns_same_round_follow_up(tmp_path: Path) -> None:
    api_modules = api()
    fixture_modules, store, round_record, package = complete_conditional_package(tmp_path)
    failure = api_modules["VerificationFailure"](
        category="oracle_quality",
        summary="The hidden acceptance oracle cannot distinguish the fallback path.",
        decision_slot_id="slot-isolation",
        work_item_id="work-isolation",
    )
    adapter = CapturingAdapter(
        lambda request: result_for(
            api_modules,
            request,
            status="fail",
            failure=failure,
        )
    )

    record = verify(
        api_modules,
        fixture_modules,
        store,
        round_record,
        package,
        root=tmp_path / "repository",
        tier="high",
        adapter=adapter,
    )

    diagnostic = next(item for item in record.payload["diagnostics"] if item["failure_category"] == "oracle_quality")
    follow_up = record.payload["risk_verification"]["same_round_follow_ups"][0]
    assert diagnostic["gate"] == "implementation_readiness"
    assert diagnostic["decision_slot_id"] == "slot-isolation"
    assert diagnostic["work_item_id"] == "work-isolation"
    assert follow_up == {
        "category": "oracle_quality",
        "decision_slot_id": "slot-isolation",
        "work_item_id": "work-isolation",
        "action": "replan",
        "summary": "The hidden acceptance oracle cannot distinguish the fallback path.",
    }
    assert api_modules["readiness_for_delivery"](record)["gates"]["implementation_readiness"] == "fail"


def test_unsafe_attestation_cannot_turn_a_high_risk_run_into_a_pass(tmp_path: Path) -> None:
    api_modules = api()
    fixture_modules, store, round_record, package = complete_conditional_package(tmp_path)
    adapter = CapturingAdapter(
        lambda request: result_for(
            api_modules,
            request,
            status="pass",
            isolation=safe_isolation(repository_mutated=True, host_secrets_exposed=True),
        )
    )

    record = verify(
        api_modules,
        fixture_modules,
        store,
        round_record,
        package,
        root=tmp_path / "repository",
        tier="high",
        adapter=adapter,
    )

    executed = record.payload["risk_verification"]["executed_checks"][0]
    assert executed["status"] == "fail"
    assert executed["isolation"]["repository_mutated"] is True
    assert executed["isolation"]["host_secrets_exposed"] is True
    assert record.payload["risk_verification"]["failures"][0]["category"] == "repository_fit"
    assert api_modules["readiness_for_delivery"](record)["gates"]["repository_fit"] == "fail"
