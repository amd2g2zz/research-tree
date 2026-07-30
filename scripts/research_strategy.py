"""Deterministic frontier ranking for intent-constrained recursive descent."""

from __future__ import annotations

import re


def _tokens(value: str) -> set[str]:
    return {item for item in re.findall(r"[\w-]+", value.lower()) if len(item) > 2}


def _jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / len(left | right) if left or right else 0.0


def rank_frontier(state: dict, frame_id: str) -> list[dict]:
    """Rank deferred alternatives without inventing a new research direction.

    Semantic ratings come from the Extractor proposal; this scorer combines them
    with observable graph state so the Branch Selector can explain its choice.
    """
    frame = state["frames"][frame_id]
    all_clauses = state["intent_versions"][-1]["clauses"]
    clause_coverage = len(frame["intent_clause_ids"]) / max(1, len(all_clauses))
    other_topics = [_tokens(item["focus"] + " " + item["information_gap"])
                    for item in state["frames"].values() if item["id"] != frame_id]
    ranked = []
    for gap_id in frame["gap_ids"]:
        gap = state["gaps"][gap_id]
        frontier = state.get("frontier", {}).get(gap_id, {})
        if gap["status"] != "open" or frontier.get("status", "deferred") != "deferred":
            continue
        triggers = [state["cognitions"][item]["confidence"] for item in gap["trigger_cognition_ids"]]
        uncertainty = 1.0 - (sum(triggers) / len(triggers)) if triggers else 0.7
        topic = _tokens(gap["description"] + " " + gap["discriminator"])
        novelty = 1.0 - max((_jaccard(topic, other) for other in other_topics), default=0.0)
        gain = float(gap.get("expected_information_gain", 0.5))
        cost = float(gap.get("acquisition_cost", 0.5))
        temporal_pressure = 1.0 if frame.get("temporal_scope") else 0.3
        reactivation = min(0.08, 0.03 * int(frontier.get("reactivation_count", 0)))
        score = (0.32 * gain + 0.24 * uncertainty + 0.18 * novelty +
                 0.16 * clause_coverage + 0.10 * temporal_pressure - 0.12 * cost + reactivation)
        ranked.append({
            "gap_id": gap_id,
            "score": round(score, 6),
            "components": {"expected_information_gain": gain, "uncertainty": round(uncertainty, 6),
                           "novelty": round(novelty, 6), "constraint_coverage": round(clause_coverage, 6),
                           "temporal_pressure": temporal_pressure, "acquisition_cost": cost,
                           "reactivation": round(reactivation, 6)},
            "revisit_conditions": frontier.get("revisit_conditions", []),
        })
    return sorted(ranked, key=lambda item: (-item["score"], item["gap_id"]))
