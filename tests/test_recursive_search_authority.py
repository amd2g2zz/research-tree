from pathlib import Path

from research_tree import evaluate_research_stop, finalize_research_delivery, initialize_research_state


def slots() -> dict[str, dict[str, object]]:
    return {
        "slot-authority": {
            "status": "open",
            "priority": "P0",
            "uncertainty": "high",
            "question": "Can a compatibility projection close this slot?",
            "validation": {"oracle": "The coordinator verifies the closure."},
        }
    }


def test_empty_frontier_is_not_authoritative_closure() -> None:
    state = initialize_research_state(
        round_id="round-authority-bypass", tree_id="research-tree", decision_slots=slots()
    )
    state["frontier_node_ids"] = []
    for node in state["nodes"].values():
        node["status"] = "deferred"
    state["decision_slots"]["slot-authority"].update(
        {
            "finding_ids": ["finding-one", "finding-two"],
            "anchor_fingerprints": ["anchor-one", "anchor-two"],
            "validation_passed": True,
        }
    )
    projection = evaluate_research_stop(state)
    assert projection["decision_slots"]["slot-authority"]["status"] != "closed"
    assert projection["status"] != "complete"
    assert projection["compatibility_projection"]["authority"] == "coordinator_only"
    assert "closure" in " ".join(projection["compatibility_projection"]["blocked_reasons"])


def test_report_shape_is_observation_only(tmp_path: Path) -> None:
    state = initialize_research_state(
        round_id="round-delivery-authority", tree_id="research-tree", decision_slots=slots()
    )
    state["decision_slots"]["slot-authority"]["status"] = "closed"
    technical, human = tmp_path / "technical.md", tmp_path / "human.md"
    technical.write_text("# Technical\n# Evidence\n# Risks\n\n" + "x" * 1100, encoding="utf-8")
    human.write_text("# Human\n# Reasoning\n\n" + "x" * 600, encoding="utf-8")
    projection = finalize_research_delivery(state, technical_report=technical, human_report=human)
    assert projection["status"] != "complete"
    assert projection["deliverables"]["technical_research_package"]["status"] != "verified"
    assert projection["compatibility_projection"]["authority"] == "coordinator_only"
