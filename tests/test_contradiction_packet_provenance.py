"""Tests for contradiction packet provenance rendering (issue #440, tasks.md 5.3).

Rendered packets shown to agents must keep claim provenance: each claim
carries an ``Origin:`` line drawn from the closed origin vocabulary.
"""

from __future__ import annotations

import pytest

from research_tree.contradictions import render_contradiction_packet


def _packet(claim_origin: object = "worker") -> dict[str, object]:
    claim: dict[str, object] = {
        "claim_id": "claim-1",
        "subject": "the baseline",
        "predicate": "compiles",
        "value": "true",
        "polarity": "positive",
    }
    if claim_origin is not None:
        claim["origin"] = claim_origin
    return {
        "contradiction_id": "contra-1",
        "status": "unresolved",
        "normalized_claims": [claim],
    }


def test_packet_renders_origin_line() -> None:
    rendered = render_contradiction_packet(_packet())
    assert "Origin: worker" in rendered


@pytest.mark.parametrize("origin", ("agent", "worker", "tool", "user", "repository", "generated"))
def test_packet_renders_every_origin_value(origin: str) -> None:
    rendered = render_contradiction_packet(_packet(origin))
    assert f"Origin: {origin}" in rendered


def test_packet_without_origin_renders_unknown_marker() -> None:
    rendered = render_contradiction_packet(_packet(None))
    assert "Origin: unknown" in rendered
