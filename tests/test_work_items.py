from __future__ import annotations

from pathlib import Path

import pytest


def api():
    from research_tree import (
        BlueprintTargetCompiler,
        CanonicalBlueprintTargetCompiler,
        CanonicalInputIntakeService,
        CanonicalIntentModelCompiler,
        CanonicalWorkItemCompiler,
        CanonicalWorkItemPlanner,
        CanonicalWorkItemStatusService,
        CanonicalWorkingBriefCompiler,
        InputIntakeService,
        IntentModelCompiler,
        InvalidWorkItemError,
        RunStore,
        RunLedger,
        WorkItemCompiler,
        WorkItemPlanner,
        WorkItemStatusService,
        WorkingBriefCompiler,
    )

    return {
        "BlueprintTargetCompiler": BlueprintTargetCompiler,
        "CanonicalBlueprintTargetCompiler": CanonicalBlueprintTargetCompiler,
        "CanonicalInputIntakeService": CanonicalInputIntakeService,
        "CanonicalIntentModelCompiler": CanonicalIntentModelCompiler,
        "CanonicalWorkItemCompiler": CanonicalWorkItemCompiler,
        "CanonicalWorkItemPlanner": CanonicalWorkItemPlanner,
        "CanonicalWorkItemStatusService": CanonicalWorkItemStatusService,
        "CanonicalWorkingBriefCompiler": CanonicalWorkingBriefCompiler,
        "InputIntakeService": InputIntakeService,
        "IntentModelCompiler": IntentModelCompiler,
        "InvalidWorkItemError": InvalidWorkItemError,
        "RunStore": RunStore,
        "RunLedger": RunLedger,
        "WorkItemCompiler": WorkItemCompiler,
        "WorkItemPlanner": WorkItemPlanner,
        "WorkItemStatusService": WorkItemStatusService,
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
        "[project]\nname = 'fixture'\nversion = '0.0.0'\n",
        encoding="utf-8",
    )
    return root


def context_target(tmp_path: Path):
    modules = api()
    store = modules["RunStore"](tmp_path / "store")
    round_record = store.create_round("round-work")
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
                    "authority_boundary": "It does not select the implementation architecture.",
                },
                {
                    "input_id": "input-repository",
                    "observation": "The repository has a src/agent.py run boundary.",
                    "kind": "repository_fact",
                    "authority_boundary": "It describes current code, not a recommendation.",
                },
            ],
            "hypotheses": [
                {
                    "id": "intent-agent",
                    "interpretation": "Deliver a safe implementation-ready agent path.",
                    "status": "leading",
                    "signal_refs": ["input-brief", "input-repository"],
                    "confidence": "medium",
                    "decision_consequence": "Architecture and safety boundaries need research.",
                    "validation": "repository_inspection",
                }
            ],
            "desired_outcomes": ["implementation-ready technical blueprint"],
            "success_signals": ["an implementation agent can start without rediscovery"],
            "decision_drivers": [
                {
                    "dimension": "technical",
                    "statement": "The first implementation must be safely isolated.",
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
        technical_outcome="Choose the first agent architecture and integration boundary.",
    )
    architecture = slot("slot-architecture", priority="P0")
    security = slot("slot-security", priority="P1")
    security["depends_on"] = ["slot-architecture"]
    target = modules["BlueprintTargetCompiler"](store).compile(
        round_id=round_record.id,
        target_id="blueprint-target",
        working_brief=brief,
        slots=[security, architecture],
        change={
            "kind": "initial",
            "reason": "Map the open architecture and security decisions.",
            "from_slot_ids": [],
            "to_slot_ids": ["slot-security", "slot-architecture"],
        },
    )
    return modules, store, round_record, target


def canonical_context_target(tmp_path: Path):
    modules = api()
    ledger = modules["RunLedger"](tmp_path / "ledger")
    ledger.initialize()
    round_record = ledger.create_run("round-work")
    intake = modules["CanonicalInputIntakeService"](ledger)
    intake.ingest_text(
        round_id=round_record.id,
        input_id="input-brief",
        kind="brief",
        content="Build an implementation-ready autonomous reverse-engineering agent.",
        origin_type="user",
        origin_locator="conversation:1",
        role="signal",
        expected_revision=ledger.get_revision(round_record.id),
    )
    intake.ingest_repository(
        round_id=round_record.id,
        input_id="input-repository",
        repository_root=repository(tmp_path / "repository"),
        origin_type="workspace",
        role="baseline",
        expected_revision=ledger.get_revision(round_record.id),
    )
    input_ids = ("input-brief", "input-repository")
    intake.create_context_bundle(
        round_id=round_record.id,
        input_id="input-context",
        member_input_ids=input_ids,
        origin_type="user",
        origin_locator="conversation:1",
        role="baseline",
        expected_revision=ledger.get_revision(round_record.id),
    )
    model = modules["CanonicalIntentModelCompiler"](ledger).compile(
        round_id=round_record.id,
        intent_id="intent-model",
        context_bundle_ids=("input-context",),
        input_ids=input_ids,
        analysis={
            "signals": [
                {"input_id": "input-brief", "observation": "The requester needs an autonomous agent.", "kind": "stated_goal", "authority_boundary": "It does not select the implementation architecture."},
                {"input_id": "input-repository", "observation": "The repository has a src/agent.py run boundary.", "kind": "repository_fact", "authority_boundary": "It describes current code, not a recommendation."},
            ],
            "hypotheses": [{"id": "intent-agent", "interpretation": "Deliver a safe implementation-ready agent path.", "status": "leading", "signal_refs": ["input-brief", "input-repository"], "confidence": "medium", "decision_consequence": "Architecture and safety boundaries need research.", "validation": "repository_inspection"}],
            "desired_outcomes": ["implementation-ready technical blueprint"],
            "success_signals": ["an implementation agent can start without rediscovery"],
            "decision_drivers": [{"dimension": "technical", "statement": "The first implementation must be safely isolated.", "signal_refs": ["input-brief"]}],
            "hard_constraints": ["Do not execute untrusted binaries during intake."],
            "non_goals": ["Do not require a user questionnaire."],
            "unresolved_interpretations": [],
        },
        expected_revision=ledger.get_revision(round_record.id),
    )
    brief = modules["CanonicalWorkingBriefCompiler"](ledger).compile(
        round_id=round_record.id,
        brief_id="working-brief",
        intent_model=model,
        triggers=[{"kind": "initial_request", "text": "Start", "input_ids": ["input-brief"]}],
        context_bundle_ids=("input-context",),
        selected_input_ids=input_ids,
        input_roles={"input-brief": "primary", "input-repository": "baseline"},
        material_conflicts=[],
        working_interpretation="A safe implementation-ready agent path is leading.",
        technical_outcome="Choose the first agent architecture and integration boundary.",
        expected_revision=ledger.get_revision(round_record.id),
    )
    architecture = slot("slot-architecture", priority="P0")
    security = slot("slot-security", priority="P1")
    security["depends_on"] = ["slot-architecture"]
    target = modules["CanonicalBlueprintTargetCompiler"](ledger).compile(
        round_id=round_record.id,
        target_id="blueprint-target",
        working_brief=brief,
        slots=[security, architecture],
        change={"kind": "initial", "reason": "Map the open architecture and security decisions.", "from_slot_ids": [], "to_slot_ids": ["slot-security", "slot-architecture"]},
        expected_revision=ledger.get_revision(round_record.id),
    )
    return modules, ledger, round_record, target


def slot(slot_id: str, *, priority: str) -> dict[str, object]:
    return {
        "id": slot_id,
        "kind": "architecture",
        "question": f"Which boundary should {slot_id} use?",
        "intent_hypothesis_ids": ["intent-agent"],
        "priority": priority,
        "impact": "high",
        "uncertainty": "high",
        "irreversibility": "high",
        "constraints": [
            {
                "kind": "input",
                "ref": "input-brief",
                "statement": "The first implementation must remain safe.",
            }
        ],
        "alternatives": ["isolated-worker", "in-process"],
        "repository_touchpoints": [{"path": "src/agent.py", "symbol": "run"}],
        "greenfield_assumptions": [],
        "depends_on": [],
        "evidence_standard": "repository inspection plus a bounded spike",
        "validation": {"kind": "spike", "oracle": "one fixture crosses the selected boundary"},
        "closure_rule": "select, conditionally select, defer with fallback, or block",
        "status": "open",
        "bounded_research_need": "compare both alternatives against the current boundary",
        "fallback": "retain the current boundary until this decision closes",
    }


def test_dependency_respecting_planner_emits_deterministic_bounded_work(tmp_path: Path) -> None:
    modules, ledger, round_record, target = canonical_context_target(tmp_path)
    items = modules["CanonicalWorkItemPlanner"](ledger).plan(
        round_id=round_record.id,
        blueprint_target=target,
        work_item_ids={
            "slot-architecture": "work-architecture",
            "slot-security": "work-security",
        },
        mode="dependency_respecting",
    )

    assert [item.id for item in items] == ["work-architecture", "work-security"]
    assert items[0].payload["status"] == "ready"
    assert items[1].payload["status"] == "planned"
    assert items[1].payload["depends_on"] == ("work-architecture",)
    assert items[0].payload["scope"] == "Which boundary should slot-architecture use?"
    assert items[0].payload["expected_finding_pack"]["option_effects"]
    assert items[0].parent_refs[0].to_dict() == {
        "round_id": round_record.id,
        "artifact_id": target.id,
        "revision": target.revision,
    }
    rerun = modules["CanonicalWorkItemPlanner"](ledger).plan(
        round_id=round_record.id,
        blueprint_target=target,
        work_item_ids={
            "slot-architecture": "work-architecture",
            "slot-security": "work-security",
        },
        mode="dependency_respecting",
    )
    assert [item.payload for item in rerun] == [item.payload for item in items]


def test_planner_rejects_normal_work_for_a_superseded_round(tmp_path: Path) -> None:
    modules, store, round_record, target = context_target(tmp_path)
    store.append_artifact(
        round_record.id,
        "round-supersession-round-next",
        "round-supersession",
        {"status": "superseded", "successor_round_id": "round-next"},
    )

    with pytest.raises(modules["InvalidWorkItemError"], match="superseded"):
        modules["WorkItemPlanner"](store).plan(
            round_id=round_record.id,
            blueprint_target=target,
            work_item_ids={
                "slot-architecture": "work-architecture",
                "slot-security": "work-security",
            },
        )

    with pytest.raises(modules["InvalidWorkItemError"], match="superseded"):
        modules["WorkItemCompiler"](store).compile(
            round_id=round_record.id,
            work_item_id="work-direct",
            blueprint_target=target,
            decision_slot_id="slot-architecture",
            kind="repository_analysis",
            scope="Inspect the old architecture boundary.",
            exclusions="Do not close the decision.",
            decision_change_reason="The old strategy is no longer allowed to spend work.",
            depends_on=(),
            methods=("repository_inspection",),
            budget={"tool_calls": 4, "time": "bounded"},
            completion_rule="Return a bounded Finding Pack.",
        )

    assert not [
        artifact
        for artifact in store.load_round(round_record.id).artifacts
        if artifact.kind == "work-item"
    ]


def test_serial_planner_turns_stable_topological_order_into_a_chain(tmp_path: Path) -> None:
    modules, store, round_record, target = context_target(tmp_path)
    brief = next(
        artifact
        for artifact in store.load_round(round_record.id).artifacts
        if artifact.kind == "working-brief"
    )
    independent = slot("slot-observability", priority="P1")
    serial_target = modules["BlueprintTargetCompiler"](store).compile(
        round_id=round_record.id,
        target_id="serial-target",
        working_brief=brief,
        slots=[slot("slot-architecture", priority="P0"), independent],
        change={
            "kind": "initial",
            "reason": "Compare serial planning for two independent decisions.",
            "from_slot_ids": [],
            "to_slot_ids": ["slot-architecture", "slot-observability"],
        },
    )
    items = modules["WorkItemPlanner"](store).plan(
        round_id=round_record.id,
        blueprint_target=serial_target,
        work_item_ids={
            "slot-architecture": "work-architecture",
            "slot-observability": "work-observability",
        },
        mode="serial",
    )

    assert [item.id for item in items] == ["work-architecture", "work-observability"]
    assert items[1].payload["depends_on"] == ("work-architecture",)


def test_compiler_rejects_missing_closed_and_unowned_slots_without_exception(tmp_path: Path) -> None:
    modules, store, round_record, target = context_target(tmp_path)
    compiler = modules["WorkItemCompiler"](store)
    common = {
        "round_id": round_record.id,
        "work_item_id": "work-invalid",
        "blueprint_target": target,
        "kind": "repository_analysis",
        "scope": "Inspect the bounded repository decision.",
        "exclusions": "Do not close the slot.",
        "decision_change_reason": "The result could change the selected alternative.",
        "depends_on": (),
        "methods": ("repository_inspection",),
        "budget": {"tool_calls": 4, "time": "bounded"},
        "completion_rule": "Return a Finding Pack or state why evidence is unavailable.",
    }
    with pytest.raises(modules["InvalidWorkItemError"]):
        compiler.compile(decision_slot_id="slot-missing", **common)

    invalid_hypotheses = {**common, "work_item_id": "work-unowned", "intent_hypothesis_ids": ("intent-unknown",)}
    with pytest.raises(modules["InvalidWorkItemError"]):
        compiler.compile(decision_slot_id="slot-architecture", **invalid_hypotheses)

    assert [artifact for artifact in store.load_round(round_record.id).artifacts if artifact.kind == "work-item"] == []


def test_closed_slot_requires_recorded_exception_and_deferred_status(tmp_path: Path) -> None:
    modules, store, round_record, target = context_target(tmp_path)
    closed_slots = [dict(slot_value) for slot_value in target.payload["slots"]]
    next(slot_value for slot_value in closed_slots if slot_value["id"] == "slot-architecture")[
        "status"
    ] = "selected"
    closed_target = modules["BlueprintTargetCompiler"](store).compile(
        round_id=round_record.id,
        target_id="closed-target",
        working_brief=next(
            artifact
            for artifact in store.load_round(round_record.id).artifacts
            if artifact.kind == "working-brief"
        ),
        slots=closed_slots,
        change={
            "kind": "initial",
            "reason": "Represent a closed decision for exception coverage.",
            "from_slot_ids": [],
            "to_slot_ids": ["slot-architecture", "slot-security"],
        },
    )
    compiler = modules["WorkItemCompiler"](store)
    common = {
        "round_id": round_record.id,
        "work_item_id": "work-closed",
        "blueprint_target": closed_target,
        "decision_slot_id": "slot-architecture",
        "kind": "repository_analysis",
        "scope": "Inspect the already selected decision.",
        "exclusions": "Do not reopen the decision.",
        "decision_change_reason": "Only a documented exception can change it.",
        "depends_on": (),
        "methods": ("repository_inspection",),
        "budget": {"tool_calls": 4, "time": "bounded"},
        "completion_rule": "Return a Finding Pack or state why evidence is unavailable.",
    }
    with pytest.raises(modules["InvalidWorkItemError"]):
        compiler.compile(**common)

    deferred = compiler.compile(
        **common,
        exception_reason="A regression report requires independent confirmation.",
        status="deferred",
    )
    assert deferred.payload["status"] == "deferred"
    assert deferred.payload["status_reason"] == "A regression report requires independent confirmation."


def test_status_service_appends_cancelled_and_deferred_revisions(tmp_path: Path) -> None:
    modules, store, round_record, target = context_target(tmp_path)
    work = modules["WorkItemPlanner"](store).plan(
        round_id=round_record.id,
        blueprint_target=target,
        work_item_ids={
            "slot-architecture": "work-architecture",
            "slot-security": "work-security",
        },
        mode="dependency_respecting",
    )[1]
    service = modules["WorkItemStatusService"](store)
    with pytest.raises(modules["InvalidWorkItemError"]):
        service.update(
            round_id=round_record.id,
            work_item=work,
            blueprint_target=target,
            status="cancelled",
            reason="This must not cancel active research.",
        )
    brief = next(
        artifact
        for artifact in store.load_round(round_record.id).artifacts
        if artifact.kind == "working-brief"
    )
    retained_slots = [
        dict(slot_value)
        for slot_value in target.payload["slots"]
        if slot_value["id"] != "slot-security"
    ]
    superseding_target = modules["BlueprintTargetCompiler"](store).compile(
        round_id=round_record.id,
        target_id=target.id,
        working_brief=brief,
        slots=retained_slots,
        change={
            "kind": "remove",
            "reason": "The security decision is superseded by the architecture boundary.",
            "from_slot_ids": ["slot-security"],
            "to_slot_ids": [],
        },
    )
    cancelled = service.update(
        round_id=round_record.id,
        work_item=work,
        blueprint_target=superseding_target,
        status="cancelled",
        reason="The upstream architecture decision was superseded.",
    )
    deferred = service.update(
        round_id=round_record.id,
        work_item=cancelled,
        blueprint_target=superseding_target,
        status="deferred",
        reason="Retain the cancelled evidence request for a later round.",
    )

    assert [work.revision, cancelled.revision, deferred.revision] == [1, 2, 3]
    assert cancelled.parent_refs[0].revision == work.revision
    assert deferred.parent_refs[0].revision == cancelled.revision
    assert deferred.payload["status"] == "deferred"
