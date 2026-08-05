from __future__ import annotations


def _node(
    node_id: str,
    *,
    node_type: str = "unknown",
    statement: str = "An unresolved alignment point.",
    human_only: bool = False,
    status: str = "candidate",
    impact: int = 4,
    source: str = "agent",
    attributes: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "id": node_id,
        "type": node_type,
        "statement": statement,
        "human_only": human_only,
        "status": status,
        "impact": impact,
        "confidence": "medium",
        "source": source,
        "oracle": "The ambiguity is resolved with recorded evidence or requester authority.",
        "attributes": attributes or {},
    }


def test_repeated_plan_reuses_pending_alignment_attempt(tmp_path) -> None:
    from research_tree.alignment_graph import AlignmentGraphStore

    store = AlignmentGraphStore(tmp_path / "alignment.db")
    store.initialize("align-attempt")
    first = store.plan({"nodes": [_node("authority", human_only=True)], "edges": []})
    second = store.plan()

    assert first["action"] == "ask_one"
    assert first["attempt_id"] == second["attempt_id"]
    assert second["waiting"] is True
    status = store.status()
    assert status["controller"]["pending_action_id"] == first["attempt_id"]
    assert [item["status"] for item in status["attempts"]] == ["pending"]


def test_alignment_strategy_exposes_candidate_score_factors() -> None:
    from research_tree import select_alignment_action

    action, state = select_alignment_action(
        nodes=[
            _node("technical", impact=5),
            _node("preference", human_only=True, impact=3),
        ],
        readiness={"ready": False, "reasons": ["missing supported outcome"]},
        turn=1,
        graph_digest="a" * 64,
    )

    assert action["action"] == "reconnaissance"
    assert set(action["candidate_scores"][0]["factors"]) == {
        "impact",
        "human_exclusivity",
        "researchability",
        "ambiguity_reduction",
        "decision_consequence",
        "cognitive_load_penalty",
        "repetition_penalty",
    }
    assert state.pending_action_id is None


def test_supported_conflict_selects_constructive_disagreement() -> None:
    from research_tree import select_alignment_action

    action, _ = select_alignment_action(
        nodes=[
            _node(
                "premise-conflict",
                node_type="disagreement",
                statement="Repository evidence conflicts with the stated premise.",
                status="disputed",
                impact=5,
                attributes={
                    "belief_basis": ["evidence:repo@1", "human:message@2"],
                    "disagreement_disposition": "supported",
                },
            )
        ],
        readiness={"ready": False, "reasons": ["high-impact disagreement"]},
        turn=2,
        graph_digest="b" * 64,
    )

    assert action["action"] == "constructive_disagreement"
    assert action["question"].count("?") == 1
    assert action["belief_basis"] == ["evidence:repo@1", "human:message@2"]


def test_disagreement_outcome_preserves_basis_and_attempt_lineage(tmp_path) -> None:
    from research_tree.alignment_graph import AlignmentGraphStore

    store = AlignmentGraphStore(tmp_path / "alignment.db")
    store.initialize("align-disagreement")
    first = store.plan({
        "nodes": [_node(
            "premise-conflict",
            node_type="disagreement",
            status="disputed",
            impact=5,
            attributes={
                "belief_basis": ["evidence:repo@1", "human:message@2"],
                "disagreement_disposition": "supported",
            },
        )],
        "edges": [],
    })
    result = store.record_disagreement(
        "premise-conflict",
        "not_enough_information",
        belief_basis=["evidence:repo@1", "human:message@2"],
        expected_attempt_id=first["attempt_id"],
    )

    assert result["attempt_id"] == first["attempt_id"]
    status = store.status()
    node = status["graph"]["nodes"][0]
    assert node["attributes"]["belief_basis"] == ["evidence:repo@1", "human:message@2"]
    assert status["attempts"][0]["status"] == "completed"
    assert status["attempts"][0]["outcome"]["disposition"] == "not_enough_information"


def test_readiness_reports_field_level_pass_unknown_and_fail() -> None:
    from research_tree.alignment_graph import _alignment_readiness

    result = _alignment_readiness(
        [_node("outcome", node_type="outcome", status="candidate")],
        [],
    )
    assert result["checks"]["outcome"] == "unknown"
    assert result["checks"]["intended_use"] == "fail"
    assert result["ready"] is False


def test_impossible_goal_blocks_handoff_with_one_adjustment_prompt() -> None:
    from research_tree import select_alignment_action

    action, _ = select_alignment_action(
        nodes=[
            _node(
                "feasibility",
                node_type="feasibility",
                statement="The requested capability cannot fit the confirmed resources.",
                status="rejected",
                impact=5,
                attributes={"feasibility_status": "infeasible"},
            )
        ],
        readiness={"ready": False, "reasons": ["infeasible"]},
        turn=1,
        graph_digest="c" * 64,
    )
    assert action["action"] == "authority_blocked"
    assert action["question"].count("?") == 1


def test_unknown_attempt_recovery_releases_pending_identity(tmp_path) -> None:
    from research_tree.alignment_graph import AlignmentGraphStore

    store = AlignmentGraphStore(tmp_path / "alignment.db")
    store.initialize("align-recovery")
    decision = store.plan({"nodes": [_node("unknown")], "edges": []})
    recovered = store.mark_attempt_unknown(decision["attempt_id"], reason="host outcome was lost")
    assert recovered["status"] == "unknown"
    assert store.status()["controller"]["pending_action_id"] is None
    successor = store.plan()
    assert successor["attempt_id"] != decision["attempt_id"]
