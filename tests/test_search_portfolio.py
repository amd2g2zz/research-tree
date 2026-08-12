from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_tree import (
    AdaptiveResearchPolicy,
    ArtifactRef,
    BatchCoverageAssessment,
    ContentAddressedStore,
    DurableSourceCaptureService,
    MethodBoundary,
    MethodRegistry,
    RunLedger,
    SearchPortfolio,
    SearchPortfolioComparison,
    SearchPortfolioError,
    SearchPortfolioService,
    assess_acquisition_batch,
    derive_search_portfolio,
    distinct_method_boundaries,
    validate_search_portfolio_payload,
)
from research_tree.domain import thaw_json
from research_tree.policy import DecisionSlotDeficit


def method(**overrides: object) -> MethodBoundary:
    values = {
        "method_id": "web-search",
        "provider_id": "anysearch",
        "corpus_id": "public-web",
        "boundary_kind": "search_provider",
        "permission_profile": "network-read",
        "expected_evidence_class": "secondary",
        "available": True,
        "provenance_group": "search-index:anysearch",
        "limitations": ("Search snippets require primary-source validation.",),
    }
    values.update(overrides)
    return MethodBoundary(**values)


def portfolio(**overrides: object) -> SearchPortfolio:
    values = {
        "portfolio_id": "portfolio-1",
        "intent_revision": "intent@1",
        "working_brief_revision": "brief@1",
        "strategy_revision": "strategy@1",
        "decision_slot_id": "slot-mechanism",
        "evidence_deficit": "Mechanism and implementation boundary are unresolved.",
        "authority_envelope": "confirmed technical research only",
        "subquestions": (
            {
                "subquestion_id": "sq-mechanism",
                "category": "mechanism",
                "question": "What mechanism explains the behavior?",
                "question_origin": "implicit",
                "originating_deficit": "missing mechanism",
                "expected_decision_effect": "Close mechanism evidence class.",
                "stop_or_replan_trigger": "Primary source confirms or refutes mechanism.",
            },
        ),
        "query_variants": (
            {
                "query_id": "query-1",
                "subquestion_id": "sq-mechanism",
                "originating_slot_id": "slot-mechanism",
                "query": "official architecture mechanism",
                "method_id": "web-search",
                "provider_id": "anysearch",
                "target_evidence_class": "primary",
                "expected_decision_effect": "Close mechanism evidence class.",
                "query_rewrite_reason": "method available for the originating deficit",
            },
            {
                "query_id": "query-2",
                "subquestion_id": "sq-mechanism",
                "originating_slot_id": "slot-mechanism",
                "query": "implementation source mechanism",
                "method_id": "web-search",
                "provider_id": "anysearch",
                "target_evidence_class": "primary",
                "expected_decision_effect": "Close mechanism evidence class.",
                "query_rewrite_reason": "method available for the originating deficit",
            },
        ),
        "method_boundaries": (method(),),
        "prior_acquisition_refs": ("capture-a@1",),
        "stop_criteria": ("Slot has primary mechanism evidence.",),
        "replan_triggers": ("Contradiction or shallow secondary-only evidence.",),
    }
    values.update(overrides)
    return SearchPortfolio(**values)


def assessment(**overrides: object) -> BatchCoverageAssessment:
    values = {
        "assessment_id": "assessment-1",
        "portfolio_id": "portfolio-1",
        "decision_slot_id": "slot-mechanism",
        "attempt_id": "attempt-1",
        "batch_id": "batch-1",
        "coverage": "partial",
        "novelty": "new",
        "source_depth": "snippet",
        "provenance_independence": "single_boundary",
        "contradictions": (),
        "implementation_uncertainty": "high",
        "oracle_readiness": "not_ready",
        "unresolved_decision_risk": "mechanism still underdetermined",
        "disposition": "deepen",
        "causal_refs": ("capture-a@1", "receipt-a@1", "checkpoint-a@1"),
        "next_actions": ("open-full-source",),
        "capture_refs": ("capture-a@1",),
        "receipt_refs": ("receipt-a@1",),
        "checkpoint_refs": ("checkpoint-a@1",),
    }
    values.update(overrides)
    return BatchCoverageAssessment(**values)


def test_portfolio_derives_subquestions_and_records_single_provider_boundary() -> None:
    value = derive_search_portfolio(
        portfolio_id="portfolio-1",
        intent_revision="intent@1",
        working_brief_revision="brief@1",
        strategy_revision="strategy@1",
        decision_slot_id="slot-mechanism",
        slot_question="Can the runtime close from repeated search snippets?",
        evidence_deficit="Mechanism and validation evidence are missing.",
        authority_envelope="confirmed technical research only",
        available_methods=(
            method(),
            method(
                method_id="repo-inspect",
                provider_id="git",
                corpus_id="source-tree",
                boundary_kind="repository_inspection",
                expected_evidence_class="source",
            ),
        ),
        prior_acquisition_refs=("capture-a@1",),
    )

    assert {item["category"] for item in value.to_dict()["subquestions"]} >= {"mechanism", "validation"}
    assert {item["question_origin"] for item in value.to_dict()["subquestions"]} >= {"explicit", "implicit"}
    assert value.query_variants[0]["originating_slot_id"] == "slot-mechanism"
    assert distinct_method_boundaries(value.method_boundaries) == (
        "repository_inspection:git:source-tree:default:repository_inspection:git:source-tree:search-index:anysearch",
        "search_provider:anysearch:public-web:default:search_provider:anysearch:public-web:search-index:anysearch",
    )
    assert value.query_variants[0]["expected_decision_effect"]


def test_repeated_queries_do_not_satisfy_independent_method_boundary() -> None:
    value = portfolio()

    assert len(value.query_variants) == 2
    assert distinct_method_boundaries(value.method_boundaries) == (
        "search_provider:anysearch:public-web:default:search_provider:anysearch:public-web:search-index:anysearch",
    )
    assert not value.satisfies_independent_methods(required=2)


def test_query_variants_cannot_cross_subquestion_or_decision_slot_lineage() -> None:
    with pytest.raises(SearchPortfolioError, match="subquestion_id"):
        portfolio(query_variants=({**portfolio().query_variants[0], "subquestion_id": "missing-question"},))
    with pytest.raises(SearchPortfolioError, match="originating_slot_id"):
        portfolio(query_variants=({**portfolio().query_variants[0], "originating_slot_id": "slot-other"},))


def test_degraded_capability_records_limitations_and_fallback() -> None:
    unavailable = method(available=False, limitation_code="unavailable", fallback_method_id="repo-inspect")
    value = portfolio(
        method_boundaries=(
            unavailable,
            method(
                method_id="repo-inspect",
                provider_id="git",
                corpus_id="source-tree",
                boundary_kind="repository_inspection",
            ),
        )
    )

    degraded = value.degraded_methods()

    assert degraded == ("web-search",)
    assert value.method_boundaries[0].fallback_method_id == "repo-inspect"


def test_method_registry_records_selection_capability_and_explicit_failure_boundary() -> None:
    registry = MethodRegistry(
        version="method-registry-v1",
        boundaries=(
            method(
                available=False,
                limitation_code="rate_limited",
                fallback_method_id="repo-inspect",
                invocation_adapter="host-web-search",
                output_schema="source-capture-v1",
                timeout_seconds=15,
                retryable=True,
                retry_limit=2,
                extraction_path="html-extractor-v1",
                failure_boundary="network:anysearch",
            ),
            method(
                method_id="repo-inspect",
                provider_id="git",
                corpus_id="source-tree",
                boundary_kind="repository_inspection",
                expected_evidence_class="source",
                available=True,
                invocation_adapter="local-repository-read",
                output_schema="source-capture-v1",
                timeout_seconds=5,
                extraction_path="line-symbol-v1",
                failure_boundary="filesystem:workspace",
            ),
        ),
    )

    value = derive_search_portfolio(
        portfolio_id="portfolio-registry",
        intent_revision="intent@1",
        working_brief_revision="brief@1",
        strategy_revision="strategy@1",
        decision_slot_id="slot-mechanism",
        slot_question="Which mechanism is decisive?",
        evidence_deficit="The network source is rate limited.",
        authority_envelope="confirmed technical research only",
        available_methods=registry,
    )

    assert value.method_registry_version == "method-registry-v1"
    assert value.query_variants[0]["method_id"] == "repo-inspect"
    selection = value.to_dict()["method_selection"][0]
    assert selection["status"] == "rejected"
    assert selection["invocation_adapter"] == "host-web-search"
    assert selection["failure_boundary"] == "network:anysearch"


def test_unavailable_boundaries_do_not_count_as_independent_or_available_fallbacks() -> None:
    unavailable = method(
        available=False,
        limitation_code="rate_limited",
        fallback_method_id="also-unavailable",
        failure_boundary="network:anysearch",
    )
    also_unavailable = method(
        method_id="also-unavailable",
        provider_id="docs",
        corpus_id="docs-index",
        boundary_kind="documentation_lookup",
        available=False,
        limitation_code="permission_limited",
        failure_boundary="permission:docs",
    )
    value = portfolio(method_boundaries=(unavailable, also_unavailable))

    assert not value.satisfies_independent_methods(required=1)
    selection = value.to_dict()["method_selection"][0]
    assert selection["alternate_evidence_class"] is None


def test_assessment_requires_real_strategy_revisions_for_direction_pivot() -> None:
    with pytest.raises(SearchPortfolioError, match="contradiction requires"):
        assess_acquisition_batch(
            assessment_id="assessment-pivot-missing",
            portfolio_id="portfolio-1",
            decision_slot_id="slot-mechanism",
            attempt_id="attempt-pivot",
            batch_id="batch-pivot",
            coverage="complete",
            novelty="new",
            source_depth="full_source",
            provenance_independence="independent",
            contradictions=("the starting premise is false",),
            implementation_uncertainty="low",
            oracle_readiness="ready",
            unresolved_decision_risk="strategy premise is invalid",
            causal_refs=("capture-a@1", "receipt-a@1", "checkpoint-a@1"),
            capture_refs=("capture-a@1",),
            receipt_refs=("receipt-a@1",),
            checkpoint_refs=("checkpoint-a@1",),
        )


def test_hidden_material_and_authority_expanding_pivots_are_rejected() -> None:
    with pytest.raises(SearchPortfolioError, match="hidden"):
        portfolio(
            subquestions=(
                {
                    "subquestion_id": "sq",
                    "category": "mechanism",
                    "question": "q",
                    "originating_deficit": "d",
                    "expected_decision_effect": "e",
                    "stop_or_replan_trigger": "t",
                    "private_prompt": "secret",
                },
            )
        )

    with pytest.raises(SearchPortfolioError, match="authority"):
        assessment(disposition="pivot", authority_disposition="expands_requester_outcome")


def test_shallow_batch_deepens_and_binds_capture_checkpoint_lineage() -> None:
    value = assessment()

    assert value.disposition == "deepen"
    assert value.requires_deeper_work is True
    assert value.capture_refs == ("capture-a@1",)
    assert value.receipt_refs == ("receipt-a@1",)
    assert value.checkpoint_refs == ("checkpoint-a@1",)


def test_contradiction_pivot_preserves_successor_lineage_inside_authority() -> None:
    value = assessment(
        source_depth="full_source",
        contradictions=("strategy premise is false",),
        disposition="pivot",
        authority_disposition="inside_confirmed_authority",
        superseded_strategy_revision="strategy@1",
        successor_strategy_revision="strategy@2",
        next_actions=("create-successor-strategy",),
    )

    assert value.disposition == "pivot"
    assert value.superseded_strategy_revision == "strategy@1"
    assert value.successor_strategy_revision == "strategy@2"


def test_batch_assessment_projects_depth_and_contradiction_for_policy_without_authority() -> None:
    shallow = assess_acquisition_batch(
        assessment_id="assessment-2",
        portfolio_id="portfolio-1",
        decision_slot_id="slot-mechanism",
        attempt_id="attempt-3",
        batch_id="batch-2",
        coverage="partial",
        novelty="new",
        source_depth="snippet",
        provenance_independence="single_boundary",
        contradictions=(),
        implementation_uncertainty="high",
        oracle_readiness="not_ready",
        unresolved_decision_risk="mechanism remains open",
        causal_refs=("capture-a@1",),
        capture_refs=("capture-a@1",),
        receipt_refs=("receipt-a@1",),
        checkpoint_refs=("checkpoint-a@1",),
    )
    pivot = assess_acquisition_batch(
        assessment_id="assessment-3",
        portfolio_id="portfolio-1",
        decision_slot_id="slot-mechanism",
        attempt_id="attempt-failed",
        batch_id="batch-3",
        coverage="complete",
        novelty="new",
        source_depth="full_source",
        provenance_independence="independent",
        contradictions=("starting premise is false",),
        implementation_uncertainty="low",
        oracle_readiness="ready",
        unresolved_decision_risk="strategy premise invalidated",
        causal_refs=("capture-b@1",),
        capture_refs=("capture-b@1",),
        receipt_refs=("receipt-b@1",),
        checkpoint_refs=("checkpoint-b@1",),
        superseded_strategy_revision="strategy@1",
        successor_strategy_revision="strategy@2",
    )

    assert shallow.policy_input()["requires_deeper_work"] is True
    assert shallow.disposition == "deepen"
    assert pivot.disposition == "pivot"
    assert pivot.successor_strategy_revision == "strategy@2"


def test_failed_retrieval_broadens_or_blocks_with_explicit_unavailable_lineage() -> None:
    broadened = assess_acquisition_batch(
        assessment_id="assessment-failed",
        portfolio_id="portfolio-1",
        decision_slot_id="slot-mechanism",
        attempt_id="attempt-blocked",
        batch_id="batch-failed",
        coverage="none",
        novelty="none",
        source_depth="none",
        provenance_independence="none",
        contradictions=(),
        implementation_uncertainty="unknown",
        oracle_readiness="not_ready",
        unresolved_decision_risk="primary source remains unavailable",
        causal_refs=("receipt-failed@1", "checkpoint-failed@1"),
        capture_refs=(),
        receipt_refs=("receipt-failed@1",),
        checkpoint_refs=("checkpoint-failed@1",),
        evidence_disposition="failed_retrieval",
        alternate_method_available=True,
    )
    blocked = assess_acquisition_batch(
        assessment_id="assessment-blocked",
        portfolio_id="portfolio-1",
        decision_slot_id="slot-mechanism",
        attempt_id="attempt-blocked",
        batch_id="batch-blocked",
        coverage="none",
        novelty="none",
        source_depth="none",
        provenance_independence="none",
        contradictions=(),
        implementation_uncertainty="unknown",
        oracle_readiness="not_ready",
        unresolved_decision_risk="no permitted evidence method remains",
        causal_refs=("receipt-blocked@1", "checkpoint-blocked@1"),
        capture_refs=(),
        receipt_refs=("receipt-blocked@1",),
        checkpoint_refs=("checkpoint-blocked@1",),
        evidence_disposition="permission_limited",
        alternate_method_available=False,
    )

    assert (broadened.disposition, broadened.evidence_disposition) == ("broaden", "failed_retrieval")
    assert blocked.disposition == "blocked"
    assert blocked.next_actions == ("record-typed-blocker",)
    policy = AdaptiveResearchPolicy(seed=83).evaluate(
        slots=(
            DecisionSlotDeficit(
                slot_id="slot-mechanism",
                question="Which mechanism is decisive?",
                closure_oracle="independent evidence bounds the mechanism",
            ),
        ),
        portfolio_assessments=(broadened.policy_input(),),
    )
    assert policy.proposals[0].kind == "method_switch"


def test_policy_rejects_unbound_or_incomplete_portfolio_assessment() -> None:
    with pytest.raises(ValueError, match="portfolio assessment is incomplete"):
        AdaptiveResearchPolicy(seed=83).evaluate(
            slots=(
                DecisionSlotDeficit(
                    slot_id="slot-mechanism",
                    question="Which mechanism is decisive?",
                    closure_oracle="independent evidence bounds the mechanism",
                ),
            ),
            portfolio_assessments=(
                {
                    "portfolio_id": "portfolio-1",
                    "decision_slot_id": "slot-mechanism",
                    "disposition": "deepen",
                    "causal_refs": ("capture-a@1",),
                },
            ),
        )


def _append(
    ledger: RunLedger,
    run_id: str,
    artifact_id: str,
    kind: str,
    payload: dict[str, object],
    parents: tuple[ArtifactRef, ...] = (),
):
    return ledger.append_artifact(
        run_id,
        artifact_id,
        kind,
        payload,
        parent_refs=parents,
        expected_revision=ledger.get_revision(run_id),
    )


def _portfolio_lineage(tmp_path):
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-83")
    intent = _append(
        ledger,
        "run-83",
        "intent-1",
        "intent-model",
        {
            "task_id": "task-1",
            "desired_outcomes": ["Preserve a safe migration path"],
            "hypotheses": [
                {
                    "status": "leading",
                    "interpretation": "The migration boundary is decisive.",
                    "decision_consequence": "Choose the supported migration path.",
                }
            ],
        },
    )
    brief = _append(
        ledger,
        "run-83",
        "brief-1",
        "working-brief",
        {
            "intent_model_id": "intent-1",
            "task_id": "task-1",
            "working_interpretation": "Validate the repository migration boundary.",
            "technical_outcome": "Produce an evidence-backed migration recommendation.",
            "retained_hard_constraints": ["Do not expand requester authority."],
        },
        (ArtifactRef("run-83", intent.id, intent.revision),),
    )
    target = _append(
        ledger,
        "run-83",
        "target-1",
        "blueprint-target",
        {
            "slots": [
                {
                    "id": "slot-mechanism",
                    "question": "Which migration mechanism is decisive?",
                    "bounded_research_need": "Confirm the mechanism and implementation boundary.",
                    "closure_rule": "Primary source and bounded validation agree.",
                }
            ]
        },
        (
            ArtifactRef("run-83", brief.id, brief.revision),
            ArtifactRef("run-83", intent.id, intent.revision),
        ),
    )
    strategy = _append(
        ledger,
        "run-83",
        "strategy-1",
        "strategy-projection",
        {
            "autonomy_envelope": {"allowed": ["research"]},
            "current_understanding": "Inspect the migration mechanism.",
            "method_hypotheses": [{"method": "repository inspection"}],
        },
        (ArtifactRef("run-83", target.id, target.revision),),
    )
    return ledger, intent, brief, target, strategy


def test_service_persists_portfolio_with_exact_intent_brief_strategy_and_slot_lineage(tmp_path) -> None:
    ledger, intent, brief, target, strategy = _portfolio_lineage(tmp_path)
    prior = _append(ledger, "run-83", "receipt-1", "acquisition-receipt", {"status": "succeeded"})
    service = SearchPortfolioService(ledger)

    artifact = service.plan(
        run_id="run-83",
        portfolio_id="portfolio-1",
        intent_model=intent,
        working_brief=brief,
        strategy=strategy,
        decision_map=target,
        slot=DecisionSlotDeficit(
            slot_id="slot-mechanism",
            question="Which migration mechanism is decisive?",
            closure_oracle="primary source and a bounded validation agree",
            missing_dimensions=("mechanism", "implementation", "validation"),
        ),
        authority_envelope="confirmed technical research only",
        available_methods=(
            method(available=False, limitation_code="unavailable", fallback_method_id="repo-inspect"),
            method(
                method_id="repo-inspect",
                provider_id="git",
                corpus_id="source-tree",
                boundary_kind="repository_inspection",
                expected_evidence_class="source",
            ),
        ),
        prior_acquisition_refs=(prior,),
        expected_revision=ledger.get_revision("run-83"),
    )

    assert artifact.kind == "search-portfolio"
    assert artifact.payload["run_id"] == "run-83"
    assert artifact.payload["lineage"]["intent_model_ref"] == ArtifactRef("run-83", "intent-1", 1).to_dict()
    assert artifact.payload["lineage"]["strategy_ref"] == ArtifactRef("run-83", "strategy-1", 1).to_dict()
    registry_ref = ArtifactRef.from_dict(artifact.payload["lineage"]["method_registry_ref"])
    registry_artifact = ledger.get_artifact(registry_ref)
    assert registry_artifact.kind == "method-registry"
    assert registry_ref in artifact.parent_refs
    assert artifact.payload["method_registry_digest"] == registry_artifact.payload["digest"]
    assert artifact.payload["prior_acquisition_refs"] == ("receipt-1@1",)
    assert artifact.payload["query_variants"][0]["method_id"] == "repo-inspect"
    assert ArtifactRef("run-83", prior.id, prior.revision) in artifact.parent_refs
    assert {item["category"] for item in artifact.payload["subquestions"]} >= {
        "mechanism",
        "implementation",
        "validation",
    }
    assert "safe migration path" in artifact.payload["query_variants"][0]["query"].lower()
    rejected = next(item for item in artifact.payload["method_selection"] if item["method_id"] == "web-search")
    assert rejected["status"] == "rejected"
    assert rejected["fallback_method_id"] == "repo-inspect"
    root = Path(__file__).resolve().parents[1]
    schema = json.loads(
        (
            root / "openspec" / "changes" / "unify-research-runtime-alpha2" / "schemas" / "search-portfolio-v1.json"
        ).read_text(encoding="utf-8")
    )
    assert schema["$id"].endswith("search-portfolio-v1.json")
    assert set(schema["required"]) == set(artifact.payload)
    assert schema["properties"]["status"]["enum"] == ["active", "blocked"]
    assert set(schema["$defs"]["subquestion"]["required"]) == set(artifact.payload["subquestions"][0])
    assert set(schema["$defs"]["queryVariant"]["required"]) == set(artifact.payload["query_variants"][0])
    assert set(schema["$defs"]["methodBoundary"]["required"]) == set(artifact.payload["method_boundaries"][0])
    assert set(schema["$defs"]["methodSelection"]["required"]) == set(artifact.payload["method_selection"][0])
    invalid_payload = thaw_json(artifact.payload)
    invalid_payload["run_id"] = 83
    with pytest.raises(SearchPortfolioError, match="run_id"):
        validate_search_portfolio_payload(invalid_payload, run_id="run-83")
    invalid_payload = thaw_json(artifact.payload)
    invalid_payload["subquestions"] = [{}]
    with pytest.raises(SearchPortfolioError, match="subquestions"):
        validate_search_portfolio_payload(invalid_payload, run_id="run-83")


def test_registered_method_identity_rejects_same_name_with_different_boundaries(tmp_path) -> None:
    ledger, intent, brief, target, strategy = _portfolio_lineage(tmp_path)
    service = SearchPortfolioService(ledger)
    registered = MethodRegistry(
        registry_id="registered-methods",
        version="method-registry-v1",
        boundaries=(method(failure_boundary="network:anysearch"),),
    )
    registry_artifact = service.register_methods(
        run_id="run-83",
        registry=registered,
        expected_revision=ledger.get_revision("run-83"),
    )
    altered = MethodRegistry(
        registry_id="registered-methods",
        version="method-registry-v1",
        boundaries=(method(failure_boundary="network:other-index"),),
    )

    with pytest.raises(SearchPortfolioError, match="does not match"):
        service.plan(
            run_id="run-83",
            portfolio_id="portfolio-mismatched-registry",
            intent_model=intent,
            working_brief=brief,
            strategy=strategy,
            decision_map=target,
            slot=DecisionSlotDeficit(
                slot_id="slot-mechanism",
                question="Which migration mechanism is decisive?",
                closure_oracle="primary source and a bounded validation agree",
            ),
            authority_envelope="confirmed technical research only",
            available_methods=altered,
            method_registry=registry_artifact,
            expected_revision=ledger.get_revision("run-83"),
        )


def test_service_rejects_stale_lineage_and_unbound_batch_artifacts(tmp_path) -> None:
    ledger, intent, brief, target, strategy = _portfolio_lineage(tmp_path)
    service = SearchPortfolioService(ledger)
    portfolio_artifact = service.plan(
        run_id="run-83",
        portfolio_id="portfolio-1",
        intent_model=intent,
        working_brief=brief,
        strategy=strategy,
        decision_map=target,
        slot=DecisionSlotDeficit(
            slot_id="slot-mechanism",
            question="Which migration mechanism is decisive?",
            closure_oracle="primary source and a bounded validation agree",
        ),
        authority_envelope="confirmed technical research only",
        available_methods=(method(),),
        expected_revision=ledger.get_revision("run-83"),
    )
    capture = _append(ledger, "run-83", "capture-1", "source-capture", {"status": "committed"})
    receipt = _append(ledger, "run-83", "receipt-1", "acquisition-receipt", {"status": "succeeded"})
    checkpoint = _append(ledger, "run-83", "checkpoint-1", "analysis-checkpoint", {"status": "saved"})
    with pytest.raises(SearchPortfolioError, match="capture artifact lacks attempt_id"):
        service.record_assessment(
            run_id="run-83",
            assessment=assessment(
                portfolio_id="portfolio-1",
                decision_slot_id="slot-mechanism",
                causal_refs=("capture-1@1", "receipt-1@1", "checkpoint-1@1"),
                capture_refs=("capture-1@1",),
                receipt_refs=("receipt-1@1",),
                checkpoint_refs=("checkpoint-1@1",),
            ),
            portfolio_ref=ArtifactRef("run-83", portfolio_artifact.id, portfolio_artifact.revision),
            capture_artifacts=(capture,),
            receipt_artifacts=(receipt,),
            checkpoint_artifacts=(checkpoint,),
            expected_revision=ledger.get_revision("run-83"),
        )

    newer_intent = _append(ledger, "run-83", "intent-1", "intent-model", {"task_id": "task-1", "revision": 2})
    with pytest.raises(SearchPortfolioError, match="stale"):
        service.plan(
            run_id="run-83",
            portfolio_id="portfolio-2",
            intent_model=intent,
            working_brief=brief,
            strategy=strategy,
            decision_map=target,
            slot=DecisionSlotDeficit(
                slot_id="slot-mechanism",
                question="Which migration mechanism is decisive?",
                closure_oracle="primary source and a bounded validation agree",
            ),
            authority_envelope="confirmed technical research only",
            available_methods=(method(),),
            expected_revision=ledger.get_revision("run-83"),
        )
    assert newer_intent.revision == 2


def test_service_resumes_real_capture_receipt_and_checkpoint_without_reacquisition(tmp_path) -> None:
    ledger, intent, brief, target, strategy = _portfolio_lineage(tmp_path)
    portfolio_service = SearchPortfolioService(ledger)
    portfolio_artifact = portfolio_service.plan(
        run_id="run-83",
        portfolio_id="portfolio-resume",
        intent_model=intent,
        working_brief=brief,
        strategy=strategy,
        decision_map=target,
        slot=DecisionSlotDeficit(
            slot_id="slot-mechanism",
            question="Which migration mechanism is decisive?",
            closure_oracle="primary source and a bounded validation agree",
        ),
        authority_envelope="confirmed technical research only",
        available_methods=(method(),),
        expected_revision=ledger.get_revision("run-83"),
    )
    capture_service = DurableSourceCaptureService(ledger, ContentAddressedStore(tmp_path))
    capture = capture_service.capture(
        run_id="run-83",
        capture_id="capture-resume",
        attempt_id="attempt-resume",
        data=b"captured primary source",
        media_type="text/plain",
        method_id="web-search",
        provider_id="anysearch",
        expected_revision=ledger.get_revision("run-83"),
    )
    capture_service.receipt(
        run_id="run-83",
        receipt_id="receipt-resume",
        capture=capture,
        attempt_id="attempt-resume",
        method_id="web-search",
        provider_id="anysearch",
        expected_revision=ledger.get_revision("run-83"),
    )
    capture_service.checkpoint(
        run_id="run-83",
        checkpoint_id="checkpoint-resume",
        attempt_id="attempt-resume",
        action_id="assess-resume",
        source_capture_refs=(capture.artifact_ref,),
        facts=({"claim": "the capture is committed"},),
        expected_revision=ledger.get_revision("run-83"),
    )

    resumed = capture_service.resume("run-83", "attempt-resume")
    recorded = portfolio_service.record_assessment(
        run_id="run-83",
        assessment=assessment(
            assessment_id="assessment-resume",
            portfolio_id="portfolio-resume",
            decision_slot_id="slot-mechanism",
            attempt_id="attempt-resume",
            causal_refs=("capture-resume@1", "receipt-resume@1", "checkpoint-resume@1"),
            capture_refs=("capture-resume@1",),
            receipt_refs=("receipt-resume@1",),
            checkpoint_refs=("checkpoint-resume@1",),
        ),
        portfolio_ref=ArtifactRef("run-83", portfolio_artifact.id, portfolio_artifact.revision),
        capture_artifacts=(ledger.get_artifact(resumed.capture.artifact_ref),),
        receipt_artifacts=(ledger.get_artifact(resumed.receipt.artifact_ref),),
        checkpoint_artifacts=(ledger.get_artifact(resumed.checkpoint.artifact_ref),),
        expected_revision=ledger.get_revision("run-83"),
    )

    assert recorded.kind == "batch-coverage-assessment"
    assert {reference.artifact_id for reference in recorded.parent_refs} >= {
        "capture-resume",
        "receipt-resume",
        "checkpoint-resume",
    }


def test_all_unavailable_methods_persist_blocked_plan_with_rejected_trace(tmp_path) -> None:
    ledger, intent, brief, target, strategy = _portfolio_lineage(tmp_path)
    artifact = SearchPortfolioService(ledger).plan(
        run_id="run-83",
        portfolio_id="portfolio-blocked",
        intent_model=intent,
        working_brief=brief,
        strategy=strategy,
        decision_map=target,
        slot=DecisionSlotDeficit(
            slot_id="slot-mechanism",
            question="Which migration mechanism is decisive?",
            closure_oracle="primary source and a bounded validation agree",
        ),
        authority_envelope="confirmed technical research only",
        available_methods=MethodRegistry(
            version="method-registry-v1",
            boundaries=(
                method(
                    available=False,
                    limitation_code="permission_limited",
                    invocation_adapter="host-web-search",
                    failure_boundary="permission:host-web-search",
                ),
            ),
        ),
        expected_revision=ledger.get_revision("run-83"),
    )

    assert artifact.payload["status"] == "blocked"
    assert artifact.payload["method_capability"]["blocking_reason"] == "no_available_method_boundary"
    assert artifact.payload["query_variants"]
    assert artifact.payload["method_selection"][0]["status"] == "rejected"


def test_prior_failed_outcome_rewrites_query_and_single_backend_is_degraded(tmp_path) -> None:
    ledger, intent, brief, target, strategy = _portfolio_lineage(tmp_path)
    failed = _append(
        ledger,
        "run-83",
        "receipt-prior-failed",
        "acquisition-receipt",
        {"attempt_id": "attempt-prior", "status": "failed"},
    )
    artifact = SearchPortfolioService(ledger).plan(
        run_id="run-83",
        portfolio_id="portfolio-prior-outcome",
        intent_model=intent,
        working_brief=brief,
        strategy=strategy,
        decision_map=target,
        slot=DecisionSlotDeficit(
            slot_id="slot-mechanism",
            question="Which migration mechanism is decisive?",
            closure_oracle="primary source and a bounded validation agree",
        ),
        authority_envelope="confirmed technical research only",
        available_methods=(method(),),
        prior_acquisition_refs=(failed,),
        expected_revision=ledger.get_revision("run-83"),
    )

    assert "prior receipt failed" in artifact.payload["query_variants"][0]["query"]
    assert "prior acquisition outcome" in artifact.payload["query_variants"][0]["query_rewrite_reason"]
    assert artifact.payload["method_capability"]["degraded"] is True


def test_controlled_legacy_comparison_publishes_only_explicit_deltas_and_limits() -> None:
    comparison = SearchPortfolioComparison(
        comparison_id="legacy-direct-query-v1",
        shared_input_digest="a" * 64,
        legacy_rediscovery_count=3,
        portfolio_rediscovery_count=1,
        legacy_coverage=0.25,
        portfolio_coverage=0.75,
        legacy_depth=1,
        portfolio_depth=3,
        legacy_closed=False,
        portfolio_closed=True,
        limitations=("Static fixture; it does not claim provider-live causality.",),
    )

    assert comparison.to_dict()["deltas"] == {
        "rediscovery": -2,
        "coverage": 0.5,
        "depth": 2,
        "decision_closure": 1,
    }


def test_controlled_comparison_fixture_matches_runtime_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = json.loads(
        (
            root
            / "openspec"
            / "changes"
            / "add-intent-derived-search-portfolios"
            / "evidence"
            / "legacy-direct-query-comparison-v1.json"
        ).read_text(encoding="utf-8")
    )
    comparison = SearchPortfolioComparison(
        comparison_id=payload["comparison_id"],
        shared_input_digest=payload["shared_input_digest"],
        legacy_rediscovery_count=payload["legacy"]["rediscovery_count"],
        portfolio_rediscovery_count=payload["portfolio"]["rediscovery_count"],
        legacy_coverage=payload["legacy"]["coverage"],
        portfolio_coverage=payload["portfolio"]["coverage"],
        legacy_depth=payload["legacy"]["depth"],
        portfolio_depth=payload["portfolio"]["depth"],
        legacy_closed=payload["legacy"]["closed"],
        portfolio_closed=payload["portfolio"]["closed"],
        limitations=tuple(payload["limitations"]),
    )

    assert comparison.to_dict()["deltas"] == payload["deltas"]
    assert payload["release_manifest_link"] == "evaluation/results/alpha2-release-candidate-v1.json"


def test_failed_receipt_and_checkpoint_persist_a_captureless_assessment(tmp_path) -> None:
    ledger, intent, brief, target, strategy = _portfolio_lineage(tmp_path)
    portfolio_service = SearchPortfolioService(ledger)
    portfolio_artifact = portfolio_service.plan(
        run_id="run-83",
        portfolio_id="portfolio-failed",
        intent_model=intent,
        working_brief=brief,
        strategy=strategy,
        decision_map=target,
        slot=DecisionSlotDeficit(
            slot_id="slot-mechanism",
            question="Which migration mechanism is decisive?",
            closure_oracle="primary source and a bounded validation agree",
        ),
        authority_envelope="confirmed technical research only",
        available_methods=(method(),),
        expected_revision=ledger.get_revision("run-83"),
    )
    capture_service = DurableSourceCaptureService(ledger, ContentAddressedStore(tmp_path))
    receipt = capture_service.receipt(
        run_id="run-83",
        receipt_id="receipt-failed",
        attempt_id="attempt-failed",
        method_id="web-search",
        provider_id="anysearch",
        status="failed",
        failure_history=({"code": "http_404", "at": "2026-08-12T00:00:00+00:00"},),
        expected_revision=ledger.get_revision("run-83"),
    )
    checkpoint = capture_service.checkpoint(
        run_id="run-83",
        checkpoint_id="checkpoint-failed",
        attempt_id="attempt-failed",
        action_id="assess-failed",
        source_capture_refs=(),
        facts=(),
        method_outcomes=({"method_id": "web-search", "status": "failed"},),
        next_actions=("switch-to-alternate-method",),
        expected_revision=ledger.get_revision("run-83"),
    )
    assessment_value = assess_acquisition_batch(
        assessment_id="assessment-failed-real",
        portfolio_id="portfolio-failed",
        decision_slot_id="slot-mechanism",
        attempt_id="attempt-failed",
        batch_id="batch-failed",
        coverage="none",
        novelty="none",
        source_depth="none",
        provenance_independence="none",
        contradictions=(),
        implementation_uncertainty="unknown",
        oracle_readiness="not_ready",
        unresolved_decision_risk="source was not found",
        causal_refs=("receipt-failed@1", "checkpoint-failed@1"),
        capture_refs=(),
        receipt_refs=("receipt-failed@1",),
        checkpoint_refs=("checkpoint-failed@1",),
        evidence_disposition="http_404",
        alternate_method_available=True,
    )

    recorded = portfolio_service.record_assessment(
        run_id="run-83",
        assessment=assessment_value,
        portfolio_ref=ArtifactRef("run-83", portfolio_artifact.id, portfolio_artifact.revision),
        capture_artifacts=(),
        receipt_artifacts=(ledger.get_artifact(receipt.artifact_ref),),
        checkpoint_artifacts=(ledger.get_artifact(checkpoint.artifact_ref),),
        expected_revision=ledger.get_revision("run-83"),
    )

    assert recorded.payload["assessment"]["disposition"] == "broaden"
    assert recorded.payload["assessment"]["evidence_disposition"] == "http_404"


def test_pivot_assessment_requires_exact_persisted_successor_lineage(tmp_path) -> None:
    ledger, intent, brief, target, strategy = _portfolio_lineage(tmp_path)
    service = SearchPortfolioService(ledger)
    portfolio_artifact = service.plan(
        run_id="run-83",
        portfolio_id="portfolio-pivot",
        intent_model=intent,
        working_brief=brief,
        strategy=strategy,
        decision_map=target,
        slot=DecisionSlotDeficit(
            slot_id="slot-mechanism",
            question="Which migration mechanism is decisive?",
            closure_oracle="primary source and a bounded validation agree",
        ),
        authority_envelope="confirmed technical research only",
        available_methods=(method(),),
        expected_revision=ledger.get_revision("run-83"),
    )
    capture_service = DurableSourceCaptureService(ledger, ContentAddressedStore(tmp_path))
    capture = capture_service.capture(
        run_id="run-83",
        capture_id="capture-pivot",
        attempt_id="attempt-pivot",
        data=b"contradictory evidence",
        media_type="text/plain",
        method_id="web-search",
        provider_id="anysearch",
        expected_revision=ledger.get_revision("run-83"),
    )
    receipt = capture_service.receipt(
        run_id="run-83",
        receipt_id="receipt-pivot",
        capture=capture,
        attempt_id="attempt-pivot",
        method_id="web-search",
        provider_id="anysearch",
        expected_revision=ledger.get_revision("run-83"),
    )
    checkpoint = capture_service.checkpoint(
        run_id="run-83",
        checkpoint_id="checkpoint-pivot",
        attempt_id="attempt-pivot",
        action_id="assess-pivot",
        source_capture_refs=(capture.artifact_ref,),
        facts=({"claim": "premise is contradicted"},),
        contradictions=("starting premise is false",),
        expected_revision=ledger.get_revision("run-83"),
    )
    successor = _append(
        ledger,
        "run-83",
        "strategy-1",
        "strategy-projection",
        {"current_understanding": "follow contradictory evidence"},
        (ArtifactRef("run-83", strategy.id, strategy.revision),),
    )
    pivot = assess_acquisition_batch(
        assessment_id="assessment-pivot-real",
        portfolio_id="portfolio-pivot",
        decision_slot_id="slot-mechanism",
        attempt_id="attempt-pivot",
        batch_id="batch-pivot",
        coverage="complete",
        novelty="new",
        source_depth="full_source",
        provenance_independence="independent",
        contradictions=("starting premise is false",),
        implementation_uncertainty="low",
        oracle_readiness="ready",
        unresolved_decision_risk="starting strategy is invalid",
        causal_refs=("capture-pivot@1", "receipt-pivot@1", "checkpoint-pivot@1"),
        capture_refs=("capture-pivot@1",),
        receipt_refs=("receipt-pivot@1",),
        checkpoint_refs=("checkpoint-pivot@1",),
        superseded_strategy_revision="strategy-1@1",
        successor_strategy_revision="strategy-1@2",
    )

    recorded = service.record_assessment(
        run_id="run-83",
        assessment=pivot,
        portfolio_ref=ArtifactRef("run-83", portfolio_artifact.id, portfolio_artifact.revision),
        capture_artifacts=(ledger.get_artifact(capture.artifact_ref),),
        receipt_artifacts=(ledger.get_artifact(receipt.artifact_ref),),
        checkpoint_artifacts=(ledger.get_artifact(checkpoint.artifact_ref),),
        successor_strategy=successor,
        expected_revision=ledger.get_revision("run-83"),
    )

    assert ArtifactRef("run-83", successor.id, successor.revision) in recorded.parent_refs
