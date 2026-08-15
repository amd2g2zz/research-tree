from __future__ import annotations

from pathlib import Path

import pytest

from research_tree import ArtifactRef, CandidateContext, CanonicalFeedbackRoundService, InvalidIntentModelError
from research_tree.run_ledger import LedgerConflictError, LedgerIntegrityError
from canonical_finding_fixture import RUN_ID, canonical_context


def _successor_analysis() -> dict[str, object]:
    return {
        "signals": [
            {
                "input_id": "input-feedback",
                "observation": "The requester rejects the prior isolation direction.",
                "kind": "stated_goal",
                "authority_boundary": "Does not prove an implementation choice.",
            },
            {
                "input_id": "input-brief",
                "observation": "The original brief remains relevant context.",
                "kind": "context",
                "authority_boundary": "Does not retain the prior decision.",
            },
            {
                "input_id": "input-repository",
                "observation": "The repository baseline needs fresh validation.",
                "kind": "constraint",
                "authority_boundary": "Requires a new inspection.",
            },
        ],
        "hypotheses": [
            {
                "id": "intent-successor",
                "interpretation": "Re-evaluate the isolated worker boundary.",
                "status": "leading",
                "signal_refs": ["input-feedback", "input-brief", "input-repository"],
                "confidence": "high",
                "decision_consequence": "Review the worker boundary again.",
                "validation": "repository_inspection",
            }
        ],
        "desired_outcomes": ["a revised implementation-ready blueprint"],
        "success_signals": ["the successor can start bounded research"],
        "decision_drivers": [
            {
                "dimension": "technical",
                "statement": "The successor must preserve inspectable lineage.",
                "signal_refs": ["input-feedback"],
            }
        ],
        "hard_constraints": ["Do not mutate predecessor artifacts."],
        "non_goals": ["Do not silently reuse the prior decision."],
        "unresolved_interpretations": [],
    }


def _candidates(ledger) -> tuple[CandidateContext, ...]:
    snapshot = ledger.load_run(RUN_ID)
    dispositions = {
        "decision-isolation": "overturn",
        "finding-isolation": "downgrade",
        "input-brief": "reuse",
        "input-context": "ignore",
        "input-repository": "revalidate",
    }
    by_id = {artifact.id: artifact for artifact in snapshot.artifacts}
    return tuple(
        CandidateContext(
            candidate_id=f"candidate-{artifact_id}",
            artifact=by_id[artifact_id],
            disposition=disposition,
            rationale=f"Explicitly assessed {artifact_id} for the successor.",
        )
        for artifact_id, disposition in sorted(dispositions.items())
    )


def _start_successor(service: CanonicalFeedbackRoundService, ledger, **overrides):
    request = {
        "prior_round_id": RUN_ID,
        "successor_round_id": "round-successor",
        "feedback_input_id": "input-feedback",
        "feedback_text": "Re-evaluate the prior isolation direction with a new implementation plan.",
        "feedback_origin_locator": "conversation:2",
        "change_dimensions": ("priority", "success_definition"),
        "change_reason": "The requester changed the implementation direction.",
        "safe_checkpoint": "After the current active work boundary.",
        "candidates": _candidates(ledger),
        "intent_id": "intent-successor",
        "intent_input_ids": ("input-feedback", "input-brief", "input-repository"),
        "intent_analysis": _successor_analysis(),
        "context_bundle_id": "context-successor",
        "context_member_input_ids": ("input-feedback", "input-brief", "input-repository"),
        "brief_id": "brief-successor",
        "selected_input_ids": ("input-feedback", "input-brief", "input-repository"),
        "input_roles": {
            "input-feedback": "primary",
            "input-brief": "context",
            "input-repository": "constraint",
        },
        "material_conflicts": (),
        "working_interpretation": "The prior direction must be re-evaluated.",
        "technical_outcome": "Produce a revised implementation-ready blueprint.",
        "strategy_id": "strategy-successor",
        "strategy_summary": "Re-evaluate the worker boundary with fresh evidence.",
        "strategy_focus": ("worker boundary", "repository integration"),
        "expected_predecessor_revision": ledger.get_revision(RUN_ID),
    }
    request.update(overrides)
    return service.start_successor(**request)


def test_canonical_successor_commits_predecessor_and_successor_together(tmp_path: Path) -> None:
    ledger, *_ = canonical_context(tmp_path)
    service = CanonicalFeedbackRoundService(ledger)
    prior_before = ledger.load_run(RUN_ID)

    result = _start_successor(service, ledger)

    assert result.round.parent_round_id == RUN_ID
    assert result.feedback_input.round_id == result.round.id
    assert [artifact.id for artifact in result.carried_inputs] == ["input-brief", "input-repository"]
    assert result.lineage.parent_refs[0] == ArtifactRef(result.round.id, "input-feedback", 1)
    assert result.supersession.parent_refs[0] == ArtifactRef(result.round.id, "input-feedback", 1)
    assert result.supersession.payload["successor_round_id"] == result.round.id
    current_prior = ledger.load_run(RUN_ID)
    assert all(artifact in current_prior.artifacts for artifact in prior_before.artifacts)
    assert len(current_prior.artifacts) == len(prior_before.artifacts) + 1
    assert ledger.get_revision(result.round.id) == len(ledger.load_run(result.round.id).artifacts)


def test_canonical_successor_failure_rolls_back_both_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger, *_ = canonical_context(tmp_path)
    service = CanonicalFeedbackRoundService(ledger)
    prior_before = ledger.load_run(RUN_ID)
    monkeypatch.setattr(ledger, "_before_commit", lambda: (_ for _ in ()).throw(RuntimeError("injected")))

    with pytest.raises(RuntimeError, match="injected"):
        _start_successor(service, ledger)

    assert ledger.load_run(RUN_ID) == prior_before
    with pytest.raises(LedgerIntegrityError, match="run does not exist: round-successor"):
        ledger.load_run("round-successor")


def test_canonical_overall_rejection_creates_a_root_with_prior_provenance(tmp_path: Path) -> None:
    ledger, *_ = canonical_context(tmp_path)
    service = CanonicalFeedbackRoundService(ledger)

    result = _start_successor(
        service,
        ledger,
        successor_round_id="round-root",
        overall_rejection=True,
    )

    assert result.round.parent_round_id is None
    assert result.lineage.payload["lineage_kind"] == "new_root"
    assert any(reference.round_id == RUN_ID for reference in result.lineage.parent_refs)
    assert result.supersession.payload["successor_round_id"] == result.round.id


def test_canonical_successor_rejects_invalid_plan_or_stale_predecessor_without_writes(tmp_path: Path) -> None:
    ledger, *_ = canonical_context(tmp_path)
    service = CanonicalFeedbackRoundService(ledger)
    prior_before = ledger.load_run(RUN_ID)

    with pytest.raises(InvalidIntentModelError):
        _start_successor(service, ledger, intent_analysis={"signals": []})

    with pytest.raises(LedgerConflictError, match="stale run revision"):
        _start_successor(service, ledger, expected_predecessor_revision=ledger.get_revision(RUN_ID) - 1)

    assert ledger.load_run(RUN_ID) == prior_before
    with pytest.raises(LedgerIntegrityError, match="run does not exist: round-successor"):
        ledger.load_run("round-successor")
