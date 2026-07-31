from __future__ import annotations

from pathlib import Path

import pytest


def api():
    from research_tree import (
        AdaptivePortfolioScheduler,
        BlueprintTargetCompiler,
        InputIntakeService,
        IntentModelCompiler,
        InvalidPortfolioError,
        RunStore,
        WorkItemCompiler,
        WorkingBriefCompiler,
    )

    return {
        "AdaptivePortfolioScheduler": AdaptivePortfolioScheduler,
        "BlueprintTargetCompiler": BlueprintTargetCompiler,
        "InputIntakeService": InputIntakeService,
        "IntentModelCompiler": IntentModelCompiler,
        "InvalidPortfolioError": InvalidPortfolioError,
        "RunStore": RunStore,
        "WorkItemCompiler": WorkItemCompiler,
        "WorkingBriefCompiler": WorkingBriefCompiler,
    }


def repository(root: Path) -> Path:
    root.mkdir()
    (root / "src").mkdir()
    (root / "src" / "agent.py").write_text(
        "def run() -> str:\n    return 'ready'\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        "[project]\nname = 'scheduler-fixture'\nversion = '0.0.0'\n",
        encoding="utf-8",
    )
    return root


def slot(
    slot_id: str,
    *,
    priority: str,
    depends_on: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": slot_id,
        "kind": "architecture",
        "question": f"Which bounded choice should {slot_id} resolve?",
        "intent_hypothesis_ids": ["intent-agent"],
        "priority": priority,
        "impact": "high" if priority == "P0" else "medium",
        "uncertainty": "high",
        "irreversibility": "high" if priority == "P0" else "medium",
        "constraints": [
            {
                "kind": "input",
                "ref": "input-brief",
                "statement": "The first implementation must remain safe.",
            }
        ],
        "alternatives": ["candidate-a", "candidate-b"],
        "repository_touchpoints": [{"path": "src/agent.py", "symbol": "run"}],
        "greenfield_assumptions": [],
        "depends_on": depends_on or [],
        "evidence_standard": "repository inspection and bounded validation",
        "validation": {"kind": "spike", "oracle": "one fixture validates the boundary"},
        "closure_rule": "select, defer, or block with a fallback",
        "status": "open",
        "bounded_research_need": "compare both candidates against the repository boundary",
        "fallback": "retain the current boundary until this decision closes",
    }


def context(tmp_path: Path):
    modules = api()
    store = modules["RunStore"](tmp_path / "store")
    round_record = store.create_round("round-scheduler")
    intake = modules["InputIntakeService"](store)
    intake.ingest_text(
        round_id=round_record.id,
        input_id="input-brief",
        kind="brief",
        content="Build an implementation-ready autonomous reverse-engineering agent.",
        origin_type="user",
        origin_locator="conversation:1",
        role="signal",
    )
    intake.ingest_repository(
        round_id=round_record.id,
        input_id="input-repository",
        repository_root=repository(tmp_path / "repository"),
        origin_type="workspace",
        role="baseline",
    )
    intake.create_context_bundle(
        round_id=round_record.id,
        input_id="input-context",
        member_input_ids=("input-brief", "input-repository"),
        origin_type="user",
        origin_locator="conversation:1",
        role="baseline",
    )
    model = modules["IntentModelCompiler"](store).compile(
        round_id=round_record.id,
        intent_id="intent-model",
        context_bundle_ids=("input-context",),
        input_ids=("input-brief", "input-repository"),
        analysis={
            "signals": [
                {
                    "input_id": "input-brief",
                    "observation": "The requester needs an autonomous agent.",
                    "kind": "stated_goal",
                    "authority_boundary": "It does not choose research priority.",
                },
                {
                    "input_id": "input-repository",
                    "observation": "The repository exposes a run boundary.",
                    "kind": "repository_fact",
                    "authority_boundary": "It records current code, not a recommendation.",
                },
            ],
            "hypotheses": [
                {
                    "id": "intent-agent",
                    "interpretation": "Deliver a safe implementation-ready agent path.",
                    "status": "leading",
                    "signal_refs": ["input-brief", "input-repository"],
                    "confidence": "medium",
                    "decision_consequence": "High-impact boundaries need bounded research.",
                    "validation": "repository_inspection",
                }
            ],
            "desired_outcomes": ["implementation-ready technical blueprint"],
            "success_signals": ["an implementation agent can start without rediscovery"],
            "decision_drivers": [
                {
                    "dimension": "technical",
                    "statement": "The first implementation must remain safe.",
                    "signal_refs": ["input-brief"],
                }
            ],
            "hard_constraints": ["Do not execute untrusted binaries during intake."],
            "non_goals": ["Do not require a user questionnaire."],
            "unresolved_interpretations": [],
        },
    )
    brief = modules["WorkingBriefCompiler"](store).compile(
        round_id=round_record.id,
        brief_id="working-brief",
        intent_model=model,
        triggers=[{"kind": "initial_request", "text": "Start", "input_ids": ["input-brief"]}],
        context_bundle_ids=("input-context",),
        selected_input_ids=("input-brief", "input-repository"),
        input_roles={"input-brief": "primary", "input-repository": "baseline"},
        material_conflicts=[],
        working_interpretation="A safe implementation-ready agent path is leading.",
        technical_outcome="Choose the first agent boundaries and validation path.",
    )
    target = modules["BlueprintTargetCompiler"](store).compile(
        round_id=round_record.id,
        target_id="blueprint-target",
        working_brief=brief,
        slots=[
            slot("slot-boundary", priority="P0"),
            slot("slot-sandbox", priority="P0"),
            slot("slot-logging", priority="P1", depends_on=["slot-boundary"]),
        ],
        change={
            "kind": "initial",
            "reason": "Map independent and dependent research decisions.",
            "from_slot_ids": [],
            "to_slot_ids": ["slot-boundary", "slot-sandbox", "slot-logging"],
        },
    )
    compiler = modules["WorkItemCompiler"](store)
    work_boundary = compiler.compile(
        round_id=round_record.id,
        work_item_id="work-boundary",
        blueprint_target=target,
        decision_slot_id="slot-boundary",
        kind="repository_analysis",
        scope="Inspect the current boundary.",
        exclusions="Do not close the decision.",
        decision_change_reason="A boundary fact can change the architecture choice.",
        depends_on=[],
        methods=["repository_inspection"],
        budget={"tool_calls": 8, "time": "bounded"},
        completion_rule="Return a bounded Finding Pack.",
    )
    work_sandbox = compiler.compile(
        round_id=round_record.id,
        work_item_id="work-sandbox",
        blueprint_target=target,
        decision_slot_id="slot-sandbox",
        kind="repository_analysis",
        scope="Inspect the sandbox boundary.",
        exclusions="Do not close the decision.",
        decision_change_reason="A sandbox fact can change the isolation choice.",
        depends_on=[],
        methods=["repository_inspection"],
        budget={"tool_calls": 8, "time": "bounded"},
        completion_rule="Return a bounded Finding Pack.",
    )
    work_logging = compiler.compile(
        round_id=round_record.id,
        work_item_id="work-logging",
        blueprint_target=target,
        decision_slot_id="slot-logging",
        kind="repository_analysis",
        scope="Inspect observability after the boundary is known.",
        exclusions="Do not close the decision.",
        decision_change_reason="A boundary result changes logging integration.",
        depends_on=["work-boundary"],
        methods=["repository_inspection"],
        budget={"tool_calls": 8, "time": "bounded"},
        completion_rule="Return a bounded Finding Pack.",
    )
    return modules, store, round_record, target, (work_boundary, work_sandbox, work_logging)


def scoring_inputs() -> dict[str, dict[str, int]]:
    return {
        "work-boundary": {
            "expected_information_gain": 90,
            "cost": 10,
            "duplicate_risk": 0,
        },
        "work-sandbox": {
            "expected_information_gain": 70,
            "cost": 10,
            "duplicate_risk": 0,
        },
        "work-logging": {
            "expected_information_gain": 60,
            "cost": 8,
            "duplicate_risk": 5,
        },
    }


def schedule(modules, store, round_record, target, works, **kwargs):
    return modules["AdaptivePortfolioScheduler"](store).schedule(
        round_id=round_record.id,
        portfolio_id="research-portfolio",
        blueprint_target=target,
        work_items=works,
        scoring_inputs=scoring_inputs(),
        tool_call_budget=16,
        max_parallelism=2,
        **kwargs,
    )


def test_scheduler_is_reproducible_and_dispatches_only_independent_ready_work(tmp_path: Path) -> None:
    modules, store, round_record, target, works = context(tmp_path)
    portfolio = schedule(modules, store, round_record, target, works)
    from research_tree.domain import thaw_json

    payload = thaw_json(portfolio.payload)

    assert portfolio.kind == "work-portfolio"
    assert payload["work_dependency_dag"] == [
        {"work_item_id": "work-boundary", "depends_on": []},
        {"work_item_id": "work-logging", "depends_on": ["work-boundary"]},
        {"work_item_id": "work-sandbox", "depends_on": []},
    ]
    assert payload["ready_portfolio"] == ["work-boundary", "work-sandbox"]
    assert payload["dispatch_batches"] == [
        {
            "batch": 1,
            "work_item_ids": ["work-boundary", "work-sandbox"],
            "reason": "All items are dependency-independent, non-duplicate, and budgeted.",
        }
    ]
    decisions = {item["work_item_id"]: item for item in payload["scheduling_decisions"]}
    assert decisions["work-boundary"]["action"] == "dispatch"
    assert decisions["work-sandbox"]["action"] == "dispatch"
    assert decisions["work-logging"] == {
        "work_item_id": "work-logging",
        "action": "waiting",
        "reason": "Waiting for incomplete dependencies: work-boundary.",
        "score": decisions["work-logging"]["score"],
    }
    assert decisions["work-boundary"]["score_components"]["downstream_leverage"] > 0

    fresh_modules, fresh_store, fresh_round, fresh_target, fresh_works = context(tmp_path / "fresh")
    fresh = schedule(fresh_modules, fresh_store, fresh_round, fresh_target, fresh_works)
    assert thaw_json(fresh.payload) == payload


def test_budget_exhaustion_and_duplicate_work_are_explicitly_recorded(tmp_path: Path) -> None:
    modules, store, round_record, target, works = context(tmp_path)
    compiler = modules["WorkItemCompiler"](store)
    duplicate = compiler.compile(
        round_id=round_record.id,
        work_item_id="work-boundary-copy",
        blueprint_target=target,
        decision_slot_id="slot-boundary",
        kind="repository_analysis",
        scope="Inspect the current boundary.",
        exclusions="Do not close the decision.",
        decision_change_reason="A boundary fact can change the architecture choice.",
        depends_on=[],
        methods=["repository_inspection"],
        budget={"tool_calls": 8, "time": "bounded"},
        completion_rule="Return a bounded Finding Pack.",
    )
    inputs = scoring_inputs() | {
        "work-boundary-copy": {
            "expected_information_gain": 80,
            "cost": 10,
            "duplicate_risk": 0,
        }
    }
    portfolio = modules["AdaptivePortfolioScheduler"](store).schedule(
        round_id=round_record.id,
        portfolio_id="research-portfolio",
        blueprint_target=target,
        work_items=(*works, duplicate),
        scoring_inputs=inputs,
        tool_call_budget=8,
        max_parallelism=2,
        event={
            "kind": "budget_saturated",
            "reason": "Only one bounded investigation fits the current budget.",
            "affected_work_item_ids": ["work-sandbox"],
            "evidence_refs": [],
        },
    )

    decisions = {item["work_item_id"]: item for item in portfolio.payload["scheduling_decisions"]}
    assert decisions["work-boundary-copy"]["action"] == "cancelled"
    assert decisions["work-boundary-copy"]["reason"].startswith("Duplicate of work-boundary")
    assert decisions["work-boundary"]["action"] == "dispatch"
    assert decisions["work-sandbox"]["action"] == "deferred"
    assert decisions["work-sandbox"]["reason"] == "Tool-call budget is exhausted by higher-ranked work."
    assert portfolio.payload["budget"] == {
        "tool_call_limit": 8,
        "scheduled_tool_calls": 8,
        "remaining_tool_calls": 0,
    }


def test_dependency_cycle_rejects_before_persisting_portfolio(tmp_path: Path) -> None:
    modules, store, round_record, target, works = context(tmp_path)
    from research_tree.domain import thaw_json

    boundary, _sandbox, logging = works
    cyclic_payload = thaw_json(boundary.payload)
    cyclic_payload["depends_on"] = [logging.id]
    cyclic = store.append_artifact(
        round_record.id,
        boundary.id,
        boundary.kind,
        cyclic_payload,
        parent_refs=boundary.parent_refs,
    )
    inputs = scoring_inputs()
    with pytest.raises(modules["InvalidPortfolioError"]):
        modules["AdaptivePortfolioScheduler"](store).schedule(
            round_id=round_record.id,
            portfolio_id="research-portfolio",
            blueprint_target=target,
            work_items=(cyclic, works[1], logging),
            scoring_inputs=inputs,
            tool_call_budget=16,
            max_parallelism=2,
        )
    assert not [
        artifact
        for artifact in store.load_round(round_record.id).artifacts
        if artifact.kind == "work-portfolio"
    ]


def test_replan_retains_prior_provenance_and_records_priority_change_event(tmp_path: Path) -> None:
    modules, store, round_record, target, works = context(tmp_path)
    first = schedule(modules, store, round_record, target, works)
    revised_scores = scoring_inputs()
    revised_scores["work-sandbox"] = {
        "expected_information_gain": 99,
        "cost": 1,
        "duplicate_risk": 0,
    }
    second = modules["AdaptivePortfolioScheduler"](store).schedule(
        round_id=round_record.id,
        portfolio_id="research-portfolio",
        blueprint_target=target,
        work_items=works,
        scoring_inputs=revised_scores,
        tool_call_budget=16,
        max_parallelism=2,
        prior_portfolio=first,
        event={
            "kind": "repository_fact_disproved",
            "reason": "Repository inspection invalidated the sandbox cost assumption.",
            "affected_work_item_ids": ["work-sandbox"],
            "evidence_refs": [
                {"artifact_id": works[1].id, "revision": works[1].revision}
            ],
        },
    )

    assert second.revision == 2
    assert second.parent_refs[0].artifact_id == first.id
    assert second.parent_refs[0].revision == first.revision
    from research_tree.domain import thaw_json

    payload = thaw_json(second.payload)
    assert payload["replan_event"] == {
        "kind": "repository_fact_disproved",
        "reason": "Repository inspection invalidated the sandbox cost assumption.",
        "affected_work_item_ids": ["work-sandbox"],
        "evidence_refs": [
            {
                "round_id": round_record.id,
                "artifact_id": works[1].id,
                "revision": works[1].revision,
            }
        ],
    }
    assert payload["ready_portfolio"][0] == "work-sandbox"


def test_replan_requires_the_latest_prior_portfolio_reference(tmp_path: Path) -> None:
    modules, store, round_record, target, works = context(tmp_path)
    first = schedule(modules, store, round_record, target, works)

    with pytest.raises(modules["InvalidPortfolioError"]):
        schedule(modules, store, round_record, target, works)

    portfolios = [
        artifact
        for artifact in store.load_round(round_record.id).artifacts
        if artifact.kind == "work-portfolio"
    ]
    assert portfolios == [first]


def test_duplicate_canonical_never_depends_on_a_cancelled_duplicate(tmp_path: Path) -> None:
    modules, store, round_record, target, works = context(tmp_path)
    duplicate = modules["WorkItemCompiler"](store).compile(
        round_id=round_record.id,
        work_item_id="work-boundary-copy",
        blueprint_target=target,
        decision_slot_id="slot-boundary",
        kind="repository_analysis",
        scope="Inspect the current boundary.",
        exclusions="Do not close the decision.",
        decision_change_reason="A boundary fact can change the architecture choice.",
        depends_on=["work-boundary"],
        methods=["repository_inspection"],
        budget={"tool_calls": 8, "time": "bounded"},
        completion_rule="Return a bounded Finding Pack.",
    )
    inputs = scoring_inputs() | {
        "work-boundary": {
            "expected_information_gain": 0,
            "cost": 100,
            "duplicate_risk": 0,
        },
        "work-boundary-copy": {
            "expected_information_gain": 100,
            "cost": 0,
            "duplicate_risk": 0,
        }
    }

    portfolio = modules["AdaptivePortfolioScheduler"](store).schedule(
        round_id=round_record.id,
        portfolio_id="research-portfolio",
        blueprint_target=target,
        work_items=(*works, duplicate),
        scoring_inputs=inputs,
        tool_call_budget=16,
        max_parallelism=2,
    )

    decisions = {item["work_item_id"]: item for item in portfolio.payload["scheduling_decisions"]}
    assert decisions["work-boundary"]["action"] == "dispatch"
    assert decisions["work-boundary-copy"]["action"] == "cancelled"
    assert decisions["work-boundary-copy"]["reason"].startswith(
        "Duplicate of work-boundary"
    )


def test_running_work_reserves_budget_before_new_dispatch(tmp_path: Path) -> None:
    modules, store, round_record, target, works = context(tmp_path)
    from research_tree.domain import thaw_json

    boundary, sandbox, logging = works
    running_payload = thaw_json(boundary.payload)
    running_payload["status"] = "running"
    running_payload["status_reason"] = "A worker already owns this bounded investigation."
    running_boundary = store.append_artifact(
        round_record.id,
        boundary.id,
        boundary.kind,
        running_payload,
        parent_refs=boundary.parent_refs,
    )

    portfolio = modules["AdaptivePortfolioScheduler"](store).schedule(
        round_id=round_record.id,
        portfolio_id="research-portfolio",
        blueprint_target=target,
        work_items=(running_boundary, sandbox, logging),
        scoring_inputs=scoring_inputs(),
        tool_call_budget=8,
        max_parallelism=2,
    )

    decisions = {item["work_item_id"]: item for item in portfolio.payload["scheduling_decisions"]}
    assert decisions["work-boundary"]["action"] == "running"
    assert decisions["work-sandbox"]["action"] == "deferred"
    assert portfolio.payload["dispatch_batches"] == ()
    assert portfolio.payload["budget"] == {
        "tool_call_limit": 8,
        "scheduled_tool_calls": 8,
        "remaining_tool_calls": 0,
    }


def test_running_work_reserves_parallelism_before_new_dispatch(tmp_path: Path) -> None:
    modules, store, round_record, target, works = context(tmp_path)
    from research_tree.domain import thaw_json

    boundary, sandbox, logging = works
    running_payload = thaw_json(boundary.payload)
    running_payload["status"] = "running"
    running_payload["status_reason"] = "A worker already owns this bounded investigation."
    running_boundary = store.append_artifact(
        round_record.id,
        boundary.id,
        boundary.kind,
        running_payload,
        parent_refs=boundary.parent_refs,
    )

    portfolio = modules["AdaptivePortfolioScheduler"](store).schedule(
        round_id=round_record.id,
        portfolio_id="research-portfolio",
        blueprint_target=target,
        work_items=(running_boundary, sandbox, logging),
        scoring_inputs=scoring_inputs(),
        tool_call_budget=16,
        max_parallelism=1,
    )

    decisions = {item["work_item_id"]: item for item in portfolio.payload["scheduling_decisions"]}
    assert decisions["work-boundary"]["action"] == "running"
    assert decisions["work-sandbox"]["action"] == "deferred"
    assert portfolio.payload["dispatch_batches"] == ()
    assert portfolio.payload["budget"] == {
        "tool_call_limit": 16,
        "scheduled_tool_calls": 8,
        "remaining_tool_calls": 8,
    }


def test_terminal_dependency_defers_downstream_work_instead_of_waiting_forever(
    tmp_path: Path,
) -> None:
    modules, store, round_record, target, works = context(tmp_path)
    from research_tree.domain import thaw_json

    boundary, sandbox, logging = works
    cancelled_payload = thaw_json(boundary.payload)
    cancelled_payload["status"] = "cancelled"
    cancelled_payload["status_reason"] = "The boundary question was superseded."
    cancelled_boundary = store.append_artifact(
        round_record.id,
        boundary.id,
        boundary.kind,
        cancelled_payload,
        parent_refs=boundary.parent_refs,
    )

    portfolio = modules["AdaptivePortfolioScheduler"](store).schedule(
        round_id=round_record.id,
        portfolio_id="research-portfolio",
        blueprint_target=target,
        work_items=(cancelled_boundary, sandbox, logging),
        scoring_inputs=scoring_inputs(),
        tool_call_budget=16,
        max_parallelism=2,
    )

    decisions = {item["work_item_id"]: item for item in portfolio.payload["scheduling_decisions"]}
    assert decisions["work-logging"]["action"] == "deferred"
    assert decisions["work-logging"]["reason"].startswith(
        "Blocked by terminal dependencies: work-boundary"
    )


def test_later_evidence_driven_replan_requires_affected_work_and_evidence(
    tmp_path: Path,
) -> None:
    modules, store, round_record, target, works = context(tmp_path)
    first = schedule(modules, store, round_record, target, works)

    with pytest.raises(modules["InvalidPortfolioError"]):
        modules["AdaptivePortfolioScheduler"](store).schedule(
            round_id=round_record.id,
            portfolio_id="research-portfolio",
            blueprint_target=target,
            work_items=works,
            scoring_inputs=scoring_inputs(),
            tool_call_budget=16,
            max_parallelism=2,
            prior_portfolio=first,
            event={
                "kind": "repository_fact_disproved",
                "reason": "The previous repository assumption was disproved.",
                "affected_work_item_ids": [],
                "evidence_refs": [],
            },
        )

    with pytest.raises(modules["InvalidPortfolioError"]):
        modules["AdaptivePortfolioScheduler"](store).schedule(
            round_id=round_record.id,
            portfolio_id="research-portfolio",
            blueprint_target=target,
            work_items=works,
            scoring_inputs=scoring_inputs(),
            tool_call_budget=16,
            max_parallelism=2,
            prior_portfolio=first,
            event={
                "kind": "repository_fact_disproved",
                "reason": "The previous repository assumption was disproved.",
                "affected_work_item_ids": ["work-sandbox"],
                "evidence_refs": [],
            },
        )

    portfolios = [
        artifact
        for artifact in store.load_round(round_record.id).artifacts
        if artifact.kind == "work-portfolio"
    ]
    assert portfolios == [first]
