from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest


def api():
    from research_tree import (
        BlueprintTargetCompiler,
        CanonicalBlueprintTargetCompiler,
        CanonicalInputIntakeService,
        CanonicalIntentModelCompiler,
        CanonicalWorkingBriefCompiler,
        InputIntakeService,
        IntentModelCompiler,
        InvalidBlueprintTargetError,
        RunStore,
        RunLedger,
        WorkingBriefCompiler,
    )

    return {
        "BlueprintTargetCompiler": BlueprintTargetCompiler,
        "CanonicalBlueprintTargetCompiler": CanonicalBlueprintTargetCompiler,
        "CanonicalInputIntakeService": CanonicalInputIntakeService,
        "CanonicalIntentModelCompiler": CanonicalIntentModelCompiler,
        "CanonicalWorkingBriefCompiler": CanonicalWorkingBriefCompiler,
        "InputIntakeService": InputIntakeService,
        "IntentModelCompiler": IntentModelCompiler,
        "InvalidBlueprintTargetError": InvalidBlueprintTargetError,
        "RunStore": RunStore,
        "RunLedger": RunLedger,
        "WorkingBriefCompiler": WorkingBriefCompiler,
    }


def repository(root: Path) -> Path:
    root.mkdir()
    (root / "src").mkdir()
    (root / "src" / "agent.py").write_text(
        "def run() -> str:\n    return 'ready'\n",
        encoding="utf-8",
    )
    (root / "tests").mkdir()
    (root / "tests" / "test_agent.py").write_text(
        "from src.agent import run\n\ndef test_run():\n    assert run() == 'ready'\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        "[project]\nname = 'fixture'\nversion = '0.0.0'\n",
        encoding="utf-8",
    )
    return root


def intent_analysis(input_ids: tuple[str, ...]) -> dict[str, object]:
    signals = [
        {
            "input_id": "input-brief",
            "observation": "The requester needs a buildable autonomous reverse-engineering agent.",
            "kind": "stated_goal",
            "authority_boundary": "It does not select an isolation architecture.",
        }
    ]
    if "input-repository" in input_ids:
        signals.append(
            {
                "input_id": "input-repository",
                "observation": "The repository has a src/agent.py run boundary.",
                "kind": "repository_fact",
                "authority_boundary": "It records current structure, not a future design decision.",
            }
        )
    return {
        "signals": signals,
        "hypotheses": [
            {
                "id": "intent-agent",
                "interpretation": "Deliver a safe, implementation-ready autonomous agent path.",
                "status": "leading",
                "signal_refs": list(input_ids),
                "confidence": "medium",
                "decision_consequence": "Isolation and integration boundaries must be researched.",
                "validation": "repository_inspection",
            }
        ],
        "desired_outcomes": ["implementation-ready technical blueprint"],
        "success_signals": ["an implementation agent can start without rediscovery"],
        "decision_drivers": [
            {
                "dimension": "technical",
                "statement": "The first implementation must be safe to inspect and evolve.",
                "signal_refs": ["input-brief"],
            }
        ],
        "hard_constraints": ["Do not execute untrusted binaries during intake."],
        "non_goals": ["Do not require a user questionnaire."],
        "unresolved_interpretations": [],
    }


def context(tmp_path: Path, *, with_repository: bool = True):
    modules = api()
    store = modules["RunStore"](tmp_path / "store")
    round_record = store.create_round("round-map")
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
    input_ids = ("input-brief",)
    if with_repository:
        intake.ingest_repository(
            round_id=round_record.id,
            input_id="input-repository",
            repository_root=repository(tmp_path / "repository"),
            origin_type="workspace",
            role="baseline",
        )
        input_ids = ("input-brief", "input-repository")
    intake.create_context_bundle(
        round_id=round_record.id,
        input_id="input-context",
        member_input_ids=input_ids,
        origin_type="user",
        origin_locator="conversation:1",
        role="baseline",
    )
    model = modules["IntentModelCompiler"](store).compile(
        round_id=round_record.id,
        intent_id="intent-model",
        context_bundle_ids=("input-context",),
        input_ids=input_ids,
        analysis=intent_analysis(input_ids),
    )
    roles = {"input-brief": "primary"}
    if with_repository:
        roles["input-repository"] = "baseline"
    brief = modules["WorkingBriefCompiler"](store).compile(
        round_id=round_record.id,
        brief_id="working-brief",
        intent_model=model,
        triggers=[{"kind": "initial_request", "text": "Start", "input_ids": ["input-brief"]}],
        context_bundle_ids=("input-context",),
        selected_input_ids=input_ids,
        input_roles=roles,
        material_conflicts=[],
        working_interpretation="A safe implementation-ready agent path is the leading intent.",
        technical_outcome="Choose the architecture and integration boundary for the first agent.",
    )
    return modules, store, round_record, brief


def canonical_context(tmp_path: Path, *, with_repository: bool = True):
    modules = api()
    ledger = modules["RunLedger"](tmp_path / "ledger")
    ledger.initialize()
    round_record = ledger.create_run("round-map")
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
    input_ids = ("input-brief",)
    if with_repository:
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
        analysis=intent_analysis(input_ids),
        expected_revision=ledger.get_revision(round_record.id),
    )
    roles = {"input-brief": "primary"}
    if with_repository:
        roles["input-repository"] = "baseline"
    brief = modules["CanonicalWorkingBriefCompiler"](ledger).compile(
        round_id=round_record.id,
        brief_id="working-brief",
        intent_model=model,
        triggers=[{"kind": "initial_request", "text": "Start", "input_ids": ["input-brief"]}],
        context_bundle_ids=("input-context",),
        selected_input_ids=input_ids,
        input_roles=roles,
        material_conflicts=[],
        working_interpretation="A safe implementation-ready agent path is the leading intent.",
        technical_outcome="Choose the architecture and integration boundary for the first agent.",
        expected_revision=ledger.get_revision(round_record.id),
    )
    return modules, ledger, round_record, brief


def slot(slot_id: str, *, priority: str = "P0", with_repository: bool = True) -> dict[str, object]:
    return {
        "id": slot_id,
        "kind": "architecture",
        "question": f"Which isolation boundary should {slot_id} use?",
        "intent_hypothesis_ids": ["intent-agent"],
        "priority": priority,
        "impact": "high",
        "uncertainty": "high",
        "irreversibility": "high",
        "constraints": [
            {
                "kind": "input",
                "ref": "input-brief",
                "statement": "The result must support a safe first implementation.",
            }
        ],
        "alternatives": ["isolated-worker", "in-process"],
        "repository_touchpoints": (
            [{"path": "src/agent.py", "symbol": "run"}] if with_repository else []
        ),
        "greenfield_assumptions": ([] if with_repository else ["The initial integration boundary is new."]),
        "depends_on": [],
        "evidence_standard": "repository inspection plus a bounded spike",
        "validation": {"kind": "spike", "oracle": "one fixture completes through the selected boundary"},
        "closure_rule": "select, conditionally select, defer with fallback, or block",
        "status": "open",
        "bounded_research_need": "compare the two alternatives against the current boundary",
        "fallback": "retain the current boundary until this decision closes",
    }


def initial_change(*slot_ids: str) -> dict[str, object]:
    return {
        "kind": "initial",
        "reason": "Map the implementation decisions implied by the Working Brief.",
        "from_slot_ids": [],
        "to_slot_ids": list(slot_ids),
    }


def compile_target(modules, store, round_record, brief, slots, change):
    return modules["BlueprintTargetCompiler"](store).compile(
        round_id=round_record.id,
        target_id="blueprint-target",
        working_brief=brief,
        slots=slots,
        change=change,
    )


def compile_canonical_target(modules, ledger, round_record, brief, slots, change):
    return modules["CanonicalBlueprintTargetCompiler"](ledger).compile(
        round_id=round_record.id,
        target_id="blueprint-target",
        working_brief=brief,
        slots=slots,
        change=change,
        expected_revision=ledger.get_revision(round_record.id),
    )


def test_repository_backed_target_preserves_brief_model_and_anchor_lineage(tmp_path: Path) -> None:
    modules, ledger, round_record, brief = canonical_context(tmp_path)
    target = compile_canonical_target(
        modules,
        ledger,
        round_record,
        brief,
        [slot("slot-architecture")],
        initial_change("slot-architecture"),
    )

    assert target.kind == "blueprint-target"
    assert target.payload["brief_id"] == brief.id
    assert target.payload["intent_model_id"] == "intent-model"
    assert target.payload["slots"][0]["repository_touchpoints"] == (
        {"path": "src/agent.py", "symbol": "run"},
    )
    assert target.parent_refs[0].artifact_id == brief.id
    rehydrated = modules["RunLedger"](ledger.workspace).load_run(round_record.id)
    assert target in rehydrated.artifacts


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("intent_hypothesis_ids", []),
        ("intent_hypothesis_ids", ["intent-unknown"]),
        ("alternatives", []),
        ("bounded_research_need", ""),
        ("bounded_research_need", "   "),
        ("validation", {"kind": "spike", "oracle": ""}),
        ("fallback", ""),
    ],
)
def test_p0_slot_requires_owned_bounded_and_reversible_closure(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    modules, ledger, round_record, brief = canonical_context(tmp_path)
    invalid = slot("slot-architecture")
    invalid[field] = value

    with pytest.raises(modules["InvalidBlueprintTargetError"]):
        compile_canonical_target(
            modules,
            ledger,
            round_record,
            brief,
            [invalid],
            initial_change("slot-architecture"),
        )

    assert [artifact for artifact in ledger.load_run(round_record.id).artifacts if artifact.kind == "blueprint-target"] == []


def test_anchor_greenfield_and_dependency_failures_are_rejected_before_append(tmp_path: Path) -> None:
    modules, ledger, round_record, brief = canonical_context(tmp_path)
    invalid_anchor = slot("slot-architecture")
    invalid_anchor["repository_touchpoints"] = [{"path": "src/missing.py", "symbol": "run"}]
    with pytest.raises(modules["InvalidBlueprintTargetError"]):
        compile_canonical_target(
            modules,
            ledger,
            round_record,
            brief,
            [invalid_anchor],
            initial_change("slot-architecture"),
        )

    first = slot("slot-one")
    second = slot("slot-two")
    first["depends_on"] = ["slot-two"]
    second["depends_on"] = ["slot-one"]
    with pytest.raises(modules["InvalidBlueprintTargetError"]):
        compile_canonical_target(
            modules,
            ledger,
            round_record,
            brief,
            [first, second],
            initial_change("slot-one", "slot-two"),
        )

    no_repo_modules, no_repo_ledger, no_repo_round, no_repo_brief = canonical_context(
        tmp_path / "greenfield", with_repository=False
    )
    missing_assumption = slot("slot-greenfield", with_repository=False)
    missing_assumption["greenfield_assumptions"] = []
    with pytest.raises(no_repo_modules["InvalidBlueprintTargetError"]):
        compile_canonical_target(
            no_repo_modules,
            no_repo_ledger,
            no_repo_round,
            no_repo_brief,
            [missing_assumption],
            initial_change("slot-greenfield"),
        )


def test_controlled_add_split_merge_reprioritize_and_remove_append_revisions(tmp_path: Path) -> None:
    modules, store, round_record, brief = context(tmp_path)
    architecture = slot("slot-architecture", priority="P1")
    operations = modules["BlueprintTargetCompiler"](store)
    first = operations.compile(
        round_id=round_record.id,
        target_id="blueprint-target",
        working_brief=brief,
        slots=[architecture],
        change=initial_change("slot-architecture"),
    )
    security = slot("slot-security")
    added = operations.compile(
        round_id=round_record.id,
        target_id="blueprint-target",
        working_brief=brief,
        slots=[architecture, security],
        change={
            "kind": "add",
            "reason": "Repository inspection exposed a security boundary.",
            "from_slot_ids": [],
            "to_slot_ids": ["slot-security"],
        },
    )
    storage = slot("slot-storage")
    interface = slot("slot-interface")
    split = operations.compile(
        round_id=round_record.id,
        target_id="blueprint-target",
        working_brief=brief,
        slots=[architecture, storage, interface],
        change={
            "kind": "split",
            "reason": "Security work separates state and interface decisions.",
            "from_slot_ids": ["slot-security"],
            "to_slot_ids": ["slot-storage", "slot-interface"],
        },
    )
    runtime = slot("slot-runtime")
    merged = operations.compile(
        round_id=round_record.id,
        target_id="blueprint-target",
        working_brief=brief,
        slots=[architecture, runtime],
        change={
            "kind": "merge",
            "reason": "The two decisions converge on one runtime boundary.",
            "from_slot_ids": ["slot-storage", "slot-interface"],
            "to_slot_ids": ["slot-runtime"],
        },
    )
    reprioritized_architecture = deepcopy(architecture)
    reprioritized_architecture["priority"] = "P0"
    reprioritized = operations.compile(
        round_id=round_record.id,
        target_id="blueprint-target",
        working_brief=brief,
        slots=[reprioritized_architecture, runtime],
        change={
            "kind": "reprioritize",
            "reason": "The architecture boundary blocks all remaining work.",
            "from_slot_ids": ["slot-architecture"],
            "to_slot_ids": ["slot-architecture"],
        },
    )
    removed = operations.compile(
        round_id=round_record.id,
        target_id="blueprint-target",
        working_brief=brief,
        slots=[reprioritized_architecture],
        change={
            "kind": "remove",
            "reason": "Runtime work is no longer needed in this round.",
            "from_slot_ids": ["slot-runtime"],
            "to_slot_ids": [],
        },
    )

    assert [target.revision for target in (first, added, split, merged, reprioritized, removed)] == [1, 2, 3, 4, 5, 6]
    assert removed.parent_refs[0].artifact_id == first.id
    assert removed.parent_refs[0].revision == reprioritized.revision
    assert removed.payload["change"]["kind"] == "remove"


def test_invalid_revision_change_is_rejected_without_a_new_target_revision(tmp_path: Path) -> None:
    modules, store, round_record, brief = context(tmp_path)
    first = compile_target(
        modules,
        store,
        round_record,
        brief,
        [slot("slot-architecture")],
        initial_change("slot-architecture"),
    )
    with pytest.raises(modules["InvalidBlueprintTargetError"]):
        compile_target(
            modules,
            store,
            round_record,
            brief,
            [slot("slot-architecture")],
            {
                "kind": "add",
                "reason": "This does not add a new decision.",
                "from_slot_ids": [],
                "to_slot_ids": ["slot-architecture"],
            },
        )

    targets = [artifact for artifact in store.load_round(round_record.id).artifacts if artifact.kind == "blueprint-target"]
    assert targets == [first]


def test_target_id_cannot_reuse_an_input_artifact_id(tmp_path: Path) -> None:
    modules, store, round_record, brief = context(tmp_path)

    with pytest.raises(modules["InvalidBlueprintTargetError"]):
        modules["BlueprintTargetCompiler"](store).compile(
            round_id=round_record.id,
            target_id="input-brief",
            working_brief=brief,
            slots=[slot("slot-architecture")],
            change=initial_change("slot-architecture"),
        )


def test_target_revision_cannot_switch_to_a_new_working_brief_revision(tmp_path: Path) -> None:
    modules, store, round_record, brief = context(tmp_path)
    first = compile_target(
        modules,
        store,
        round_record,
        brief,
        [slot("slot-architecture")],
        initial_change("slot-architecture"),
    )
    model = next(
        artifact
        for artifact in store.load_round(round_record.id).artifacts
        if artifact.id == "intent-model"
    )
    newer_brief = modules["WorkingBriefCompiler"](store).compile(
        round_id=round_record.id,
        brief_id="working-brief",
        intent_model=model,
        triggers=[{"kind": "new_material", "text": "Refine", "input_ids": ["input-brief"]}],
        context_bundle_ids=("input-context",),
        selected_input_ids=("input-brief", "input-repository"),
        input_roles={"input-brief": "primary", "input-repository": "baseline"},
        material_conflicts=[],
        working_interpretation="The same technical outcome remains leading.",
        technical_outcome="Choose the architecture and integration boundary for the first agent.",
    )

    with pytest.raises(modules["InvalidBlueprintTargetError"]):
        compile_target(
            modules,
            store,
            round_record,
            newer_brief,
            [slot("slot-architecture"), slot("slot-security")],
            {
                "kind": "add",
                "reason": "A new decision appears in the revised Brief.",
                "from_slot_ids": [],
                "to_slot_ids": ["slot-security"],
            },
        )

    targets = [artifact for artifact in store.load_round(round_record.id).artifacts if artifact.kind == "blueprint-target"]
    assert targets == [first]
