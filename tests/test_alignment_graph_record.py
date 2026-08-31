"""F-3 regression: AlignmentGraphStore.record speech-act authority contract.

Issue #383: bare ``except Exception`` in ``AlignmentGraphStore.record``
silently demoted nodes to ``candidate`` when ``speech_acts.transition``
raised, which violated the canonical AuthorityTransition contract from
issue #316.

This test asserts that ``AlignmentGraphStore.record`` re-raises
``AuthorityTransitionError`` (no demotion, no silent candidate fallback),
and emits a structured warning log so the rejection is observable.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from research_tree.alignment_graph import AlignmentGraphStore
from research_tree.speech_acts import AuthorityTransitionError


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
