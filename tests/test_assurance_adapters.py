from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import research_tree

from canonical_finding_fixture import canonical_context


_RESOLVERS = {}


def api():
    from research_tree import (
        ArtifactRef,
        AssuranceAdapterSet,
        CanonicalAssuranceAdapterRunner,
        CanonicalAssuranceStrategySelector,
        InvalidAssuranceError,
    )

    return {
        "ArtifactRef": ArtifactRef,
        "AssuranceAdapterSet": AssuranceAdapterSet,
        "CanonicalAssuranceAdapterRunner": CanonicalAssuranceAdapterRunner,
        "CanonicalAssuranceStrategySelector": CanonicalAssuranceStrategySelector,
        "InvalidAssuranceError": InvalidAssuranceError,
    }


def test_legacy_assurance_exports_are_absent() -> None:
    assert not hasattr(research_tree, "AssuranceStrategySelector")
    assert not hasattr(research_tree, "AssuranceAdapterRunner")


def decision_context(tmp_path: Path):
    (
        ledger,
        resolver,
        round_record,
        _model,
        _brief,
        target,
        work,
        finding,
        decision,
        _evidence,
        _anchor,
    ) = canonical_context(tmp_path)
    modules = api()
    _RESOLVERS[ledger] = resolver
    return modules, ledger, round_record, target, work, finding, decision


def strategy_for(api_modules, store, round_record, target):
    artifact_ref = api_modules["ArtifactRef"]
    snapshot = store.load_run(round_record.id)
    by_key = {(item.id, item.revision): item for item in snapshot.artifacts}
    brief_ref = next(ref for ref in target.parent_refs if ref.artifact_id == target.payload["brief_id"])
    model_ref = next(ref for ref in target.parent_refs if ref.artifact_id == target.payload["intent_model_id"])
    brief = by_key[(brief_ref.artifact_id, brief_ref.revision)]
    model = by_key[(model_ref.artifact_id, model_ref.revision)]
    lineage = store.append_artifact(
        round_record.id,
        "feedback-lineage",
        "feedback-lineage",
        {"summary": "A persisted strategy source for assurance selection tests."},
        expected_revision=store.get_revision(round_record.id),
    )
    return store.append_artifact(
        round_record.id,
        "strategy-assurance",
        "research-strategy",
        {
            "id": "strategy-assurance",
            "round_id": round_record.id,
            "intent_model_id": model.id,
            "working_brief_id": brief.id,
            "feedback_lineage_id": lineage.id,
            "change_dimensions": ["priority"],
            "summary": "Use assurance only where the selected decision warrants it.",
            "focus": ["isolation evidence"],
            "autonomy": {
                "ask_user": "only_non_recoverable_decisions",
                "routine_unknowns": "record_assumptions_and_validate",
            },
        },
        parent_refs=(
            artifact_ref(model.round_id, model.id, model.revision),
            artifact_ref(brief.round_id, brief.id, brief.revision),
            artifact_ref(lineage.round_id, lineage.id, lineage.revision),
        ),
        expected_revision=store.get_revision(round_record.id),
    )


def select(api_modules, store, round_record, target, strategy, policies):
    return api_modules["CanonicalAssuranceStrategySelector"](store).select(
        round_id=round_record.id,
        selection_id="assurance-selection",
        strategy=strategy,
        blueprint_target=target,
        policies=policies,
        expected_revision=store.get_revision(round_record.id),
    )


def policy(*, evidence_standard: str, failure_mode: str) -> dict[str, str]:
    return {
        "decision_slot_id": "slot-isolation",
        "risk_tier": "high",
        "evidence_standard": evidence_standard,
        "decision_value": "high",
        "failure_mode": failure_mode,
        "selection_reason": "The isolation decision affects the security boundary.",
    }


def source() -> dict[str, str]:
    return {
        "locator": "https://example.test/security-guide",
        "version": "published-2026-07-31",
        "extraction_boundary": "sections 2 through 4",
        "applicability": "the selected worker-isolation decision",
    }


class PassingAcquisition:
    def acquire(self, request):
        assert request["source"]["locator"] == "https://example.test/security-guide"
        return {
            "status": "passed",
            "summary": "Fetched the versioned primary guidance.",
            "source_version": "release-42",
            "extraction_boundary": "sections 2 through 5",
            "applicability": "the current worker-isolation boundary",
        }


class PassingPrimaryValidation:
    def validate_primary_source(self, request):
        assert request["source"]["version"] == "release-42"
        return {"status": "passed", "summary": "Publisher and primary status are verified."}


class PassingReview:
    def review(self, request):
        assert request["decision"]["decision_slot_id"] == "slot-isolation"
        return {"status": "passed", "summary": "The evidence applies to the selected boundary."}


class PassingIntegrity:
    def verify_integrity(self, request):
        return {"status": "passed", "summary": "Version and extraction boundary are internally consistent."}


class FailedIntegrity:
    def verify_integrity(self, request):
        return {"status": "failed", "summary": "The cited version does not match the extracted boundary."}


class FailedReview:
    def review(self, request):
        return {"status": "failed", "summary": "The reviewed guidance does not apply to this isolation boundary."}


def high_assurance_adapters(api_modules, *, review=None, integrity=None):
    return api_modules["AssuranceAdapterSet"](
        source_acquisition=PassingAcquisition(),
        primary_source_validation=PassingPrimaryValidation(),
        evidence_review=PassingReview() if review is None else review,
        provenance_integrity=PassingIntegrity() if integrity is None else integrity,
    )


def run(api_modules, store, round_record, selection, decision, *, adapters, evidence_id="assurance-evidence"):
    return api_modules["CanonicalAssuranceAdapterRunner"](store, _RESOLVERS[store]).run(
        round_id=round_record.id,
        evidence_id=evidence_id,
        selection=selection,
        decision=decision,
        source=source(),
        adapters=adapters,
        expected_revision=store.get_revision(round_record.id),
    )


def test_ordinary_strategy_selects_no_adapters_and_keeps_the_p0_path_optional(
    tmp_path: Path,
) -> None:
    api_modules = api()
    _modules, store, round_record, target, _work, _finding, decision = decision_context(tmp_path)
    strategy = strategy_for(api_modules, store, round_record, target)

    selection = select(api_modules, store, round_record, target, strategy, policies=[])
    result = run(
        api_modules,
        store,
        round_record,
        selection,
        decision,
        adapters=api_modules["AssuranceAdapterSet"](),
    )

    assert selection.payload["decisions"] == ()
    assert result.evidence.payload["adapter_results"] == ()
    assert result.evidence.payload["status"] == "passed"
    assert result.follow_up is None
    assert result.blocked_decision is None
    assert decision.payload["status"] == "selected"


def test_high_assurance_adapters_persist_versioned_provenance_with_exact_decision_lineage(
    tmp_path: Path,
) -> None:
    api_modules = api()
    _modules, store, round_record, target, _work, finding, decision = decision_context(tmp_path)
    before_finding = deepcopy(finding.to_dict())
    strategy = strategy_for(api_modules, store, round_record, target)
    selection = select(
        api_modules,
        store,
        round_record,
        target,
        strategy,
        policies=[policy(evidence_standard="high_assurance", failure_mode="follow_up")],
    )

    result = run(
        api_modules,
        store,
        round_record,
        selection,
        decision,
        adapters=high_assurance_adapters(api_modules),
    )

    assert selection.payload["decisions"] == (
        {
            "decision_slot_id": "slot-isolation",
            "risk_tier": "high",
            "evidence_standard": "high_assurance",
            "decision_value": "high",
            "adapters": (
                "source_acquisition",
                "primary_source_validation",
                "evidence_review",
                "provenance_integrity",
            ),
            "failure_mode": "follow_up",
            "selection_reason": "The isolation decision affects the security boundary.",
        },
    )
    assert result.evidence.payload["source"] == {
        "locator": "https://example.test/security-guide",
        "version": "release-42",
        "extraction_boundary": "sections 2 through 5",
        "applicability": "the current worker-isolation boundary",
    }
    assert result.evidence.payload["review_result"]["status"] == "passed"
    assert result.evidence.payload["integrity_result"]["status"] == "passed"
    assert tuple(item["adapter_kind"] for item in result.evidence.payload["adapter_results"]) == (
        "source_acquisition",
        "primary_source_validation",
        "evidence_review",
        "provenance_integrity",
    )
    assert result.evidence.payload["decision_ref"] == {
        "round_id": round_record.id,
        "artifact_id": decision.id,
        "revision": decision.revision,
    }
    assert result.follow_up is None
    assert result.blocked_decision is None
    assert finding.to_dict() == before_finding
    rehydrated = store.load_run(round_record.id)
    assert result.evidence in rehydrated.artifacts


def test_failed_integrity_creates_targeted_follow_up_without_mutating_prior_findings(
    tmp_path: Path,
) -> None:
    api_modules = api()
    _modules, store, round_record, target, _work, finding, decision = decision_context(tmp_path)
    before_finding = deepcopy(finding.to_dict())
    strategy = strategy_for(api_modules, store, round_record, target)
    selection = select(
        api_modules,
        store,
        round_record,
        target,
        strategy,
        policies=[policy(evidence_standard="high_assurance", failure_mode="follow_up")],
    )

    result = run(
        api_modules,
        store,
        round_record,
        selection,
        decision,
        adapters=high_assurance_adapters(api_modules, integrity=FailedIntegrity()),
    )

    assert result.evidence.payload["status"] == "failed"
    assert result.evidence.payload["integrity_result"] == {
        "status": "failed",
        "summary": "The cited version does not match the extracted boundary.",
    }
    assert result.follow_up is not None
    assert result.follow_up.kind == "assurance-follow-up"
    assert result.follow_up.payload["decision_slot_id"] == "slot-isolation"
    assert result.follow_up.payload["kind"] == "evaluation"
    assert result.blocked_decision is None
    assert result.resolution.payload["status"] == "follow_up"
    assert finding.to_dict() == before_finding
    assert decision.payload["status"] == "selected"


def test_failed_high_assurance_review_appends_a_blocked_decision_revision(
    tmp_path: Path,
) -> None:
    api_modules = api()
    _modules, store, round_record, target, _work, finding, decision = decision_context(tmp_path)
    before_decision = deepcopy(decision.to_dict())
    before_finding = deepcopy(finding.to_dict())
    strategy = strategy_for(api_modules, store, round_record, target)
    selection = select(
        api_modules,
        store,
        round_record,
        target,
        strategy,
        policies=[policy(evidence_standard="high_assurance", failure_mode="block")],
    )

    result = run(
        api_modules,
        store,
        round_record,
        selection,
        decision,
        adapters=high_assurance_adapters(api_modules, review=FailedReview()),
    )

    assert result.follow_up is None
    assert result.blocked_decision is not None
    assert result.blocked_decision.id == decision.id
    assert result.blocked_decision.revision == decision.revision + 1
    assert result.blocked_decision.payload["status"] == "blocked"
    assert result.blocked_decision.payload["selected_option"] is None
    assert any(item["option"] == "isolated-worker" for item in result.blocked_decision.payload["alternatives"])
    assert result.resolution.payload["status"] == "blocked"
    assert result.resolution.payload["decision_ref"]["revision"] == result.blocked_decision.revision
    assert decision.to_dict() == before_decision
    assert finding.to_dict() == before_finding


def test_missing_selected_adapter_rejects_before_persisting_partial_evidence(tmp_path: Path) -> None:
    api_modules = api()
    _modules, store, round_record, target, _work, _finding, decision = decision_context(tmp_path)
    strategy = strategy_for(api_modules, store, round_record, target)
    selection = select(
        api_modules,
        store,
        round_record,
        target,
        strategy,
        policies=[policy(evidence_standard="primary_source", failure_mode="follow_up")],
    )
    assert selection.payload["decisions"][0]["adapters"] == (
        "source_acquisition",
        "primary_source_validation",
        "evidence_review",
    )

    with pytest.raises(api_modules["InvalidAssuranceError"], match="selected adapter"):
        run(
            api_modules,
            store,
            round_record,
            selection,
            decision,
            adapters=api_modules["AssuranceAdapterSet"](),
        )

    assert not [item for item in store.load_run(round_record.id).artifacts if item.kind == "assurance-evidence"]


def test_selection_rejects_a_strategy_that_does_not_share_the_target_brief(
    tmp_path: Path,
) -> None:
    api_modules = api()
    _modules, store, round_record, target, _work, _finding, _decision = decision_context(tmp_path)
    strategy = strategy_for(api_modules, store, round_record, target)
    incompatible_payload = strategy.to_dict()["payload"]
    incompatible_payload["id"] = "strategy-mismatch"
    incompatible_payload["working_brief_id"] = "brief-mismatch"
    incompatible = store.append_artifact(
        round_record.id,
        "strategy-mismatch",
        "research-strategy",
        incompatible_payload,
        parent_refs=strategy.parent_refs,
        expected_revision=store.get_revision(round_record.id),
    )

    with pytest.raises(api_modules["InvalidAssuranceError"], match="share the exact Working Brief"):
        select(
            api_modules,
            store,
            round_record,
            target,
            incompatible,
            policies=[policy(evidence_standard="primary_source", failure_mode="follow_up")],
        )

    assert not [
        item for item in store.load_run(round_record.id).artifacts if item.kind == "assurance-adapter-selection"
    ]
