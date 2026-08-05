from research_tree import select_alignment_action


def test_alignment_strategy_keeps_internal_gaps_and_one_open_prompt():
    action, state = select_alignment_action(
        nodes=[
            {"id": "goal", "statement": "the goal", "status": "candidate", "impact": 5, "human_only": True, "ask_count": 0},
            {"id": "architecture", "statement": "the architecture", "status": "candidate", "impact": 4, "human_only": False, "ask_count": 0},
        ],
        readiness={"ready": False}, turn=1, graph_digest="a" * 64,
    )
    assert action["action"] == "ask_one"
    assert action["question"].count("?") == 1
    assert state.unresolved_gaps == ("goal", "architecture")
    assert state.cognitive_load == 2


def test_alignment_strategy_reconnoiters_agent_verifiable_gap():
    action, state = select_alignment_action(
        nodes=[{"id": "unknown", "statement": "unknown", "status": "candidate", "impact": 3, "human_only": False, "ask_count": 0}],
        readiness={"ready": False}, turn=2, graph_digest="b" * 64,
    )
    assert action["action"] == "reconnaissance"
    assert action["question"] is None
    assert state.pending_action_id is None
