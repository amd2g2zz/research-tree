from __future__ import annotations

from copy import deepcopy


def _deficit(kind: str = "validation_pending") -> dict[str, object]:
    return {
        "deficit_id": "deficit-slot-1-validation",
        "slot_id": "slot-1",
        "kind": kind,
        "trigger": "The required oracle has not passed.",
        "action": "validation",
        "source_refs": ["decision:decision-1@1"],
        "required_evidence_classes": ["repository", "oracle"],
        "closure_oracle": "A reproducible OracleRun passes for the selected decision.",
    }


def test_policy_proposes_typed_actions_from_canonical_deficits() -> None:
    from research_tree.policy import AdaptiveResearchPolicy

    actions = AdaptiveResearchPolicy().propose_from_deficits(
        run_id="run-1",
        deficits=[_deficit()],
        slot_priorities={"slot-1": "P0"},
        policy_seed=7,
    )

    assert len(actions) == 1
    action = actions[0]
    assert set(
        (
            "action_id",
            "run_id",
            "slot_id",
            "action_kind",
            "objective",
            "trigger_refs",
            "missing_evidence",
            "method_boundary",
            "closure_oracle",
            "mandatory",
            "policy_version",
            "policy_seed",
            "score_components",
        )
    ) <= set(action)
    assert action["run_id"] == "run-1"
    assert action["mandatory"] is True
    assert action["trigger_refs"] == ["decision:decision-1@1"]
    assert action["missing_evidence"] == ["repository", "oracle"]
    assert action["closure_oracle"].startswith("A reproducible")
    assert set(action["score_components"]) == {
        "evidence_class",
        "independence",
        "contradiction",
        "oracle",
        "implementation_uncertainty",
        "decision_closure",
    }


def test_policy_gain_ratio_and_failure_boost_are_reproducible() -> None:
    from research_tree.policy import AdaptiveResearchPolicy

    policy = AdaptiveResearchPolicy(gain_ratio_epsilon=0.1)
    candidates = [
        {
            "slot_id": "slot-2",
            "priority": "P1",
            "action_kind": "deep_dive",
            "question": "same question",
            "selection_value": 0.5,
            "expected_gain": 0.2,
            "estimated_cost": 1.0,
        },
        {
            "slot_id": "slot-2",
            "priority": "P1",
            "action_kind": "deep_dive",
            "question": "same question",
            "selection_value": 0.4,
            "expected_gain": 0.2,
            "estimated_cost": 1.0,
        },
        {
            "slot_id": "slot-3",
            "priority": "P1",
            "action_kind": "validation",
            "question": "failed oracle",
            "selection_value": 0.1,
            "expected_gain": 0.1,
            "estimated_cost": 1.0,
            "oracle_failure": True,
        },
    ]
    first = policy.prune(candidates)
    second = policy.prune(deepcopy(candidates))

    assert first == second
    assert first[1]["status"] == "pruned"
    assert first[1]["prune_reason"] in {"duplicate_optional_action", "dominated_optional_action"}
    assert first[2]["oracle_failure_boost"] > 0
    assert first[2]["recovery_required"] is True


def test_policy_never_score_prunes_p0_or_mandatory_counterevidence() -> None:
    from research_tree.policy import AdaptiveResearchPolicy

    action = {
        "action_id": "action-p0-counter",
        "slot_id": "p0",
        "priority": "P0",
        "mandatory": True,
        "action_kind": "adversarial",
        "question": "Find counterevidence",
        "selection_value": 0.0,
        "expected_gain": 0.0,
        "estimated_cost": 100.0,
    }
    result = AdaptiveResearchPolicy().prune([action], protected_slots=set())

    assert result[0]["status"] != "pruned"
    assert result[0]["mandatory"] is True
    assert result[0]["exemption_reason"]


def test_realized_delta_exposes_six_closure_components() -> None:
    from research_tree.policy import AdaptiveResearchPolicy

    result = AdaptiveResearchPolicy().apply(
        {"slot-1": {"priority": "P0", "question": "Validate"}},
        [
            {
                "id": "finding-components",
                "decision_slot_id": "slot-1",
                "observations": [
                    {
                        "claim": "Observed",
                        "anchor": {"kind": "repository", "ref": "src/a.py"},
                        "provenance_group": "repo-a",
                    }
                ],
                "option_effects": [{"option": "a", "effect": "supports"}],
                "remaining_uncertainties": ["Need an oracle"],
                "oracle_run_refs": [],
            }
        ],
    )

    assert set(result["realized_delta"]["closure_components"]) == {
        "evidence_class",
        "independence",
        "contradiction",
        "oracle",
        "implementation_uncertainty",
        "decision_closure",
    }


def test_policy_grows_correction_and_failed_oracle_method_switches() -> None:
    from research_tree.policy import AdaptiveResearchPolicy

    result = AdaptiveResearchPolicy().apply(
        {"slot-1": {"priority": "P1", "question": "Choose method"}},
        [{
            "id": "finding-correction",
            "decision_slot_id": "slot-1",
            "observations": [],
            "option_effects": [],
            "correction": {
                "kind": "adversarial",
                "question": "Recheck the corrected premise",
                "evidence_needed": "Independent counterevidence",
                "oracle": "Counterevidence is resolved",
            },
            "oracle_status": "failed",
        }],
    )

    growth = result["growth"]
    assert any(item["action_kind"] == "adversarial" for item in growth)
    assert any(item["action_kind"] == "method_switch" for item in growth)


def test_recursive_projection_rejects_unbounded_worker_topic() -> None:
    from research_tree import apply_research_results, initialize_research_state

    state = initialize_research_state(
        round_id="round-unbounded",
        tree_id="research-tree",
        decision_slots={"slot-1": {"priority": "P1", "question": "Bounded"}},
    )
    finding = {
        "id": "finding-unbounded",
        "decision_slot_id": "slot-1",
        "research_node_id": "root:slot-1",
        "observations": [{"claim": "x", "anchor": {"kind": "source", "ref": "a"}}],
        "option_effects": [],
        "research_continuations": [{"question": "Look at anything else"}],
        "remaining_uncertainties": [],
    }
    next_state = apply_research_results(state, [finding])
    assert not any(node["question"] == "Look at anything else" for node in next_state["nodes"].values())
