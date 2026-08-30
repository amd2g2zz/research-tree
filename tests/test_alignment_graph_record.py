"""F-3 regression: AlignmentGraphStore.record + AlignmentProtocol.record_belief.

Issue #383: bare ``except Exception`` in ``AlignmentGraphStore.record``
silently demoted nodes to ``candidate`` when ``speech_acts.transition``
raised, which violated the canonical AuthorityTransition contract from
issue #316.  ``AlignmentProtocol.record_belief`` used ``except Exception
# noqa: BLE001`` and folded every error into a single
``AlignmentProtocolError``, also swallowing unexpected exceptions.

These tests assert that:

* ``AlignmentGraphStore.record`` re-raises ``AuthorityTransitionError``
  (no demotion, no silent candidate fallback), and emits a structured
  warning log so the rejection is observable.
* ``AlignmentProtocol.record_belief`` still wraps
  ``AuthorityTransitionError`` as ``AlignmentProtocolError`` while
  preserving ``__cause__`` (``raise ... from error`` chain).
* ``AlignmentProtocol.record_belief`` propagates unexpected
  ``ValueError`` instances verbatim — they are not folded into
  ``AlignmentProtocolError`` anymore.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from research_tree.alignment_graph import AlignmentGraphStore
from research_tree.alignment_protocol import AlignmentProtocol, AlignmentProtocolError
from research_tree.run_ledger import RunLedger
from research_tree.speech_acts import AuthorityTransitionError, SpeechAct


def _seed_store(tmp_path: Path) -> AlignmentGraphStore:
    store = AlignmentGraphStore(tmp_path / "alignment.db")
    store.initialize("run-383")
    store.merge(
        {
            "nodes": [
                {
                    "id": "node-1",
                    "type": "research_question",
                    "statement": "Question under alignment pressure.",
                    "status": "candidate",
                    "confidence": "low",
                    "source": "agent",
                    "oracle": "An executable validation.",
                }
            ]
        }
    )
    return store


def _seed_protocol(tmp_path: Path) -> AlignmentProtocol:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-383")
    return AlignmentProtocol(ledger, "run-383")


def test_record_answered_with_invalid_speech_act_raises_authority_transition_error(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``AlignmentGraphStore.record`` re-raises ``AuthorityTransitionError``.

    Previously a bare ``except Exception: status = "candidate"`` swallowed
    every transition failure and silently demoted the node.  The narrow
    contract re-raises so the caller learns the transition was rejected.
    """

    store = _seed_store(tmp_path)
    caplog.set_level(logging.WARNING, logger="research_tree.alignment_graph")

    with patch("research_tree.speech_acts.transition") as fake_transition:
        fake_transition.side_effect = AuthorityTransitionError(
            "speech-act 'answered' cannot transition from 'candidate'"
        )

        with pytest.raises(AuthorityTransitionError, match="cannot transition"):
            store.record("node-1", "answered", "fingerprint-383")

    assert any("alignment_graph_record_speech_transition_rejected" in record.message for record in caplog.records), (
        "expected structured warning to be emitted before re-raising"
    )


def test_record_belief_propagates_authority_transition_error_chain(
    tmp_path: Path,
) -> None:
    """``record_belief`` wraps ``AuthorityTransitionError`` with ``__cause__`` set.

    The narrow contract still surfaces speech-act rejections as
    ``AlignmentProtocolError`` (canonical envelope) while preserving the
    underlying error in ``__cause__`` via ``raise ... from error``.
    """

    service = _seed_protocol(tmp_path)
    bad_act = SpeechAct(
        kind="acceptance",
        speaker_role="human",
        speaker_id="requester",
        addressee="agent",
        authority_scope="research_owner",  # not decision_owner → AuthorityTransitionError
        timestamp="2026-08-31T00:00:00+00:00",
        claim_id="claim-1",
    )

    with pytest.raises(AlignmentProtocolError) as excinfo:
        service.record_belief(
            belief_id="belief-383-1",
            actor="human",
            field="authority",
            statement="Approval granted.",
            confidence="high",
            human_only=True,
            speech_act=bad_act,
        )

    assert isinstance(excinfo.value.__cause__, AuthorityTransitionError)
    assert "decision_owner" in str(excinfo.value.__cause__)


def test_record_belief_propagates_value_error_as_value_error(
    tmp_path: Path,
) -> None:
    """Unexpected ``ValueError`` from ``transition`` propagates verbatim.

    ``AuthorityTransitionError`` is a ``ValueError`` subclass, so the
    narrowed ``except AuthorityTransitionError`` is necessary to avoid
    swallowing plain ``ValueError`` instances from the same call site.
    """

    service = _seed_protocol(tmp_path)
    act = SpeechAct(
        kind="assert",
        speaker_role="agent",
        speaker_id="agent-1",
        addressee="human",
        authority_scope="research_owner",
        timestamp="2026-08-31T00:00:00+00:00",
        basis_refs=("evidence-1",),
    )

    with patch("research_tree.speech_acts.transition") as fake_transition:
        fake_transition.side_effect = ValueError("unexpected validation failure")

        with pytest.raises(ValueError, match="unexpected validation failure"):
            service.record_belief(
                belief_id="belief-383-2",
                actor="agent",
                field="scope",
                statement="The bounded scope is reachable.",
                confidence="medium",
                speech_act=act,
            )
