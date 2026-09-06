"""Issue #489: policy selection becomes contract emission (the canonical loop).

Each alignment turn the engine emits structured contract terms — ``target_gap``
(the graph node this turn must advance, ranked with #496 divergence awareness
and the #490 user-move redirect), ``required_traces`` (finite types from the
``turn_contract`` registry, derived from gap shape and the response-cost
class), ``cost_cap`` (the user response-production ceiling), and ``taboos``
(already-answered and ask-spent nodes) — then verifies the recorded traces
against the terms at record time, and the #497 turn record persists terms +
traces + user move. The 13-candidate strategy list never appears here: it is
prompt-layer craft (``references/alignment-craft.md``), not engine vocabulary.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from research_tree.alignment_graph import AlignmentGraphStore
from research_tree.alignment_turn_record import AlignmentTurnRecordStore
from research_tree.turn_contract import (
    RESPONSE_CLASS_DISCRIMINATION,
    RESPONSE_CLASS_GENERATION,
    ContractTerms,
    MissingTraceError,
)


def _store(tmp_path: Path, *, run_shaped: bool = False) -> AlignmentGraphStore:
    database = tmp_path / "alignment" / "alignment.db" if run_shaped else tmp_path / "alignment.db"
    store = AlignmentGraphStore(database)
    store.initialize("run-489")
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


def _signal(category: str, rule: str = "rule") -> dict[str, str]:
    return {"category": category, "confidence": "high", "rule": rule}


def _feed_user_move(run_root: Path, category: str, rule: str = "rule") -> None:
    """Persist one ``alignment_user_move`` feed record the way the hook does."""
    events = run_root / "events"
    events.mkdir(parents=True, exist_ok=True)
    existing = len(list(events.glob("*.json")))
    path = events / f"20260907T000000{existing:03d}Z-{existing:016x}.json"
    path.write_text(
        json.dumps(
            {
                "schema": 1,
                "route": "alignment_user_move",
                "category": category,
                "confidence": "high",
                "rule": rule,
            }
        ),
        encoding="utf-8",
    )


def test_plan_emits_contract_terms_ranked_from_the_graph(tmp_path: Path) -> None:
    """target_gap follows the divergence-aware ranking; taboos name spent/settled nodes."""
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-fresh", 5, "candidate"), ("gap-axis", 3, "candidate"), ("gap-spent", 2, "candidate"))

    decision = store.plan()
    assert decision["action"] == "ask_one"
    assert decision["gap_id"] == "gap-fresh"
    terms = decision["contract_terms"]
    assert terms["target_gap"] == "gap-fresh"
    assert terms["taboos"] == []
    assert terms["schema_version"] == 1

    # The answer settles the node: it leaves the ranking and becomes taboo.
    store.record("gap-fresh", "answered", "fp-1")
    decision = store.plan()
    assert decision["gap_id"] == "gap-axis"
    assert decision["contract_terms"]["target_gap"] == "gap-axis"
    assert decision["contract_terms"]["taboos"] == ["gap-fresh"]

    store.record("gap-axis", "unchanged", "fp-axis")
    decision = store.plan()
    assert decision["gap_id"] == "gap-axis"
    store.record("gap-axis", "unchanged", "fp-axis", new_axes=["What about the cost constraint?"])

    # The ask budget on the axis node is spent, but the active divergence axis
    # outranks it: the turn stays on the axis.
    decision = store.plan()
    assert decision["action"] == "ask_one"
    assert decision["node_id"] == "gap-axis"
    assert decision["axis_id"]
    assert decision["contract_terms"]["target_gap"] == "gap-axis"

    store.record("gap-axis", "unchanged", "fp-axis")
    decision = store.plan()
    assert decision["gap_id"] == "gap-axis"
    store.record("gap-axis", "unchanged", "fp-axis")

    # The axis is spent and locally stalled with no axis left: the ranking
    # excludes it into taboos and moves to the remaining fresh gap.
    decision = store.plan()
    assert decision["action"] == "ask_one"
    assert decision["node_id"] == "gap-spent"
    terms = decision["contract_terms"]
    assert terms["target_gap"] == "gap-spent"
    assert set(terms["taboos"]) == {"gap-fresh", "gap-axis"}
    assert terms["target_gap"] not in terms["taboos"]
    # Additive surface: the existing decision keys are unchanged.
    assert decision["question"]
    assert "alignment_score" in decision


def test_user_move_redirect_is_applied_via_the_response_policy(tmp_path: Path) -> None:
    """The #490 verdict moves target-gap selection from the observed user move."""
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 5, "candidate"), ("gap-b", 4, "candidate"))
    store.plan()

    redirected = store.plan(user_signal=_signal("interruption", "explicit_stop"))
    policy = redirected["user_move_policy"]
    assert policy["gap_directive"] == "redirect"
    assert policy["user_move"] == RESPONSE_CLASS_GENERATION
    assert redirected["contract_terms"]["target_gap"] == "gap-b"

    answered = store.plan(user_signal=_signal("answer", "direct_affirmative"))
    assert answered["user_move_policy"]["gap_directive"] == "advance"
    # The answer settles the outstanding ask (gap-b): it becomes taboo and
    # selection advances to the next candidate.
    assert answered["contract_terms"]["target_gap"] == "gap-a"
    assert "gap-b" in answered["contract_terms"]["taboos"]

    corrected = store.plan(user_signal=_signal("correction", "explicit_wrong"))
    assert corrected["user_move_policy"]["gap_directive"] == "reopen"
    assert corrected["contract_terms"]["target_gap"] == "gap-a"
    assert "gap-a" not in corrected["contract_terms"]["taboos"]
    assert corrected["contract_terms"]["required_traces"] == ["guess-statement"]


def test_plan_reads_the_fed_user_move_record_from_the_run_events_surface(tmp_path: Path) -> None:
    """The persisted alignment_user_move feed is the default emission transport."""
    store = _store(tmp_path, run_shaped=True)
    _merge_gaps(store, ("gap-a", 5, "candidate"), ("gap-b", 4, "candidate"))
    store.plan()
    _feed_user_move(tmp_path, "interruption", "explicit_stop")

    decision = store.plan()
    assert decision["user_move_policy"]["gap_directive"] == "redirect"
    assert decision["contract_terms"]["target_gap"] == "gap-b"


def test_required_traces_derive_from_gap_type(tmp_path: Path) -> None:
    """Proposal-shaped gaps need a survey or option set; misunderstood intent needs a guess."""
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-proposal", 5, "candidate"))

    decision = store.plan()
    assert decision["contract_terms"]["required_traces"] == ["possibility-survey"]

    # A disputed point is a misunderstood-intent gap: the turn must restate
    # the corrected understanding.
    disputed = _store(tmp_path / "disputed")
    _merge_gaps(disputed, ("gap-disputed", 5, "disputed"))
    decision = disputed.plan()
    assert decision["contract_terms"]["required_traces"] == ["guess-statement"]

    # The same derivation holds when a correction re-opened the asked node.
    reopened = _store(tmp_path / "reopened")
    _merge_gaps(reopened, ("gap-asked", 5, "candidate"), ("gap-other", 4, "candidate"))
    reopened.plan()
    decision = reopened.plan(user_signal=_signal("correction", "explicit_wrong"))
    assert decision["contract_terms"]["target_gap"] == "gap-asked"
    assert decision["contract_terms"]["required_traces"] == ["guess-statement"]


def test_proposal_gap_under_a_discrimination_cap_requires_the_option_set(tmp_path: Path) -> None:
    """A pointing response requires the options be shown: option-set under a discrimination cap."""
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 5, "candidate"), ("gap-b", 4, "candidate"))
    store.plan()

    # The repeated correction drops the ceiling to the one-sentence floor and
    # re-opens the corrected node (misunderstood intent).
    decision = store.plan(
        user_signal=_signal("correction", "explicit_no"),
        previous_category="correction",
    )
    assert decision["contract_terms"]["cost_cap"] == {
        "response_class": RESPONSE_CLASS_DISCRIMINATION,
        "max_sentences": 1,
    }
    assert decision["contract_terms"]["required_traces"] == ["guess-statement"]

    # The user answers the re-opened ask; the next candidate is asked under
    # the carried floor cap, so the pointing turn requires the option set.
    store.record("gap-a", "answered", "fp-1")
    decision = store.plan()
    assert decision["node_id"] == "gap-b"
    assert decision["contract_terms"]["cost_cap"] == {
        "response_class": RESPONSE_CLASS_DISCRIMINATION,
        "max_sentences": 1,
    }
    assert decision["contract_terms"]["required_traces"] == ["option-set"]

    # Non-asking decisions emit an empty trace gate.
    ready = _store(tmp_path / "ready")
    ready.merge(_handoff_ready_graph())
    decision = ready.plan()
    assert decision["action"] == "await_human_confirmation"
    assert decision["contract_terms"]["cost_cap"] == {
        "response_class": RESPONSE_CLASS_DISCRIMINATION,
        "max_sentences": 1,
    }
    assert decision["contract_terms"]["required_traces"] == []


def test_cost_cap_reflects_the_user_move_class(tmp_path: Path) -> None:
    """Correction lowers (never raises); neutral keeps; interruption raises."""
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 5, "candidate"))
    store.plan()

    corrected = store.plan(user_signal=_signal("correction", "explicit_wrong"))
    assert corrected["contract_terms"]["cost_cap"] == {
        "response_class": RESPONSE_CLASS_GENERATION,
        "max_sentences": 2,
    }
    repeated = store.plan(
        user_signal=_signal("correction", "explicit_no"),
        previous_category="correction",
    )
    assert repeated["contract_terms"]["cost_cap"] == {
        "response_class": RESPONSE_CLASS_DISCRIMINATION,
        "max_sentences": 1,
    }
    neutral = store.plan(user_signal=_signal("neutral", "default"))
    assert neutral["contract_terms"]["cost_cap"] == {
        "response_class": RESPONSE_CLASS_DISCRIMINATION,
        "max_sentences": 1,
    }
    raised = store.plan(user_signal=_signal("interruption", "explicit_stop"))
    assert raised["contract_terms"]["cost_cap"] == {
        "response_class": RESPONSE_CLASS_GENERATION,
        "max_sentences": None,
    }


def test_a_recorded_turn_missing_a_required_trace_fails_verification_naming_the_term(
    tmp_path: Path,
) -> None:
    """Verify at record time via turn_contract.verify_traces(): the term is named."""
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 5, "candidate"))
    decision = store.plan()
    required = decision["contract_terms"]["required_traces"][0]
    before = store.status()

    with pytest.raises(MissingTraceError, match=f"missing required trace: {required}"):
        store.record("gap-a", "unchanged", "fp-1", traces=[])

    # Fail-closed: nothing was persisted for the failed turn.
    after = store.status()
    assert after["controller"]["turn"] == before["controller"]["turn"]
    assert after["controller"]["revision"] == before["controller"]["revision"]

    # An unregistered trace type fails the same gate.
    with pytest.raises(Exception, match="unregistered trace type"):
        store.record("gap-a", "unchanged", "fp-1", traces=[{"type": "not-a-trace", "payload": {}}])


def test_a_recorded_turn_carrying_the_traces_persists_terms_traces_and_user_move(
    tmp_path: Path,
) -> None:
    """The passing turn reports the satisfied terms and persists the whole loop (#497)."""
    store = _store(tmp_path, run_shaped=True)
    _merge_gaps(store, ("gap-a", 5, "candidate"))
    decision = store.plan()
    required = decision["contract_terms"]["required_traces"][0]
    traces = [{"type": required, "payload": {"possibilities": ["build", "buy"]}}]

    result = store.record("gap-a", "changed", "fp-2", traces=traces, user_move=RESPONSE_CLASS_GENERATION)
    assert result["verified_traces"] == (required,)

    with sqlite3.connect(store.database) as connection:
        connection.row_factory = sqlite3.Row
        details = json.loads(
            connection.execute(
                "SELECT details_json FROM events WHERE event_type='response_recorded' ORDER BY sequence DESC LIMIT 1"
            ).fetchone()["details_json"]
        )
    assert details["traces"] == traces
    assert details["user_move"] == RESPONSE_CLASS_GENERATION

    # Canonical loop step 4: the #497 turn record carries terms + traces + user move.
    records = AlignmentTurnRecordStore(store.database.parent)
    terms = ContractTerms.from_dict(decision["contract_terms"])
    records.append(
        turn_index=1,
        mirror="the auth model is understood as option a",
        gap="whether the auth model is option a",
        delta_summary="the requester corrected the auth model",
        user_move=RESPONSE_CLASS_GENERATION,
        contract_terms=terms,
        traces=traces,
    )
    persisted = records.records()[0]
    assert persisted.contract_terms == terms
    assert persisted.contract_terms is not None
    assert persisted.contract_terms.target_gap == "gap-a"
    assert persisted.traces == ({"type": required, "payload": {"possibilities": ["build", "buy"]}},)
    assert persisted.user_move == RESPONSE_CLASS_GENERATION


def test_legacy_record_without_traces_stays_green_after_an_emitting_plan(tmp_path: Path) -> None:
    """Additive surface: existing record() call sites keep working unchanged."""
    store = _store(tmp_path)
    _merge_gaps(store, ("gap-a", 5, "candidate"))
    store.plan()

    result = store.record("gap-a", "unchanged", "fp-1")
    assert "verified_traces" not in result
    assert result["next_action"] == "plan"

    decision = store.plan()
    assert decision["action"] == "ask_one"
    assert decision["contract_terms"]["target_gap"] == "gap-a"


def test_emit_turn_contract_never_names_engine_strategies(tmp_path: Path) -> None:
    """The enumerated space is contract terms and trace types, never behaviors."""
    from research_tree import alignment_graph

    for name in (
        "echo-guess",
        "example-anchor",
        "constraint-menu",
        "teach-then-verify",
        "counterexample",
        "proportionality-challenge",
        "consequence-warning",
        "mirror",
    ):
        assert not hasattr(alignment_graph, name.replace("-", "_"))
        assert name not in alignment_graph.EDGE_RELATIONS
        assert name not in alignment_graph.NODE_TYPES
    craft = Path(__file__).parents[1] / "references" / "alignment-craft.md"
    assert "must never become engine enums" in craft.read_text(encoding="utf-8")


def _handoff_ready_graph() -> dict[str, object]:
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
    nodes: list[dict[str, object]] = [
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
