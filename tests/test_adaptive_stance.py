"""Adaptive stance controller tests (issue #526).

One controller, three outputs, four measured signals. ``resolve_stance``
maps clarity (the #491 alignment score), vagueness (#524 registry open
share), conflict (registry conflict pairs + #490 correction frequency), and
the #525 violation rate onto S1 trust-first / S2 structured / S3 strict with
named thresholds; recovered clarity steps the tier back down and an explicit
user-side override beats the computed tier. The emission reflects the tier:
S1 default-trust (no forced proportionality on ordinary proposals), S2
reuses the #520 novice posture and forces the gather turn when open
directions exceed the concurrency bound, S3 makes the challenges explicit
and freezes new divergence axes. The one-question invariant is a hard gate
in S2/S3; the blocked and handoff dispositions carry the score visibly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from research_tree.alignment_graph import AlignmentGraphError, AlignmentGraphStore, _gap_required_traces, resolve_stance
from research_tree.brief_refinery import BriefRefinery, BriefRefineryStore
from research_tree.discipline import DisciplineViolationStore
from research_tree.turn_contract import CostCap


def _store(tmp_path: Path) -> AlignmentGraphStore:
    store = AlignmentGraphStore(tmp_path / "alignment" / "alignment.db")
    store.initialize("run-526")
    return store


def _merge_gaps(store: AlignmentGraphStore, *specs: tuple[str, int, str]) -> None:
    store.merge(
        {
            "nodes": [
                {
                    "id": gap_id,
                    "type": "unknown",
                    "statement": f"Requester-only dimension {gap_id}.",
                    "status": status,
                    "impact": impact,
                    "human_only": True,
                    "confidence": "low",
                    "source": "agent",
                }
                for gap_id, impact, status in specs
            ]
        }
    )


def _cap(response_class: str = "discrimination") -> CostCap:
    return CostCap(response_class=response_class, max_sentences=1)


def _node(**overrides: Any) -> dict[str, Any]:
    node: dict[str, Any] = {"id": "gap-a", "status": "candidate", "human_only": True, "impact": 3, "attributes": {}}
    node.update(overrides)
    return node


def _write_registry(run_root: Path, *, conflict_pairs: int = 0) -> None:
    """Persist a brief registry whose live objects are all still open."""
    candidates = [
        {
            "statement": f"Prefer bundled tooling {index}",
            "topic": f"topic-{index}",
            "polarity": "positive",
            "requested_type": "preference",
            "anchors": ["turn-1"],
        }
        for index in range(2 + conflict_pairs)
    ]
    candidates.extend(
        {
            "statement": f"Avoid bundled tooling {index}",
            "topic": f"topic-{index}",
            "polarity": "negative",
            "requested_type": "preference",
            "anchors": ["turn-1"],
        }
        for index in range(conflict_pairs)
    )
    refinery = BriefRefinery()
    refinery.extract({"candidates": candidates})
    BriefRefineryStore(run_root).save(refinery)


def _write_violations(run_root: Path, count: int) -> None:
    DisciplineViolationStore(run_root).append(
        [
            {"turn_index": index, "dimension": "questions", "measured": 2, "cap": 1, "source": "agent_turn_budget"}
            for index in range(count)
        ]
    )


def _feed_corrections(run_root: Path, count: int) -> None:
    events = run_root / "events"
    events.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        (events / f"20260912T00000{index}Z-{index:016x}.json").write_text(
            json.dumps(
                {
                    "schema": 1,
                    "route": "alignment_user_move",
                    "category": "correction",
                    "confidence": "high",
                    "rule": "explicit_wrong",
                }
            ),
            encoding="utf-8",
        )


# --- Scenario: resolve_stance thresholds — each tier reached and left --------


def test_resolve_stance_starts_trust_first_and_stays_there_without_signals() -> None:
    assert resolve_stance(0, 0.0, 0, 0.0) == "S1"
    assert resolve_stance(0, 0.49, 0, 0.0) == "S1"
    assert resolve_stance(0, 0.0, 1, 0.0) == "S1"
    assert resolve_stance(0, 0.0, 0, 0.39) == "S1"


def test_high_vagueness_reaches_and_leaves_s2() -> None:
    assert resolve_stance(0, 0.5, 0, 0.0) == "S2"
    assert resolve_stance(0, 1.0, 0, 0.0) == "S2"
    assert resolve_stance(85, 0.9, 0, 0.0) == "S1"


def test_high_conflict_reaches_s3() -> None:
    assert resolve_stance(0, 0.0, 2, 0.0) == "S3"
    assert resolve_stance(0, 0.9, 5, 0.0) == "S3"


def test_high_violation_rate_reaches_s3() -> None:
    assert resolve_stance(0, 0.0, 0, 0.4) == "S3"
    assert resolve_stance(0, 0.9, 0, 1.0) == "S3"


def test_recovered_clarity_steps_the_tier_back_down() -> None:
    assert resolve_stance(85, 0.0, 5, 0.0) == "S2"
    assert resolve_stance(84, 0.0, 5, 0.0) == "S3"
    assert resolve_stance(100, 0.0, 0, 0.0) == "S1"


def test_resolve_stance_rejects_out_of_range_signals() -> None:
    for args in (
        (101, 0.0, 0, 0.0),
        (-1, 0.0, 0, 0.0),
        (0, 1.5, 0, 0.0),
        (0, -0.1, 0, 0.0),
        (0, 0.0, -1, 0.0),
        (0, 0.0, 0, 2.0),
    ):
        with pytest.raises(AlignmentGraphError):
            resolve_stance(*args)
    with pytest.raises(AlignmentGraphError):
        resolve_stance(True, 0.0, 0, 0.0)


# --- Scenario: override param wins; unknown tier/override rejected ------------


def test_the_explicit_override_beats_the_computed_tier() -> None:
    assert resolve_stance(0, 0.9, 9, 0.9, override="S1") == "S1"
    assert resolve_stance(100, 0.0, 0, 0.0, override="S3") == "S3"


def test_unknown_tier_and_override_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(AlignmentGraphError):
        resolve_stance(0, 0.0, 0, 0.0, override="S4")
    store = _store(tmp_path)
    with pytest.raises(AlignmentGraphError, match="stance"):
        store.plan(stance="S9")
    with pytest.raises(AlignmentGraphError, match="stance"):
        store.plan(stance="trust-first")


# --- Scenario: S1 default-trust — ordinary proposals are not strip-searched ---


def test_s1_ordinary_proposal_emits_no_forced_proportionality() -> None:
    assert _gap_required_traces(_node(), reopened=False, cap=_cap(), stance="S1") == ("option-set",)
    assert _gap_required_traces(_node(), reopened=False, cap=_cap("generation"), stance="S1") == ("possibility-survey",)


def test_plan_computed_s1_leaves_the_ordinary_proposal_ungated(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-calm", 3, "candidate"))
    decision = store.plan()
    assert decision["stance"] == "S1"
    assert decision["stance_signals"] == {"clarity": 40, "vagueness": 0.0, "conflict": 0, "violation_rate": 0.0}
    assert decision["contract_terms"]["required_traces"] == ["possibility-survey"]


def test_a_magnitude_signal_promotes_the_assessment_outside_s3() -> None:
    high_impact = _node(impact=4)
    assert _gap_required_traces(high_impact, reopened=False, cap=_cap(), stance="S1") == (
        "option-set",
        "proportionality_assessment",
    )
    judged = _node(impact=2, attributes={"proportionality_assessment": {"direction": "over"}})
    assert _gap_required_traces(judged, reopened=False, cap=_cap(), stance="S2") == (
        "option-set",
        "proportionality_assessment",
    )
    assert _gap_required_traces(_node(impact=2), reopened=False, cap=_cap(), stance="S1") == ("option-set",)


# --- Scenario: S2 novice posture + gather duty on axis overflow ---------------


def test_s2_reuses_the_novice_posture(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 3, "candidate"))
    _write_registry(tmp_path)
    decision = store.plan()
    assert decision["stance"] == "S2"
    assert decision["contract_terms"]["cost_cap"]["response_class"] == "discrimination"
    assert decision["contract_terms"]["required_traces"] == ["possibility-survey", "option-set"]


def test_plan_computes_s2_from_the_registry_vagueness(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 3, "candidate"))
    _write_registry(tmp_path)
    assert store.plan()["stance"] == "S2"


@pytest.mark.parametrize("stance", ["S2", "S3"])
def test_axis_overflow_forces_the_gather_action(tmp_path: Path, stance: str) -> None:
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 3, "candidate"))
    store.plan()
    store.record("gap-a", "unchanged", "fp-1", new_axes=["Direction one", "Direction two", "Direction three"])
    decision = store.plan(stance=stance)
    assert decision["action"] == "gather"
    assert decision["question"] is None
    assert len(decision["gather_options"]) == 3
    assert decision["contract_terms"]["required_traces"] == ["option-set"]
    assert decision["contract_terms"]["cost_cap"]["response_class"] == "discrimination"


def test_s1_records_axes_without_the_gather_duty(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 3, "candidate"))
    store.plan()
    store.record("gap-a", "unchanged", "fp-1", new_axes=["Direction one", "Direction two", "Direction three"])
    decision = store.plan()
    assert decision["stance"] == "S1"
    assert decision["action"] == "ask_one"


# --- Scenario: S3 explicit challenges + axis freeze ---------------------------


def test_s3_ask_turns_carry_the_explicit_challenge_traces(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 3, "candidate"))
    decision = store.plan(stance="S3")
    assert decision["stance"] == "S3"
    assert decision["contract_terms"]["required_traces"] == ["possibility-survey", "proportionality_assessment"]
    assert decision["contract_terms"]["deferred_traces"] == ["counterargument"]


def test_s3_disputed_gaps_echo_first_then_challenge() -> None:
    disputed = _node(status="disputed")
    assert _gap_required_traces(disputed, reopened=False, cap=_cap(), stance="S3") == (
        "guess-statement",
        "proportionality_assessment",
        "counterargument",
    )
    assert _gap_required_traces(disputed, reopened=False, cap=_cap(), stance="S1") == ("guess-statement",)


def test_s3_freezes_new_divergence_axes(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 3, "candidate"))
    store.plan(stance="S3")
    with pytest.raises(AlignmentGraphError, match="frozen"):
        store.record("gap-a", "unchanged", "fp-1", new_axes=["What about the cost constraint?"])
    assert store.status()["controller"]["turn"] == 0


# --- Scenario: the four signals drive the computed tier -----------------------


def test_plan_computes_s3_from_the_discipline_violation_rate(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 3, "candidate"))
    _write_violations(tmp_path, 4)
    decision = store.plan()
    assert decision["stance"] == "S3"
    assert decision["stance_signals"]["violation_rate"] == 0.4


def test_correction_frequency_feeds_the_conflict_signal(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 3, "candidate"))
    _feed_corrections(tmp_path, 2)
    decision = store.plan()
    assert decision["stance_signals"]["conflict"] == 2
    assert decision["stance"] == "S3"


def test_the_declared_stance_beats_the_computed_signals(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 3, "candidate"))
    _write_registry(tmp_path)
    decision = store.plan(stance="S1")
    assert decision["stance"] == "S1"
    assert "stance_signals" not in decision
    assert decision["contract_terms"]["required_traces"] == ["possibility-survey"]


# --- Scenario: tier-crossing invariants hold ----------------------------------


def test_the_one_question_limit_is_a_hard_gate_in_s2_and_s3(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 3, "candidate"))
    store.plan(stance="S2")
    with pytest.raises(AlignmentGraphError, match="question"):
        store.record("gap-a", "unchanged", "fp-1", question_count=2)
    assert store.status()["controller"]["turn"] == 0


def test_s1_keeps_the_flag_not_block_question_budget(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 5, "candidate"))
    store.plan()
    result = store.record("gap-a", "unchanged", "fp-1", question_count=2)
    assert result["turn_budget_violations"] == [{"dimension": "max_questions", "limit": 1, "observed": 2}]


# --- Scenario: score transparency ---------------------------------------------


def test_the_blocked_disposition_carries_the_score_and_remaining_gaps(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 5, "candidate"), ("gap-b", 4, "candidate"))
    for index in range(6):
        store.plan()
        store.record("gap-a", "unchanged", f"fp-{index}")
    decision = store.plan()
    assert decision["action"] == "alignment_incomplete"
    assert decision["score_summary"].startswith("understood ~")
    assert "gap-a" in decision["score_summary"]
    assert "gap-b" in decision["score_summary"]


def test_the_handoff_decision_carries_the_score_summary(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.merge(_handoff_ready_graph())
    decision = store.plan()
    assert decision["action"] == "await_human_confirmation"
    assert decision["score_summary"] == "understood ~100%; remaining: none"


def test_waive_reads_as_a_mutual_acknowledgment(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 5, "candidate"))
    result = store.waive("Proceeding with the stated scope is good enough for this run")
    assert result["waived"] is True
    assert result["score_summary"].startswith("understood ~0%")
    assert "gap-a" in result["score_summary"]


def _handoff_ready_graph() -> dict[str, Any]:
    required = {
        "goal": ("outcome", "Produce an implementation-driving technical strategy."),
        "use": ("intended_use", "Use the result to authorize and plan implementation."),
        "scope": ("scope_boundary", "Research and design only; no implementation yet."),
        "delivery": ("delivery", "Deliver a professional evidence-anchored technical package."),
        "authority": ("authority", "The agent owns autonomous research after confirmation."),
        "success": ("success_oracle", "Every P0 decision has evidence and a validation oracle."),
        "feasibility": ("feasibility", "The strategy is technically plausible in the stated environment."),
        "strategy": ("strategy", "Use recursive decision-risk research with independent validation."),
    }
    nodes: list[dict[str, Any]] = [
        {
            "id": node_id,
            "type": node_type,
            "statement": statement,
            "status": "supported",
            "impact": 5,
            "human_only": False,
            "confidence": "high",
            "source": "joint",
        }
        for node_id, (node_type, statement) in required.items()
    ]
    nodes.append(
        {
            "id": "question-architecture",
            "type": "research_question",
            "statement": "Which architecture best satisfies the confirmed strategy?",
            "status": "candidate",
            "impact": 5,
            "human_only": False,
            "confidence": "low",
            "source": "joint",
            "oracle": "The leading architecture survives an independent executable validation.",
        }
    )
    return {"nodes": nodes, "edges": []}
