from __future__ import annotations

import hashlib
import json
from pathlib import Path

from research_tree.domain import canonical_json_bytes


def test_three_hosts_share_strategy_projection_semantics() -> None:
    root = Path(__file__).parents[1]
    case = json.loads(
        (
            root / "openspec/changes/add-four-stage-strategy-handoff/evidence/strategy-handoff-black-box-v1.json"
        ).read_text(encoding="utf-8")
    )
    payload = case["projection"]
    digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    assert {host: digest for host in case["hosts"]} == {host: case["expected_digest"] for host in case["hosts"]}
    assert case["unavailable_hosts"] == []
