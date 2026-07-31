from __future__ import annotations

from pathlib import Path

import pytest

from test_intent_and_brief import compile_model, context


def api():
    from research_tree import (
        CandidateContext,
        FeedbackRoundService,
        InvalidFeedbackError,
        InvalidIntentModelError,
        InvalidWorkingBriefError,
        RoundNotFoundError,
        WorkingBriefCompiler,
    )

    return {
        "CandidateContext": CandidateContext,
        "FeedbackRoundService": FeedbackRoundService,
        "InvalidFeedbackError": InvalidFeedbackError,
        "InvalidIntentModelError": InvalidIntentModelError,
        "InvalidWorkingBriefError": InvalidWorkingBriefError,
        "RoundNotFoundError": RoundNotFoundError,
        "WorkingBriefCompiler": WorkingBriefCompiler,
    }


def predecessor(tmp_path: Path):
    modules, store, round_record = context(tmp_path)
    model = compile_model(modules, store, round_record)
    brief = modules["WorkingBriefCompiler"](store).compile(
        round_id=round_record.id,
        brief_id="working-brief",
        intent_model=model,
        triggers=[
            {
                "kind": "initial_request",
                "text": "Start the reverse-engineering research.",
                "input_ids": ["input-brief"],
            }
        ],
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
        working_interpretation="A local-first demo is currently leading.",
        technical_outcome="Produce an implementation-ready technical blueprint.",
    )
    finding = store.append_artifact(
        round_record.id,
        "finding-isolation",
        "finding-pack",
        {"summary": "The prior isolation finding is candidate context."},
    )
    decision = store.append_artifact(
        round_record.id,
        "decision-hosting",
        "decision-ledger-entry",
        {"summary": "The hosted option was previously selected."},
    )
    work = store.append_artifact(
        round_record.id,
        "work-active",
        "work-item",
        {"status": "running", "scope": "Complete the old hosting spike."},
    )
    return modules, store, round_record, model, brief, finding, decision, work


def successor_analysis() -> dict[str, object]:
    return {
        "signals": [
            {
                "input_id": "input-feedback",
                "observation": "The requester rejects the hosted direction.",
                "kind": "stated_goal",
                "authority_boundary": "Does not prove an implementation choice.",
            },
            {
                "input_id": "input-brief",
                "observation": "The original brief still asks for a reverse-engineering agent.",
                "kind": "context",
                "authority_boundary": "Does not retain the earlier deployment decision.",
            },
            {
                "input_id": "input-local",
                "observation": "The local execution constraint remains candidate material.",
                "kind": "constraint",
                "authority_boundary": "Requires fresh technical validation.",
            },
        ],
        "hypotheses": [
            {
                "id": "intent-local-successor",
                "interpretation": "Enable an inspectable local-first reverse-engineering workflow.",
                "status": "leading",
                "signal_refs": ["input-feedback", "input-brief", "input-local"],
                "confidence": "high",
                "decision_consequence": "Research local isolation, evidence capture, and operator controls.",
                "validation": "repository_inspection",
            }
        ],
        "desired_outcomes": ["a local, implementation-ready technical blueprint"],
        "success_signals": ["an implementation agent can build the local path"],
        "decision_drivers": [
            {
                "dimension": "technical",
                "statement": "The implementation must be inspectable locally.",
                "signal_refs": ["input-feedback"],
            }
        ],
        "hard_constraints": ["Do not execute untrusted binaries during intake."],
        "non_goals": ["Do not retain hosted deployment merely from prior approval."],
        "unresolved_interpretations": [],
    }


def candidates(api_modules, store, round_record, *, dispositions: dict[str, str]):
    candidate_context = api_modules["CandidateContext"]
    latest = {
        artifact.id: artifact
        for artifact in store.load_round(round_record.id).artifacts
        if artifact.kind in {"input-ledger-entry", "finding-pack", "decision-ledger-entry"}
    }
    return tuple(
        candidate_context(
            candidate_id=f"candidate-{artifact_id}",
            artifact=latest[artifact_id],
            disposition=dispositions[artifact_id],
            rationale=f"Explicitly assessed {artifact_id} for the successor.",
        )
        for artifact_id in sorted(dispositions)
    )


def start_successor(api_modules, store, prior_round, candidate_context, **overrides):
    request = {
        "prior_round_id": prior_round.id,
        "successor_round_id": "round-successor",
        "feedback_input_id": "input-feedback",
        "feedback_text": "Reject hosted deployment; make the first path local and inspectable.",
        "feedback_origin_locator": "conversation:2",
        "change_dimensions": ("priority", "success_definition"),
        "change_reason": "The requester changed the required operating model.",
        "safe_checkpoint": "After the active finding-pack boundary.",
        "candidates": candidate_context,
        "intent_id": "intent-successor",
        "intent_input_ids": ("input-feedback", "input-brief", "input-local"),
        "intent_analysis": successor_analysis(),
        "context_bundle_id": "context-successor",
        "context_member_input_ids": ("input-feedback", "input-brief", "input-local"),
        "brief_id": "brief-successor",
        "selected_input_ids": ("input-feedback", "input-brief", "input-local"),
        "input_roles": {
            "input-feedback": "primary",
            "input-brief": "context",
            "input-local": "constraint",
        },
        "material_conflicts": (),
        "working_interpretation": "A local, inspectable workflow is now the leading direction.",
        "technical_outcome": "Produce a local-first technical research and implementation plan.",
        "strategy_id": "strategy-successor",
        "strategy_summary": "Re-evaluate isolation and integration for local operation.",
        "strategy_focus": ("local isolation", "repository integration"),
    }
    request.update(overrides)
    return api_modules["FeedbackRoundService"](store).start_successor(**request)


def test_target_changing_feedback_creates_immutable_successor_with_explicit_context(
    tmp_path: Path,
) -> None:
    api_modules = api()
    modules, store, prior_round, model, brief, finding, decision, work = predecessor(tmp_path)
    before_model = model
    before_brief = brief
    candidate_context = candidates(
        api_modules,
        store,
        prior_round,
        dispositions={
            "decision-hosting": "overturn",
            "finding-isolation": "downgrade",
            "input-brief": "reuse",
            "input-cloud": "ignore",
            "input-context": "ignore",
            "input-local": "revalidate",
        },
    )

    result = start_successor(api_modules, store, prior_round, candidate_context)

    assert result.round.parent_round_id == prior_round.id
    assert result.feedback_input.payload["kind"] == "feedback"
    assert result.intent_model.round_id == result.round.id
    assert result.working_brief.round_id == result.round.id
    assert result.strategy.kind == "research-strategy"
    assert result.strategy.payload["feedback_lineage_id"] == result.lineage.id
    assert result.lineage.payload["lineage_kind"] == "successor"
    assert result.lineage.payload["candidate_context"][0]["id"] == "candidate-decision-hosting"
    assert {
        (candidate.artifact.round_id, candidate.artifact.id, candidate.artifact.revision)
        for candidate in candidate_context
    } <= {
        (reference.round_id, reference.artifact_id, reference.revision)
        for reference in result.lineage.parent_refs
    }
    assert result.working_brief.payload["prior_material_disposition"] == {
        "decision-hosting": "overturn",
        "finding-isolation": "downgrade",
        "input-brief": "reuse",
        "input-cloud": "ignore",
        "input-context": "ignore",
        "input-local": "revalidate",
    }
    carried_by_id = {artifact.id: artifact for artifact in result.carried_inputs}
    assert set(carried_by_id) == {"input-brief", "input-local"}
    assert carried_by_id["input-brief"].parent_refs[0].round_id == prior_round.id
    assert carried_by_id["input-brief"].payload["used_by_rounds"] == ("round-successor",)
    assert result.supersession.payload["status"] == "superseded"
    assert result.supersession.payload["successor_round_id"] == result.round.id
    assert result.supersession.payload["active_work"] == (
        {
            "work_item_ref": {
                "round_id": prior_round.id,
                "artifact_id": work.id,
                "revision": work.revision,
            },
            "status_at_checkpoint": "running",
            "disposition": "superseded",
        },
    )
    prior = store.load_round(prior_round.id)
    stored_model = next(artifact for artifact in prior.artifacts if artifact == before_model)
    stored_brief = next(artifact for artifact in prior.artifacts if artifact == before_brief)
    assert stored_model.payload == before_model.payload
    assert stored_brief.payload == before_brief.payload
    assert finding in prior.artifacts
    assert decision in prior.artifacts
    assert work.payload["status"] == "running"
    rehydrated = modules["RunStore"](store.root).load_round(result.round.id)
    stored_lineage = next(artifact for artifact in rehydrated.artifacts if artifact == result.lineage)
    stored_strategy = next(artifact for artifact in rehydrated.artifacts if artifact == result.strategy)
    assert stored_lineage.payload == result.lineage.payload
    assert (
        stored_strategy.parent_refs[-1].round_id,
        stored_strategy.parent_refs[-1].artifact_id,
        stored_strategy.parent_refs[-1].revision,
    ) == (result.lineage.round_id, result.lineage.id, result.lineage.revision)


def test_overall_rejection_starts_a_new_root_but_preserves_prior_provenance(tmp_path: Path) -> None:
    api_modules = api()
    modules, store, prior_round, *_ = predecessor(tmp_path)
    candidate_context = candidates(
        api_modules,
        store,
        prior_round,
        dispositions={
            "decision-hosting": "overturn",
            "finding-isolation": "ignore",
            "input-brief": "reuse",
            "input-cloud": "ignore",
            "input-context": "ignore",
            "input-local": "revalidate",
        },
    )

    result = start_successor(
        api_modules,
        store,
        prior_round,
        candidate_context,
        overall_rejection=True,
    )

    assert result.round.parent_round_id is None
    assert result.lineage.payload["lineage_kind"] == "new_root"
    assert any(reference.round_id == prior_round.id for reference in result.lineage.parent_refs)


def test_same_round_replanning_records_feedback_without_creating_successor_artifacts(
    tmp_path: Path,
) -> None:
    api_modules = api()
    modules, store, prior_round, model, brief, *_ = predecessor(tmp_path)

    replan = api_modules["FeedbackRoundService"](store).record_same_round_replan(
        round_id=prior_round.id,
        replan_id="replan-budget",
        feedback_input_id="input-budget-feedback",
        feedback_text="Keep the target, but use the remaining budget on repository inspection.",
        feedback_origin_locator="conversation:2",
        reason="Only the work allocation changes.",
    )

    snapshot = store.load_round(prior_round.id)
    assert replan.kind == "same-round-replan"
    assert replan.payload["classification"] == "same_round_replan"
    assert model in snapshot.artifacts
    assert brief in snapshot.artifacts
    assert not [artifact for artifact in snapshot.artifacts if artifact.kind == "research-strategy"]
    with pytest.raises(api_modules["RoundNotFoundError"]):
        store.load_round("round-successor")


def test_missing_candidate_disposition_rejects_before_creating_successor_round(tmp_path: Path) -> None:
    api_modules = api()
    modules, store, prior_round, *_ = predecessor(tmp_path)
    incomplete_candidates = candidates(
        api_modules,
        store,
        prior_round,
        dispositions={
            "decision-hosting": "overturn",
            "finding-isolation": "ignore",
            "input-brief": "reuse",
            "input-context": "ignore",
            "input-local": "revalidate",
        },
    )

    with pytest.raises(api_modules["InvalidFeedbackError"], match="explicitly disposition"):
        start_successor(api_modules, store, prior_round, incomplete_candidates)

    with pytest.raises(api_modules["RoundNotFoundError"]):
        store.load_round("round-successor")


@pytest.mark.parametrize(
    ("overrides", "error_name"),
    (
        ({"intent_analysis": {"signals": []}}, "InvalidIntentModelError"),
        (
            {
                "input_roles": {
                    "input-feedback": "primary",
                    "input-brief": "context",
                }
            },
            "InvalidWorkingBriefError",
        ),
        (
            {
                "material_conflicts": (
                    {"input_ids": ["input-brief"], "status": "open", "note": "Malformed."},
                )
            },
            "InvalidWorkingBriefError",
        ),
        (
            {
                "delivery_targets": {
                    "technical_research_package": "yes",
                    "human_brief": True,
                    "openspec": False,
                }
            },
            "InvalidWorkingBriefError",
        ),
    ),
    ids=("intent-analysis", "input-roles", "material-conflicts", "late-brief-validation"),
)
def test_rejected_successor_compilation_is_atomic_and_retryable(
    tmp_path: Path,
    overrides: dict[str, object],
    error_name: str,
) -> None:
    api_modules = api()
    modules, store, prior_round, *_ = predecessor(tmp_path)
    candidate_context = candidates(
        api_modules,
        store,
        prior_round,
        dispositions={
            "decision-hosting": "overturn",
            "finding-isolation": "downgrade",
            "input-brief": "reuse",
            "input-cloud": "ignore",
            "input-context": "ignore",
            "input-local": "revalidate",
        },
    )

    before = store.load_round(prior_round.id)
    with pytest.raises(api_modules[error_name]):
        start_successor(api_modules, store, prior_round, candidate_context, **overrides)

    with pytest.raises(api_modules["RoundNotFoundError"]):
        store.load_round("round-successor")
    assert store.load_round(prior_round.id) == before

    result = start_successor(api_modules, store, prior_round, candidate_context)

    assert result.round.id == "round-successor"
