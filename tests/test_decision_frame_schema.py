from __future__ import annotations

import json
from pathlib import Path

from research_tree.decision_frame import DecisionFrame


def test_decision_frame_fixture_is_valid_and_versioned() -> None:
    root = Path(__file__).parents[1]
    fixture = json.loads(
        (
            root
            / "openspec"
            / "changes"
            / "unify-research-runtime-alpha2"
            / "schemas"
            / "examples"
            / "decision-frame-v1.json"
        ).read_text(encoding="utf-8")
    )
    frame = DecisionFrame.from_dict(fixture)
    assert frame.schema_version == 1
    assert frame.status == "clarification_required"
