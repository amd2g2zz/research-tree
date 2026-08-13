from __future__ import annotations

from pathlib import Path

import pytest
def finding(
    finding_id: str,
    *,
    anchor: str,
    uncertainty: str | None = None,
    continuation: dict[str, object] | None = None,
    validation: object | None = None,
    node_id: str | None = None,
) -> dict[str, object]:
    return {
        "id": finding_id,
        "decision_slot_id": "slot-architecture",
        "research_node_id": node_id,
        "observations": [
            {
                "claim": "The architecture requires a replayable research state.",
                "anchor": {"kind": "source", "ref": anchor},
            }
        ],
        "option_effects": [{"option": "persistent-tree", "effect": "supports"}],
        "remaining_uncertainties": [] if uncertainty is None else [uncertainty],
        "research_continuations": [] if continuation is None else [continuation],
        "validation_result": validation,
    }


def slots(*, priority: str = "P0") -> dict[str, dict[str, object]]:
    return {
        "slot-architecture": {
            "status": "open",
            "priority": priority,
            "uncertainty": "high",
            "question": "How should recursive research state be maintained?",
            "validation": {"oracle": "restart and replay preserves the active frontier"},
        }
    }


def worker_validation(status: object = "passed") -> dict[str, object]:
    return {
        "status": status,
        "oracle": "restart and replay preserves the active frontier",
        "evidence_ref": f"runs/restart-replay-{status}.json",
    }


def active_validation_nodes(state: dict[str, object]) -> list[dict[str, object]]:
    nodes = state["nodes"]
    assert isinstance(nodes, dict)
    return [
        node
        for node in nodes.values()
        if isinstance(node, dict)
        and node["status"] in {"frontier", "running"}
        and node["action_kind"] == "validation"
    ]


def worker_verifier_question(epoch: int = 1) -> str:
    return (
        "Produce verifier-needed proof for the worker-reported validation pass "
        f"(continuation epoch {epoch})."
    )


def test_existing_findings_seed_growth_without_claiming_initial_gain() -> None:
    from research_tree import initialize_research_state

    baseline = finding(
        "finding-baseline",
        anchor="https://example.test/primary",
        uncertainty="Crash recovery has not been tested.",
    )
    state = initialize_research_state(
        round_id="round-recursive",
        tree_id="research-tree",
        decision_slots=slots(),
        baseline_findings=(baseline,),
    )

    assert state["transition_index"] == 0
    assert state["delta_history"] == []
    assert state["consumed_finding_ids"] == ["finding-baseline"]
    assert state["nodes"]["root:slot-architecture"]["realized_delta"] == 0.0
    assert state["nodes"]["root:slot-architecture"]["status"] == "frontier"
    children = [node for node in state["nodes"].values() if node["parent_id"]]
    assert [node["question"] for node in children] == [
        "Crash recovery has not been tested."
    ]


def test_priority_band_prevents_p1_residual_from_displacing_p0() -> None:
    from research_tree import initialize_research_state, select_research_actions

    decision_slots = {
        "slot-p0": {
            "status": "open", "priority": "P0", "uncertainty": "medium",
            "question": "Validate the critical architecture.",
            "validation": {"oracle": "The critical architecture passes its experiment."},
        },
        "slot-p1": {
            "status": "open", "priority": "P1", "uncertainty": "high",
            "question": "Characterize a secondary unknown.",
            "validation": {"oracle": "The secondary unknown is bounded."},
        },
    }
    state = initialize_research_state(
        round_id="round-priority",
        tree_id="research-tree",
        decision_slots=decision_slots,
    )
    actions = select_research_actions(state, max_parallelism=2)
    assert [action["decision_slot_id"] for action in actions] == ["slot-p0", "slot-p1"]


def test_finding_pack_grows_successor_and_duplicate_evidence_has_zero_delta() -> None:
    from research_tree import apply_research_results, initialize_research_state

    state = initialize_research_state(
        round_id="round-recursive",
        tree_id="research-tree",
        decision_slots=slots(),
    )
    first = finding(
        "finding-first",
        anchor="https://example.test/primary",
        node_id="root:slot-architecture",
        continuation={
            "kind": "validation",
            "question": "Does replay preserve the exact frontier after a crash?",
            "trigger": "Persistence is proposed but not executed.",
            "evidence_needed": "A restart-and-replay experiment.",
            "oracle": "The recovered frontier equals the checkpoint frontier.",
            "estimated_cost": 1,
        },
    )
    after_first = apply_research_results(state, (first,))

    assert after_first["transition_index"] == 1
    assert after_first["delta_history"][0]["realized_delta"] > 0
    next_nodes = [
        after_first["nodes"][node_id]
        for node_id in after_first["frontier_node_ids"]
    ]
    assert [node["action_kind"] for node in next_nodes] == ["validation"]

    duplicate = finding(
        "finding-duplicate",
        anchor="https://example.test/primary",
        node_id=next_nodes[0]["id"],
    )
    after_duplicate = apply_research_results(after_first, (duplicate,))

    assert after_duplicate["delta_history"][-1]["realized_delta"] == 0.0
    assert after_duplicate["delta_history"][-1]["duplicate_only"] is True
    assert after_duplicate["penalty_history"][-1]["kind"] == "no_state_change"
    assert after_duplicate["status"] == "searching"
    assert any(
        "Triangulate" in after_duplicate["nodes"][node_id]["question"]
        for node_id in after_duplicate["frontier_node_ids"]
    )


def test_worker_reported_pass_cannot_close_validation_or_delivery() -> None:
    from research_tree import (
        apply_research_results,
        finalize_research_delivery,
        initialize_research_state,
    )

    state = initialize_research_state(
        round_id="round-recursive",
        tree_id="research-tree",
        decision_slots=slots(),
    )
    first = apply_research_results(
        state,
        (
            finding(
                "finding-one",
                anchor="source:primary",
                node_id="root:slot-architecture",
            ),
        ),
    )
    assert first["status"] == "searching"
    assert any(
        "Triangulate" in first["nodes"][node_id]["question"]
        for node_id in first["frontier_node_ids"]
    )
    triangulation_node_id = first["frontier_node_ids"][0]

    second = apply_research_results(
        first,
        (
            finding(
                "finding-two",
                anchor="experiment:restart-replay",
                node_id=triangulation_node_id,
                validation={
                    "status": "passed",
                    "oracle": "restart and replay preserves the active frontier",
                    "evidence_ref": "runs/restart-replay/result.json",
                },
            ),
        ),
    )
    slot = second["decision_slots"]["slot-architecture"]
    assert second["status"] == "searching"
    assert slot["validation_passed"] is False
    assert slot["validation_status"] == "reported_passed_untrusted"
    verifier_nodes = [
        second["nodes"][node_id]
        for node_id in second["frontier_node_ids"]
        if second["nodes"][node_id]["action_kind"] == "validation"
    ]
    assert len(verifier_nodes) == 1
    assert verifier_nodes[0]["mandatory"] is True
    assert "verifier-needed" in verifier_nodes[0]["question"]
    with pytest.raises(ValueError, match="decision-slot closure"):
        finalize_research_delivery(
            second,
            technical_report=Path("technical.md"),
            human_report=Path("human.md"),
        )


def test_worker_pass_with_unrelated_frontier_still_emits_verifier_needed_node() -> None:
    from research_tree import apply_research_results, initialize_research_state

    state = initialize_research_state(
        round_id="round-pass-with-frontier",
        tree_id="research-tree",
        decision_slots=slots(),
    )
    result = apply_research_results(
        state,
        (
            finding(
                "finding-pass-with-frontier",
                anchor="source:primary",
                node_id="root:slot-architecture",
                continuation={
                    "kind": "deep_dive",
                    "question": "Trace the implementation boundary independently.",
                    "trigger": "The worker exposed an implementation gap.",
                    "evidence_needed": "A source-bound implementation trace.",
                    "oracle": "The implementation boundary is resolved.",
                },
                validation=worker_validation(),
            ),
        ),
    )

    verifier_nodes = active_validation_nodes(result)
    assert len(verifier_nodes) == 1
    assert verifier_nodes[0]["mandatory"] is True
    assert "verifier-needed" in verifier_nodes[0]["question"]
    assert any(
        node["question"] == "Trace the implementation boundary independently."
        for node in result["nodes"].values()
        if isinstance(node, dict) and node["status"] == "frontier"
    )


def test_repeated_fresh_worker_passes_keep_one_active_verifier_node() -> None:
    from research_tree import apply_research_results, initialize_research_state

    state = initialize_research_state(
        round_id="round-repeated-worker-pass",
        tree_id="research-tree",
        decision_slots=slots(),
    )
    first = apply_research_results(
        state,
        (
            finding(
                "finding-pass-one",
                anchor="source:primary",
                node_id="root:slot-architecture",
                continuation={
                    "kind": "deep_dive",
                    "question": "Inspect the first report independently.",
                    "trigger": "The first report needs a separate trace.",
                    "evidence_needed": "A source-bound implementation trace.",
                    "oracle": "The first report is independently bounded.",
                },
                validation=worker_validation(),
            ),
        ),
    )
    first_verifier = active_validation_nodes(first)[0]
    unrelated_node = [
        node
        for node in first["nodes"].values()
        if isinstance(node, dict)
        and node["status"] == "frontier"
        and node["action_kind"] == "deep_dive"
    ][0]

    second = apply_research_results(
        first,
        (
            finding(
                "finding-pass-two",
                anchor="experiment:restart-replay-two",
                node_id=unrelated_node["id"],
                validation=worker_validation(),
            ),
        ),
    )

    verifier_nodes = active_validation_nodes(second)
    assert len(verifier_nodes) == 1
    assert verifier_nodes[0]["id"] == first_verifier["id"]
    assert second["decision_slots"]["slot-architecture"]["validation_attempts"] == 2


def test_completed_verifier_node_is_replaced_for_later_untrusted_pass() -> None:
    from research_tree import apply_research_results, initialize_research_state

    state = initialize_research_state(
        round_id="round-pass-recovery",
        tree_id="research-tree",
        decision_slots=slots(),
    )
    first = apply_research_results(
        state,
        (
            finding(
                "finding-recovery-one",
                anchor="source:primary",
                node_id="root:slot-architecture",
                validation=worker_validation(),
            ),
        ),
    )
    completed_verifier = active_validation_nodes(first)[0]
    completed_verifier["status"] = "completed"
    completed_verifier["terminal_reason"] = "worker submitted another untrusted pass"

    second = apply_research_results(
        first,
        (
            finding(
                "finding-recovery-two",
                anchor="experiment:restart-replay-two",
                node_id=completed_verifier["id"],
                validation=worker_validation(),
            ),
        ),
    )

    verifier_nodes = active_validation_nodes(second)
    assert len(verifier_nodes) == 1
    assert verifier_nodes[0]["id"] != completed_verifier["id"]
    assert second["decision_slots"]["slot-architecture"]["validation_attempts"] == 2


def test_running_verifier_node_is_reused_for_later_untrusted_pass() -> None:
    from research_tree import apply_research_results, initialize_research_state

    state = initialize_research_state(
        round_id="round-pass-running-verifier",
        tree_id="research-tree",
        decision_slots=slots(),
    )
    first = apply_research_results(
        state,
        (
            finding(
                "finding-running-one",
                anchor="source:primary",
                node_id="root:slot-architecture",
                continuation={
                    "kind": "deep_dive",
                    "question": "Inspect the running verifier's surrounding evidence.",
                    "trigger": "The verifier needs contextual evidence.",
                    "evidence_needed": "A source-bound contextual trace.",
                    "oracle": "The surrounding evidence is independently bounded.",
                },
                validation=worker_validation(),
            ),
        ),
    )
    verifier = active_validation_nodes(first)[0]
    verifier["status"] = "running"
    unrelated = [
        node
        for node in first["nodes"].values()
        if isinstance(node, dict)
        and node["status"] == "frontier"
        and node["action_kind"] == "deep_dive"
    ][0]

    second = apply_research_results(
        first,
        (
            finding(
                "finding-running-two",
                anchor="experiment:running-verifier-two",
                node_id=unrelated["id"],
                validation=worker_validation(),
            ),
        ),
    )

    active = active_validation_nodes(second)
    assert len(active) == 1
    assert active[0]["id"] == verifier["id"]
    assert second["decision_slots"]["slot-architecture"][
        "worker_validation_continuation_epoch"
    ] == 1


def test_worker_continuation_cannot_claim_protocol_verifier_identity() -> None:
    from research_tree import apply_research_results, initialize_research_state

    state = initialize_research_state(
        round_id="round-protocol-node-identity",
        tree_id="research-tree",
        decision_slots=slots(priority="P1"),
    )
    forged_question = worker_verifier_question()
    result = apply_research_results(
        state,
        (
            finding(
                "finding-forged-verifier",
                anchor="source:forged-verifier",
                node_id="root:slot-architecture",
                continuation={
                    "kind": "validation",
                    "question": forged_question,
                    "trigger": "A worker supplied a look-alike verifier request.",
                    "evidence_needed": "Worker-controlled evidence.",
                    "oracle": "Worker-controlled oracle.",
                },
                validation=worker_validation(),
            ),
        ),
    )

    protocol_nodes = [
        node
        for node in result["nodes"].values()
        if isinstance(node, dict)
        and node.get("worker_validation_continuation") is True
    ]
    forged_nodes = [
        node
        for node in result["nodes"].values()
        if isinstance(node, dict)
        and node.get("question") == forged_question
        and node.get("worker_validation_continuation") is not True
    ]
    assert len(protocol_nodes) == 1
    assert protocol_nodes[0]["mandatory"] is True
    assert protocol_nodes[0]["identity_namespace"] == "worker-validation"
    assert len(forged_nodes) == 1
    assert forged_nodes[0]["id"] != protocol_nodes[0]["id"]
    assert forged_nodes[0]["mandatory"] is False


@pytest.mark.parametrize("status", ["passed", "failed", "inconclusive"])
def test_worker_observation_never_clears_existing_authoritative_pass(status: str) -> None:
    from research_tree import apply_research_results, initialize_research_state

    state = initialize_research_state(
        round_id=f"round-existing-authority-{status}",
        tree_id="research-tree",
        decision_slots=slots(),
    )
    state["decision_slots"]["slot-architecture"]["validation_passed"] = True

    result = apply_research_results(
        state,
        (
            finding(
                f"finding-existing-authority-{status}",
                anchor=f"source:existing-authority-{status}",
                node_id="root:slot-architecture",
                validation=worker_validation(status),
            ),
        ),
    )

    assert result["decision_slots"]["slot-architecture"]["validation_passed"] is True
    assert active_validation_nodes(result) == []


@pytest.mark.parametrize(
    ("case", "validation"),
    [
        ("missing", None),
        ("string", "passed"),
        ("list", ["passed"]),
        ("empty-mapping", {}),
        ("none-status", worker_validation(None)),
        ("empty-status", worker_validation("")),
        ("unknown-status", worker_validation("unknown")),
    ],
)
def test_malformed_worker_validation_is_ignored(case: str, validation: object) -> None:
    from research_tree import apply_research_results, initialize_research_state

    state = initialize_research_state(
        round_id=f"round-malformed-worker-validation-{case}",
        tree_id="research-tree",
        decision_slots=slots(),
    )
    result = apply_research_results(
        state,
        (
            finding(
                f"finding-malformed-{case}",
                anchor=f"source:malformed-{case}",
                node_id="root:slot-architecture",
                validation=validation,
            ),
        ),
    )
    slot = result["decision_slots"]["slot-architecture"]
    assert slot["validation_passed"] is False
    assert slot["validation_status"] == "pending"
    assert slot["validation_attempts"] == 0
    assert slot["validation_failures"] == 0


def test_baseline_worker_pass_cannot_close_slot() -> None:
    from research_tree import initialize_research_state

    state = initialize_research_state(
        round_id="round-baseline-worker-pass",
        tree_id="research-tree",
        decision_slots=slots(),
        baseline_findings=(
            finding(
                "finding-baseline-worker-pass",
                anchor="source:baseline",
                validation=worker_validation(),
            ),
        ),
    )

    slot = state["decision_slots"]["slot-architecture"]
    assert slot["validation_passed"] is False
    assert slot["validation_status"] == "reported_passed_untrusted"
    assert len(active_validation_nodes(state)) == 1


def test_branch_complexity_suppresses_unconstrained_sibling_growth() -> None:
    from research_tree import apply_research_results, initialize_research_state

    def state_with_continuations(count: int) -> dict[str, object]:
        state = initialize_research_state(
            round_id=f"round-branches-{count}",
            tree_id="research-tree",
            decision_slots=slots(priority="P1"),
        )
        pack = finding(
            f"finding-branches-{count}",
            anchor=f"source:branches-{count}",
            node_id="root:slot-architecture",
        )
        pack["research_continuations"] = [
            {
                "kind": "deep_dive",
                "question": f"Resolve bounded branch {index}.",
                "trigger": "The landscape exposed a bounded gap.",
                "evidence_needed": "Independent evidence for the bounded gap.",
                "oracle": "The bounded gap is resolved.",
                "estimated_cost": 1,
            }
            for index in range(count)
        ]
        return apply_research_results(state, (pack,))

    narrow = state_with_continuations(1)
    broad = state_with_continuations(4)
    narrow_node = narrow["nodes"][narrow["frontier_node_ids"][0]]
    broad_nodes = [broad["nodes"][node_id] for node_id in broad["frontier_node_ids"]]

    assert narrow_node["branch_complexity"] == 1.0
    assert {node["branch_complexity"] for node in broad_nodes} == {3.0}
    assert max(node["selection_value"] for node in broad_nodes) < narrow_node["selection_value"]


def test_failed_validation_boosts_residual_and_grows_independent_retry() -> None:
    from research_tree import apply_research_results, initialize_research_state

    state = initialize_research_state(
        round_id="round-validation-boost",
        tree_id="research-tree",
        decision_slots=slots(),
    )
    first = apply_research_results(
        state,
        (
            finding(
                "finding-validation-failed-one",
                anchor="experiment:failed-one",
                node_id="root:slot-architecture",
                validation={
                    "status": "failed",
                    "oracle": "restart and replay preserves the active frontier",
                    "evidence_ref": "runs/failed-one.json",
                },
            ),
        ),
    )
    slot = first["decision_slots"]["slot-architecture"]
    assert slot["validation_failures"] == 1
    assert slot["residual_risk"] == 1.4

    second = apply_research_results(
        first,
        (
            finding(
                "finding-validation-failed-two",
                anchor="experiment:failed-two",
                node_id=first["frontier_node_ids"][0],
                validation={
                    "status": "failed",
                    "oracle": "restart and replay preserves the active frontier",
                    "evidence_ref": "runs/failed-two.json",
                },
            ),
        ),
    )
    retry = second["nodes"][second["frontier_node_ids"][0]]
    assert second["decision_slots"]["slot-architecture"]["residual_risk"] == 1.8
    assert retry["mandatory"] is True
    assert "independent method" in retry["question"]


def test_soft_frontier_limit_does_not_prune_mandatory_closure_work() -> None:
    from research_tree import RecursiveSearchConfig, initialize_research_state

    decision_slots = slots()
    decision_slots["slot-validation"] = {
        "status": "open",
        "priority": "P0",
        "uncertainty": "high",
        "question": "How will the leading conclusion be falsified?",
        "validation": {"oracle": "an independent method can reproduce the result"},
    }
    state = initialize_research_state(
        round_id="round-mandatory-capacity",
        tree_id="research-tree",
        decision_slots=decision_slots,
        config=RecursiveSearchConfig(max_frontier=1),
    )

    assert len(state["frontier_node_ids"]) == 2
    assert all(state["nodes"][node_id]["mandatory"] for node_id in state["frontier_node_ids"])


def test_tree_state_persists_and_replays_unconsumed_finding_after_restart(
    tmp_path: Path,
) -> None:
    from research_tree import (
        ResearchTreeStateError,
        ResearchTreeStateService,
        RunStore,
        apply_research_results,
        initialize_research_state,
    )

    root = tmp_path / "run-store"
    store = RunStore(root)
    round_record = store.create_round("round-recursive")
    baseline_payload = finding(
        "finding-baseline",
        anchor="source:baseline",
        uncertainty="The independent replay experiment is missing.",
    )
    baseline = store.append_artifact(
        round_record.id,
        "finding-baseline",
        "finding-pack",
        baseline_payload,
    )
    initial_state = initialize_research_state(
        round_id=round_record.id,
        tree_id="research-tree",
        decision_slots=slots(),
        baseline_findings=(baseline,),
    )
    service = ResearchTreeStateService(store)
    first = service.initialize(
        round_id=round_record.id,
        tree_id="research-tree",
        state=initial_state,
        baseline_findings=(baseline,),
    )

    pending_payload = finding(
        "finding-pending",
        anchor="experiment:restart-replay",
        validation={
            "status": "passed",
            "oracle": "restart and replay preserves the active frontier",
            "evidence_ref": "runs/restart-replay/result.json",
        },
    )
    pending = store.append_artifact(
        round_record.id,
        "finding-pending",
        "finding-pack",
        pending_payload,
    )

    rehydrated_service = ResearchTreeStateService(RunStore(root))
    checkpoint, unconsumed = rehydrated_service.recover_unconsumed(
        round_id=round_record.id,
        tree_id="research-tree",
    )
    assert checkpoint == first
    assert unconsumed == (pending,)

    next_state = apply_research_results(checkpoint.payload, unconsumed)
    second = rehydrated_service.transition(
        round_id=round_record.id,
        previous=checkpoint,
        state=next_state,
        consumed_findings=unconsumed,
    )
    latest, remaining = ResearchTreeStateService(RunStore(root)).recover_unconsumed(
        round_id=round_record.id,
        tree_id="research-tree",
    )
    assert latest == second
    assert latest.revision == 2
    assert remaining == ()
    assert {ref.artifact_id for ref in latest.parent_refs} == {
        "research-tree",
        "finding-pending",
    }

    with pytest.raises(ResearchTreeStateError, match="stale"):
        rehydrated_service.transition(
            round_id=round_record.id,
            previous=first,
            state=next_state,
            consumed_findings=unconsumed,
        )


def test_persisted_coordinator_exposes_successor_actions_across_processes(
    tmp_path: Path,
) -> None:
    from research_tree import RecursiveResearchCoordinator, RunStore

    root = tmp_path / "run-store"
    store = RunStore(root)
    round_record = store.create_round("round-coordinator")
    coordinator = RecursiveResearchCoordinator(store)
    coordinator.initialize(
        round_id=round_record.id,
        tree_id="research-tree",
        decision_slots=slots(),
    )
    first_action = coordinator.next_actions(
        round_id=round_record.id,
        tree_id="research-tree",
        max_parallelism=1,
    )[0]
    assert first_action["decision_oracle"] == (
        "restart and replay preserves the active frontier"
    )
    assert first_action["execution_context"] == {}
    persisted_finding = store.append_artifact(
        round_record.id,
        "finding-coordinator",
        "finding-pack",
        finding(
            "finding-coordinator",
            anchor="source:coordinator",
            node_id=first_action["id"],
            uncertainty="An independent execution check is still required.",
        ),
    )
    RecursiveResearchCoordinator(RunStore(root)).ingest(
        round_id=round_record.id,
        tree_id="research-tree",
        finding_packs=(persisted_finding,),
    )

    actions_after_restart = RecursiveResearchCoordinator(RunStore(root)).next_actions(
        round_id=round_record.id,
        tree_id="research-tree",
        max_parallelism=2,
    )
    assert actions_after_restart
    assert actions_after_restart[0]["parent_id"] == first_action["id"]
    assert actions_after_restart[0]["question"] == (
        "An independent execution check is still required."
    )
