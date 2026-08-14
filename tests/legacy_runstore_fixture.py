from __future__ import annotations

from pathlib import Path

from test_deliveries import decision_kwargs, intent_analysis, readiness, repository, slot


def api():
    from research_tree import (
        ArtifactRef,
        BlueprintTargetCompiler,
        DecisionLedgerCompiler,
        DeliveryCompiler,
        FindingPackCompiler,
        InputIntakeService,
        IntentModelCompiler,
        InvalidDeliveryError,
        RunStore,
        WorkItemPlanner,
        WorkingBriefCompiler,
    )

    return {
        "ArtifactRef": ArtifactRef,
        "BlueprintTargetCompiler": BlueprintTargetCompiler,
        "DecisionLedgerCompiler": DecisionLedgerCompiler,
        "DeliveryCompiler": DeliveryCompiler,
        "FindingPackCompiler": FindingPackCompiler,
        "InputIntakeService": InputIntakeService,
        "IntentModelCompiler": IntentModelCompiler,
        "InvalidDeliveryError": InvalidDeliveryError,
        "RunStore": RunStore,
        "WorkItemPlanner": WorkItemPlanner,
        "WorkingBriefCompiler": WorkingBriefCompiler,
    }


def finding_payload(option: str, effect: str, claim: str) -> dict[str, object]:
    return {
        "observations": [
            {
                "claim": claim,
                "anchor": {"kind": "repository", "ref": "src/agent.py:run"},
                "applicability": "the supplied Python repository",
                "confidence": "medium",
                "limitation": "This does not measure production startup overhead.",
            }
        ],
        "option_effects": [{"option": option, "effect": effect}],
        "implementation_implications": ["The run boundary needs an explicit adapter."],
        "remaining_uncertainties": ["Measure startup overhead with a spike."],
    }


def compile_finding(modules, store, round_record, work, finding_id: str, **payload):
    return modules["FindingPackCompiler"](store).compile(
        round_id=round_record.id,
        finding_id=finding_id,
        work_item=work,
        **payload,
    )


def context(tmp_path: Path, *, include_decision: bool = True):
    modules = api()
    store = modules["RunStore"](tmp_path / "store")
    round_record = store.create_round("round-delivery")
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
        analysis=intent_analysis(),
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
    isolation = slot(
        "slot-isolation",
        kind="architecture",
        priority="P0",
        alternatives=["isolated-worker", "in-process"],
    )
    observability = slot(
        "slot-observability",
        kind="operations",
        priority="P1",
        alternatives=["structured-logging", "minimal-logging"],
        depends_on=["slot-isolation"],
    )
    target = modules["BlueprintTargetCompiler"](store).compile(
        round_id=round_record.id,
        target_id="blueprint-target",
        working_brief=brief,
        slots=[observability, isolation],
        change={
            "kind": "initial",
            "reason": "Map implementation decisions for the first agent.",
            "from_slot_ids": [],
            "to_slot_ids": ["slot-observability", "slot-isolation"],
        },
    )
    items = modules["WorkItemPlanner"](store).plan(
        round_id=round_record.id,
        blueprint_target=target,
        work_item_ids={
            "slot-isolation": "work-isolation",
            "slot-observability": "work-observability",
        },
    )
    isolation_work = next(item for item in items if item.payload["decision_slot_id"] == "slot-isolation")
    if not include_decision:
        return modules, store, round_record, model, brief, target, None, None
    finding = compile_finding(
        modules,
        store,
        round_record,
        isolation_work,
        "finding-isolation",
        **finding_payload(
            "isolated-worker",
            "supports",
            "The existing run boundary can host an explicit worker adapter.",
        ),
    )
    decision = modules["DecisionLedgerCompiler"](store).converge(
        round_id=round_record.id,
        decision_id="decision-isolation",
        **decision_kwargs(target, finding),
    )
    return modules, store, round_record, model, brief, target, finding, decision


def compile_deliveries(
    modules,
    store,
    round_record,
    brief,
    target,
    decisions,
    *,
    readiness_input: dict[str, object] | None = None,
):
    return modules["DeliveryCompiler"](store).compile(
        round_id=round_record.id,
        technical_package_id="technical-package",
        human_brief_id="human-brief",
        working_brief=brief,
        blueprint_target=target,
        decision_entries=decisions,
        readiness=readiness() if readiness_input is None else readiness_input,
    )
