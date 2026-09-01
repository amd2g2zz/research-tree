from __future__ import annotations

import pytest

from research_tree import (
    IntentDerivedSearchPortfolioPlanner,
    InvalidSearchPortfolioError,
    MethodRegistration,
    MethodRegistry,
)


def registration(method_id: str, provider_id: str, *, availability: str = "available") -> MethodRegistration:
    kwargs: dict[str, object] = {}
    if availability != "available":
        kwargs["degradation_reason"] = "rate-limited"
    return MethodRegistration(
        method_id=method_id,
        provider_id=provider_id,
        capability="search",
        failure_boundary=f"{provider_id}-{method_id}",
        availability=availability,
        **kwargs,
    )


def plan(*registrations: MethodRegistration):
    registry = MethodRegistry(registry_id="registry-adaptive", registrations=tuple(registrations))
    return IntentDerivedSearchPortfolioPlanner(registry).plan(
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


def test_plan_fans_out_across_distinct_available_providers() -> None:
    result = plan(
        registration("web", "anysearch"),
        registration("news", "duckduckgo"),
    )

    selected_providers = {item.provider_id for item in result.portfolio.selected_methods}
    assert selected_providers == {"anysearch", "duckduckgo"}
    assert result.provider_fanout == 2


def test_plan_fanout_counts_distinct_providers_not_registrations() -> None:
    result = plan(
        registration("web", "anysearch"),
        registration("news", "anysearch"),
        registration("docs", "duckduckgo"),
    )

    assert result.provider_fanout == 2
    assert {item.provider_id for item in result.portfolio.selected_methods} == {"anysearch", "duckduckgo"}


def test_unavailable_providers_neither_selected_nor_counted() -> None:
    result = plan(
        registration("web", "anysearch"),
        registration("news", "duckduckgo"),
        registration("docs", "archive", availability="unavailable"),
    )

    assert result.provider_fanout == 2
    assert "archive" not in {item.provider_id for item in result.portfolio.selected_methods}


def test_degraded_providers_still_count_as_available_fanout() -> None:
    result = plan(
        registration("web", "anysearch"),
        registration("news", "duckduckgo", availability="degraded"),
    )

    assert result.provider_fanout == 2
    assert {item.provider_id for item in result.portfolio.selected_methods} == {"anysearch", "duckduckgo"}


def test_single_available_provider_plan_reports_fanout_one() -> None:
    result = plan(registration("web", "anysearch"))

    assert [item.provider_id for item in result.portfolio.selected_methods] == ["anysearch"]
    assert result.provider_fanout == 1


def test_planner_rejects_registry_without_available_provider() -> None:
    with pytest.raises(InvalidSearchPortfolioError, match="available"):
        plan(registration("web", "archive", availability="unavailable"))
