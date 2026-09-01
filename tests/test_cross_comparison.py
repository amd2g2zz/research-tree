from __future__ import annotations

import pytest

from research_tree import (
    MethodExecutionOutcome,
    SearchPortfolioExecutor,
    apply_cross_comparison,
    compare_portfolio_batch,
)


def outcome(
    outcome_id: str,
    method_id: str,
    provider_id: str,
    *,
    capture_refs: tuple[str, ...] = (),
    batch_id: str = "batch-1",
) -> MethodExecutionOutcome:
    return MethodExecutionOutcome(
        outcome_id=outcome_id,
        portfolio_id="portfolio-adaptive",
        batch_id=batch_id,
        method_id=method_id,
        provider_id=provider_id,
        failure_boundary=f"{provider_id}-{method_id}",
        selection_reason="primary-coverage",
        disposition="captured" if capture_refs else "no-result",
        query_refs=(f"{outcome_id}-q1",),
        capture_refs=capture_refs,
    )


def capture(
    capture_ref: str,
    outcome_id: str,
    provider_id: str,
    *,
    upstream_id: str | None = None,
    fingerprint: str | None = None,
    matched_terms: tuple[str, ...] = (),
    source_kind: str = "full-source",
) -> dict[str, object]:
    return {
        "capture_ref": capture_ref,
        "outcome_id": outcome_id,
        "method_id": "web",
        "provider_id": provider_id,
        "upstream_id": upstream_id,
        "content_fingerprint": fingerprint,
        "matched_terms": list(matched_terms),
        "source_kind": source_kind,
    }


def test_same_url_two_providers_collapse_to_single_upstream_identity() -> None:
    comparison = compare_portfolio_batch(
        comparison_id="comparison-1",
        portfolio_id="portfolio-adaptive",
        batch_id="batch-1",
        outcomes=(
            outcome("o-a", "web", "anysearch", capture_refs=("cap-1",)),
            outcome("o-b", "web", "duckduckgo", capture_refs=("cap-2",)),
        ),
        captures=(
            capture("cap-1", "o-a", "anysearch", upstream_id="https://example.test/a", fingerprint="fp-a"),
            capture("cap-2", "o-b", "duckduckgo", upstream_id="https://example.test/a", fingerprint="fp-a"),
        ),
        intent_terms=("mechanism",),
    )

    assert len(comparison.identity_groups) == 1
    assert comparison.provider_fanout == 2
    assert len(comparison.duplicates) == 1
    duplicate = comparison.duplicates[0]
    assert duplicate.capture_ref == "cap-2"
    assert duplicate.provider_id == "duckduckgo"
    assert duplicate.origin_capture_ref == "cap-1"
    assert duplicate.origin_provider_id == "anysearch"
    assert comparison.dedup_ratio == pytest.approx(0.5)


def test_relevance_scoring_writes_back_measured_outcome_fields() -> None:
    first = outcome("o-a", "web", "anysearch", capture_refs=("cap-1",))
    second = outcome("o-b", "web", "duckduckgo", capture_refs=("cap-2",))
    comparison = compare_portfolio_batch(
        comparison_id="comparison-2",
        portfolio_id="portfolio-adaptive",
        batch_id="batch-1",
        outcomes=(first, second),
        captures=(
            capture(
                "cap-1",
                "o-a",
                "anysearch",
                upstream_id="https://example.test/a",
                fingerprint="fp-a",
                matched_terms=("mechanism", "retry"),
            ),
            capture(
                "cap-2",
                "o-b",
                "duckduckgo",
                upstream_id="https://example.test/a",
                fingerprint="fp-a",
                matched_terms=("mechanism",),
            ),
        ),
        intent_terms=("mechanism", "retry"),
    )

    measured_first, measured_second = apply_cross_comparison(comparison, (first, second))

    assert first.novelty == "none" and first.coverage == "none" and first.source_quality == "unknown"
    assert measured_first.novelty == "new"
    assert measured_first.coverage == "complete"
    assert measured_first.source_quality == "high"
    assert measured_first.boundary == first.boundary
    assert measured_second.novelty == "low"
    assert measured_second.coverage == "partial"
    assert comparison.provider_relevance["anysearch"] == pytest.approx(1.0)
    assert comparison.provider_relevance["duckduckgo"] == pytest.approx(0.5)


def test_content_conflict_on_shared_identity_records_contradiction() -> None:
    first = outcome("o-a", "web", "anysearch", capture_refs=("cap-1",))
    second = outcome("o-b", "web", "duckduckgo", capture_refs=("cap-2",))
    comparison = compare_portfolio_batch(
        comparison_id="comparison-3",
        portfolio_id="portfolio-adaptive",
        batch_id="batch-1",
        outcomes=(first, second),
        captures=(
            capture("cap-1", "o-a", "anysearch", upstream_id="https://example.test/a", fingerprint="fp-a"),
            capture("cap-2", "o-b", "duckduckgo", upstream_id="https://example.test/a", fingerprint="fp-b"),
        ),
        intent_terms=("mechanism",),
    )

    measured_first, measured_second = apply_cross_comparison(comparison, (first, second))

    assert comparison.identity_groups[0].content_conflict is True
    assert measured_first.contradictions == measured_second.contradictions
    assert len(measured_first.contradictions) == 1
    assert "content-conflict" in measured_first.contradictions[0]


def test_comparison_round_trips_canonically() -> None:
    comparison = compare_portfolio_batch(
        comparison_id="comparison-4",
        portfolio_id="portfolio-adaptive",
        batch_id="batch-1",
        outcomes=(outcome("o-a", "web", "anysearch", capture_refs=("cap-1",)),),
        captures=(capture("cap-1", "o-a", "anysearch", upstream_id="https://example.test/a", fingerprint="fp-a"),),
        intent_terms=("mechanism",),
    )

    revived = type(comparison).from_dict(comparison.to_dict())

    assert revived.canonical_json_bytes() == comparison.canonical_json_bytes()


def test_executor_applies_cross_comparison_when_captures_are_declared() -> None:
    from research_tree import IntentDerivedSearchPortfolioPlanner, MethodRegistration, MethodRegistry

    registry = MethodRegistry(
        registry_id="registry-adaptive",
        registrations=(
            MethodRegistration(
                method_id="web",
                provider_id="anysearch",
                capability="search",
                failure_boundary="anysearch-web",
                availability="available",
            ),
            MethodRegistration(
                method_id="news",
                provider_id="duckduckgo",
                capability="search",
                failure_boundary="duckduckgo-news",
                availability="available",
            ),
        ),
    )
    portfolio = IntentDerivedSearchPortfolioPlanner(registry).plan(
        portfolio_id="portfolio-adaptive",
        run_id="run-adaptive",
        intent_revision="intent-1",
        brief_revision="brief-1",
        strategy_revision="strategy-1",
        decision_slot_id="slot-1",
        slot_question="Which mechanism explains the observed behavior?",
        evidence_deficit_revision="deficit-1",
        evidence_deficit="Independent confirmation is missing.",
        closure_oracle="Two independent providers corroborate the mechanism.",
        assumptions=("Recorded provider state reflects real availability.",),
    )
    adapters = {
        ("web", "anysearch"): lambda selection: outcome("o-a", "web", "anysearch", capture_refs=("cap-1",)),
        ("news", "duckduckgo"): lambda selection: outcome("o-b", "news", "duckduckgo", capture_refs=("cap-2",)),
    }

    execution = SearchPortfolioExecutor(registry).run(
        portfolio.portfolio,
        adapters,
        batch_id="batch-1",
        captures=(
            capture("cap-1", "o-a", "anysearch", upstream_id="https://example.test/a", fingerprint="fp-a"),
            capture("cap-2", "o-b", "duckduckgo", upstream_id="https://example.test/a", fingerprint="fp-a"),
        ),
        intent_terms=("mechanism",),
    )

    measured = {item.provider_id: item for item in execution.batches[0].outcomes}
    assert measured["anysearch"].novelty == "new"
    assert measured["duckduckgo"].novelty == "low"
