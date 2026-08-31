"""Goal-wiring contracts: slot serves validation and projection lifecycle CLI wiring."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from research_tree.alignment_graph import (
    confirm as alignment_confirm,
)
from research_tree.alignment_graph import (
    database_path,
)
from research_tree.alignment_graph import (
    init as alignment_init,
)
from research_tree.alignment_graph import (
    plan as alignment_plan,
)
from research_tree.alignment_handoff import goal_decomposition, initialize_research_from_alignment
from research_tree.cli import main as cli_main
from research_tree.coordinator import (
    CoordinatorConflictError,
    IllegalTransitionError,
    ResearchRunCoordinator,
)
from research_tree.decision_frame import DecisionFrame, IntentHypothesis
from research_tree.decision_map import CanonicalBlueprintTargetCompiler, InvalidBlueprintTargetError
from research_tree.domain import ArtifactRef, ArtifactRevision, thaw_json
from research_tree.run_ledger import RunLedger
from research_tree.strategy_projection import StrategyProjection
from research_tree.work_items import (
    WORK_ITEM_KIND,
    CanonicalWorkItemCompiler,
    InvalidWorkItemError,
)

RUN_ID = "round-goal"


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _append(
    ledger: RunLedger,
    artifact_id: str,
    kind: str,
    payload: dict,
    parents: tuple[ArtifactRef, ...] = (),
) -> ArtifactRevision:
    return ledger.append_artifact(
        RUN_ID,
        artifact_id,
        kind,
        payload,
        parent_refs=parents,
        expected_revision=ledger.get_revision(RUN_ID),
    )


def slot(
    slot_id: str,
    *,
    priority: str = "P0",
    target_id: str = "decision-1",
    oracle_ids: tuple[str, ...] = ("oracle-1",),
) -> dict:
    """A Decision Slot payload in the exact decision_map whitelist shape plus `serves`."""

    return {
        "id": slot_id,
        "kind": "architecture",
        "question": f"Which boundary should {slot_id} use?",
        "intent_hypothesis_ids": ["intent-agent"],
        "priority": priority,
        "impact": "high",
        "uncertainty": "high",
        "irreversibility": "high",
        "constraints": [
            {
                "kind": "input",
                "ref": "input-brief",
                "statement": "The first implementation must remain safe.",
            }
        ],
        "alternatives": ["isolated-worker", "in-process"],
        "repository_touchpoints": [{"path": "src/agent.py", "symbol": "run"}],
        "greenfield_assumptions": [],
        "depends_on": [],
        "evidence_standard": "repository inspection plus a bounded spike",
        "validation": {"kind": "spike", "oracle": "one fixture crosses the selected boundary"},
        "closure_rule": "select, conditionally select, defer with fallback, or block",
        "status": "open",
        "bounded_research_need": "compare both alternatives against the current boundary",
        "fallback": "retain the current boundary until this decision closes",
        "serves": {"target_id": target_id, "oracle_ids": list(oracle_ids)},
    }


def confirm_projection(ledger: RunLedger, run_id: str, projection: StrategyProjection) -> ArtifactRevision:
    """Persist a projection and the authoritative handoff_confirmed lifecycle event for it."""

    stored = ledger.append_strategy_projection(
        run_id,
        projection.projection_id,
        projection.to_dict(),
        parent_refs=(
            projection.decision_frame_ref,
            projection.alignment_handoff_ref,
            projection.target_ref,
        ),
        expected_revision=ledger.get_revision(run_id),
    )
    ledger.append_artifact(
        run_id,
        "event-goal-confirm",
        "lifecycle-event",
        {
            "event_id": "event-goal-confirm",
            "idempotency_key": "confirm-goal",
            "event": "handoff_confirmed",
            "from": "handoff_pending",
            "to": "autonomous_research",
            "actor": "human",
            "payload": {
                "projection_ref": ArtifactRef(run_id, stored.id, stored.revision).to_dict(),
                "display_digest": projection.display_digest,
                "confirmation": f"I accept {projection.display_digest} and authorize research.",
            },
        },
        parent_refs=(),
        expected_revision=ledger.get_revision(run_id),
    )
    return stored


def projection(
    run_id: str,
    *,
    frame_ref: ArtifactRef,
    handoff_ref: ArtifactRef,
    target_ref: ArtifactRef,
    decision_targets: tuple = ("decision-1",),
    success_oracles: tuple = ({"id": "oracle-1", "evidence_standard_ids": ("standard-1",)},),
    status: str = "displayed",
    projection_id: str = "projection-1",
) -> StrategyProjection:
    return StrategyProjection.create(
        projection_id=projection_id,
        run_id=run_id,
        decision_frame_ref=frame_ref,
        alignment_handoff_ref=handoff_ref,
        target_ref=target_ref,
        current_understanding="Validate the requester decision.",
        assumptions=("requester owns outcome",),
        decision_targets=decision_targets,
        tracks=({"id": "track-1"},),
        method_hypotheses=({"method": "repository"},),
        depth="deep",
        evidence_expectations=("independent source",),
        autonomy_envelope={"allowed": ["research"]},
        replanning_policy={"same_round": ["depth"]},
        success_oracles=success_oracles,
        delivery_contract={"technical": "package", "human": "report"},
        stop_rule="oracles pass",
        preference_influences=(),
        revision=1,
        status=status,
    )


def attach_confirmed_projection(ledger: RunLedger, run_id: str, target: ArtifactRevision) -> StrategyProjection:
    """Append handoff, frame, projection, and confirm event so a run can compile work items."""

    handoff = ledger.append_artifact(
        run_id,
        "handoff-1",
        "alignment-handoff",
        {"confirmed": True},
        expected_revision=ledger.get_revision(run_id),
    )
    frame = ledger.append_artifact(
        run_id,
        "strategy-frame",
        "decision-frame",
        {"status": "ready_for_strategy"},
        expected_revision=ledger.get_revision(run_id),
    )
    goal_projection = projection(
        run_id,
        frame_ref=ArtifactRef(run_id, frame.id, frame.revision),
        handoff_ref=ArtifactRef(run_id, handoff.id, handoff.revision),
        target_ref=ArtifactRef(run_id, target.id, target.revision),
    )
    confirm_projection(ledger, run_id, goal_projection)
    return goal_projection


def goal_run(
    tmp_path: Path,
    *,
    slots: tuple[dict, ...] = (),
    target_id: str = "decision-1",
    success_oracles: tuple = ({"id": "oracle-1", "evidence_standard_ids": ("standard-1",)},),
):
    """A ledger run holding a confirmed projection and a blueprint target carrying slots."""

    ledger = RunLedger(tmp_path / "ledger")
    ledger.initialize()
    ledger.create_run(RUN_ID)
    handoff = _append(ledger, "handoff-1", "alignment-handoff", {"confirmed": True})
    target = _append(
        ledger,
        "blueprint-target",
        "blueprint-target",
        {
            "id": "blueprint-target",
            "round_id": RUN_ID,
            "brief_id": "working-brief",
            "intent_model_id": "intent-model",
            "slots": list(slots),
        },
        (ArtifactRef(RUN_ID, handoff.id, handoff.revision),),
    )
    frame = _append(ledger, "strategy-frame", "decision-frame", {"status": "ready_for_strategy"})
    goal_projection = projection(
        RUN_ID,
        frame_ref=ArtifactRef(RUN_ID, frame.id, frame.revision),
        handoff_ref=ArtifactRef(RUN_ID, handoff.id, handoff.revision),
        target_ref=ArtifactRef(RUN_ID, target.id, target.revision),
        decision_targets=(target_id,),
        success_oracles=success_oracles,
    )
    confirm_projection(ledger, RUN_ID, goal_projection)
    return ledger, target


def work_item_arguments(target: ArtifactRevision, slot_id: str = "slot-1") -> dict:
    return {
        "round_id": RUN_ID,
        "work_item_id": "work-goal",
        "blueprint_target": target,
        "decision_slot_id": slot_id,
        "kind": "repository_analysis",
        "scope": "Inspect the bounded isolation boundary.",
        "exclusions": "Do not close the Decision Slot.",
        "decision_change_reason": "The result can change the selected alternative.",
        "depends_on": (),
        "methods": ("repository_inspection",),
        "budget": {"tool_calls": 4, "time": "bounded"},
        "completion_rule": "Return a Finding Pack or state why evidence is unavailable.",
    }


def complete_alignment_graph() -> dict:
    """The minimal complete alignment graph shape proven by test_alignment_controller."""

    required = {
        "goal": ("outcome", "Produce an implementation-driving technical strategy."),
        "use": ("intended_use", "Use the result to authorize and plan implementation."),
        "scope": ("scope_boundary", "Research and design only; no implementation yet."),
        "delivery": ("delivery", "Deliver a professional evidence-anchored technical package."),
        "authority": ("authority", "The agent owns autonomous research after confirmation."),
        "success": ("success_oracle", "Every P0 decision has evidence and a validation oracle."),
        "feasibility": ("feasibility", "The strategy is technically plausible in the stated environment."),
        "strategy": ("strategy", "Use recursive decision-risk research with independent validation."),
    }
    nodes: list[dict] = [
        {
            "id": node_id,
            "type": node_type,
            "statement": statement,
            "status": "supported",
            "impact": 5,
            "human_only": False,
            "confidence": "high",
            "source": "joint",
        }
        for node_id, (node_type, statement) in required.items()
    ]
    nodes.extend(
        [
            {
                "id": "question-architecture",
                "type": "research_question",
                "statement": "Which architecture best satisfies the confirmed strategy?",
                "status": "candidate",
                "impact": 5,
                "human_only": False,
                "confidence": "low",
                "source": "joint",
                "oracle": "The leading architecture survives an independent executable validation.",
            },
            {
                "id": "evidence-recon",
                "type": "evidence",
                "statement": "Initial reconnaissance found a persisted coordinator pattern.",
                "status": "supported",
                "impact": 3,
                "human_only": False,
                "confidence": "medium",
                "source": "reconnaissance",
                "attributes": {"anchor": {"kind": "source", "ref": "https://example.test/coordinator"}},
            },
        ]
    )
    return {
        "nodes": nodes,
        "edges": [
            {
                "id": "edge-recon-supports",
                "source_id": "evidence-recon",
                "target_id": "question-architecture",
                "relation": "supports",
                "status": "active",
                "confidence": "medium",
                "provenance": "alignment reconnaissance turn 1",
            },
            {
                "id": "edge-recon-limits",
                "source_id": "evidence-recon",
                "target_id": "question-architecture",
                "relation": "limits",
                "status": "active",
                "confidence": "low",
                "provenance": "alignment reconnaissance turn 2",
            },
        ],
    }


def confirmed_alignment(workspace: Path, *, run_id: str = RUN_ID, project_id: str = "proj-goal") -> Path:
    """Create a fully confirmed SQLite alignment graph and return its database path."""

    alignment_init(workspace, run_id, project_id=project_id)
    graph_file = workspace / "graph.json"
    graph_file.write_text(json.dumps(complete_alignment_graph()), encoding="utf-8")
    decision = alignment_plan(workspace, run_id, graph_file, project_id=project_id)
    alignment_confirm(
        workspace,
        run_id,
        "I confirm the stated outcome and authorize autonomous research within that scope.",
        decision["alignment_digest"],
        project_id=project_id,
    )
    return database_path(workspace, run_id, project_id)


def wired_run(tmp_path: Path, *, success_oracles: tuple | None = None):
    """A coordinator run initialized from a handoff and blueprint target, ready for strategy.

    Returns (workspace, ledger, coordinator, target, frame_ref) with the confirmed
    SQLite alignment graph in place so the CLI confirm verb can bridge to the tree.
    """

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ledger = RunLedger(workspace)
    ledger.initialize()
    ledger.create_run(RUN_ID)
    confirmed_alignment(workspace, run_id=RUN_ID, project_id="proj-goal")
    handoff = _append(ledger, "handoff-1", "alignment-handoff", {"confirmed": True})
    target = _append(
        ledger,
        "blueprint-target",
        "blueprint-target",
        {
            "id": "blueprint-target",
            "round_id": RUN_ID,
            "brief_id": "working-brief",
            "intent_model_id": "intent-model",
            "slots": [slot("slot-1")],
        },
        (ArtifactRef(RUN_ID, handoff.id, handoff.revision),),
    )
    coordinator = ResearchRunCoordinator(ledger)
    coordinator.initialize(
        run_id=RUN_ID,
        alignment_handoff=handoff,
        blueprint_target=target,
        expected_revision=ledger.get_revision(RUN_ID),
    )
    frame = DecisionFrame.create(
        frame_id="strategy-frame",
        run_id=RUN_ID,
        requester_wording="Choose the customer decision to validate.",
        primary_decision={"id": "decision-1", "statement": "Choose the customer decision", "success_signal": "signal"},
        target_ref=ArtifactRef(RUN_ID, target.id, target.revision),
        hypotheses=(
            IntentHypothesis(
                id="selected",
                interpretation="selected decision",
                ambiguity="explicit",
                owner="requester",
                researchable=False,
                decision_consequence="sets scope",
                source_refs=("input-1",),
                disposition="selected",
                next_action="form strategy",
                primary_decision_id="decision-1",
                material=True,
                evidence_ranked=True,
            ),
        ),
    )
    frame_artifact = coordinator.persist_decision_frame(frame, expected_revision=ledger.get_revision(RUN_ID))
    if success_oracles is None:
        success_oracles = ({"id": "oracle-1", "evidence_standard_ids": ("standard-1",)},)
    goal_projection = projection(
        RUN_ID,
        frame_ref=ArtifactRef(RUN_ID, frame_artifact.id, frame_artifact.revision),
        handoff_ref=ArtifactRef(RUN_ID, handoff.id, handoff.revision),
        target_ref=ArtifactRef(RUN_ID, target.id, target.revision),
        decision_targets=({"id": "decision-1", "oracle_ids": ("oracle-1",)},),
        success_oracles=success_oracles,
        status="draft",
    )
    projection_file = workspace / "projection.json"
    projection_file.write_text(json.dumps(goal_projection.to_dict(), sort_keys=True), encoding="utf-8")
    return workspace, ledger, coordinator, target, projection_file


def strategy_arguments(workspace: Path) -> list[str]:
    return ["strategy", "--workspace", str(workspace), "--project-id", "proj-goal", "--run-id", RUN_ID]


def json_output(capsys: pytest.CaptureFixture[str]) -> dict:
    captured = capsys.readouterr()
    # Issue #440: strip the balanced rt:* tag wrapper before parsing.
    import re as _re

    out = captured.out.strip()
    open_match = _re.search(r"<rt:(?:tool-output|error)[^>]*>", out)
    if open_match:
        close = "</rt:tool-output>" if "<rt:tool-output" in out else "</rt:error>"
        out = out[open_match.end() : out.rindex(close)]
    return json.loads(out)


# ---------------------------------------------------------------------------
# B1: slot serves validation
# ---------------------------------------------------------------------------


def test_serves_happy_path_compiles(tmp_path: Path) -> None:
    ledger, target = goal_run(tmp_path, slots=(slot("slot-1"),))
    work = CanonicalWorkItemCompiler(ledger).compile(
        **work_item_arguments(target), expected_revision=ledger.get_revision(RUN_ID)
    )

    assert work.payload["serves"] == {"target_id": "decision-1", "oracle_ids": ("oracle-1",)}
    assert goal_decomposition(ledger.load_run(RUN_ID).artifacts) == (
        {"slot_id": "slot-1", "target_id": "decision-1", "oracle_ids": ["oracle-1"], "priority": "P0"},
    )


def test_serves_unknown_target_rejected(tmp_path: Path) -> None:
    ledger, target = goal_run(tmp_path, slots=(slot("slot-1", target_id="decision-unknown"),))
    with pytest.raises(
        InvalidWorkItemError,
        match=re.escape("serves.target_id not in confirmed strategy-projection decision_targets: decision-unknown"),
    ):
        CanonicalWorkItemCompiler(ledger).compile(
            **work_item_arguments(target), expected_revision=ledger.get_revision(RUN_ID)
        )


def test_serves_unknown_oracle_rejected(tmp_path: Path) -> None:
    ledger, target = goal_run(tmp_path, slots=(slot("slot-1", oracle_ids=("oracle-unknown",)),))
    with pytest.raises(
        InvalidWorkItemError,
        match=re.escape("serves.oracle_id not in confirmed strategy-projection success_oracles: oracle-unknown"),
    ):
        CanonicalWorkItemCompiler(ledger).compile(
            **work_item_arguments(target), expected_revision=ledger.get_revision(RUN_ID)
        )


def test_p0_slot_requires_oracle(tmp_path: Path) -> None:
    ledger, target = goal_run(tmp_path, slots=(slot("slot-1", oracle_ids=()),))
    with pytest.raises(
        InvalidWorkItemError,
        match=re.escape("P0 slot requires non-empty serves.oracle_ids: slot-1"),
    ):
        CanonicalWorkItemCompiler(ledger).compile(
            **work_item_arguments(target), expected_revision=ledger.get_revision(RUN_ID)
        )


def test_unconfirmed_projection_rejects_compile(tmp_path: Path) -> None:
    ledger = RunLedger(tmp_path / "ledger")
    ledger.initialize()
    ledger.create_run(RUN_ID)
    handoff = _append(ledger, "handoff-1", "alignment-handoff", {"confirmed": True})
    target = _append(
        ledger,
        "blueprint-target",
        "blueprint-target",
        {
            "id": "blueprint-target",
            "round_id": RUN_ID,
            "brief_id": "working-brief",
            "intent_model_id": "intent-model",
            "slots": [slot("slot-1")],
        },
        (ArtifactRef(RUN_ID, handoff.id, handoff.revision),),
    )
    with pytest.raises(InvalidWorkItemError, match="confirmed strategy-projection"):
        CanonicalWorkItemCompiler(ledger).compile(
            **work_item_arguments(target), expected_revision=ledger.get_revision(RUN_ID)
        )
    assert [item for item in ledger.load_run(RUN_ID).artifacts if item.kind == WORK_ITEM_KIND] == []


def test_handoff_projects_goal_decomposition(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ledger = RunLedger(workspace / "ledger")
    ledger.initialize()
    ledger.create_run(RUN_ID)
    confirmed_alignment(workspace)
    _target = _append(
        ledger,
        "blueprint-target",
        "blueprint-target",
        {
            "id": "blueprint-target",
            "round_id": RUN_ID,
            "brief_id": "working-brief",
            "intent_model_id": "intent-model",
            "slots": [
                slot("slot-3", priority="P1", oracle_ids=("oracle-3",)),
                slot("slot-1"),
                slot("slot-2", priority="P1", oracle_ids=("oracle-2",)),
            ],
        },
        (),
    )
    initialize_research_from_alignment(
        ledger,
        round_id=RUN_ID,
        tree_id=f"tree-{RUN_ID}",
        alignment_database=database_path(workspace, RUN_ID, "proj-goal"),
        expected_revision=ledger.get_revision(RUN_ID),
    )
    handoff_artifact = next(
        item
        for item in ledger.load_run(RUN_ID).artifacts
        if item.kind == "alignment-handoff" and item.id.startswith("alignment-handoff-")
    )
    assert handoff_artifact.payload["confirmed"] is True
    assert handoff_artifact.payload["goal_decomposition"] == (
        {"slot_id": "slot-1", "target_id": "decision-1", "oracle_ids": ("oracle-1",), "priority": "P0"},
        {"slot_id": "slot-2", "target_id": "decision-1", "oracle_ids": ("oracle-2",), "priority": "P1"},
        {"slot_id": "slot-3", "target_id": "decision-1", "oracle_ids": ("oracle-3",), "priority": "P1"},
    )


def test_slot_whitelist_requires_serves(tmp_path: Path) -> None:
    from test_decision_map import canonical_context as map_context
    from test_decision_map import initial_change

    modules, ledger, round_record, brief = map_context(tmp_path)
    invalid = slot("slot-architecture")
    invalid.pop("serves")
    with pytest.raises(InvalidBlueprintTargetError, match="serves"):
        CanonicalBlueprintTargetCompiler(ledger).compile(
            round_id=round_record.id,
            target_id="blueprint-target",
            working_brief=brief,
            slots=[invalid],
            change=initial_change("slot-architecture"),
            expected_revision=ledger.get_revision(round_record.id),
        )

    written = CanonicalBlueprintTargetCompiler(ledger).compile(
        round_id=round_record.id,
        target_id="blueprint-target",
        working_brief=brief,
        slots=[slot("slot-architecture")],
        change=initial_change("slot-architecture"),
        expected_revision=ledger.get_revision(round_record.id),
    )
    assert written.payload["slots"][0]["serves"] == {"target_id": "decision-1", "oracle_ids": ("oracle-1",)}


# ---------------------------------------------------------------------------
# R1: projection lifecycle CLI wiring
# ---------------------------------------------------------------------------


def test_strategy_lifecycle_cli_wires_display_confirm_and_tree_bridge(tmp_path: Path, capsys) -> None:
    workspace, ledger, coordinator, target, projection_file = wired_run(tmp_path)
    arguments = strategy_arguments(workspace)

    assert cli_main([*arguments, "propose", "--projection", str(projection_file)]) == 0
    proposed = json_output(capsys)
    assert proposed["command"] == "strategy.propose"
    assert proposed["status"] == "proposed"
    assert coordinator.state(RUN_ID).payload["state"] == "alignment"
    stored = [item for item in ledger.load_run(RUN_ID).artifacts if item.kind == "strategy-projection"]
    assert [item.payload["status"] for item in stored] == ["draft"]

    assert cli_main([*arguments, "display"]) == 0
    displayed = json_output(capsys)
    assert displayed["command"] == "strategy.display"
    assert displayed["status"] == "displayed"
    digest = displayed["result"]["display_digest"]
    assert digest != json.loads(projection_file.read_text(encoding="utf-8"))["display_digest"]
    assert displayed["result"]["goal_decomposition"] == [
        {"slot_id": "slot-1", "target_id": "decision-1", "oracle_ids": ["oracle-1"], "priority": "P0"}
    ]
    assert coordinator.state(RUN_ID).payload["state"] == "handoff_pending"
    statuses = [
        item.payload["status"]
        for item in sorted(
            (item for item in ledger.load_run(RUN_ID).artifacts if item.kind == "strategy-projection"),
            key=lambda item: item.revision,
        )
    ]
    assert statuses == ["draft", "displayed"]

    with pytest.raises(InvalidWorkItemError, match="confirmed strategy-projection"):
        CanonicalWorkItemCompiler(ledger).compile(
            **work_item_arguments(target), expected_revision=ledger.get_revision(RUN_ID)
        )

    assert cli_main([*arguments, "confirm", "--confirmation", "okay"]) == 2
    rejected = json_output(capsys)
    assert rejected["code"] == "generic_confirmation"
    assert coordinator.state(RUN_ID).payload["state"] == "handoff_pending"

    confirmation = f"I accept the displayed strategy {digest} and authorize research."
    assert cli_main([*arguments, "confirm", "--confirmation", confirmation]) == 0
    confirmed = json_output(capsys)
    assert confirmed["command"] == "strategy.confirm"
    assert confirmed["status"] == "confirmed"
    assert coordinator.state(RUN_ID).payload["state"] == "autonomous_research"
    trees = [item for item in ledger.load_run(RUN_ID).artifacts if item.id == f"tree-{RUN_ID}"]
    assert len(trees) == 1
    assert trees[0].payload["decision_slots"]

    work = CanonicalWorkItemCompiler(ledger).compile(
        **work_item_arguments(target), expected_revision=ledger.get_revision(RUN_ID)
    )
    assert work.payload["serves"] == {"target_id": "decision-1", "oracle_ids": ("oracle-1",)}

    bridged = next(
        item
        for item in ledger.load_run(RUN_ID).artifacts
        if item.kind == "alignment-handoff" and item.id.startswith("alignment-handoff-")
    )
    assert bridged.payload["confirmed"] is True
    assert bridged.payload["goal_decomposition"] == (
        {"slot_id": "slot-1", "target_id": "decision-1", "oracle_ids": ("oracle-1",), "priority": "P0"},
    )


def test_display_rejects_oracle_without_evidence_standard(tmp_path: Path, capsys) -> None:
    workspace, ledger, coordinator, _target, projection_file = wired_run(
        tmp_path, success_oracles=({"id": "oracle-1", "evidence_standard_ids": ()},)
    )
    arguments = strategy_arguments(workspace)
    assert cli_main([*arguments, "propose", "--projection", str(projection_file)]) == 0
    json_output(capsys)
    state_before = coordinator.state(RUN_ID)

    assert cli_main([*arguments, "display"]) == 2
    failure = json_output(capsys)
    assert failure["code"] == "success_oracles[0] requires non-empty evidence_standard_ids: oracle-1"
    assert coordinator.state(RUN_ID) == state_before
    assert not any(item.kind == "lifecycle-event" for item in ledger.load_run(RUN_ID).artifacts)
    assert [
        item.payload["status"] for item in ledger.load_run(RUN_ID).artifacts if item.kind == "strategy-projection"
    ] == ["draft"]


def test_display_rejects_dangling_decision_target_oracle_reference(tmp_path: Path, capsys) -> None:
    workspace, ledger, coordinator, _target, projection_file = wired_run(tmp_path)
    # rebuild the projection with a dangling decision-target oracle reference
    stored = [item for item in ledger.load_run(RUN_ID).artifacts if item.kind == "strategy-projection"]
    assert stored == []
    handoff = next(item for item in ledger.load_run(RUN_ID).artifacts if item.kind == "alignment-handoff")
    frame = next(item for item in ledger.load_run(RUN_ID).artifacts if item.kind == "decision-frame")
    target = next(item for item in ledger.load_run(RUN_ID).artifacts if item.kind == "blueprint-target")
    dangling = projection(
        RUN_ID,
        frame_ref=ArtifactRef(RUN_ID, frame.id, frame.revision),
        handoff_ref=ArtifactRef(RUN_ID, handoff.id, handoff.revision),
        target_ref=ArtifactRef(RUN_ID, target.id, target.revision),
        decision_targets=({"id": "decision-1", "oracle_ids": ("oracle-missing",)},),
        success_oracles=({"id": "oracle-1", "evidence_standard_ids": ("standard-1",)},),
        status="draft",
    )
    projection_file.write_text(json.dumps(dangling.to_dict(), sort_keys=True), encoding="utf-8")
    arguments = strategy_arguments(workspace)

    assert cli_main([*arguments, "propose", "--projection", str(projection_file)]) == 0
    json_output(capsys)
    state_before = coordinator.state(RUN_ID)

    assert cli_main([*arguments, "display"]) == 2
    failure = json_output(capsys)
    assert failure["code"] == "decision_targets[0] oracle_ids entry not in success_oracles: oracle-missing"
    assert coordinator.state(RUN_ID) == state_before
    assert not any(item.kind == "lifecycle-event" for item in ledger.load_run(RUN_ID).artifacts)


# ---------------------------------------------------------------------------
# R3: falsifiability gate at the coordinator authority layer
# ---------------------------------------------------------------------------


def _core_artifacts(ledger: RunLedger) -> tuple[ArtifactRevision, ArtifactRevision, ArtifactRevision]:
    run_artifacts = ledger.load_run(RUN_ID).artifacts
    return (
        next(item for item in run_artifacts if item.kind == "alignment-handoff"),
        next(item for item in run_artifacts if item.kind == "decision-frame"),
        next(item for item in run_artifacts if item.kind == "blueprint-target"),
    )


def _displayed_projection(
    ledger: RunLedger,
    *,
    projection_id: str,
    success_oracles: tuple,
) -> StrategyProjection:
    """A projection persisted-ready against the run's core artifacts with a displayed status."""

    handoff, frame, target = _core_artifacts(ledger)
    return projection(
        RUN_ID,
        frame_ref=ArtifactRef(RUN_ID, frame.id, frame.revision),
        handoff_ref=ArtifactRef(RUN_ID, handoff.id, handoff.revision),
        target_ref=ArtifactRef(RUN_ID, target.id, target.revision),
        decision_targets=({"id": "decision-1", "oracle_ids": ("oracle-1",)},),
        success_oracles=success_oracles,
        status="displayed",
        projection_id=projection_id,
    )


def _unfalsifiable_projection(ledger: RunLedger) -> StrategyProjection:
    """A projection whose success oracle is a bare string (no evidence standards).

    Persisted directly through the coordinator API with a hand-forged ``displayed``
    status — the bypass vector the authority layer must close.
    """

    return _displayed_projection(ledger, projection_id="projection-unfalsifiable", success_oracles=("oracle-1",))


def test_display_strategy_rejects_unfalsifiable_projection_without_cli(tmp_path: Path) -> None:
    workspace, ledger, coordinator, _target, _projection_file = wired_run(tmp_path)
    unfalsifiable = _unfalsifiable_projection(ledger)
    coordinator.persist_strategy_projection(unfalsifiable, expected_revision=ledger.get_revision(RUN_ID))
    state_before = coordinator.state(RUN_ID)
    revision_before = ledger.get_revision(RUN_ID)

    with pytest.raises(CoordinatorConflictError, match="evidence_standard_ids"):
        coordinator.display_strategy(RUN_ID, unfalsifiable, expected_revision=revision_before)

    assert coordinator.state(RUN_ID) == state_before
    assert ledger.get_revision(RUN_ID) == revision_before
    assert not any(item.kind == "lifecycle-event" for item in ledger.load_run(RUN_ID).artifacts)
    statuses = [
        item.payload["status"] for item in ledger.load_run(RUN_ID).artifacts if item.kind == "strategy-projection"
    ]
    assert statuses == ["displayed"]


def test_display_strategy_rejects_dangling_oracle_reference_without_cli(tmp_path: Path) -> None:
    workspace, ledger, coordinator, _target, _projection_file = wired_run(tmp_path)
    handoff, frame, target = _core_artifacts(ledger)
    dangling = projection(
        RUN_ID,
        frame_ref=ArtifactRef(RUN_ID, frame.id, frame.revision),
        handoff_ref=ArtifactRef(RUN_ID, handoff.id, handoff.revision),
        target_ref=ArtifactRef(RUN_ID, target.id, target.revision),
        decision_targets=({"id": "decision-1", "oracle_ids": ("oracle-missing",)},),
        success_oracles=({"id": "oracle-1", "evidence_standard_ids": ("standard-1",)},),
        status="displayed",
        projection_id="projection-dangling",
    )
    coordinator.persist_strategy_projection(dangling, expected_revision=ledger.get_revision(RUN_ID))
    state_before = coordinator.state(RUN_ID)
    revision_before = ledger.get_revision(RUN_ID)

    with pytest.raises(CoordinatorConflictError, match="oracle-missing"):
        coordinator.display_strategy(RUN_ID, dangling, expected_revision=revision_before)

    assert coordinator.state(RUN_ID) == state_before
    assert ledger.get_revision(RUN_ID) == revision_before
    assert not any(item.kind == "lifecycle-event" for item in ledger.load_run(RUN_ID).artifacts)


def test_direct_transition_rejects_unfalsifiable_projection(tmp_path: Path) -> None:
    """The gate holds for every caller: transition() invoked directly, display_strategy bypassed."""

    workspace, ledger, coordinator, _target, _projection_file = wired_run(tmp_path)
    unfalsifiable = _unfalsifiable_projection(ledger)
    coordinator.persist_strategy_projection(unfalsifiable, expected_revision=ledger.get_revision(RUN_ID))
    state_before = coordinator.state(RUN_ID)

    with pytest.raises(IllegalTransitionError, match="projection_unfalsifiable"):
        coordinator.transition(
            RUN_ID,
            "alignment_projection_ready",
            "coordinator",
            expected_revision=ledger.get_revision(RUN_ID),
            payload={
                "projection_ref": ArtifactRef(RUN_ID, unfalsifiable.projection_id, unfalsifiable.revision).to_dict(),
                "display_digest": unfalsifiable.display_digest,
            },
        )

    assert coordinator.state(RUN_ID) == state_before
    assert not any(item.kind == "lifecycle-event" for item in ledger.load_run(RUN_ID).artifacts)
    rejections = [item for item in ledger.load_run(RUN_ID).artifacts if item.kind == "lifecycle-rejection"]
    assert len(rejections) == 1
    assert "projection_unfalsifiable" in rejections[0].payload["reason"]
    assert "evidence_standard_ids" in rejections[0].payload["reason"]


def test_direct_transition_digest_failure_reason_stays_projection_required(tmp_path: Path) -> None:
    """A digest failure keeps the generic reason, so the two guard failures are distinguishable."""

    workspace, ledger, coordinator, _target, _projection_file = wired_run(tmp_path)
    unfalsifiable = _unfalsifiable_projection(ledger)
    coordinator.persist_strategy_projection(unfalsifiable, expected_revision=ledger.get_revision(RUN_ID))

    with pytest.raises(IllegalTransitionError, match="projection_required"):
        coordinator.transition(
            RUN_ID,
            "alignment_projection_ready",
            "coordinator",
            expected_revision=ledger.get_revision(RUN_ID),
            payload={
                "projection_ref": ArtifactRef(RUN_ID, unfalsifiable.projection_id, unfalsifiable.revision).to_dict(),
                "display_digest": "f" * 64,
            },
        )

    rejections = [item for item in ledger.load_run(RUN_ID).artifacts if item.kind == "lifecycle-rejection"]
    assert [item.payload["reason"] for item in rejections] == ["projection_required"]


def test_direct_transition_accepts_falsifiable_projection(tmp_path: Path) -> None:
    """The guard closes the bypass without breaking legitimate direct callers."""

    workspace, ledger, coordinator, _target, _projection_file = wired_run(tmp_path)
    falsifiable = _displayed_projection(
        ledger,
        projection_id="projection-direct",
        success_oracles=({"id": "oracle-1", "evidence_standard_ids": ("standard-1",)},),
    )
    coordinator.persist_strategy_projection(falsifiable, expected_revision=ledger.get_revision(RUN_ID))

    state = coordinator.transition(
        RUN_ID,
        "alignment_projection_ready",
        "coordinator",
        expected_revision=ledger.get_revision(RUN_ID),
        payload={
            "projection_ref": ArtifactRef(RUN_ID, falsifiable.projection_id, falsifiable.revision).to_dict(),
            "display_digest": falsifiable.display_digest,
        },
    )

    assert state.payload["state"] == "handoff_pending"


def test_confirm_handoff_requires_displayed_projection(tmp_path: Path) -> None:
    workspace, ledger, coordinator, _target, projection_file = wired_run(tmp_path)
    proposal = StrategyProjection.from_dict(json.loads(projection_file.read_text(encoding="utf-8")))
    coordinator.persist_strategy_projection(proposal, expected_revision=ledger.get_revision(RUN_ID))
    state_before = coordinator.state(RUN_ID)

    with pytest.raises(CoordinatorConflictError, match="strategy_projection_not_displayed"):
        coordinator.confirm_handoff(
            RUN_ID,
            projection_ref=ArtifactRef(RUN_ID, proposal.projection_id, proposal.revision),
            confirmation=f"I accept the displayed strategy {proposal.display_digest} and authorize research.",
            expected_revision=ledger.get_revision(RUN_ID),
            actor="human",
        )

    assert coordinator.state(RUN_ID) == state_before
    assert not any(item.kind == "lifecycle-event" for item in ledger.load_run(RUN_ID).artifacts)


# ---------------------------------------------------------------------------
# R3 review fixes 2+3: latest_confirmed fail-closed boundaries at compile
# ---------------------------------------------------------------------------


def _lifecycle_confirm_event(
    ledger: RunLedger,
    event_id: str,
    projection_ref: ArtifactRef,
    display_digest: str,
) -> ArtifactRevision:
    """Append a handoff_confirmed event, optionally against a non-matching digest."""

    return _append(
        ledger,
        event_id,
        "lifecycle-event",
        {
            "event_id": event_id,
            "idempotency_key": event_id,
            "event": "handoff_confirmed",
            "from": "handoff_pending",
            "to": "autonomous_research",
            "actor": "human",
            "payload": {
                "projection_ref": projection_ref.to_dict(),
                "display_digest": display_digest,
                "confirmation": f"I accept {display_digest} and authorize research.",
            },
        },
    )


def test_trailing_corrupt_confirmation_rejects_compilation(tmp_path: Path) -> None:
    ledger, target = goal_run(tmp_path, slots=(slot("slot-1"),))
    confirmed = next(item for item in ledger.load_run(RUN_ID).artifacts if item.kind == "strategy-projection")
    _lifecycle_confirm_event(
        ledger,
        "event-corrupt-confirm",
        ArtifactRef(RUN_ID, confirmed.id, confirmed.revision),
        "f" * 64,
    )

    with pytest.raises(InvalidWorkItemError, match="confirmed strategy-projection"):
        CanonicalWorkItemCompiler(ledger).compile(
            **work_item_arguments(target), expected_revision=ledger.get_revision(RUN_ID)
        )


# ---------------------------------------------------------------------------
# R4: defense-in-depth falsifiability re-entry (confirm + compile boundaries)
# ---------------------------------------------------------------------------


def test_confirm_handoff_rejects_unfalsifiable_projection(tmp_path: Path) -> None:
    """A pre-gate (hand-written) handoff_pending ledger cannot confirm an unfalsifiable
    projection: the confirm boundary re-validates the projection content itself."""

    workspace, ledger, coordinator, _target, _projection_file = wired_run(tmp_path)
    falsifiable = _displayed_projection(
        ledger,
        projection_id="projection-legit",
        success_oracles=({"id": "oracle-1", "evidence_standard_ids": ("standard-1",)},),
    )
    coordinator.persist_strategy_projection(falsifiable, expected_revision=ledger.get_revision(RUN_ID))
    coordinator.display_strategy(RUN_ID, falsifiable, expected_revision=ledger.get_revision(RUN_ID))
    unfalsifiable = _unfalsifiable_projection(ledger)
    ledger.append_strategy_projection(
        RUN_ID,
        unfalsifiable.projection_id,
        unfalsifiable.to_dict(),
        parent_refs=(
            unfalsifiable.decision_frame_ref,
            unfalsifiable.alignment_handoff_ref,
            unfalsifiable.target_ref,
        ),
        expected_revision=ledger.get_revision(RUN_ID),
    )
    state_before = coordinator.state(RUN_ID)

    with pytest.raises(CoordinatorConflictError, match="evidence_standard_ids"):
        coordinator.confirm_handoff(
            RUN_ID,
            projection_ref=ArtifactRef(RUN_ID, unfalsifiable.projection_id, unfalsifiable.revision),
            confirmation=f"I accept {unfalsifiable.display_digest} and authorize research.",
            expected_revision=ledger.get_revision(RUN_ID),
            actor="human",
        )

    assert coordinator.state(RUN_ID) == state_before
    assert not any(
        item.kind == "lifecycle-event" and item.payload.get("event") == "handoff_confirmed"
        for item in ledger.load_run(RUN_ID).artifacts
    )


def test_compile_rejects_unfalsifiable_confirmed_projection(tmp_path: Path) -> None:
    """The serves basis itself must be falsifiable: a hand-confirmed legacy projection with
    bare-string oracles cannot authorize work items."""

    ledger, target = goal_run(tmp_path, slots=(slot("slot-1"),), success_oracles=("oracle-1",))

    with pytest.raises(InvalidWorkItemError, match="unfalsifiable"):
        CanonicalWorkItemCompiler(ledger).compile(
            **work_item_arguments(target), expected_revision=ledger.get_revision(RUN_ID)
        )

    assert not any(item.kind == WORK_ITEM_KIND for item in ledger.load_run(RUN_ID).artifacts)


def test_superseded_confirmation_rejects_compilation(tmp_path: Path) -> None:
    ledger, target = goal_run(tmp_path, slots=(slot("slot-1"),))
    confirmed = next(item for item in ledger.load_run(RUN_ID).artifacts if item.kind == "strategy-projection")
    revised_payload = thaw_json(confirmed.payload)
    revised_payload["revision"] = 2
    revised_payload["display_payload"]["revision"] = 2
    revised_payload["display_digest"] = "a" * 64
    revised_payload["content_hash"] = "b" * 64
    _append(
        ledger,
        confirmed.id,
        "strategy-projection",
        revised_payload,
        (ArtifactRef(RUN_ID, confirmed.id, confirmed.revision),),
    )

    with pytest.raises(InvalidWorkItemError, match="confirmed strategy-projection"):
        CanonicalWorkItemCompiler(ledger).compile(
            **work_item_arguments(target), expected_revision=ledger.get_revision(RUN_ID)
        )
