from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


def finding(
    finding_id: str,
    *,
    anchor: str,
    uncertainty: str | None = None,
    continuation: dict[str, object] | None = None,
    validation: dict[str, str] | None = None,
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
        "oracle_run_refs": [] if validation is None else [
            {
                "oracle_run_id": validation["evidence_ref"],
                "oracle_spec_id": validation["oracle"],
                "oracle_spec_version": 1,
                "attempt_id": f"attempt-{finding_id}",
            }
        ],
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


def test_stop_requires_independent_evidence_and_validation(tmp_path: Path) -> None:
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

    second_run = {
        "oracle_run_id": "runs/restart-replay/result.json",
        "oracle_spec_id": "restart and replay preserves the active frontier",
        "oracle_spec_version": 1,
        "attempt_id": "attempt-finding-two",
        "verdict": "passed",
        "reproducibility_status": "reproducible",
    }
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
        oracle_runs={second_run["oracle_run_id"]: second_run},
    )
    assert second["status"] == "delivery_pending"
    assert second["stop_reason"] == (
        "decision slots closed; both research deliverables are still pending"
    )
    technical = tmp_path / "technical.md"
    technical.write_text("# Technical Package\n\n## Evidence\n\n## Validation\n", encoding="utf-8")
    technical.write_text(technical.read_text(encoding="utf-8") + ("x" * 1100), encoding="utf-8")
    human = tmp_path / "human.md"
    human.write_text("# Human Report\n\n## Findings\n\n" + ("x" * 600), encoding="utf-8")
    delivered = finalize_research_delivery(
        second,
        technical_report=technical,
        human_report=human,
    )
    assert delivered["status"] == "complete"
    assert delivered["deliverables"]["technical_research_package"]["status"] == "verified"


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
    first_run = {
        "oracle_run_id": "runs/failed-one.json",
        "oracle_spec_id": "restart and replay preserves the active frontier",
        "oracle_spec_version": 1,
        "attempt_id": "attempt-finding-validation-failed-one",
        "verdict": "failed",
        "reproducibility_status": "reproducible",
    }
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
        oracle_runs={first_run["oracle_run_id"]: first_run},
    )
    slot = first["decision_slots"]["slot-architecture"]
    assert slot["validation_failures"] == 1
    assert slot["residual_risk"] == 1.4

    second_run = {
        "oracle_run_id": "runs/failed-two.json",
        "oracle_spec_id": "restart and replay preserves the active frontier",
        "oracle_spec_version": 1,
        "attempt_id": "attempt-finding-validation-failed-two",
        "verdict": "failed",
        "reproducibility_status": "reproducible",
    }
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
        oracle_runs={second_run["oracle_run_id"]: second_run},
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

    replay_run = {
        "oracle_run_id": "runs/restart-replay/result.json",
        "oracle_spec_id": "restart and replay preserves the active frontier",
        "oracle_spec_version": 1,
        "attempt_id": "attempt-finding-pending",
        "verdict": "passed",
        "reproducibility_status": "reproducible",
    }
    next_state = apply_research_results(
        checkpoint.payload,
        unconsumed,
        oracle_runs={replay_run["oracle_run_id"]: replay_run},
    )
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
    assert actions_after_restart[0]["question"] == "An independent execution check is still required."


def test_cli_runs_persisted_recursive_growth_across_processes(tmp_path: Path) -> None:
    from research_tree import RunStore

    root = tmp_path / "run-store"
    slots_path = tmp_path / "decision-slots.json"
    slots_path.write_text(json.dumps(slots()), encoding="utf-8")

    def cli(*arguments: str) -> dict[str, object]:
        completed = subprocess.run(
            [sys.executable, "-m", "research_tree", *arguments],
            text=True,
            capture_output=True,
            check=False,
            env={
                **os.environ,
                "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
            },
        )
        assert completed.returncode == 0, completed.stderr
        return json.loads(completed.stdout)

    cli("create-round", "--store", str(root), "--round-id", "round-cli-tree")
    cli(
        "tree-init",
        "--store",
        str(root),
        "--round-id",
        "round-cli-tree",
        "--decision-slots",
        str(slots_path),
    )
    first = cli(
        "tree-next",
        "--store",
        str(root),
        "--round-id",
        "round-cli-tree",
        "--max-parallelism",
        "1",
    )
    first_action = first["actions"][0]
    store = RunStore(root)
    stored = store.append_artifact(
        "round-cli-tree",
        "finding-cli-one",
        "finding-pack",
        finding(
            "finding-cli-one",
            anchor="source:cli-primary",
            node_id=first_action["id"],
            uncertainty="The CLI recovery path still needs independent execution.",
        ),
    )
    ingest = cli(
        "tree-ingest",
        "--store",
        str(root),
        "--round-id",
        "round-cli-tree",
        "--finding",
        stored.id,
    )
    assert ingest["revision"] == 2

    successor = cli(
        "tree-next",
        "--store",
        str(root),
        "--round-id",
        "round-cli-tree",
        "--max-parallelism",
        "2",
    )
    assert successor["actions"]
    assert successor["actions"][0]["parent_id"] == first_action["id"]
    assert successor["actions"][0]["question"] == (
        "The CLI recovery path still needs independent execution."
    )
