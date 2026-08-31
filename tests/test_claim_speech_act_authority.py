"""Canonical claim, speech-act, and authority-transition model.

Issue #316: ``record_belief`` defaults to ``supported`` only when basis_refs
is non-empty; ``answered`` events no longer mechanically produce
``resolved`` nodes; status vocabulary is unified through SpeechAct +
AuthorityTransition.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from research_tree.alignment_graph import AlignmentGraphStore
from research_tree.claims import Claim
from research_tree.speech_acts import (
    BELIEF_STATUSES,
    SPEAKER_ROLES,
    SPEECH_ACT_KINDS,
    AuthorityTransition,
    AuthorityTransitionError,
    SpeechAct,
    transition,
)


def test_answered_alone_does_not_resolve(tmp_path: Path) -> None:
    """An answered event alone cannot transition a node to resolved."""

    store = AlignmentGraphStore(tmp_path / "alignment.db")
    store.initialize("run-graph-1")
    store.merge(
        {
            "nodes": [
                {
                    "id": "node-question",
                    "type": "research_question",
                    "statement": "Which architecture is best?",
                    "status": "candidate",
                    "confidence": "low",
                    "source": "agent",
                    "oracle": "An executable validation.",
                }
            ]
        }
    )

    result = store.record("node-question", "answered", "fingerprint-1")

    status = next(node["status"] for node in store.status()["graph"]["nodes"] if node["id"] == "node-question")
    assert status != "resolved"
    assert result["state_changed"] is True


def test_acceptance_speech_act_resolves_belief() -> None:
    """An acceptance speech-act under decision_owner transitions candidate -> resolved."""

    act = SpeechAct(
        kind="acceptance",
        speaker_role="human",
        speaker_id="requester",
        addressee="agent",
        authority_scope="decision_owner",
        timestamp="2026-08-30T00:00:00+00:00",
        claim_id="claim-1",
    )
    assert transition("candidate", act) == "resolved"


def test_assertion_with_basis_becomes_candidate() -> None:
    """An assertion speech-act with basis_refs -> candidate."""

    act = SpeechAct(
        kind="assert",
        speaker_role="agent",
        speaker_id="agent-1",
        addressee="human",
        authority_scope="research_owner",
        timestamp="2026-08-30T00:00:00+00:00",
        basis_refs=("evidence-1",),
    )
    assert transition("candidate", act) == "candidate"


def test_assertion_without_basis_becomes_unasserted() -> None:
    """An assertion without basis_refs -> unasserted (not candidate, not supported)."""

    act = SpeechAct(
        kind="assert",
        speaker_role="agent",
        speaker_id="agent-1",
        addressee="human",
        authority_scope="research_owner",
        timestamp="2026-08-30T00:00:00+00:00",
        basis_refs=(),
    )
    assert transition("candidate", act) == "unasserted"
    assert "unasserted" in BELIEF_STATUSES


def test_status_vocabulary_is_unified() -> None:
    """BELIEF_STATUSES is the single canonical vocabulary; consumers import it."""

    expected = {
        "candidate",
        "isolated",
        "corroborated",
        "rejected",
        "superseded",
        "contested",
        "unasserted",
        "resolved",
    }
    assert expected.issubset(BELIEF_STATUSES)
    assert "answered" not in BELIEF_STATUSES
    assert "supported" not in BELIEF_STATUSES
    assert "accepted" not in BELIEF_STATUSES
    assert "disputed" not in BELIEF_STATUSES


def test_alignment_graph_normalizes_foreign_status(tmp_path: Path) -> None:
    """A foreign status read from the graph is normalized with a deprecation note."""

    store = AlignmentGraphStore(tmp_path / "alignment.db")
    store.initialize("run-graph-2")
    store.merge(
        {
            "nodes": [
                {
                    "id": "node-strategy",
                    "type": "strategy",
                    "statement": "Strategy direction.",
                    "status": "supported",
                    "confidence": "medium",
                    "source": "agent",
                }
            ]
        }
    )

    with store._connect() as connection:  # type: ignore[attr-defined]
        connection.execute(
            "UPDATE nodes SET status=? WHERE node_id=?",
            ("answered", "node-strategy"),
        )

    nodes = store.status()["graph"]["nodes"]
    node = next(item for item in nodes if item["id"] == "node-strategy")
    assert node["status"] in BELIEF_STATUSES
    assert node["status"] != "answered"


def test_claim_carries_speech_act_metadata() -> None:
    """Claim now optionally carries speech_act, claim_kind, authority fields."""

    act = SpeechAct(
        kind="assert",
        speaker_role="agent",
        speaker_id="agent-1",
        addressee="human",
        authority_scope="research_owner",
        timestamp="2026-08-30T00:00:00+00:00",
        basis_refs=("evidence-1",),
    )
    claim = Claim(
        claim_id="claim-meta",
        subject="research-tree",
        predicate="ships",
        value="version 2",
        polarity="positive",
        scope="public release",
        version="2",
        time_range="2026-08",
        conditions=("default distribution",),
        speech_act=act,
        claim_kind="assertion",
        authority="research_owner",
    )

    assert claim.speech_act is act
    assert claim.claim_kind == "assertion"
    assert claim.authority == "research_owner"


def test_claim_admission_unchanged_with_metadata() -> None:
    """Adding optional speech_act metadata does not break backward-compat defaults."""

    claim = Claim(
        claim_id="claim-default",
        subject="research-tree",
        predicate="ships",
        value="version 2",
        polarity="positive",
        scope="public release",
        version="2",
        time_range="2026-08",
        conditions=("default distribution",),
    )

    assert claim.speech_act is None
    assert claim.claim_kind is None
    assert claim.authority is None


def test_speech_act_kind_validation() -> None:
    """SpeechAct validates the kind against the canonical vocabulary."""

    with pytest.raises(AuthorityTransitionError):
        SpeechAct(
            kind="unknown_kind",  # type: ignore[arg-type]
            speaker_role="agent",
            speaker_id="agent-1",
            addressee="human",
            authority_scope="research_owner",
            timestamp="2026-08-30T00:00:00+00:00",
        )


def test_speaker_role_validation() -> None:
    """SpeechAct validates the speaker role."""

    with pytest.raises(AuthorityTransitionError):
        SpeechAct(
            kind="assert",
            speaker_role="alien",  # type: ignore[arg-type]
            speaker_id="agent-1",
            addressee="human",
            authority_scope="research_owner",
            timestamp="2026-08-30T00:00:00+00:00",
        )


def test_acceptance_without_authority_scope_is_rejected() -> None:
    """Acceptance needs decision_owner authority; otherwise transition raises."""

    act = SpeechAct(
        kind="acceptance",
        speaker_role="human",
        speaker_id="requester",
        addressee="agent",
        authority_scope="research_owner",
        timestamp="2026-08-30T00:00:00+00:00",
        claim_id="claim-1",
    )
    with pytest.raises(AuthorityTransitionError):
        transition("candidate", act)


def test_authority_transition_table_is_exposed() -> None:
    """The transition table is a module-level constant for callers to inspect."""

    assert isinstance(AuthorityTransition, dict)
    assert "assert" in AuthorityTransition
    assert "acceptance" in AuthorityTransition
    assert "answered" in AuthorityTransition


def test_speech_act_vocabulary_constants() -> None:
    """The kind/role/scope vocabularies are exported."""

    assert "assert" in SPEECH_ACT_KINDS
    assert "claim" in SPEECH_ACT_KINDS
    assert "answered" in SPEECH_ACT_KINDS
    assert "human" in SPEAKER_ROLES
    assert "agent" in SPEAKER_ROLES
    assert "operator" in SPEAKER_ROLES
