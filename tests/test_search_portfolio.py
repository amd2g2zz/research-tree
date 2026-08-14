from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_tree import (
    ACQUISITION_DISPOSITIONS,
    AdaptiveResearchPolicy,
    ArtifactRef,
    BATCH_DECISIONS,
    BatchCoverageAssessment,
    ContentAddressedStore,
    DurableSourceCaptureService,
    IntentDerivedSearchPortfolioPlanner,
    InvalidSearchPortfolioError,
    MethodExecutionOutcome,
    MethodRegistration,
    MethodRegistry,
    MethodSelection,
    PortfolioBatch,
    SearchPortfolioExecutor,
    SearchPortfolioService,
    RunLedger,
    ReassessmentPolicy,
    RejectedMethod,
    SearchPortfolio,
    Subquestion,
    assess_acquisition_batch,
)
from test_adaptive_policy import slot as policy_slot


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "openspec" / "changes" / "unify-research-runtime-alpha2" / "schemas"


def registration(
    method_id: str,
    provider_id: str,
    *,
    availability: str = "available",
    degradation_reason: str | None = None,
) -> MethodRegistration:
    return MethodRegistration(
        method_id=method_id,
        provider_id=provider_id,
        capability="web-search",
        failure_boundary=f"{provider_id}-boundary",
        availability=availability,
        degradation_reason=degradation_reason,
    )


def registry(*registrations: MethodRegistration) -> MethodRegistry:
    return MethodRegistry(registry_id="registry-1", registrations=registrations)


def selection(method_id: str, provider_id: str, *query_refs: str) -> MethodSelection:
    return MethodSelection(
        method_id=method_id,
        provider_id=provider_id,
        failure_boundary=f"{provider_id}-boundary",
        query_refs=query_refs,
        selection_reason="primary-coverage",
    )


def portfolio(
    *,
    portfolio_id: str = "portfolio-1",
    run_id: str = "run-1",
    slot_id: str = "slot-1",
    intent_revision: str = "intent-1",
    brief_revision: str = "brief-1",
    selected_methods: tuple[MethodSelection, ...] = (selection("web-search", "provider-a", "query-1"),),
    rejected_methods: tuple[RejectedMethod, ...] = (
        RejectedMethod(
            method_id="repository-inspection",
            provider_id="provider-b",
            rejection_reason="not-needed",
        ),
    ),
) -> SearchPortfolio:
    return SearchPortfolio(
        portfolio_id=portfolio_id,
        run_id=run_id,
        slot_id=slot_id,
        intent_revision=intent_revision,
        brief_revision=brief_revision,
        subquestions=(
            Subquestion(
                subquestion_id="question-1",
                text="What mechanism is implicit?",
                kind="implicit",
                decision_impact="p1",
            ),
        ),
        selected_methods=selected_methods,
        rejected_methods=rejected_methods,
        reassessment_policy=ReassessmentPolicy(
            after_batch=True,
            allowed_dispositions=("validate", "deepen"),
        ),
        status="active",
    )


def test_typed_portfolio_round_trips_canonically_without_raw_query_material() -> None:
    value = portfolio(
        selected_methods=(
            selection("documentation", "provider-c", "query-3"),
            selection("web-search", "provider-a", "query-2", "query-1"),
        ),
        rejected_methods=(
            RejectedMethod(
                method_id="repository-inspection",
                provider_id="provider-b",
                rejection_reason="not-needed",
            ),
            RejectedMethod(
                method_id="scholarly-search",
                provider_id="provider-d",
                rejection_reason="budget-limited",
            ),
        ),
    )

    payload = value.to_dict()

    assert SearchPortfolio.from_dict(payload) == value
    assert value.canonical_json_bytes() == SearchPortfolio.from_dict(payload).canonical_json_bytes()
    assert payload["selected_methods"][0]["method_id"] == "documentation"
    assert payload["selected_methods"][1]["query_refs"] == ["query-1", "query-2"]
    assert payload["reassessment_policy"]["allowed_dispositions"] == ["deepen", "validate"]
    assert b"raw_query" not in value.canonical_json_bytes()
    assert b"private_prompt" not in value.canonical_json_bytes()


def test_registry_validates_selected_and_rejected_method_pairs() -> None:
    value = portfolio()
    methods = registry(
        registration("web-search", "provider-a"),
        registration("repository-inspection", "provider-b"),
    )

    assert methods.validate_portfolio(value) is value
    assert value.validate_against(methods) is value
    assert methods.resolve("web-search", "provider-a").failure_boundary == "provider-a-boundary"
    assert MethodRegistry.from_dict(methods.to_dict()) == methods


def test_multiple_queries_on_one_provider_do_not_establish_independence() -> None:
    one_boundary = portfolio(
        selected_methods=(selection("web-search", "provider-a", "query-1", "query-2", "query-3"),),
    )
    same_provider = portfolio(
        selected_methods=(
            selection("web-search", "provider-a", "query-1"),
            selection("documentation", "provider-a", "query-2"),
        ),
    )
    same_method = portfolio(
        selected_methods=(
            selection("web-search", "provider-a", "query-1"),
            selection("web-search", "provider-b", "query-2"),
        ),
    )
    independent = portfolio(
        selected_methods=(
            selection("web-search", "provider-a", "query-1"),
            selection("documentation", "provider-b", "query-2"),
        ),
    )

    assert one_boundary.has_independent_method_provider_boundaries(2) is False
    assert same_provider.has_independent_method_provider_boundaries(2) is False
    assert same_method.has_independent_method_provider_boundaries(2) is False
    assert independent.has_independent_method_provider_boundaries(2) is True


def test_unavailable_or_unknown_selection_fails_closed() -> None:
    value = portfolio(rejected_methods=())
    unavailable = registry(
        registration(
            "web-search",
            "provider-a",
            availability="unavailable",
            degradation_reason="provider-outage",
        )
    )

    with pytest.raises(InvalidSearchPortfolioError, match="unavailable"):
        unavailable.validate_portfolio(value)
    with pytest.raises(InvalidSearchPortfolioError, match="not registered"):
        registry().validate_portfolio(value)


def test_degraded_registration_is_explicit_but_still_selectable() -> None:
    value = portfolio(rejected_methods=())
    methods = registry(
        registration(
            "web-search",
            "provider-a",
            availability="degraded",
            degradation_reason="single-provider",
        )
    )

    assert methods.validate_portfolio(value) is value
    assert methods.resolve("web-search", "provider-a").to_dict()["degradation_reason"] == "single-provider"


def test_registry_rejects_unknown_fields_duplicate_boundaries_and_invalid_degradation() -> None:
    methods = registry(registration("web-search", "provider-a"))

    unknown_field = methods.to_dict()
    unknown_field["raw_prompt"] = "private instructions"
    with pytest.raises(InvalidSearchPortfolioError, match="fields"):
        MethodRegistry.from_dict(unknown_field)

    duplicate_boundary = methods.to_dict()
    duplicate_boundary["registrations"].append(dict(duplicate_boundary["registrations"][0]))
    with pytest.raises(InvalidSearchPortfolioError, match="unique"):
        MethodRegistry.from_dict(duplicate_boundary)

    with pytest.raises(InvalidSearchPortfolioError, match="degradation_reason"):
        registration(
            "web-search",
            "provider-a",
            availability="degraded",
            degradation_reason="private-reason",
        )

    with pytest.raises(InvalidSearchPortfolioError, match="registrations must be a sequence"):
        MethodRegistry(registry_id="registry-1", registrations=None)  # type: ignore[arg-type]


def test_strict_decoding_rejects_unknown_fields_duplicates_and_raw_query_text() -> None:
    value = portfolio()

    unknown_field = value.to_dict()
    unknown_field["raw_query"] = "private search phrase"
    with pytest.raises(InvalidSearchPortfolioError, match="fields"):
        SearchPortfolio.from_dict(unknown_field)

    duplicate_selection = value.to_dict()
    duplicate_selection["selected_methods"].append(dict(duplicate_selection["selected_methods"][0]))
    with pytest.raises(InvalidSearchPortfolioError, match="unique"):
        SearchPortfolio.from_dict(duplicate_selection)

    raw_query_reference = value.to_dict()
    raw_query_reference["selected_methods"][0]["query_refs"] = ["private search phrase"]
    with pytest.raises(InvalidSearchPortfolioError, match="query_refs"):
        SearchPortfolio.from_dict(raw_query_reference)

    unsupported_reason = value.to_dict()
    unsupported_reason["selected_methods"][0]["selection_reason"] = "because-i-said-so"
    with pytest.raises(InvalidSearchPortfolioError, match="selection_reason"):
        SearchPortfolio.from_dict(unsupported_reason)


def test_registry_and_portfolio_schema_mirror_the_public_value_objects() -> None:
    portfolio_schema = json.loads((SCHEMAS / "search-portfolio-v2.json").read_text(encoding="utf-8"))
    registry_schema = json.loads((SCHEMAS / "method-registry-v1.json").read_text(encoding="utf-8"))

    assert not (SCHEMAS / "search-portfolio-v1.json").exists()
    assert portfolio_schema["additionalProperties"] is False
    assert set(portfolio_schema["required"]) == set(portfolio().to_dict())
    assert portfolio_schema["$defs"]["selectedMethod"]["additionalProperties"] is False
    assert registry_schema["additionalProperties"] is False
    assert registry_schema["$defs"]["registration"]["additionalProperties"] is False


def test_portfolio_has_no_legacy_schema_reader_or_method_alias() -> None:
    legacy_payload = portfolio().to_dict()
    legacy_payload.pop("schema_version")
    legacy_payload.pop("kind")
    legacy_payload["methods"] = legacy_payload.pop("selected_methods")

    with pytest.raises(InvalidSearchPortfolioError, match="fields"):
        SearchPortfolio.from_dict(legacy_payload)


@pytest.mark.parametrize("schema_version", [True, 2.0])
def test_portfolio_rejects_non_integer_schema_versions(schema_version: object) -> None:
    payload = portfolio().to_dict()
    payload["schema_version"] = schema_version

    with pytest.raises(InvalidSearchPortfolioError, match="schema_version"):
        SearchPortfolio.from_dict(payload)


@pytest.mark.parametrize("schema_version", [True, 1.0])
def test_registry_rejects_non_integer_schema_versions(schema_version: object) -> None:
    payload = registry(registration("web-search", "provider-a")).to_dict()
    payload["schema_version"] = schema_version

    with pytest.raises(InvalidSearchPortfolioError, match="schema_version"):
        MethodRegistry.from_dict(payload)


def test_strict_decoding_rejects_non_string_object_keys() -> None:
    payload = {1: "not-json"}

    with pytest.raises(InvalidSearchPortfolioError, match="keys must be strings"):
        SearchPortfolio.from_dict(payload)


def test_intent_derived_planner_adds_bounded_non_keyword_decision_coverage() -> None:
    result = IntentDerivedSearchPortfolioPlanner(
        registry(
            registration("web-search", "provider-a"),
            registration("repository-inspection", "provider-b"),
        )
    ).plan(
        portfolio_id="portfolio-planned",
        run_id="run-1",
        intent_revision="intent-2",
        brief_revision="brief-3",
        strategy_revision="strategy-4",
        decision_slot_id="slot-1",
        slot_question="Should this interface preserve compatibility?",
        evidence_deficit_revision="deficit-5",
        evidence_deficit="The available evidence is incomplete.",
        closure_oracle="A primary source and repository check agree on the selected option.",
        assumptions=("The documented interface represents the supported boundary.",),
        material_change_dimensions=("evidence",),
    )

    assert {item.coverage for item in result.planned_subquestions} == {
        "mechanism",
        "counterevidence",
        "implementation",
        "edge-case",
        "validation",
        "consequence",
    }
    assert len(result.planned_subquestions) == 6
    assert result.human_decision_reopen is False
    assert result.portfolio.validate_against(result.registry) is result.portfolio
    assert {rewrite.intent_revision for rewrite in result.query_rewrites} == {"intent-2"}
    assert {rewrite.brief_revision for rewrite in result.query_rewrites} == {"brief-3"}
    assert {rewrite.strategy_revision for rewrite in result.query_rewrites} == {"strategy-4"}
    assert {rewrite.evidence_deficit_revision for rewrite in result.query_rewrites} == {"deficit-5"}
    assert {rewrite.decision_slot_id for rewrite in result.query_rewrites} == {"slot-1"}


@pytest.mark.parametrize(
    ("change_dimensions", "expected_reopen"),
    [
        (("evidence", "implementation"), False),
        (("authority",), True),
        (("safety",), True),
        (("requester-outcome",), True),
    ],
)
def test_intent_derived_planner_reopens_humans_only_for_material_changes(
    change_dimensions: tuple[str, ...],
    expected_reopen: bool,
) -> None:
    result = IntentDerivedSearchPortfolioPlanner(registry(registration("web-search", "provider-a"))).plan(
        portfolio_id="portfolio-reopen",
        run_id="run-1",
        intent_revision="intent-1",
        brief_revision="brief-1",
        strategy_revision="strategy-1",
        decision_slot_id="slot-1",
        slot_question="Should the interface preserve compatibility?",
        evidence_deficit_revision="deficit-1",
        evidence_deficit="The current evidence is incomplete.",
        closure_oracle="The validation fixture and repository observation agree.",
        assumptions=("The current API remains the decision boundary.",),
        material_change_dimensions=change_dimensions,
    )

    assert result.human_decision_reopen is expected_reopen


def execution_outcome(
    *,
    outcome_id: str = "outcome-1",
    batch_id: str = "batch-1",
    method_id: str = "web-search",
    provider_id: str = "provider-a",
    disposition: str = "captured",
    coverage: str = "complete",
    novelty: str = "new",
    source_quality: str = "high",
    source_depth: str = "full-source",
    contradictions: tuple[str, ...] = (),
    unresolved_decision_risk: str = "low",
    capture_refs: tuple[str, ...] = ("capture-1",),
) -> MethodExecutionOutcome:
    return MethodExecutionOutcome(
        outcome_id=outcome_id,
        portfolio_id="portfolio-1",
        batch_id=batch_id,
        method_id=method_id,
        provider_id=provider_id,
        failure_boundary=f"{provider_id}-boundary",
        selection_reason="primary-coverage",
        disposition=disposition,
        query_refs=("query-1",),
        capture_refs=capture_refs,
        coverage=coverage,
        novelty=novelty,
        source_quality=source_quality,
        source_depth=source_depth,
        contradictions=contradictions,
        unresolved_decision_risk=unresolved_decision_risk,
    )


def test_execution_preserves_boundaries_and_chooses_typed_alternate_after_failure() -> None:
    value = portfolio(
        selected_methods=(
            selection("web-search", "provider-a", "query-1"),
            selection("repository-inspection", "provider-b", "query-2"),
        ),
        rejected_methods=(),
    )
    methods = registry(
        registration("web-search", "provider-a"),
        registration("repository-inspection", "provider-b"),
    )

    result = SearchPortfolioExecutor(methods).execute(
        value,
        (PortfolioBatch("batch-1", "portfolio-1", (execution_outcome(disposition="rate-limit", capture_refs=()),)),),
    )

    assert "rate-limit" in ACQUISITION_DISPOSITIONS
    assert result.assessments[0].disposition == "switch"
    assert result.assessments[0].alternate_method_available is True
    assert result.alternatives[0].method_id == "repository-inspection"
    assert result.alternatives[0].selection_reason == "fallback"


def test_single_provider_execution_reports_degraded_capability_not_independence() -> None:
    value = portfolio(rejected_methods=())
    methods = registry(registration("web-search", "provider-a"))

    result = SearchPortfolioExecutor(methods).execute(
        value,
        (PortfolioBatch("batch-1", "portfolio-1", (execution_outcome(),)),),
    )

    assert result.degraded_capability is True
    assert result.assessments[0].provenance_independence == "single-boundary"
    assert result.assessments[0].disposition == "stop"
    assert result.assessments[0].coverage == "complete"


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        ("http-404", "switch"),
        ("no-result", "rewrite"),
        ("parser-failure", "switch"),
        ("rate-limit", "switch"),
        ("shallow", "deepen"),
    ],
)
def test_typed_failure_dispositions_drive_distinct_batch_decisions(failure: str, expected: str) -> None:
    outcome = execution_outcome(
        disposition=failure,
        coverage="none" if failure != "shallow" else "partial",
        source_depth="none" if failure != "shallow" else "snippet",
        capture_refs=(),
    )

    assessment = assess_acquisition_batch(
        assessment_id="assessment-1",
        portfolio_id="portfolio-1",
        batch_id="batch-1",
        outcomes=(outcome,),
        alternate_method_available=failure != "no-result",
    )

    assert assessment.disposition == expected
    assert assessment.disposition in BATCH_DECISIONS
    assert assessment.evidence_disposition == failure


def test_batch_assessment_records_all_decision_metrics_and_pivots_on_contradiction() -> None:
    assessment = assess_acquisition_batch(
        assessment_id="assessment-pivot",
        portfolio_id="portfolio-1",
        batch_id="batch-1",
        outcomes=(
            execution_outcome(
                contradictions=("initial mechanism is false",),
                unresolved_decision_risk="high",
            ),
            execution_outcome(
                outcome_id="outcome-2",
                method_id="repository-inspection",
                provider_id="provider-b",
                capture_refs=("capture-2",),
                source_quality="medium",
            ),
        ),
    )

    assert isinstance(assessment, BatchCoverageAssessment)
    assert assessment.coverage == "complete"
    assert assessment.novelty == "new"
    assert assessment.source_quality == "medium"
    assert assessment.contradictions == ("initial mechanism is false",)
    assert assessment.unresolved_decision_risk == "high"
    assert assessment.disposition == "pivot"
    assert assessment.requires_deeper_work is True
    assert assessment.to_dict() == BatchCoverageAssessment.from_dict(assessment.to_dict()).to_dict()
    assert b"private_prompt" not in assessment.canonical_json_bytes()


def test_runtime_service_persists_complete_portfolio_lineage_and_decision(tmp_path) -> None:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-lineage")

    def append(artifact_id, kind, payload, parent_refs=()):
        return ledger.append_artifact(
            "run-lineage",
            artifact_id,
            kind,
            payload,
            parent_refs=parent_refs,
            expected_revision=ledger.get_revision("run-lineage"),
        )

    intent = append("intent-1", "intent-model", {"task_id": "task-1", "revision": "intent-1"})
    brief = append(
        "brief-1",
        "working-brief",
        {"task_id": "task-1", "domain_id": "domain-1", "revision": "brief-1"},
        (ArtifactRef("run-lineage", intent.id, intent.revision),),
    )
    target = append(
        "target-1",
        "blueprint-target",
        {"decision_slots": [{"id": "slot-1"}]},
        (ArtifactRef("run-lineage", brief.id, brief.revision),),
    )
    strategy = append(
        "strategy-1",
        "strategy-projection",
        {"revision": "strategy-1"},
        (ArtifactRef("run-lineage", target.id, target.revision),),
    )
    method_registry = registry(
        registration("web-search", "provider-a"),
        registration("repository-inspection", "provider-b"),
    )
    plan = IntentDerivedSearchPortfolioPlanner(method_registry).plan(
        portfolio_id="portfolio-lineage",
        run_id="run-lineage",
        intent_revision="intent-1",
        brief_revision="brief-1",
        strategy_revision="strategy-1",
        decision_slot_id="slot-1",
        slot_question="Which implementation boundary is decisive?",
        evidence_deficit_revision="deficit-1",
        evidence_deficit="The implementation boundary is not closed.",
        closure_oracle="Independent source and repository evidence agree.",
        assumptions=("The selected decision slot remains current.",),
    )
    service = SearchPortfolioService(ledger)
    registry_artifact = service.register_methods(
        run_id="run-lineage",
        registry=method_registry,
        expected_revision=ledger.get_revision("run-lineage"),
    )
    portfolio_artifact = service.plan(
        run_id="run-lineage",
        plan=plan,
        intent_model=intent,
        working_brief=brief,
        strategy=strategy,
        decision_map=target,
        method_registry=registry_artifact,
        expected_revision=ledger.get_revision("run-lineage"),
    )
    query_ref = plan.query_rewrites[0].query_ref
    capture_service = DurableSourceCaptureService(ledger, ContentAddressedStore(tmp_path))
    capture = capture_service.capture(
        run_id="run-lineage",
        capture_id="capture-1",
        attempt_id="attempt-1",
        data=b"implementation evidence",
        media_type="text/plain",
        method_id=plan.query_rewrites[0].method_id,
        provider_id=plan.query_rewrites[0].provider_id,
        expected_revision=ledger.get_revision("run-lineage"),
    )
    receipt = capture_service.receipt(
        run_id="run-lineage",
        receipt_id="receipt-1",
        capture=capture,
        attempt_id="attempt-1",
        method_id=plan.query_rewrites[0].method_id,
        provider_id=plan.query_rewrites[0].provider_id,
        expected_revision=ledger.get_revision("run-lineage"),
    )
    checkpoint = capture_service.checkpoint(
        run_id="run-lineage",
        checkpoint_id="checkpoint-1",
        attempt_id="attempt-1",
        action_id="action-1",
        source_capture_refs=(capture.artifact_ref,),
        facts=({"claim": "implementation evidence is captured"},),
        expected_revision=ledger.get_revision("run-lineage"),
    )
    finding = append(
        "finding-1",
        "finding-pack",
        {"attempt_id": "attempt-1", "status": "committed"},
        (checkpoint.artifact_ref,),
    )
    outcome = MethodExecutionOutcome(
        outcome_id="outcome-1",
        portfolio_id=plan.portfolio.portfolio_id,
        batch_id="batch-1",
        method_id=plan.query_rewrites[0].method_id,
        provider_id=plan.query_rewrites[0].provider_id,
        failure_boundary=plan.portfolio.selected_methods[0].failure_boundary,
        selection_reason=plan.portfolio.selected_methods[0].selection_reason,
        disposition="captured",
        query_refs=(query_ref,),
        capture_refs=(f"{capture.artifact_ref.artifact_id}@{capture.artifact_ref.revision}",),
        receipt_refs=(f"{receipt.artifact_ref.artifact_id}@{receipt.artifact_ref.revision}",),
        checkpoint_refs=(f"{checkpoint.artifact_ref.artifact_id}@{checkpoint.artifact_ref.revision}",),
        coverage="complete",
        novelty="new",
        source_quality="high",
        source_depth="full-source",
        unresolved_decision_risk="low",
    )
    batch = PortfolioBatch("batch-1", plan.portfolio.portfolio_id, (outcome,))
    assessment = assess_acquisition_batch(
        assessment_id="assessment-1",
        portfolio_id=plan.portfolio.portfolio_id,
        batch_id="batch-1",
        outcomes=(outcome,),
        decision_slot_id="slot-1",
        attempt_id="attempt-1",
        next_actions=("submit-for-closure-assessment",),
        disposition="stop",
    )
    batch_artifact = service.record_batch(
        run_id="run-lineage",
        batch=batch,
        portfolio_ref=ArtifactRef("run-lineage", portfolio_artifact.id, portfolio_artifact.revision),
        finding_artifacts=(finding,),
        expected_revision=ledger.get_revision("run-lineage"),
    )
    assessment_artifact = service.record_assessment(
        run_id="run-lineage",
        assessment=assessment,
        portfolio_ref=ArtifactRef("run-lineage", portfolio_artifact.id, portfolio_artifact.revision),
        batch_ref=ArtifactRef("run-lineage", batch_artifact.id, batch_artifact.revision),
        capture_artifacts=(ledger.get_artifact(capture.artifact_ref),),
        receipt_artifacts=(ledger.get_artifact(receipt.artifact_ref),),
        checkpoint_artifacts=(ledger.get_artifact(checkpoint.artifact_ref),),
        finding_artifacts=(finding,),
        expected_revision=ledger.get_revision("run-lineage"),
    )

    artifacts = ledger.list_artifacts("run-lineage")
    decision = next(item for item in artifacts if item.kind == "portfolio-decision")
    assert registry_artifact.kind == "method-registry"
    assert {item for item in (intent.id, brief.id, strategy.id, target.id, registry_artifact.id)} <= {
        reference.artifact_id for reference in portfolio_artifact.parent_refs
    }
    assert ArtifactRef("run-lineage", portfolio_artifact.id, portfolio_artifact.revision) in batch_artifact.parent_refs
    assert ArtifactRef("run-lineage", batch_artifact.id, batch_artifact.revision) in assessment_artifact.parent_refs
    assert ArtifactRef("run-lineage", finding.id, finding.revision) in assessment_artifact.parent_refs
    assert decision.payload["decision"] == "stop"


def test_policy_consumes_persisted_assessment_without_becoming_persistence_authority() -> None:
    assessment = dict(
        portfolio_id="portfolio-1",
        batch_id="batch-1",
        decision_slot_id="slot-architecture",
        disposition="pivot",
        evidence_disposition="captured",
        causal_refs=("assessment-1",),
    )
    evaluation = AdaptiveResearchPolicy().evaluate(slots=(policy_slot(),), portfolio_assessments=(assessment,))

    assert evaluation.trace.normalized_inputs["portfolio_assessments"][0]["disposition"] == "pivot"
    assert evaluation.proposals
