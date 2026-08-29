from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from canonical_finding_fixture import canonical_context

from research_tree import (
    ArtifactRef,
    CanonicalDecisionLedgerCompiler,
    CanonicalDeliveryCompiler,
    CanonicalFindingPackCompiler,
    EvidenceAnchor,
    EvidenceArtifact,
    InvalidDeliveryError,
    RunLedger,
)
from research_tree.claims import Claim, ClaimGrounding
from research_tree.domain import thaw_json
from research_tree.work_items import WORK_ITEM_KIND


def api():
    return {
        "ArtifactRef": ArtifactRef,
        "CanonicalDecisionLedgerCompiler": CanonicalDecisionLedgerCompiler,
        "CanonicalDeliveryCompiler": CanonicalDeliveryCompiler,
        "CanonicalFindingPackCompiler": CanonicalFindingPackCompiler,
        "InvalidDeliveryError": InvalidDeliveryError,
        "RunLedger": RunLedger,
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
        "from src.agent import run\n\n\ndef test_run():\n    assert run() == 'ready'\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        "[project]\nname = 'fixture'\nversion = '0.0.0'\n",
        encoding="utf-8",
    )
    return root


def intent_analysis() -> dict[str, object]:
    return {
        "signals": [
            {
                "input_id": "input-brief",
                "observation": "The requester needs a safe autonomous agent.",
                "kind": "stated_goal",
                "authority_boundary": "It does not choose an isolation architecture.",
            },
            {
                "input_id": "input-repository",
                "observation": "The repository has a src/agent.py run boundary.",
                "kind": "repository_fact",
                "authority_boundary": "It records current behavior, not a recommendation.",
            },
        ],
        "hypotheses": [
            {
                "id": "intent-agent",
                "interpretation": "Deliver an implementation-ready safe agent path.",
                "status": "leading",
                "signal_refs": ["input-brief", "input-repository"],
                "confidence": "medium",
                "decision_consequence": "Isolation and observability boundaries must close.",
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
        "non_goals": ["Do not force a user questionnaire."],
        "unresolved_interpretations": [],
    }


def slot(
    slot_id: str,
    *,
    kind: str,
    priority: str,
    alternatives: list[str],
    depends_on: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": slot_id,
        "kind": kind,
        "question": f"Which implementation choice should {slot_id} make?",
        "intent_hypothesis_ids": ["intent-agent"],
        "priority": priority,
        "impact": "high",
        "uncertainty": "high",
        "irreversibility": "medium",
        "constraints": [
            {
                "kind": "input",
                "ref": "input-brief",
                "statement": "The first implementation must remain safe.",
            }
        ],
        "alternatives": alternatives,
        "repository_touchpoints": [{"path": "src/agent.py", "symbol": "run"}],
        "greenfield_assumptions": [],
        "depends_on": depends_on or [],
        "evidence_standard": "repository inspection plus a bounded spike",
        "validation": {
            "kind": "spike",
            "oracle": "one fixture completes through the selected boundary",
        },
        "closure_rule": "select, conditionally select, defer with fallback, or block",
        "status": "open",
        "bounded_research_need": "compare alternatives against the current repository boundary",
        "fallback": "retain the current boundary until this decision closes",
    }


def readiness() -> dict[str, object]:
    return {
        "risk_tier": "medium",
        "gates": {
            "intent_alignment": "pass",
            "decision_closure": "fail",
            "traceability": "pass",
            "repository_fit": "pass",
            "implementation_readiness": "deferred",
            "operational_quality": "deferred",
        },
        "findings": [
            {
                "gate": "decision_closure",
                "summary": "Observability remains open and needs a bounded spike.",
            }
        ],
        "next_work_item_ids": ["work-observability"],
    }


def decision_kwargs(target, finding) -> dict[str, object]:
    return {
        "blueprint_target": target,
        "decision_slot_id": "slot-isolation",
        "finding_packs": [finding],
        "status": "conditional",
        "selected_option": "isolated-worker",
        "alternatives": [
            {
                "option": "in-process",
                "disposition": "deferred",
                "reason": "Startup cost needs a bounded validation spike.",
            }
        ],
        "anchors": [{"kind": "finding", "ref": finding.id}],
        "design_consequence": "Add a worker adapter at src/agent.py:run.",
        "repository_touchpoints": [{"path": "src/agent.py", "symbol": "run"}],
        "validation": {
            "kind": "spike",
            "oracle": "one fixture completes through the worker adapter",
        },
        "change_tasks": [
            {
                "id": "change-worker-adapter",
                "description": "Introduce the selected isolation adapter.",
                "acceptance_oracle": "The fixture crosses the adapter without direct binary execution.",
                "repository_touchpoints": [{"path": "src/agent.py", "symbol": "run"}],
            }
        ],
        "assumptions": ["The local worker boundary is sufficient for the first demo."],
        "fallback": "Keep the in-process boundary behind a feature flag.",
        "reversal_condition": "A spike shows worker startup overhead breaks the first workflow.",
        "revision_reason": "Initial convergence from bounded isolation research.",
    }


def observability_slot() -> dict[str, object]:
    return {
        "id": "slot-observability",
        "kind": "operations",
        "question": "Which implementation choice should slot-observability make?",
        "intent_hypothesis_ids": ["intent-agent"],
        "priority": "P1",
        "impact": "high",
        "uncertainty": "high",
        "irreversibility": "medium",
        "constraints": [
            {
                "kind": "input",
                "ref": "input-brief",
                "statement": "The first implementation must remain safe.",
            }
        ],
        "alternatives": ["structured-logging", "minimal-logging"],
        "repository_touchpoints": [{"path": "src/agent.py", "symbol": "run"}],
        "greenfield_assumptions": [],
        "depends_on": ["slot-isolation"],
        "evidence_standard": "repository inspection plus a bounded spike",
        "validation": {
            "kind": "spike",
            "oracle": "one fixture completes through the selected boundary",
        },
        "closure_rule": "select, conditionally select, defer with fallback, or block",
        "status": "open",
        "bounded_research_need": "compare alternatives against the current repository boundary",
        "fallback": "retain the current boundary until this decision closes",
    }


def append_artifact(ledger, round_record, artifact_id, kind, payload, parent_refs=()):
    return ledger.append_artifact(
        round_record.id,
        artifact_id,
        kind,
        payload,
        parent_refs=parent_refs,
        expected_revision=ledger.get_revision(round_record.id),
    )


def assert_no_delivery_artifacts(ledger, round_record) -> None:
    kinds = {artifact.kind for artifact in ledger.load_run(round_record.id).artifacts}
    assert "technical-research-package" not in kinds
    assert "human-research-report" not in kinds


def context(tmp_path: Path):
    modules = api()
    (
        ledger,
        resolver,
        round_record,
        model,
        brief,
        initial_target,
        initial_work,
        _initial_finding,
        _initial_decision,
        _evidence,
        anchor,
    ) = canonical_context(tmp_path)
    modules["resolver"] = resolver
    target_payload = thaw_json(initial_target.payload)
    target_payload["slots"][0]["question"] = "Which implementation choice should slot-isolation make?"
    target_payload["slots"].append(observability_slot())
    target = append_artifact(
        ledger,
        round_record,
        initial_target.id,
        initial_target.kind,
        target_payload,
        initial_target.parent_refs,
    )
    isolation_work_payload = thaw_json(initial_work.payload)
    isolation_work_payload["id"] = "work-isolation-delivery"
    isolation_work = append_artifact(
        ledger,
        round_record,
        "work-isolation-delivery",
        WORK_ITEM_KIND,
        isolation_work_payload,
        (ArtifactRef(round_record.id, target.id, target.revision),),
    )
    append_artifact(
        ledger,
        round_record,
        "work-observability",
        WORK_ITEM_KIND,
        {
            "id": "work-observability",
            "round_id": round_record.id,
            "blueprint_target_id": target.id,
            "decision_slot_id": "slot-observability",
        },
        (ArtifactRef(round_record.id, target.id, target.revision),),
    )
    independent_ref = ArtifactRef(round_record.id, "strict-source-independent", 1)
    independent_artifact = EvidenceArtifact.from_revision(
        independent_ref,
        ledger.get_artifact(independent_ref),
    )
    independent_anchor = EvidenceAnchor(
        artifact_ref=independent_ref,
        artifact_digest=independent_artifact.content_digest,
        artifact_revision=1,
        selector_type="line",
        selector_value={"start": 1, "end": 1},
        extractor_version="fixture-reader-v1",
        applicability="direct support",
        confidence="high",
        limitations=(),
    )
    isolation_claim = Claim(
        claim_id="claim-isolation-delivery",
        subject="source",
        predicate="supports",
        value="the isolated worker boundary",
        polarity="positive",
        scope="fixture boundary",
        version="fixture-v1",
        time_range="fixture-time",
    )
    finding = modules["CanonicalFindingPackCompiler"](ledger, resolver).compile(
        round_id=round_record.id,
        finding_id="finding-isolation-delivery",
        work_item=isolation_work,
        observations=[
            {
                "claim_id": isolation_claim.claim_id,
                "claim": "The source supports an isolated worker boundary.",
                "anchor": anchor.to_dict(),
                "applicability": "the fixture boundary",
                "confidence": "high",
                "limitation": "fixture evidence only",
            }
        ],
        option_effects=[{"option": "isolated-worker", "effect": "supports", "claim_ids": [isolation_claim.claim_id]}],
        implementation_implications=["Introduce an isolated worker boundary."],
        remaining_uncertainties=["Measure startup overhead with a spike."],
        claims=[isolation_claim],
        claim_groundings=[
            ClaimGrounding("grounding-isolation-delivery", isolation_claim.claim_id, anchor.to_dict()),
            ClaimGrounding(
                "grounding-isolation-delivery-independent", isolation_claim.claim_id, independent_anchor.to_dict()
            ),
        ],
        expected_revision=ledger.get_revision(round_record.id),
    )
    decision = modules["CanonicalDecisionLedgerCompiler"](ledger, resolver).converge(
        round_id=round_record.id,
        decision_id="decision-isolation-delivery",
        **decision_kwargs(target, finding),
        expected_revision=ledger.get_revision(round_record.id),
    )
    return modules, ledger, round_record, model, brief, target, finding, decision


def compile_deliveries(
    modules,
    ledger,
    round_record,
    brief,
    target,
    decisions,
    *,
    readiness_input: dict[str, object] | None = None,
):
    return modules["CanonicalDeliveryCompiler"](ledger, modules["resolver"]).compile(
        round_id=round_record.id,
        technical_package_id="technical-package",
        human_brief_id="human-brief",
        working_brief=brief,
        blueprint_target=target,
        decision_entries=decisions,
        readiness=readiness() if readiness_input is None else readiness_input,
        expected_revision=ledger.get_revision(round_record.id),
    )


def test_compiles_traceable_agent_package_and_independent_human_brief(tmp_path: Path) -> None:
    modules, ledger, round_record, model, brief, target, _finding, decision = context(tmp_path)

    deliveries = compile_deliveries(modules, ledger, round_record, brief, target, [decision])

    technical = deliveries.technical_package
    human = deliveries.human_brief
    document = technical.payload["document"]
    record = document["decision_records"][0]
    closure = {entry["decision_slot_id"]: entry for entry in document["blueprint_closure"]}

    assert technical.kind == "technical-research-package"
    assert human.kind == "human-research-report"
    assert deliveries.human_research_report is human
    assert deliveries.human_brief is human
    assert human.payload["markdown"].startswith("# Human Research Report:")
    assert record["intent_hypothesis_ids"] == ("intent-agent",)
    assert record["repository_touchpoints"] == ({"path": "src/agent.py", "symbol": "run"},)
    assert record["validation"]["oracle"].startswith("one fixture")
    assert record["fallback"].startswith("Keep the in-process")
    assert record["reversal_condition"].startswith("A spike")
    assert record["change_tasks"][0]["acceptance_oracle"].startswith("The fixture")
    assert closure["slot-isolation"]["status"] == "conditional"
    assert closure["slot-observability"]["status"] == "missing"
    assert "src/agent.py" in technical.payload["markdown"]
    assert "change-worker-adapter" not in human.payload["markdown"]
    assert "A safe implementation-ready agent path is leading." in human.payload["markdown"]
    assert human.payload["technical_package_ref"] == {
        "round_id": round_record.id,
        "artifact_id": technical.id,
        "revision": technical.revision,
    }
    expected_refs = {
        modules["ArtifactRef"](round_record.id, brief.id, brief.revision),
        modules["ArtifactRef"](round_record.id, model.id, model.revision),
        modules["ArtifactRef"](round_record.id, target.id, target.revision),
        modules["ArtifactRef"](round_record.id, decision.id, decision.revision),
    }
    assert expected_refs <= set(technical.parent_refs)
    assert expected_refs <= set(human.parent_refs)


def test_missing_blueprint_closure_and_nonpassing_readiness_are_visible(tmp_path: Path) -> None:
    modules, ledger, round_record, _model, brief, target, _finding, decision = context(tmp_path)

    deliveries = compile_deliveries(modules, ledger, round_record, brief, target, [decision])
    technical = deliveries.technical_package
    human = deliveries.human_brief

    closure = {entry["decision_slot_id"]: entry for entry in technical.payload["document"]["blueprint_closure"]}
    assert closure["slot-observability"] == {
        "decision_slot_id": "slot-observability",
        "priority": "P1",
        "question": "Which implementation choice should slot-observability make?",
        "intent_hypothesis_ids": ("intent-agent",),
        "status": "missing",
        "selected_option": None,
        "closure_or_fallback": "retain the current boundary until this decision closes",
        "next_action": "Create or converge a Decision Ledger entry for this slot.",
    }
    assert technical.payload["document"]["readiness_record"]["gates"]["decision_closure"] == "fail"
    assert "missing" in technical.payload["markdown"].lower()
    assert "slot-observability" in human.payload["markdown"]
    assert "Observability remains open and needs a bounded spike." in human.payload["markdown"]
    assert "work-observability" in human.payload["markdown"]


def test_human_brief_makes_unclosed_decisions_and_readiness_follow_up_standalone(
    tmp_path: Path,
) -> None:
    modules, ledger, round_record, _model, brief, target, _finding, decision = context(tmp_path)

    human = compile_deliveries(modules, ledger, round_record, brief, target, [decision]).human_brief

    document = human.payload["document"]
    assert document["unclosed_blueprint_items"] == (
        {
            "decision_slot_id": "slot-isolation",
            "priority": "P0",
            "question": "Which implementation choice should slot-isolation make?",
            "status": "conditional",
            "closure_or_fallback": "Keep the in-process boundary behind a feature flag.",
            "next_action": "Run spike validation: one fixture completes through the worker adapter",
        },
        {
            "decision_slot_id": "slot-observability",
            "priority": "P1",
            "question": "Which implementation choice should slot-observability make?",
            "status": "missing",
            "closure_or_fallback": "retain the current boundary until this decision closes",
            "next_action": "Create or converge a Decision Ledger entry for this slot.",
        },
    )
    assert document["readiness_findings"] == (
        {
            "gate": "decision_closure",
            "summary": "Observability remains open and needs a bounded spike.",
        },
    )
    assert document["next_work_item_ids"] == ("work-observability",)
    assert "## Unclosed Design Obligations" in human.payload["markdown"]
    assert "slot-observability" in human.payload["markdown"]
    assert "Create or converge a Decision Ledger entry" in human.payload["markdown"]
    assert "Observability remains open and needs a bounded spike." in human.payload["markdown"]
    assert "work-observability" in human.payload["markdown"]


def test_passing_decision_closure_gate_cannot_contradict_missing_or_blocked_slots(
    tmp_path: Path,
) -> None:
    modules, ledger, round_record, _model, brief, target, _finding, decision = context(tmp_path)
    inconsistent = readiness()
    inconsistent["gates"]["decision_closure"] = "pass"

    with pytest.raises(modules["InvalidDeliveryError"], match="decision_closure"):
        compile_deliveries(
            modules,
            ledger,
            round_record,
            brief,
            target,
            [decision],
            readiness_input=inconsistent,
        )

    assert_no_delivery_artifacts(ledger, round_record)


def test_invalid_implementation_facing_p0_record_leaves_no_delivery_artifacts(
    tmp_path: Path,
) -> None:
    modules, ledger, round_record, _model, brief, target, _finding, decision = context(tmp_path)

    invalid_payload = thaw_json(decision.payload)
    invalid_payload["change_tasks"] = []
    invalid = append_artifact(
        ledger,
        round_record,
        decision.id,
        decision.kind,
        invalid_payload,
        parent_refs=decision.parent_refs,
    )

    with pytest.raises(modules["InvalidDeliveryError"]):
        compile_deliveries(modules, ledger, round_record, brief, target, [invalid])

    assert_no_delivery_artifacts(ledger, round_record)


@pytest.mark.parametrize(
    "case",
    [
        "empty_anchor",
        "unconstrained_touchpoint",
        "task_without_touchpoint",
        "invalid_selected_option",
        "selected_option_repeated_as_alternative",
    ],
)
def test_directly_written_p0_decision_revisions_are_semantically_revalidated(
    tmp_path: Path,
    case: str,
) -> None:
    modules, ledger, round_record, _model, brief, target, _finding, decision = context(tmp_path)

    invalid_payload = thaw_json(decision.payload)
    if case == "empty_anchor":
        invalid_payload["anchors"] = [{"kind": "finding", "ref": ""}]
    elif case == "unconstrained_touchpoint":
        invalid_payload["repository_touchpoints"] = [{"path": "src/not-the-slot.py", "symbol": "run"}]
    elif case == "task_without_touchpoint":
        invalid_payload["change_tasks"] = [
            {
                "id": "change-worker-adapter",
                "description": "Introduce the selected isolation adapter.",
                "acceptance_oracle": "The fixture crosses the adapter without direct binary execution.",
                "repository_touchpoints": [],
            }
        ]
    elif case == "invalid_selected_option":
        invalid_payload["selected_option"] = "unapproved-option"
    elif case == "selected_option_repeated_as_alternative":
        invalid_payload["alternatives"] = [
            {
                "option": "isolated-worker",
                "disposition": "rejected",
                "reason": "This is deliberately inconsistent.",
            }
        ]
    else:
        raise AssertionError(f"Unhandled test case: {case}")
    invalid = append_artifact(
        ledger,
        round_record,
        decision.id,
        decision.kind,
        invalid_payload,
        parent_refs=decision.parent_refs,
    )

    with pytest.raises(modules["InvalidDeliveryError"]):
        compile_deliveries(modules, ledger, round_record, brief, target, [invalid])

    assert_no_delivery_artifacts(ledger, round_record)


def test_stale_or_ambiguous_ledger_inputs_are_rejected_before_outputs(tmp_path: Path) -> None:
    modules, ledger, round_record, _model, brief, target, finding, decision = context(tmp_path)
    revised = modules["CanonicalDecisionLedgerCompiler"](ledger, modules["resolver"]).converge(
        round_id=round_record.id,
        decision_id=decision.id,
        **decision_kwargs(target, finding),
        expected_revision=ledger.get_revision(round_record.id),
    )

    with pytest.raises(modules["InvalidDeliveryError"]):
        compile_deliveries(modules, ledger, round_record, brief, target, [decision])
    with pytest.raises(modules["InvalidDeliveryError"]):
        compile_deliveries(modules, ledger, round_record, brief, target, [revised, revised])

    assert_no_delivery_artifacts(ledger, round_record)


def test_delivery_api_has_no_worker_prose_or_default_openspec_path(tmp_path: Path) -> None:
    modules, ledger, round_record, _model, brief, target, _finding, decision = context(tmp_path)

    parameters = inspect.signature(modules["CanonicalDeliveryCompiler"].compile).parameters
    assert "worker_prose" not in parameters
    assert "architecture_text" not in parameters
    assert "openspec" not in parameters

    compile_deliveries(modules, ledger, round_record, brief, target, [decision])
    kinds = {artifact.kind for artifact in ledger.load_run(round_record.id).artifacts}
    assert "openspec" not in kinds


def test_public_payload_validators_reject_nested_schema_drift(tmp_path: Path) -> None:
    modules, ledger, round_record, _model, brief, target, _finding, decision = context(tmp_path)
    from research_tree import validate_human_brief_payload, validate_technical_package_payload

    deliveries = compile_deliveries(modules, ledger, round_record, brief, target, [decision])
    invalid_technical = thaw_json(deliveries.technical_package.payload)
    invalid_technical["document"]["decision_records"][0]["alternatives"] = [
        {"option": "in-process", "disposition": "invalid", "reason": "bad schema"}
    ]
    with pytest.raises(modules["InvalidDeliveryError"]):
        validate_technical_package_payload(invalid_technical)

    invalid_human = thaw_json(deliveries.human_brief.payload)
    invalid_human["document"]["unclosed_blueprint_items"][0].pop("next_action")
    with pytest.raises(modules["InvalidDeliveryError"]):
        validate_human_brief_payload(invalid_human)


def test_rollout_and_observability_are_structured_or_explicitly_unknown(tmp_path: Path) -> None:
    modules, ledger, round_record, _model, brief, target, _finding, decision = context(tmp_path)

    technical = compile_deliveries(modules, ledger, round_record, brief, target, [decision]).technical_package

    operational = technical.payload["document"]["rollout_and_observability"]
    assert operational["rollout"] == {
        "status": "unknown",
        "items": (),
        "next_action": "Add an explicit migration Decision Slot before defining rollout steps.",
    }
    assert operational["observability"] == {
        "status": "unknown",
        "items": (
            {
                "decision_slot_id": "slot-observability",
                "status": "missing",
                "selected_option": None,
                "validation": {
                    "kind": "spike",
                    "oracle": "one fixture completes through the selected boundary",
                },
                "fallback": "retain the current boundary until this decision closes",
                "change_task_ids": (),
                "next_action": "Create or converge a Decision Ledger entry for this slot.",
            },
        ),
        "next_action": "Create or converge the visible operations Decision Slot before defining observability behavior.",
    }
    assert "## Rollout and Observability" in technical.payload["markdown"]
    assert "migration Decision Slot" in technical.payload["markdown"]


def test_rehydrated_deliveries_preserve_exact_sources_and_rendered_documents(
    tmp_path: Path,
) -> None:
    modules, ledger, round_record, _model, brief, target, _finding, decision = context(tmp_path)
    deliveries = compile_deliveries(modules, ledger, round_record, brief, target, [decision])

    rehydrated = modules["RunLedger"](ledger.workspace).load_run(round_record.id)
    stored_technical = next(artifact for artifact in rehydrated.artifacts if artifact == deliveries.technical_package)
    stored_human = next(artifact for artifact in rehydrated.artifacts if artifact == deliveries.human_brief)

    assert stored_technical.payload["markdown"] == deliveries.technical_package.payload["markdown"]
    assert stored_human.payload["markdown"] == deliveries.human_brief.payload["markdown"]
    assert modules["ArtifactRef"](round_record.id, decision.id, decision.revision) in stored_technical.parent_refs
    assert (
        modules["ArtifactRef"](
            round_record.id,
            deliveries.technical_package.id,
            deliveries.technical_package.revision,
        )
        in stored_human.parent_refs
    )


def test_readiness_cannot_pass_while_blueprint_closure_is_missing(tmp_path: Path) -> None:
    modules, ledger, round_record, _model, brief, target, _finding, decision = context(tmp_path)
    contradictory = readiness()
    contradictory["gates"]["decision_closure"] = "pass"

    with pytest.raises(modules["InvalidDeliveryError"]):
        modules["CanonicalDeliveryCompiler"](ledger, modules["resolver"]).compile(
            round_id=round_record.id,
            technical_package_id="technical-package",
            human_brief_id="human-brief",
            working_brief=brief,
            blueprint_target=target,
            decision_entries=[decision],
            readiness=contradictory,
            expected_revision=ledger.get_revision(round_record.id),
        )

    assert_no_delivery_artifacts(ledger, round_record)


def test_malformed_p0_ledger_trace_is_rejected_before_outputs(tmp_path: Path) -> None:
    modules, ledger, round_record, _model, brief, target, _finding, decision = context(tmp_path)

    malformed_payload = thaw_json(decision.payload)
    malformed_payload["anchors"] = [{"not_an_anchor": "missing-kind-and-ref"}]
    malformed_payload["repository_touchpoints"] = [{"not_a_touchpoint": "missing-path-and-symbol"}]
    malformed = append_artifact(
        ledger,
        round_record,
        decision.id,
        decision.kind,
        malformed_payload,
        parent_refs=decision.parent_refs,
    )

    with pytest.raises(modules["InvalidDeliveryError"]):
        compile_deliveries(modules, ledger, round_record, brief, target, [malformed])

    assert_no_delivery_artifacts(ledger, round_record)


def test_public_payload_validators_reject_shallow_placeholder_documents() -> None:
    from research_tree import (
        InvalidDeliveryError,
        validate_human_brief_payload,
        validate_technical_package_payload,
    )

    with pytest.raises(InvalidDeliveryError):
        validate_technical_package_payload({"document": {}, "markdown": "placeholder"})
    with pytest.raises(InvalidDeliveryError):
        validate_human_brief_payload(
            {
                "technical_package_ref": {
                    "round_id": None,
                    "artifact_id": None,
                    "revision": None,
                },
                "document": {},
                "markdown": "placeholder",
            }
        )


def test_technical_package_makes_operational_handoff_explicit(tmp_path: Path) -> None:
    modules, ledger, round_record, _model, brief, target, _finding, decision = context(tmp_path)

    technical = compile_deliveries(modules, ledger, round_record, brief, target, [decision]).technical_package
    handoff = technical.payload["document"]["operational_handoff"]

    assert set(handoff) == {"observability", "rollout", "rollback"}
    assert handoff["observability"]["status"] == "missing"
    assert handoff["rollout"]["status"] == "derived_from_ordered_change_tasks"
    assert handoff["rollback"][0]["fallback"].startswith("Keep the in-process")
    assert "Operational Handoff" in technical.payload["markdown"]
