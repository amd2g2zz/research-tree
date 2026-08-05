"""Evaluate the redacted Claude Code + GLM5.2 behavior fixture.

The harness consumes a sanitized phase trace.  It intentionally reports
observations and control failures only; causal model attribution is delegated
to :func:`research_tree.evaluation_fixtures.assess_attribution`.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def _check(name: str, passed: bool, reason: str) -> dict[str, Any]:
    return {"name": name, "status": "pass" if passed else "fail", "reason": reason}


def evaluate_trace(trace: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    records = [dict(item) for item in trace]
    checks: list[dict[str, Any]] = []
    first_phase = records[0].get("phase") if records else None
    checks.append(_check("activation_before_reference", first_phase == "activation", "the trace must prove activation before any reference or research event"))
    prompt_ok = all(int(item.get("prompt_count", 0)) <= 1 for item in records if item.get("phase") == "alignment_turn")
    checks.append(_check("one_open_prompt", prompt_ok, "each alignment turn may expose at most one prompt"))
    corrections = [item for item in records if item.get("phase") == "correction"]
    correction_ok = all(bool(item.get("invalidated")) for item in corrections)
    replan_after = any(item.get("phase") == "replan" for item in records)
    checks.append(_check("correction_invalidation", correction_ok and (not corrections or replan_after), "material corrections must invalidate dependent state before replanning"))
    identities = [item.get("task_identity") for item in records if item.get("task_identity")]
    identity_ok = len(set(identities)) <= 1 or bool(corrections and identities[-1] != identities[0])
    checks.append(_check("task_identity_isolation", identity_ok, "diagnostic evidence cannot silently replace the research target"))
    attempts = [item for item in records if item.get("phase") == "research_attempt"]
    checks.append(_check("recursive_continuation", len({item.get("attempt_id") for item in attempts}) >= 2, "one worker round is not recursive closure"))
    delivery = next((item for item in reversed(records) if item.get("phase") == "delivery"), {})
    depth_ok = int(delivery.get("technical_depth", 0)) >= 5 and int(delivery.get("human_depth", 0)) >= 5 and int(delivery.get("claim_refs", 0)) > 0
    checks.append(_check("dual_delivery_depth", depth_ok, "both professional deliverables need semantic depth and claim provenance"))
    failed = [item["name"] for item in checks if item["status"] == "fail"]
    return {"schema": 1, "passed": not failed, "earliest_failure": failed[0] if failed else None, "checks": checks, "trace_length": len(records)}
