from __future__ import annotations

import hashlib
import json
from pathlib import Path

from research_tree.decision_frame import DecisionFrame
from research_tree.domain import canonical_json_bytes


ROOT = Path(__file__).parents[1]
CASE = ROOT / "openspec/changes/clarify-intent-before-strategy/evidence/intent-decision-frame-black-box-v1.json"


def test_evaluator_owned_intent_frame_metrics_are_cross_host_replayable() -> None:
    case = json.loads(CASE.read_text(encoding="utf-8"))
    frame_payload = json.loads((ROOT / case["frame_fixture"]).read_text(encoding="utf-8"))
    frame = DecisionFrame.from_dict(frame_payload)
    canonical = canonical_json_bytes(frame.to_dict())
    host_digests = {host: hashlib.sha256(canonical).hexdigest() for host in case["hosts"]}

    assert len(set(host_digests.values())) == 1
    assert frame.requester_wording == "What business model should this app use?"
    assert len(frame.hypotheses) >= 2
    assert frame.policy.action == "ask_user"
    assert frame.status != "ready_for_strategy"
    assert all(item.primary_decision_id == frame.primary_decision["id"] for item in frame.hypotheses)
    assert "stack" not in frame.primary_decision["statement"].lower()
    assert frame.selected_hypothesis_id is None
    assert all(case["metrics"].values())
