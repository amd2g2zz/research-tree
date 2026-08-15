from __future__ import annotations

from pathlib import Path

import pytest


def api():
    from research_tree import (
        CanonicalInputIntakeService,
        CanonicalIntentModelCompiler,
        CanonicalWorkingBriefCompiler,
        InputIntakeService,
        IntentModelCompiler,
        InvalidIntentModelError,
        InvalidWorkingBriefError,
        QuestionPolicy,
        RunLedger,
        RunStore,
        WorkingBriefCompiler,
    )

    return {
        "CanonicalInputIntakeService": CanonicalInputIntakeService,
        "CanonicalIntentModelCompiler": CanonicalIntentModelCompiler,
        "CanonicalWorkingBriefCompiler": CanonicalWorkingBriefCompiler,
        "InputIntakeService": InputIntakeService,
        "IntentModelCompiler": IntentModelCompiler,
        "InvalidIntentModelError": InvalidIntentModelError,
        "InvalidWorkingBriefError": InvalidWorkingBriefError,
        "QuestionPolicy": QuestionPolicy,
        "RunLedger": RunLedger,
        "RunStore": RunStore,
        "WorkingBriefCompiler": WorkingBriefCompiler,
    }


def context(tmp_path: Path):
    modules = api()
    store = modules["RunStore"](tmp_path / "store")
    round_record = store.create_round("round-intent")
    intake = modules["InputIntakeService"](store)
    for input_id, kind, content, role in (
        ("input-brief", "brief", "Build an autonomous reverse-engineering agent.", "signal"),
        ("input-local", "note", "The first demo must run locally.", "constraint"),
        ("input-cloud", "note", "The first demo must be cloud-hosted.", "constraint"),
    ):
        intake.ingest_text(
            round_id=round_record.id,
            input_id=input_id,
            kind=kind,
            content=content,
            origin_type="user",
            origin_locator="conversation:1",
            role=role,
        )
    intake.create_context_bundle(
        round_id=round_record.id,
        input_id="input-context",
        member_input_ids=("input-brief", "input-local", "input-cloud"),
        origin_type="user",
        origin_locator="conversation:1",
        role="baseline",
    )
    return modules, store, round_record


def canonical_context(tmp_path: Path):
    modules = api()
    ledger = modules["RunLedger"](tmp_path / "ledger")
    ledger.initialize()
    round_record = ledger.create_run("round-intent")
    intake = modules["CanonicalInputIntakeService"](ledger)
    for input_id, kind, content, role in (
        ("input-brief", "brief", "Build an autonomous reverse-engineering agent.", "signal"),
        ("input-local", "note", "The first demo must run locally.", "constraint"),
        ("input-cloud", "note", "The first demo must be cloud-hosted.", "constraint"),
    ):
        intake.ingest_text(
            round_id=round_record.id,
            input_id=input_id,
            kind=kind,
            content=content,
            origin_type="user",
            origin_locator="conversation:1",
            role=role,
            expected_revision=ledger.get_revision(round_record.id),
        )
    intake.create_context_bundle(
        round_id=round_record.id,
        input_id="input-context",
        member_input_ids=("input-brief", "input-local", "input-cloud"),
        origin_type="user",
        origin_locator="conversation:1",
        role="baseline",
        expected_revision=ledger.get_revision(round_record.id),
    )
    return modules, ledger, round_record


def analysis(*, unresolved: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "signals": [
            {
                "input_id": "input-brief",
                "observation": "Requester wants a reverse-engineering agent.",
                "kind": "stated_goal",
                "authority_boundary": "Does not choose a deployment mode.",
            },
            {
                "input_id": "input-local",
                "observation": "One supplied note requires local execution.",
                "kind": "constraint",
                "authority_boundary": "Conflicts with the cloud note.",
            },
            {
                "input_id": "input-cloud",
                "observation": "One supplied note requires cloud hosting.",
                "kind": "constraint",
                "authority_boundary": "Conflicts with the local note.",
            },
        ],
        "hypotheses": [
            {
                "id": "intent-local",
                "interpretation": "Enable a local-first reverse-engineering demo.",
                "status": "leading",
                "signal_refs": ["input-brief", "input-local"],
                "confidence": "medium",
                "decision_consequence": "Favors local isolation and offline prototype work.",
                "validation": "repository_inspection",
            },
            {
                "id": "intent-cloud",
                "interpretation": "Enable a cloud-hosted reverse-engineering demo.",
                "status": "viable",
                "signal_refs": ["input-brief", "input-cloud"],
                "confidence": "low",
                "decision_consequence": "Changes identity, deployment, and data-boundary research.",
                "validation": "alignment_research",
            },
        ],
        "desired_outcomes": ["implementation-ready technical blueprint"],
        "success_signals": ["implementation agent can begin without rediscovery"],
        "decision_drivers": [
            {
                "dimension": "technical",
                "statement": "The first delivery must be safe to inspect and implement.",
                "signal_refs": ["input-brief"],
            }
        ],
        "hard_constraints": ["Do not execute untrusted binaries during intake."],
        "non_goals": ["Do not force a user questionnaire."],
        "unresolved_interpretations": unresolved or [],
    }


def compile_model(modules, store, round_record, payload: dict[str, object] | None = None):
    return modules["IntentModelCompiler"](store).compile(
        round_id=round_record.id,
        intent_id="intent-model",
        context_bundle_ids=("input-context",),
        input_ids=("input-brief", "input-local", "input-cloud"),
        analysis=payload or analysis(),
    )


def compile_canonical_model(modules, ledger, round_record, payload: dict[str, object] | None = None):
    return modules["CanonicalIntentModelCompiler"](ledger).compile(
        round_id=round_record.id,
        intent_id="intent-model",
        context_bundle_ids=("input-context",),
        input_ids=("input-brief", "input-local", "input-cloud"),
        analysis=payload or analysis(),
        expected_revision=ledger.get_revision(round_record.id),
    )


def test_conflicting_context_compiles_traceable_leading_and_viable_intent(tmp_path: Path) -> None:
    modules, ledger, round_record = canonical_context(tmp_path)
    model = compile_canonical_model(modules, ledger, round_record)

    assert model.kind == "intent-model"
    assert model.payload["input_ids"] == ("input-brief", "input-local", "input-cloud")
    assert [signal["input_id"] for signal in model.payload["signals"]] == [
        "input-brief",
        "input-local",
        "input-cloud",
    ]
    assert [hypothesis["status"] for hypothesis in model.payload["hypotheses"]] == [
        "leading",
        "viable",
    ]
    assert model.payload["hypotheses"][0]["signal_refs"] == ("input-brief", "input-local")


def test_independent_input_does_not_require_a_context_bundle(tmp_path: Path) -> None:
    modules = api()
    store = modules["RunStore"](tmp_path / "store")
    round_record = store.create_round("round-independent")
    modules["InputIntakeService"](store).ingest_text(
        round_id=round_record.id,
        input_id="input-brief",
        kind="brief",
        content="Build an implementation-ready technical blueprint.",
        origin_type="user",
        origin_locator="conversation:1",
        role="signal",
    )
    payload = analysis()
    payload["signals"] = [payload["signals"][0]]
    payload["hypotheses"] = [payload["hypotheses"][0]]
    payload["hypotheses"][0]["signal_refs"] = ["input-brief"]
    payload["decision_drivers"][0]["signal_refs"] = ["input-brief"]
    model = modules["IntentModelCompiler"](store).compile(
        round_id=round_record.id,
        intent_id="intent-model",
        context_bundle_ids=(),
        input_ids=("input-brief",),
        analysis=payload,
    )

    assert model.payload["context_bundle_ids"] == ()


def test_invalid_signal_anchor_is_rejected_without_artifact(tmp_path: Path) -> None:
    modules, ledger, round_record = canonical_context(tmp_path)
    invalid = analysis()
    invalid["signals"][0]["input_id"] = "input-unknown"

    with pytest.raises(modules["InvalidIntentModelError"]):
        compile_canonical_model(modules, ledger, round_record, invalid)

    assert [artifact for artifact in ledger.load_run(round_record.id).artifacts if artifact.kind == "intent-model"] == []


def test_invalid_hypothesis_anchor_is_rejected_without_artifact(tmp_path: Path) -> None:
    modules, ledger, round_record = canonical_context(tmp_path)
    invalid = analysis()
    invalid["hypotheses"][0]["signal_refs"] = ["input-unknown"]

    with pytest.raises(modules["InvalidIntentModelError"]):
        compile_canonical_model(modules, ledger, round_record, invalid)

    assert [artifact for artifact in ledger.load_run(round_record.id).artifacts if artifact.kind == "intent-model"] == []


def test_partial_ambiguity_generates_nonblocking_question_and_brief(tmp_path: Path) -> None:
    modules, ledger, round_record = canonical_context(tmp_path)
    model = compile_canonical_model(
        modules,
        ledger,
        round_record,
        analysis(
            unresolved=[
                {
                    "hypothesis_ids": ["intent-local", "intent-cloud"],
                    "question": "Should the initial demo optimize for local or cloud deployment?",
                    "consequential": True,
                    "non_recoverable": True,
                    "rankable": False,
                }
            ]
        ),
    )
    recommendation = modules["QuestionPolicy"]().recommend(model)
    assert recommendation is not None
    assert recommendation.question.startswith("Should the initial demo")

    brief = modules["CanonicalWorkingBriefCompiler"](ledger).compile(
        round_id=round_record.id,
        brief_id="working-brief",
        intent_model=model,
        triggers=[{"kind": "initial_request", "text": "Start", "input_ids": ["input-brief"]}],
        context_bundle_ids=("input-context",),
        selected_input_ids=("input-brief", "input-local", "input-cloud"),
        input_roles={
            "input-brief": "primary",
            "input-local": "constraint",
            "input-cloud": "counterexample",
        },
        material_conflicts=[
            {
                "input_ids": ["input-local", "input-cloud"],
                "status": "open",
                "note": "Deployment direction remains unresolved.",
            }
        ],
        working_interpretation="Local-first is leading while cloud hosting remains viable.",
        technical_outcome="Choose an implementation-ready safe reverse-engineering path.",
        assumptions=["Proceed with local-first research until evidence ranks alternatives."],
        expected_revision=ledger.get_revision(round_record.id),
    )

    assert brief.payload["intent_model_id"] == model.id
    assert brief.payload["intent_hypothesis_ids"] == ("intent-local",)
    assert brief.payload["delivery_targets"] == {
        "technical_research_package": True,
        "human_brief": True,
        "openspec": False,
    }
    assert brief.parent_refs[0].artifact_id == model.id


def test_question_policy_stays_silent_when_evidence_can_rank_ambiguity(tmp_path: Path) -> None:
    modules, ledger, round_record = canonical_context(tmp_path)
    model = compile_canonical_model(
        modules,
        ledger,
        round_record,
        analysis(
            unresolved=[
                {
                    "hypothesis_ids": ["intent-local", "intent-cloud"],
                    "question": "Should not be emitted.",
                    "consequential": True,
                    "non_recoverable": True,
                    "rankable": True,
                }
            ]
        ),
    )

    assert modules["QuestionPolicy"]().recommend(model) is None


@pytest.mark.parametrize(
    ("unresolved", "status"),
    [
        (
            [
                {
                    "hypothesis_ids": ["intent-local"],
                    "question": "A single hypothesis cannot require a choice.",
                    "consequential": True,
                    "non_recoverable": True,
                    "rankable": False,
                }
            ],
            "viable",
        ),
        (
            [
                {
                    "hypothesis_ids": ["intent-local", "intent-cloud"],
                    "question": "A rejected alternative cannot require a choice.",
                    "consequential": True,
                    "non_recoverable": True,
                    "rankable": False,
                }
            ],
            "rejected",
        ),
    ],
)
def test_unresolved_question_candidates_require_active_alternatives(
    tmp_path: Path,
    unresolved: list[dict[str, object]],
    status: str,
) -> None:
    modules, ledger, round_record = canonical_context(tmp_path)
    payload = analysis(unresolved=unresolved)
    payload["hypotheses"][1]["status"] = status

    with pytest.raises(modules["InvalidIntentModelError"]):
        compile_canonical_model(modules, ledger, round_record, payload)


def test_working_brief_rejects_newer_or_unmodeled_input_revisions(tmp_path: Path) -> None:
    modules, ledger, round_record = canonical_context(tmp_path)
    model = compile_canonical_model(modules, ledger, round_record)
    intake = modules["CanonicalInputIntakeService"](ledger)
    intake.ingest_text(
        round_id=round_record.id,
        input_id="input-brief",
        kind="brief",
        content="A materially revised autonomous reverse-engineering goal.",
        origin_type="user",
        origin_locator="conversation:2",
        role="signal",
        expected_revision=ledger.get_revision(round_record.id),
    )
    intake.ingest_text(
        round_id=round_record.id,
        input_id="input-extra",
        kind="note",
        content="An unmodeled new constraint.",
        origin_type="user",
        origin_locator="conversation:2",
        role="constraint",
        expected_revision=ledger.get_revision(round_record.id),
    )
    compiler = modules["CanonicalWorkingBriefCompiler"](ledger)
    common = {
        "round_id": round_record.id,
        "brief_id": "working-brief",
        "intent_model": model,
        "triggers": [{"kind": "new_material", "text": "Refine", "input_ids": ["input-brief"]}],
        "context_bundle_ids": ("input-context",),
        "selected_input_ids": ("input-brief", "input-local", "input-cloud"),
        "input_roles": {
            "input-brief": "primary",
            "input-local": "constraint",
            "input-cloud": "counterexample",
        },
        "material_conflicts": [],
        "working_interpretation": "Local-first is the leading interpretation.",
        "technical_outcome": "Produce a technical blueprint.",
    }
    with pytest.raises(modules["InvalidWorkingBriefError"]):
        compiler.compile(**common, expected_revision=ledger.get_revision(round_record.id))

    refreshed_model = compile_canonical_model(modules, ledger, round_record)
    common["intent_model"] = refreshed_model
    common["selected_input_ids"] = ("input-brief", "input-local", "input-cloud", "input-extra")
    common["input_roles"] = {**common["input_roles"], "input-extra": "constraint"}
    with pytest.raises(modules["InvalidWorkingBriefError"]):
        compiler.compile(**common, expected_revision=ledger.get_revision(round_record.id))

    assert [artifact for artifact in ledger.load_run(round_record.id).artifacts if artifact.kind == "working-brief"] == []


def test_working_brief_rejects_a_newer_context_bundle_revision(tmp_path: Path) -> None:
    modules, ledger, round_record = canonical_context(tmp_path)
    model = compile_canonical_model(modules, ledger, round_record)
    modules["CanonicalInputIntakeService"](ledger).create_context_bundle(
        round_id=round_record.id,
        input_id="input-context",
        member_input_ids=("input-brief", "input-local", "input-cloud"),
        origin_type="user",
        origin_locator="conversation:2",
        role="baseline",
        expected_revision=ledger.get_revision(round_record.id),
    )

    with pytest.raises(modules["InvalidWorkingBriefError"]):
        modules["CanonicalWorkingBriefCompiler"](ledger).compile(
            round_id=round_record.id,
            brief_id="working-brief",
            intent_model=model,
            triggers=[{"kind": "new_material", "text": "Regroup", "input_ids": ["input-brief"]}],
            context_bundle_ids=("input-context",),
            selected_input_ids=("input-brief", "input-local", "input-cloud"),
            input_roles={
                "input-brief": "primary",
                "input-local": "constraint",
                "input-cloud": "counterexample",
            },
            material_conflicts=[],
            working_interpretation="Local-first is the leading interpretation.",
            technical_outcome="Produce a technical blueprint.",
            expected_revision=ledger.get_revision(round_record.id),
        )


def test_rehydrated_brief_preserves_exact_intent_and_input_references(tmp_path: Path) -> None:
    modules, ledger, round_record = canonical_context(tmp_path)
    model = compile_canonical_model(modules, ledger, round_record)
    brief = modules["CanonicalWorkingBriefCompiler"](ledger).compile(
        round_id=round_record.id,
        brief_id="working-brief",
        intent_model=model,
        triggers=[{"kind": "initial_request", "text": "Start", "input_ids": ["input-brief"]}],
        context_bundle_ids=("input-context",),
        selected_input_ids=("input-brief", "input-local", "input-cloud"),
        input_roles={
            "input-brief": "primary",
            "input-local": "constraint",
            "input-cloud": "counterexample",
        },
        material_conflicts=[],
        working_interpretation="Local-first is the leading interpretation.",
        technical_outcome="Produce a technical blueprint.",
        expected_revision=ledger.get_revision(round_record.id),
    )

    rehydrated = modules["RunLedger"](ledger.workspace).load_run(round_record.id)
    stored_brief = next(artifact for artifact in rehydrated.artifacts if artifact == brief)
    assert stored_brief.parent_refs[0].to_dict() == {
        "round_id": round_record.id,
        "artifact_id": model.id,
        "revision": model.revision,
    }
    assert stored_brief.payload["input_roles"] == {
        "input-brief": "primary",
        "input-local": "constraint",
        "input-cloud": "counterexample",
    }


def test_recompilation_appends_intent_and_brief_revisions_without_mutating_history(
    tmp_path: Path,
) -> None:
    modules, ledger, round_record = canonical_context(tmp_path)
    first_model = compile_canonical_model(modules, ledger, round_record)
    compiler = modules["CanonicalWorkingBriefCompiler"](ledger)
    first_brief = compiler.compile(
        round_id=round_record.id,
        brief_id="working-brief",
        intent_model=first_model,
        triggers=[{"kind": "initial_request", "text": "Start", "input_ids": ["input-brief"]}],
        context_bundle_ids=("input-context",),
        selected_input_ids=("input-brief", "input-local", "input-cloud"),
        input_roles={
            "input-brief": "primary",
            "input-local": "constraint",
            "input-cloud": "counterexample",
        },
        material_conflicts=[],
        working_interpretation="Local-first is the leading interpretation.",
        technical_outcome="Produce a technical blueprint.",
        expected_revision=ledger.get_revision(round_record.id),
    )
    second_payload = analysis()
    second_payload["desired_outcomes"] = ["a revised implementation-ready technical blueprint"]
    second_model = compile_canonical_model(modules, ledger, round_record, second_payload)
    second_brief = compiler.compile(
        round_id=round_record.id,
        brief_id="working-brief",
        intent_model=second_model,
        triggers=[{"kind": "new_material", "text": "Refine", "input_ids": ["input-brief"]}],
        context_bundle_ids=("input-context",),
        selected_input_ids=("input-brief", "input-local", "input-cloud"),
        input_roles={
            "input-brief": "primary",
            "input-local": "constraint",
            "input-cloud": "counterexample",
        },
        material_conflicts=[],
        working_interpretation="Local-first remains the leading interpretation.",
        technical_outcome="Produce a technical blueprint.",
        expected_revision=ledger.get_revision(round_record.id),
    )

    artifacts = modules["RunLedger"](ledger.workspace).load_run(round_record.id).artifacts
    first_stored_model = next(
        artifact
        for artifact in artifacts
        if artifact.id == first_model.id and artifact.revision == first_model.revision
    )
    first_stored_brief = next(
        artifact
        for artifact in artifacts
        if artifact.id == first_brief.id and artifact.revision == first_brief.revision
    )
    assert second_model.revision == first_model.revision + 1
    assert second_brief.revision == first_brief.revision + 1
    assert first_stored_model.payload["desired_outcomes"] == (
        "implementation-ready technical blueprint",
    )
    assert first_stored_brief.parent_refs[0].revision == first_model.revision
    assert second_brief.parent_refs[0].revision == second_model.revision
