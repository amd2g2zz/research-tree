from __future__ import annotations

from pathlib import Path

import pytest

from test_deliveries import (
    compile_deliveries,
    context,
    decision_kwargs,
    intent_analysis,
    readiness,
    slot,
)
from research_tree.domain import thaw_json


def api():
    from research_tree import (
        InvalidReadinessError,
        ReadinessVerifier,
        readiness_for_delivery,
    )

    return {
        "InvalidReadinessError": InvalidReadinessError,
        "ReadinessVerifier": ReadinessVerifier,
        "readiness_for_delivery": readiness_for_delivery,
    }


def package_context(tmp_path: Path):
    modules, store, round_record, model, brief, target, finding, decision = context(tmp_path)
    deliveries = compile_deliveries(
        modules,
        store,
        round_record,
        brief,
        target,
        [decision],
    )
    return (
        modules,
        store,
        round_record,
        model,
        brief,
        target,
        finding,
        decision,
        deliveries.technical_package,
    )


def verify(readiness_modules, store, round_record, technical_package, *, root: Path, risk_tier: str):
    return readiness_modules["ReadinessVerifier"](store).verify(
        round_id=round_record.id,
        readiness_id="readiness-record",
        technical_package=technical_package,
        repository_roots={"input-repository": root},
        risk_tier=risk_tier,
    )


def complete_conditional_package(tmp_path: Path):
    modules, store, round_record, model, brief, target, finding, decision = context(tmp_path)
    observability_work = next(
        artifact
        for artifact in store.load_round(round_record.id).artifacts
        if artifact.id == "work-observability"
    )
    from research_tree import FindingPackCompiler

    observability_finding = FindingPackCompiler(store).compile(
        allow_legacy_evidence=True,
        round_id=round_record.id,
        finding_id="finding-observability",
        work_item=observability_work,
        observations=[
            {
                "claim": "The existing run boundary can emit structured observability events.",
                "anchor": {"kind": "repository", "ref": "src/agent.py:run"},
                "applicability": "the supplied Python repository",
                "confidence": "medium",
                "limitation": "The event schema still needs a bounded spike.",
            }
        ],
        option_effects=[{"option": "structured-logging", "effect": "supports"}],
        implementation_implications=["The adapter emits structured events."],
        remaining_uncertainties=["Measure event overhead."],
    )
    kwargs = decision_kwargs(target, observability_finding)
    kwargs.update(
        {
            "decision_slot_id": "slot-observability",
            "selected_option": "structured-logging",
            "alternatives": [
                {
                    "option": "minimal-logging",
                    "disposition": "deferred",
                    "reason": "A bounded schema spike remains necessary.",
                }
            ],
            "design_consequence": "Emit structured events from src/agent.py:run.",
            "change_tasks": [
                {
                    "id": "change-observability",
                    "description": "Emit the selected observability event.",
                    "acceptance_oracle": "The fixture records the expected event.",
                    "repository_touchpoints": [
                        {"path": "src/agent.py", "symbol": "run"}
                    ],
                }
            ],
            "fallback": "Keep minimal logging until the event schema passes its spike.",
            "reversal_condition": "The event spike exceeds the latency budget.",
        }
    )
    observability_decision = modules["DecisionLedgerCompiler"](store).converge(
        round_id=round_record.id,
        decision_id="decision-observability",
        **kwargs,
    )
    package_readiness = readiness()
    package_readiness["gates"]["decision_closure"] = "pass"
    package_readiness["gates"]["implementation_readiness"] = "pass"
    deliveries = compile_deliveries(
        modules,
        store,
        round_record,
        brief,
        target,
        [decision, observability_decision],
        readiness_input=package_readiness,
    )
    return modules, store, round_record, deliveries.technical_package


def greenfield_package(tmp_path: Path):
    modules, store, round_record, model, brief, _target, _finding, _decision = context(tmp_path)
    greenfield_slot = slot(
        "slot-greenfield",
        kind="architecture",
        priority="P0",
        alternatives=["new-worker", "retain-boundary"],
    )
    greenfield_slot["repository_touchpoints"] = []
    greenfield_slot["greenfield_assumptions"] = [
        "The first worker implementation is a new isolated component."
    ]
    target = modules["BlueprintTargetCompiler"](store).compile(
        round_id=round_record.id,
        target_id="greenfield-target",
        working_brief=brief,
        slots=[greenfield_slot],
        change={
            "kind": "initial",
            "reason": "The selected surface is a new component.",
            "from_slot_ids": [],
            "to_slot_ids": ["slot-greenfield"],
        },
    )
    work = modules["WorkItemPlanner"](store).plan(
        round_id=round_record.id,
        blueprint_target=target,
        work_item_ids={"slot-greenfield": "work-greenfield"},
    )[0]
    from research_tree import FindingPackCompiler

    finding = FindingPackCompiler(store).compile(
        allow_legacy_evidence=True,
        round_id=round_record.id,
        finding_id="finding-greenfield",
        work_item=work,
        observations=[
            {
                "claim": "The requester authorized a new isolated component.",
                "anchor": {"kind": "input", "ref": "input-brief"},
                "applicability": "the requested first implementation",
                "confidence": "medium",
                "limitation": "No repository surface exists for the new component.",
            }
        ],
        option_effects=[{"option": "new-worker", "effect": "supports"}],
        implementation_implications=["Create the isolated component."],
        remaining_uncertainties=[],
    )
    decision = modules["DecisionLedgerCompiler"](store).converge(
        round_id=round_record.id,
        decision_id="decision-greenfield",
        blueprint_target=target,
        decision_slot_id="slot-greenfield",
        finding_packs=[finding],
        status="selected",
        selected_option="new-worker",
        alternatives=[
            {
                "option": "retain-boundary",
                "disposition": "rejected",
                "reason": "The target explicitly calls for a new component.",
            }
        ],
        anchors=[{"kind": "finding", "ref": finding.id}],
        design_consequence="Create the new isolated worker component.",
        repository_touchpoints=[],
        validation={"kind": "spike", "oracle": "The new component completes one fixture."},
        change_tasks=[
            {
                "id": "change-greenfield",
                "description": "Create the isolated worker component.",
                "acceptance_oracle": "One fixture completes through the new component.",
                "repository_touchpoints": [],
            }
        ],
        assumptions=["The component has no existing repository touchpoint."],
        fallback="Retain the current boundary until the new component is validated.",
        reversal_condition="The new component cannot complete the fixture.",
        revision_reason="Initial greenfield component decision.",
    )
    package_readiness = readiness()
    package_readiness["gates"]["decision_closure"] = "pass"
    package_readiness["gates"]["implementation_readiness"] = "pass"
    deliveries = compile_deliveries(
        modules,
        store,
        round_record,
        brief,
        target,
        [decision],
        readiness_input=package_readiness,
    )
    return store, round_record, deliveries.technical_package


def multi_repository_package(tmp_path: Path):
    modules, store, round_record, _model, _brief, _target, _finding, _decision = context(tmp_path)
    second_root = tmp_path / "repository-two"
    second_root.mkdir()
    (second_root / "src").mkdir()
    (second_root / "src" / "worker.py").write_text(
        "def inspect() -> str:\n    return 'ready'\n",
        encoding="utf-8",
    )
    intake = modules["InputIntakeService"](store)
    intake.ingest_repository(
        round_id=round_record.id,
        input_id="input-repository-two",
        repository_root=second_root,
        origin_type="workspace",
        role="baseline",
    )
    intake.create_context_bundle(
        round_id=round_record.id,
        input_id="input-context-multi",
        member_input_ids=("input-brief", "input-repository", "input-repository-two"),
        origin_type="user",
        origin_locator="conversation:multi-repository",
        role="baseline",
    )
    analysis = intent_analysis()
    analysis["signals"].append(
        {
            "input_id": "input-repository-two",
            "observation": "The second repository owns the worker inspection boundary.",
            "kind": "repository_fact",
            "authority_boundary": "It records the observed second-repository boundary.",
        }
    )
    analysis["hypotheses"][0]["signal_refs"].append("input-repository-two")
    model = modules["IntentModelCompiler"](store).compile(
        round_id=round_record.id,
        intent_id="intent-multi",
        context_bundle_ids=("input-context-multi",),
        input_ids=("input-brief", "input-repository", "input-repository-two"),
        analysis=analysis,
    )
    brief = modules["WorkingBriefCompiler"](store).compile(
        round_id=round_record.id,
        brief_id="working-brief-multi",
        intent_model=model,
        triggers=[
            {"kind": "initial_request", "text": "Start", "input_ids": ["input-brief"]}
        ],
        context_bundle_ids=("input-context-multi",),
        selected_input_ids=("input-brief", "input-repository", "input-repository-two"),
        input_roles={
            "input-brief": "primary",
            "input-repository": "baseline",
            "input-repository-two": "baseline",
        },
        material_conflicts=[],
        working_interpretation="The second repository owns the leading implementation boundary.",
        technical_outcome="Choose an integration boundary in the second repository.",
    )
    second_slot = slot(
        "slot-second-repository",
        kind="architecture",
        priority="P0",
        alternatives=["isolated-worker", "in-process"],
    )
    second_slot["repository_touchpoints"] = [{"path": "src/worker.py", "symbol": "inspect"}]
    target = modules["BlueprintTargetCompiler"](store).compile(
        round_id=round_record.id,
        target_id="blueprint-target-multi",
        working_brief=brief,
        slots=[second_slot],
        change={
            "kind": "initial",
            "reason": "The implementation surface is in the second repository.",
            "from_slot_ids": [],
            "to_slot_ids": ["slot-second-repository"],
        },
    )
    work = modules["WorkItemPlanner"](store).plan(
        round_id=round_record.id,
        blueprint_target=target,
        work_item_ids={"slot-second-repository": "work-second-repository"},
    )[0]
    from research_tree import FindingPackCompiler

    finding = FindingPackCompiler(store).compile(
        allow_legacy_evidence=True,
        round_id=round_record.id,
        finding_id="finding-second-repository",
        work_item=work,
        observations=[
            {
                "claim": "The second repository exposes the worker inspection boundary.",
                "anchor": {"kind": "repository", "ref": "src/worker.py:inspect"},
                "applicability": "the supplied second repository",
                "confidence": "medium",
                "limitation": "Production overhead remains to be measured.",
            }
        ],
        option_effects=[{"option": "isolated-worker", "effect": "supports"}],
        implementation_implications=["Add the adapter in the second repository."],
        remaining_uncertainties=["Measure worker startup overhead."],
    )
    kwargs = decision_kwargs(target, finding)
    kwargs.update(
        {
            "decision_slot_id": "slot-second-repository",
            "repository_touchpoints": [{"path": "src/worker.py", "symbol": "inspect"}],
            "design_consequence": "Add a worker adapter at src/worker.py:inspect.",
            "change_tasks": [
                {
                    "id": "change-second-worker",
                    "description": "Introduce the selected second-repository adapter.",
                    "acceptance_oracle": "The second repository fixture crosses the adapter.",
                    "repository_touchpoints": [
                        {"path": "src/worker.py", "symbol": "inspect"}
                    ],
                }
            ],
        }
    )
    decision = modules["DecisionLedgerCompiler"](store).converge(
        round_id=round_record.id,
        decision_id="decision-second-repository",
        **kwargs,
    )
    package_readiness = readiness()
    package_readiness["gates"]["decision_closure"] = "pass"
    package_readiness["gates"]["implementation_readiness"] = "pass"
    technical_package = compile_deliveries(
        modules,
        store,
        round_record,
        brief,
        target,
        [decision],
        readiness_input=package_readiness,
    ).technical_package
    return store, round_record, technical_package, tmp_path / "repository", second_root


def test_verifier_names_missing_closure_and_recommends_targeted_work(tmp_path: Path) -> None:
    readiness_modules = api()
    (
        _modules,
        store,
        round_record,
        _model,
        _brief,
        _target,
        _finding,
        _decision,
        technical_package,
    ) = package_context(tmp_path)

    record = verify(
        readiness_modules,
        store,
        round_record,
        technical_package,
        root=tmp_path / "repository",
        risk_tier="medium",
    )
    delivery_readiness = readiness_modules["readiness_for_delivery"](record)
    diagnostics = record.payload["diagnostics"]
    closure = next(item for item in diagnostics if item["gate"] == "decision_closure")

    assert record.kind == "readiness-record"
    assert delivery_readiness["gates"]["decision_closure"] == "fail"
    assert closure["decision_slot_id"] == "slot-observability"
    assert closure["status"] == "fail"
    assert closure["recommended_work"]["decision_slot_id"] == "slot-observability"
    assert delivery_readiness["next_work_item_ids"] == (
        closure["recommended_work"]["id"],
    )
    assert delivery_readiness["gates"]["implementation_readiness"] == "pass"
    assert technical_package.parent_refs[0] in record.parent_refs


def test_conditional_decisions_with_oracles_can_close_readiness(tmp_path: Path) -> None:
    readiness_modules = api()
    _modules, store, round_record, technical_package = complete_conditional_package(tmp_path)

    record = verify(
        readiness_modules,
        store,
        round_record,
        technical_package,
        root=tmp_path / "repository",
        risk_tier="medium",
    )

    gates = readiness_modules["readiness_for_delivery"](record)["gates"]
    assert gates["decision_closure"] == "pass"
    assert gates["implementation_readiness"] == "pass"
    assert not [
        item for item in record.payload["diagnostics"] if item["gate"] == "decision_closure"
    ]


def test_greenfield_assumptions_make_repository_fit_not_applicable(tmp_path: Path) -> None:
    readiness_modules = api()
    store, round_record, technical_package = greenfield_package(tmp_path)

    record = verify(
        readiness_modules,
        store,
        round_record,
        technical_package,
        root=tmp_path / "repository",
        risk_tier="default",
    )

    assert readiness_modules["readiness_for_delivery"](record)["gates"]["repository_fit"] == "not_applicable"
    assert record.payload["repository_anchor_checks"] == ()


def test_repository_fit_routes_a_touchpoint_to_its_observed_repository(tmp_path: Path) -> None:
    readiness_modules = api()
    store, round_record, technical_package, first_root, second_root = multi_repository_package(tmp_path)

    record = readiness_modules["ReadinessVerifier"](store).verify(
        round_id=round_record.id,
        readiness_id="readiness-multi-repository",
        technical_package=technical_package,
        repository_roots={
            "input-repository": first_root,
            "input-repository-two": second_root,
        },
        risk_tier="medium",
    )

    assert readiness_modules["readiness_for_delivery"](record)["gates"]["repository_fit"] == "pass"
    assert record.payload["repository_anchor_checks"] == (
        {
            "input_id": "input-repository-two",
            "path": "src/worker.py",
            "symbol": "inspect",
            "resolved": True,
            "reason": "path and top-level Python symbol resolve",
        },
    )


def test_repository_fit_resolves_paths_without_executing_repository_code(tmp_path: Path) -> None:
    readiness_modules = api()
    (
        _modules,
        store,
        round_record,
        _model,
        _brief,
        _target,
        _finding,
        _decision,
        technical_package,
    ) = package_context(tmp_path)
    alternate_root = tmp_path / "alternate-repository"
    alternate_root.mkdir()

    record = verify(
        readiness_modules,
        store,
        round_record,
        technical_package,
        root=alternate_root,
        risk_tier="medium",
    )
    delivery_readiness = readiness_modules["readiness_for_delivery"](record)
    repository_diagnostic = next(
        item for item in record.payload["diagnostics"] if item["gate"] == "repository_fit"
    )

    assert delivery_readiness["gates"]["repository_fit"] == "fail"
    assert repository_diagnostic["decision_slot_id"] == "slot-isolation"
    assert "src/agent.py" in repository_diagnostic["summary"]
    checks = record.payload["repository_anchor_checks"]
    assert checks[0]["resolved"] is False


def test_repository_symbol_check_does_not_treat_comments_or_strings_as_definitions(
    tmp_path: Path,
) -> None:
    readiness_modules = api()
    (
        _modules,
        store,
        round_record,
        _model,
        _brief,
        _target,
        _finding,
        _decision,
        technical_package,
    ) = package_context(tmp_path)
    (tmp_path / "repository" / "src" / "agent.py").write_text(
        "# run is no longer a definition\nmessage = 'run'\n",
        encoding="utf-8",
    )

    record = verify(
        readiness_modules,
        store,
        round_record,
        technical_package,
        root=tmp_path / "repository",
        risk_tier="medium",
    )

    assert readiness_modules["readiness_for_delivery"](record)["gates"]["repository_fit"] == "fail"
    assert record.payload["repository_anchor_checks"][0]["resolved"] is False


def test_missing_p0_ledger_names_the_failed_traceability_and_implementation_gates(
    tmp_path: Path,
) -> None:
    readiness_modules = api()
    modules, store, round_record, _model, brief, target, _finding, _decision = context(tmp_path)
    technical_package = compile_deliveries(
        modules,
        store,
        round_record,
        brief,
        target,
        [],
    ).technical_package

    record = verify(
        readiness_modules,
        store,
        round_record,
        technical_package,
        root=tmp_path / "repository",
        risk_tier="medium",
    )
    diagnostics = {
        item["gate"]: item
        for item in record.payload["diagnostics"]
        if item["decision_slot_id"] == "slot-isolation"
    }

    assert diagnostics["traceability"]["status"] == "fail"
    assert diagnostics["implementation_readiness"]["status"] == "fail"
    assert diagnostics["traceability"]["recommended_work"] is not None
    assert diagnostics["implementation_readiness"]["recommended_work"] is not None


def test_high_risk_unknown_operational_handoff_fails_with_a_targeted_recommendation(
    tmp_path: Path,
) -> None:
    readiness_modules = api()
    (
        _modules,
        store,
        round_record,
        _model,
        _brief,
        _target,
        _finding,
        _decision,
        technical_package,
    ) = package_context(tmp_path)

    record = verify(
        readiness_modules,
        store,
        round_record,
        technical_package,
        root=tmp_path / "repository",
        risk_tier="high",
    )
    delivery_readiness = readiness_modules["readiness_for_delivery"](record)
    operational = next(
        item for item in record.payload["diagnostics"] if item["gate"] == "operational_quality"
    )

    assert delivery_readiness["gates"]["operational_quality"] == "fail"
    assert operational["decision_slot_id"] == "slot-observability"
    assert operational["recommended_work"]["id"] in delivery_readiness["next_work_item_ids"]


def test_rehydrated_readiness_keeps_exact_package_and_source_lineage(tmp_path: Path) -> None:
    readiness_modules = api()
    (
        _modules,
        store,
        round_record,
        _model,
        _brief,
        _target,
        _finding,
        decision,
        technical_package,
    ) = package_context(tmp_path)

    record = verify(
        readiness_modules,
        store,
        round_record,
        technical_package,
        root=tmp_path / "repository",
        risk_tier="default",
    )
    rehydrated = type(store)(store.root).load_round(round_record.id)
    stored = next(artifact for artifact in rehydrated.artifacts if artifact == record)

    assert stored.payload == record.payload
    assert technical_package.id == stored.payload["technical_package_ref"]["artifact_id"]
    assert technical_package.revision == stored.payload["technical_package_ref"]["revision"]
    assert next(ref for ref in stored.parent_refs if ref.artifact_id == decision.id).revision == decision.revision


def test_invalid_package_input_leaves_no_readiness_record(tmp_path: Path) -> None:
    readiness_modules = api()
    (
        _modules,
        store,
        round_record,
        _model,
        _brief,
        _target,
        _finding,
        _decision,
        technical_package,
    ) = package_context(tmp_path)

    with pytest.raises(readiness_modules["InvalidReadinessError"]):
        readiness_modules["ReadinessVerifier"](store).verify(
            round_id=round_record.id,
            readiness_id="readiness-record",
            technical_package=technical_package,
            repository_roots={"missing-input": tmp_path / "repository"},
            risk_tier="default",
        )

    assert not [
        artifact
        for artifact in store.load_round(round_record.id).artifacts
        if artifact.kind == "readiness-record"
    ]


def test_package_decision_records_must_match_their_exact_ledger_revisions(
    tmp_path: Path,
) -> None:
    readiness_modules = api()
    (
        _modules,
        store,
        round_record,
        _model,
        _brief,
        _target,
        _finding,
        _decision,
        technical_package,
    ) = package_context(tmp_path)
    corrupted_payload = thaw_json(technical_package.payload)
    corrupted_payload["document"]["decision_records"][0]["decision_id"] = "wrong-decision"
    corrupted = store.append_artifact(
        round_record.id,
        technical_package.id,
        technical_package.kind,
        corrupted_payload,
        parent_refs=technical_package.parent_refs,
    )

    with pytest.raises(readiness_modules["InvalidReadinessError"], match="decision record"):
        verify(
            readiness_modules,
            store,
            round_record,
            corrupted,
            root=tmp_path / "repository",
            risk_tier="default",
        )

    assert not [
        artifact
        for artifact in store.load_round(round_record.id).artifacts
        if artifact.kind == "readiness-record"
    ]


def test_package_decision_records_must_match_exact_ledger_content(tmp_path: Path) -> None:
    readiness_modules = api()
    (
        _modules,
        store,
        round_record,
        _model,
        _brief,
        _target,
        _finding,
        _decision,
        technical_package,
    ) = package_context(tmp_path)
    corrupted_payload = thaw_json(technical_package.payload)
    corrupted_payload["document"]["decision_records"][0]["design_consequence"] = (
        "Invented implementation surface."
    )
    corrupted = store.append_artifact(
        round_record.id,
        technical_package.id,
        technical_package.kind,
        corrupted_payload,
        parent_refs=technical_package.parent_refs,
    )

    with pytest.raises(readiness_modules["InvalidReadinessError"], match="decision record"):
        verify(
            readiness_modules,
            store,
            round_record,
            corrupted,
            root=tmp_path / "repository",
            risk_tier="default",
        )


def test_package_closure_must_match_exact_ledger_selection(tmp_path: Path) -> None:
    readiness_modules = api()
    (
        _modules,
        store,
        round_record,
        _model,
        _brief,
        _target,
        _finding,
        _decision,
        technical_package,
    ) = package_context(tmp_path)
    corrupted_payload = thaw_json(technical_package.payload)
    closure = next(
        item
        for item in corrupted_payload["document"]["blueprint_closure"]
        if item["decision_slot_id"] == "slot-isolation"
    )
    closure["selected_option"] = "in-process"
    corrupted = store.append_artifact(
        round_record.id,
        technical_package.id,
        technical_package.kind,
        corrupted_payload,
        parent_refs=technical_package.parent_refs,
    )

    with pytest.raises(readiness_modules["InvalidReadinessError"], match="closure"):
        verify(
            readiness_modules,
            store,
            round_record,
            corrupted,
            root=tmp_path / "repository",
            risk_tier="default",
        )


def test_missing_ordered_implementation_plan_fails_the_implementation_gate(
    tmp_path: Path,
) -> None:
    readiness_modules = api()
    (
        _modules,
        store,
        round_record,
        _model,
        _brief,
        _target,
        _finding,
        _decision,
        technical_package,
    ) = package_context(tmp_path)
    corrupted_payload = thaw_json(technical_package.payload)
    corrupted_payload["document"]["implementation_plan"] = []
    corrupted = store.append_artifact(
        round_record.id,
        technical_package.id,
        technical_package.kind,
        corrupted_payload,
        parent_refs=technical_package.parent_refs,
    )

    record = verify(
        readiness_modules,
        store,
        round_record,
        corrupted,
        root=tmp_path / "repository",
        risk_tier="medium",
    )
    implementation = next(
        item
        for item in record.payload["diagnostics"]
        if item["gate"] == "implementation_readiness"
        and item["decision_slot_id"] == "slot-isolation"
    )

    assert readiness_modules["readiness_for_delivery"](record)["gates"]["implementation_readiness"] == "fail"
    assert implementation["recommended_work"] is not None


def test_missing_rollback_is_an_operational_failure_at_high_risk(tmp_path: Path) -> None:
    readiness_modules = api()
    (
        _modules,
        store,
        round_record,
        _model,
        _brief,
        _target,
        _finding,
        _decision,
        technical_package,
    ) = package_context(tmp_path)
    corrupted_payload = thaw_json(technical_package.payload)
    corrupted_payload["document"]["operational_handoff"]["rollback"] = []
    corrupted = store.append_artifact(
        round_record.id,
        technical_package.id,
        technical_package.kind,
        corrupted_payload,
        parent_refs=technical_package.parent_refs,
    )

    record = verify(
        readiness_modules,
        store,
        round_record,
        corrupted,
        root=tmp_path / "repository",
        risk_tier="high",
    )
    operational = next(
        item for item in record.payload["diagnostics"] if item["gate"] == "operational_quality"
    )

    assert readiness_modules["readiness_for_delivery"](record)["gates"]["operational_quality"] == "fail"
    assert operational["recommended_work"] is not None


def test_missing_rollout_item_is_an_operational_failure_at_high_risk(tmp_path: Path) -> None:
    readiness_modules = api()
    _modules, store, round_record, technical_package = complete_conditional_package(tmp_path)
    corrupted_payload = thaw_json(technical_package.payload)
    corrupted_payload["document"]["operational_handoff"]["rollout"]["items"] = []
    corrupted = store.append_artifact(
        round_record.id,
        technical_package.id,
        technical_package.kind,
        corrupted_payload,
        parent_refs=technical_package.parent_refs,
    )

    record = verify(
        readiness_modules,
        store,
        round_record,
        corrupted,
        root=tmp_path / "repository",
        risk_tier="high",
    )

    assert readiness_modules["readiness_for_delivery"](record)["gates"]["operational_quality"] == "fail"


def test_intent_alignment_checks_exact_model_interpretations(tmp_path: Path) -> None:
    readiness_modules = api()
    (
        _modules,
        store,
        round_record,
        _model,
        _brief,
        _target,
        _finding,
        _decision,
        technical_package,
    ) = package_context(tmp_path)
    corrupted_payload = thaw_json(technical_package.payload)
    corrupted_payload["document"]["intent_basis"]["hypotheses"][0]["interpretation"] = (
        "Invented requester intent."
    )
    corrupted = store.append_artifact(
        round_record.id,
        technical_package.id,
        technical_package.kind,
        corrupted_payload,
        parent_refs=technical_package.parent_refs,
    )

    record = verify(
        readiness_modules,
        store,
        round_record,
        corrupted,
        root=tmp_path / "repository",
        risk_tier="default",
    )

    assert readiness_modules["readiness_for_delivery"](record)["gates"]["intent_alignment"] == "fail"


def test_high_risk_greenfield_operational_failure_has_a_targeted_follow_up(
    tmp_path: Path,
) -> None:
    readiness_modules = api()
    store, round_record, technical_package = greenfield_package(tmp_path)

    record = verify(
        readiness_modules,
        store,
        round_record,
        technical_package,
        root=tmp_path / "repository",
        risk_tier="high",
    )
    operational = next(
        item for item in record.payload["diagnostics"] if item["gate"] == "operational_quality"
    )

    assert operational["decision_slot_id"] == "slot-greenfield"
    assert operational["recommended_work"]["decision_slot_id"] == "slot-greenfield"
