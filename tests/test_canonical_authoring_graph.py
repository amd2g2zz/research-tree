from __future__ import annotations

import pytest
from canonical_finding_fixture import RUN_ID, canonical_context


def test_canonical_blueprint_target_compiler_is_public() -> None:
    from research_tree import CanonicalBlueprintTargetCompiler

    assert CanonicalBlueprintTargetCompiler.__name__ == "CanonicalBlueprintTargetCompiler"


def test_canonical_intent_model_compiler_is_public() -> None:
    from research_tree import CanonicalIntentModelCompiler

    assert CanonicalIntentModelCompiler.__name__ == "CanonicalIntentModelCompiler"


def test_canonical_working_brief_compiler_is_public() -> None:
    from research_tree import CanonicalWorkingBriefCompiler

    assert CanonicalWorkingBriefCompiler.__name__ == "CanonicalWorkingBriefCompiler"


def test_canonical_input_intake_service_is_public() -> None:
    from research_tree import CanonicalInputIntakeService

    assert CanonicalInputIntakeService.__name__ == "CanonicalInputIntakeService"


def test_legacy_authoring_services_are_not_published() -> None:
    import research_tree
    from research_tree import decision_map, intake, intent, work_items

    assert not hasattr(research_tree, "BlueprintTargetCompiler")
    assert not hasattr(research_tree, "InputIntakeService")
    assert not hasattr(research_tree, "IntentModelCompiler")
    assert not hasattr(research_tree, "WorkingBriefCompiler")
    assert not hasattr(research_tree, "WorkItemCompiler")
    assert not hasattr(research_tree, "WorkItemPlanner")
    assert not hasattr(research_tree, "WorkItemStatusService")
    assert not hasattr(decision_map, "BlueprintTargetCompiler")
    assert not hasattr(intake, "InputIntakeService")
    assert not hasattr(intent, "IntentModelCompiler")
    assert not hasattr(intent, "WorkingBriefCompiler")
    assert not hasattr(work_items, "WorkItemCompiler")
    assert not hasattr(work_items, "WorkItemPlanner")
    assert not hasattr(work_items, "WorkItemStatusService")


def test_canonical_work_item_compiler_requires_current_revision(tmp_path) -> None:
    from research_tree import ArtifactRef, CanonicalWorkItemCompiler, LedgerConflictError

    ledger, _resolver, _record, _model, _brief, target, *_rest = canonical_context(tmp_path)
    compiler = CanonicalWorkItemCompiler(ledger)
    expected_revision = ledger.get_revision(RUN_ID)
    arguments = {
        "round_id": RUN_ID,
        "work_item_id": "work-item-next",
        "blueprint_target": target,
        "decision_slot_id": "slot-isolation",
        "kind": "repository_analysis",
        "scope": "Inspect the first canonical isolation boundary.",
        "exclusions": "Do not close the decision slot.",
        "decision_change_reason": "The result can revise the chosen boundary.",
        "depends_on": (),
        "methods": ("repository_inspection",),
        "budget": {"tool_calls": 4, "time": "bounded"},
        "completion_rule": "Return a bounded Finding Pack.",
    }

    written = compiler.compile(**arguments, expected_revision=expected_revision)

    assert written.parent_refs == (ArtifactRef(RUN_ID, target.id, target.revision),)
    with pytest.raises(LedgerConflictError):
        compiler.compile(**{**arguments, "work_item_id": "work-item-stale"}, expected_revision=expected_revision)


def test_canonical_work_item_planner_appends_through_one_ledger(tmp_path) -> None:
    from research_tree import CanonicalWorkItemPlanner

    ledger, _resolver, _record, _model, _brief, target, *_rest = canonical_context(tmp_path)

    planned = CanonicalWorkItemPlanner(ledger).plan(
        round_id=RUN_ID,
        blueprint_target=target,
        work_item_ids={"slot-isolation": "work-item-planned"},
    )

    assert [item.id for item in planned] == ["work-item-planned"]
    assert planned[0].parent_refs[0].artifact_id == target.id


def test_canonical_work_item_status_appends_exact_work_and_target_lineage(tmp_path) -> None:
    from research_tree import (
        CanonicalWorkItemCompiler,
        CanonicalWorkItemStatusService,
    )
    from research_tree.domain import thaw_json

    ledger, _resolver, _record, _model, _brief, target, *_rest = canonical_context(tmp_path)
    work = CanonicalWorkItemCompiler(ledger).compile(
        round_id=RUN_ID,
        work_item_id="work-item-status",
        blueprint_target=target,
        decision_slot_id="slot-isolation",
        kind="repository_analysis",
        scope="Inspect the canonical isolation boundary.",
        exclusions="Do not close the decision slot.",
        decision_change_reason="The result can revise the chosen boundary.",
        depends_on=(),
        methods=("repository_inspection",),
        budget={"tool_calls": 4, "time": "bounded"},
        completion_rule="Return a bounded Finding Pack.",
        expected_revision=ledger.get_revision(RUN_ID),
    )
    closed_payload = thaw_json(target.payload)
    closed_slot = dict(closed_payload["slots"][0])
    closed_slot["status"] = "selected"
    closed_payload["slots"] = [closed_slot]
    closed_target = ledger.append_artifact(
        RUN_ID,
        target.id,
        target.kind,
        closed_payload,
        parent_refs=target.parent_refs,
        expected_revision=ledger.get_revision(RUN_ID),
    )

    updated = CanonicalWorkItemStatusService(ledger).update(
        round_id=RUN_ID,
        work_item=work,
        blueprint_target=closed_target,
        status="cancelled",
        reason="The decision has been superseded.",
        expected_revision=ledger.get_revision(RUN_ID),
    )

    assert updated.parent_refs[0].artifact_id == work.id
    assert updated.parent_refs[1].revision == closed_target.revision


def test_canonical_input_intake_requires_current_revision_and_persists_bundle_lineage(tmp_path) -> None:
    from research_tree import ArtifactRef, CanonicalInputIntakeService, LedgerConflictError, RunLedger

    ledger = RunLedger(tmp_path / "intake-ledger")
    ledger.initialize()
    ledger.create_run("round-intake")
    intake = CanonicalInputIntakeService(ledger)

    initial_revision = ledger.get_revision("round-intake")
    source = intake.ingest_text(
        round_id="round-intake",
        input_id="input-source",
        kind="brief",
        content="Preserve exact lineage for the canonical intake.",
        origin_type="user",
        origin_locator="conversation:1",
        expected_revision=initial_revision,
    )
    bundle = intake.create_context_bundle(
        round_id="round-intake",
        input_id="input-context",
        member_input_ids=[source.id],
        origin_type="user",
        origin_locator="conversation:1",
        expected_revision=ledger.get_revision("round-intake"),
    )

    assert bundle.parent_refs == (ArtifactRef("round-intake", source.id, source.revision),)
    with pytest.raises(LedgerConflictError):
        intake.ingest_text(
            round_id="round-intake",
            input_id="input-stale",
            kind="note",
            content="A stale writer must not append an input.",
            origin_type="user",
            origin_locator="conversation:2",
            expected_revision=initial_revision,
        )


def test_canonical_blueprint_target_requires_current_ledger_revision(tmp_path) -> None:
    from research_tree import CanonicalBlueprintTargetCompiler, LedgerConflictError

    ledger, _resolver, _record, _model, brief, target, *_rest = canonical_context(tmp_path)
    compiler = CanonicalBlueprintTargetCompiler(ledger)
    expected_revision = ledger.get_revision(RUN_ID)
    change = {
        "kind": "initial",
        "reason": "Create an independently addressed canonical target.",
        "from_slot_ids": [],
        "to_slot_ids": ["slot-isolation"],
    }

    written = compiler.compile(
        round_id=RUN_ID,
        target_id="blueprint-target-next",
        working_brief=brief,
        slots=target.payload["slots"],
        change=change,
        expected_revision=expected_revision,
    )

    assert written.parent_refs[-2:] == (
        type(written.parent_refs[0])(RUN_ID, brief.id, brief.revision),
        type(written.parent_refs[0])(RUN_ID, "intent-model", 1),
    )
    with pytest.raises(LedgerConflictError):
        compiler.compile(
            round_id=RUN_ID,
            target_id="blueprint-target-stale",
            working_brief=brief,
            slots=target.payload["slots"],
            change=change,
            expected_revision=expected_revision,
        )


def test_canonical_working_brief_rejects_a_model_without_input_lineage(tmp_path) -> None:
    from research_tree import CanonicalWorkingBriefCompiler, InvalidWorkingBriefError

    ledger, _resolver, _record, model, _brief, _target, *_rest = canonical_context(tmp_path)
    with pytest.raises(InvalidWorkingBriefError, match="input_ids"):
        CanonicalWorkingBriefCompiler(ledger).compile(
            round_id=RUN_ID,
            brief_id="working-brief-next",
            intent_model=model,
            triggers=[],
            context_bundle_ids=["input-context"],
            selected_input_ids=["input-brief", "input-repository"],
            input_roles={"input-brief": "primary", "input-repository": "baseline"},
            material_conflicts=[],
            working_interpretation="The canonical model remains the current interpretation.",
            technical_outcome="Create the next lineage-bound brief.",
            expected_revision=ledger.get_revision(RUN_ID),
        )
