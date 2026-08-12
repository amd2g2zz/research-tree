from __future__ import annotations

import pytest

from research_tree import (
    BatchCoverageAssessment,
    MethodBoundary,
    SearchPortfolio,
    SearchPortfolioError,
    assess_acquisition_batch,
    derive_search_portfolio,
    distinct_method_boundaries,
)


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
                "originating_deficit": "missing mechanism",
                "expected_decision_effect": "Close mechanism evidence class.",
                "stop_or_replan_trigger": "Primary source confirms or refutes mechanism.",
            },
        ),
        "query_variants": (
            {
                "query_id": "query-1",
                "subquestion_id": "sq-mechanism",
                "query": "official architecture mechanism",
                "method_id": "web-search",
                "provider_id": "anysearch",
                "target_evidence_class": "primary",
                "expected_decision_effect": "Close mechanism evidence class.",
            },
            {
                "query_id": "query-2",
                "subquestion_id": "sq-mechanism",
                "query": "implementation source mechanism",
                "method_id": "web-search",
                "provider_id": "anysearch",
                "target_evidence_class": "primary",
                "expected_decision_effect": "Close mechanism evidence class.",
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
    assert distinct_method_boundaries(value.method_boundaries) == (
        "repository_inspection:git:source-tree:search-index:anysearch",
        "search_provider:anysearch:public-web:search-index:anysearch",
    )
    assert value.query_variants[0]["expected_decision_effect"]


def test_repeated_queries_do_not_satisfy_independent_method_boundary() -> None:
    value = portfolio()

    assert len(value.query_variants) == 2
    assert distinct_method_boundaries(value.method_boundaries) == (
        "search_provider:anysearch:public-web:search-index:anysearch",
    )
    assert not value.satisfies_independent_methods(required=2)


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
    )

    assert shallow.policy_input()["requires_deeper_work"] is True
    assert shallow.disposition == "deepen"
    assert pivot.disposition == "pivot"
    assert pivot.successor_strategy_revision == "successor-strategy"
