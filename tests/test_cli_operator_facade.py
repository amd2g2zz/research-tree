"""Issue #470 operator facade: the CLI init chain, packaged record, operating model.

The journey test drives the product exactly as an operator would: every
research-tree surface is reached through ``research_tree.cli.main`` argv (the
alignment graph is staged through the same ``AlignmentGraphStore`` API the
alignment controller CLI wraps), and the packaged ``record`` path runs in a
real subprocess.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from research_tree.alignment_graph import AlignmentGraphStore, database_path
from research_tree.cli import main as cli_main
from research_tree.decision_map import CanonicalBlueprintTargetCompiler
from research_tree.run_ledger import RunLedger

RUN_ID = "run-operator-facade"
PROJECT_ID = "proj-facade"
PACKAGE_CONTROLLER = Path("packages/codex/research-tree/scripts/alignment_controller.py")


def run_cli(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict[str, Any]]:
    rc = cli_main(list(argv))
    out = capsys.readouterr().out
    payload: dict[str, Any] = {}
    for line in out.splitlines():
        for tag in ("<rt:tool-output", "<rt:error"):
            start = line.find(tag)
            if start >= 0:
                body = line[start + len(tag) :]
                body = body.split(">", 1)[1] if ">" in body else body
                body = body.rsplit("</", 1)[0]
                payload = json.loads(body)
    return rc, payload


# ---------------------------------------------------------------------------
# Operator documents (authored as plain JSON files, as an operator would)
# ---------------------------------------------------------------------------


def _resolved_analysis() -> dict[str, Any]:
    return {
        "signals": [
            {
                "input_id": "input-brief",
                "observation": "The operator wants the CLI journey to reach the strategy gates.",
                "kind": "stated_goal",
                "authority_boundary": "It names the outcome, not the driving surface.",
            },
            {
                "input_id": "input-constraint",
                "observation": "The operator drives everything through research-tree CLI verbs.",
                "kind": "constraint",
                "authority_boundary": "It settles the driving surface for this run.",
            },
        ],
        "hypotheses": [
            {
                "id": "intent-operator-cli",
                "interpretation": "The operator CLI chain reaches the strategy gates.",
                "status": "leading",
                "signal_refs": ["input-brief", "input-constraint"],
                "confidence": "high",
                "decision_consequence": "Sets the decision surface to the CLI journey.",
                "validation": "repository_inspection",
            }
        ],
        "desired_outcomes": ["a governed run initialized and confirmed from CLI verbs alone"],
        "success_signals": ["the initialized run-state carries the compiled handoff lineage"],
        "decision_drivers": [
            {
                "dimension": "technical",
                "statement": "The chain must reuse the exact coordinator initialize contract.",
                "signal_refs": ["input-brief"],
            }
        ],
        "hard_constraints": ["Do not drive Python internals from the operator surface."],
        "non_goals": ["Do not host subprocesses."],
        "unresolved_interpretations": [],
    }


def _brief_document() -> dict[str, Any]:
    return {
        "intent_id": "intent-model",
        "brief_id": "working-brief",
        "inputs": [
            {
                "id": "input-brief",
                "kind": "brief",
                "content": "Reach the strategy gates of this governed run through CLI verbs alone.",
                "origin_type": "user",
                "origin_locator": "conversation:operator-facade",
                "role": "signal",
            },
            {
                "id": "input-constraint",
                "kind": "note",
                "content": "Every step must be a documented research-tree CLI command.",
                "origin_type": "user",
                "origin_locator": "conversation:operator-facade",
                "role": "constraint",
            },
        ],
        "context_bundle_ids": [],
        "analysis": _resolved_analysis(),
        "triggers": [
            {"kind": "initial_request", "text": "Run the operator facade journey.", "input_ids": ["input-brief"]}
        ],
        "selected_input_ids": ["input-brief", "input-constraint"],
        "input_roles": {"input-brief": "primary", "input-constraint": "constraint"},
        "material_conflicts": [],
        "working_interpretation": "The CLI chain is the leading, resolved intent.",
        "technical_outcome": "Initialize and confirm one governed run from CLI verbs alone.",
        "assumptions": ["The alignment graph is confirmed before initialize runs."],
    }


def _blueprint_document() -> dict[str, Any]:
    return {
        "target_id": "blueprint-target",
        "slots": [
            {
                "id": "slot-operator-cli",
                "kind": "validation",
                "question": "Does the CLI chain carry the compiled handoff to a confirmed strategy?",
                "intent_hypothesis_ids": ["intent-operator-cli"],
                "priority": "P0",
                "impact": "high",
                "uncertainty": "high",
                "irreversibility": "low",
                "constraints": [
                    {
                        "kind": "input",
                        "ref": "input-constraint",
                        "statement": "Every step must be a documented research-tree CLI command.",
                    }
                ],
                "alternatives": ["operator-cli-chain", "in-process-chain"],
                "repository_touchpoints": [],
                "greenfield_assumptions": ["The bind bridge is the compile-time handoff parent."],
                "depends_on": [],
                "evidence_standard": "canonical receipts of the CLI journey",
                "validation": {"kind": "test", "oracle": "one governed run confirms strategy from CLI verbs"},
                "closure_rule": "select, conditionally select, defer with fallback, or block",
                "status": "open",
                "bounded_research_need": "prove the prepared run initializes through the CLI",
                "fallback": "the run stays prepared instead of declaring a pass",
                "serves": {
                    "target_id": "decision-operator-cli",
                    "oracle_ids": ["oracle-cli-confirmation"],
                },
            }
        ],
        "change": {
            "kind": "initial",
            "reason": "Map the implementation decision implied by the resolved Working Brief.",
            "from_slot_ids": [],
            "to_slot_ids": ["slot-operator-cli"],
        },
    }


def _frame_document() -> dict[str, Any]:
    return {
        "frame_id": "frame-operator-cli",
        "run_id": RUN_ID,
        "requester_wording": "Confirm the operator CLI journey reaches the strategy gates.",
        "primary_decision": {
            "id": "decision-operator-cli",
            "statement": "Does the CLI chain carry the compiled handoff to a confirmed strategy?",
            "success_signal": "one governed run confirms strategy from CLI verbs alone",
        },
        "hypotheses": [
            {
                "id": "selected",
                "interpretation": "The operator CLI chain reaches the strategy gates.",
                "ambiguity": "explicit",
                "owner": "requester",
                "researchable": False,
                "decision_consequence": "sets the run scope",
                "source_refs": ["input-brief", "input-constraint"],
                "disposition": "selected",
                "next_action": "form strategy",
                "primary_decision_id": "decision-operator-cli",
                "material": True,
                "evidence_ranked": True,
            }
        ],
    }


def _graph_document() -> dict[str, Any]:
    required = {
        "goal": ("outcome", "Reach the strategy gates of this run from CLI verbs alone."),
        "use": ("intended_use", "Authorize the governed operator lane through CLI verbs."),
        "scope": ("scope_boundary", "One governed run driven by research-tree CLI verbs."),
        "delivery": ("delivery", "Deliver the confirmed strategy and its operating model view."),
        "authority": ("authority", "The agent owns autonomous research after the confirmation."),
        "success": (
            "success_oracle",
            "The initialized run confirms the displayed strategy end to end.",
        ),
        "feasibility": ("feasibility", "Every stage is a real public CLI verb proven by tests."),
        "strategy": ("strategy", "Use the compiled handoff bridge to confirm the strategy."),
    }
    nodes = [
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
    nodes.append(
        {
            "id": "question-operator-cli",
            "type": "research_question",
            "statement": "Does the CLI chain reach the strategy gates?",
            "status": "candidate",
            "impact": 5,
            "human_only": False,
            "confidence": "low",
            "source": "joint",
            "oracle": "The initialized run confirms the displayed strategy.",
        }
    )
    return {"nodes": nodes, "edges": []}


def _confirm_alignment_graph(workspace: Path) -> None:
    store = AlignmentGraphStore(database_path(workspace, RUN_ID, PROJECT_ID))
    store.initialize(RUN_ID)
    decision = store.plan(_graph_document())
    store.confirm(
        "I confirm the stated outcome and authorize autonomous research within that scope.",
        decision["alignment_digest"],
    )


def _write_docs(workspace: Path) -> dict[str, Path]:
    docs = workspace / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    paths = {
        "brief": docs / "brief.json",
        "blueprint": docs / "blueprint.json",
        "frame": docs / "frame.json",
    }
    paths["brief"].write_text(json.dumps(_brief_document()), encoding="utf-8")
    paths["blueprint"].write_text(json.dumps(_blueprint_document()), encoding="utf-8")
    paths["frame"].write_text(json.dumps(_frame_document()), encoding="utf-8")
    return paths


def _common_args(workspace: Path) -> list[str]:
    return ["--workspace", str(workspace), "--project-id", PROJECT_ID, "--run-id", RUN_ID]


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


def _prepare_run(capsys, workspace: Path) -> None:
    rc, payload = run_cli(
        capsys,
        "run",
        "--host",
        "claude",
        *_common_args(workspace),
        "--outcome",
        "Reach the strategy gates from CLI verbs alone.",
        "--scope",
        "One governed run.",
        "--authority",
        "Autonomous research after confirmation.",
        "--success-oracle",
        "The initialized run confirms the displayed strategy.",
    )
    assert rc == 0, payload


# ---------------------------------------------------------------------------
# Journey: run -> initialize -> strategy propose/display/confirm
# ---------------------------------------------------------------------------


def test_cli_initializes_prepared_run_and_confirms_strategy(capsys, workspace: Path) -> None:
    _prepare_run(capsys, workspace)
    _confirm_alignment_graph(workspace)
    docs = _write_docs(workspace)

    rc, payload = run_cli(
        capsys,
        "initialize",
        *_common_args(workspace),
        "--brief",
        str(docs["brief"]),
        "--blueprint",
        str(docs["blueprint"]),
        "--frame",
        str(docs["frame"]),
        "--idempotency-key",
        "init-operator",
    )
    assert rc == 0, payload
    result = payload["result"]
    assert result["state"] == "alignment"
    frame_ref = result["frame_ref"]
    ledger = RunLedger(workspace)
    artifacts = ledger.load_run(RUN_ID).artifacts
    target = next(item for item in artifacts if item.kind == "blueprint-target")
    handoff = next(item for item in artifacts if item.kind == "alignment-handoff")
    assert any(ref.artifact_id == handoff.id and ref.revision == handoff.revision for ref in target.parent_refs), (
        "the compiled blueprint target must carry the exact handoff revision"
    )

    projection = {
        "projection_id": "strategy-operator-cli",
        "run_id": RUN_ID,
        "decision_frame_ref": frame_ref,
        "alignment_handoff_ref": {
            "round_id": RUN_ID,
            "artifact_id": handoff.id,
            "revision": handoff.revision,
        },
        "target_ref": {"round_id": RUN_ID, "artifact_id": target.id, "revision": target.revision},
        "current_understanding": "Confirm the operator CLI journey reaches the strategy gates.",
        "assumptions": ["the canonical receipts are the evidence"],
        "decision_targets": [{"id": "decision-operator-cli", "oracle_ids": ["oracle-cli-confirmation"]}],
        "tracks": [{"id": "track-operator"}],
        "method_hypotheses": [{"method": "operator-cli-chain"}],
        "depth": "deep",
        "evidence_expectations": ["canonical receipts"],
        "autonomy_envelope": {"allowed": ["research"], "authority": "research_owner"},
        "replanning_policy": {"same_round": ["depth"]},
        "success_oracles": [{"id": "oracle-cli-confirmation", "evidence_standard_ids": ["standard-cli"]}],
        "delivery_contract": {"technical": "package", "human": "report"},
        "stop_rule": "the confirmed strategy satisfies the oracle",
        "preference_influences": [],
        "revision": 1,
        "status": "draft",
    }
    projection_path = workspace / "docs" / "projection.json"
    projection_path.write_text(json.dumps(projection), encoding="utf-8")
    verification = {
        "schema": 1,
        "id": "alignment-verification-1",
        "round_id": RUN_ID,
        "projection_ref": {
            "round_id": RUN_ID,
            "artifact_id": "strategy-operator-cli",
            "revision": 1,
        },
        "authority_fingerprint": "computed-by-the-cli",
        "verifier_identity": "agent-verifier-support",
        "session_context": "session-main",
        "understood": {
            "outcome": "Independently restated: confirm the operator CLI journey.",
            "scope": "Independently restated: one governed run.",
            "authority": "Independently restated: autonomous research within the envelope.",
            "success_oracles": [{"id": "oracle-cli-confirmation", "understanding": "Independently restated oracle."}],
        },
        "discrepancies": [],
    }
    verification_path = workspace / "docs" / "alignment-verification.json"
    verification_path.write_text(json.dumps(verification), encoding="utf-8")

    rc, payload = run_cli(
        capsys,
        "strategy",
        *_common_args(workspace),
        "propose",
        "--projection",
        str(projection_path),
        "--alignment-verification",
        str(verification_path),
    )
    assert rc == 0, payload

    rc, payload = run_cli(capsys, "strategy", *_common_args(workspace), "display")
    assert rc == 0, payload
    display_digest = payload["result"]["display_digest"]
    assert isinstance(display_digest, str) and display_digest

    rc, payload = run_cli(
        capsys,
        "strategy",
        *_common_args(workspace),
        "confirm",
        "--confirmation",
        "I accept the displayed digest " + display_digest + " and authorize the research.",
    )
    assert rc == 0, payload
    assert payload["result"]["state"] == "autonomous_research"


def test_cli_initialize_names_missing_working_brief(capsys, workspace: Path) -> None:
    _prepare_run(capsys, workspace)
    _confirm_alignment_graph(workspace)
    rc, payload = run_cli(capsys, "initialize", *_common_args(workspace))
    assert rc == 2, payload
    assert payload["code"] == "working_brief_missing"


# ---------------------------------------------------------------------------
# Operating model exposure
# ---------------------------------------------------------------------------


def test_cli_operating_model_renders_operator_sections(capsys, workspace: Path) -> None:
    _prepare_run(capsys, workspace)
    rc = cli_main(["operating-model", *_common_args(workspace)])
    out = capsys.readouterr().out
    assert rc == 0
    for section in (
        "## Operating Model",
        "### Roles",
        "### SLA",
        "### Concurrency limits",
        "### Blockers",
        "### Fallback plan",
    ):
        assert section in out, section


# ---------------------------------------------------------------------------
# Packaged record fix (#470 F2)
# ---------------------------------------------------------------------------


def test_packaged_record_reaches_rc0(capsys, workspace: Path) -> None:
    store = AlignmentGraphStore(database_path(workspace, RUN_ID, PROJECT_ID))
    store.initialize(RUN_ID)
    store.plan(_graph_document())
    completed = subprocess.run(
        [
            sys.executable,
            str(PACKAGE_CONTROLLER),
            "--workspace",
            str(workspace),
            "--project-id",
            PROJECT_ID,
            "record",
            "--run-id",
            RUN_ID,
            "--node-id",
            "question-operator-cli",
            "--outcome",
            "answered",
            "--fingerprint",
            "operator-turn-1",
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert completed.returncode == 0, completed.stderr
    assert "turn" in completed.stdout


# ---------------------------------------------------------------------------
# Bind bridge unit contracts
# ---------------------------------------------------------------------------


def _seed_bound_fixture(workspace: Path):
    """Prepare a run with brief + confirmed handoff; return (ledger, brief, handoff)."""
    from research_tree.alignment_handoff import initialize_research_from_alignment
    from research_tree.intake import CanonicalInputIntakeService
    from research_tree.intent import CanonicalIntentModelCompiler, CanonicalWorkingBriefCompiler

    ledger = RunLedger(workspace)
    ledger.initialize()
    ledger.create_run(RUN_ID)
    intake = CanonicalInputIntakeService(ledger)
    for input_id, kind, role in (("input-brief", "brief", "signal"), ("input-constraint", "note", "constraint")):
        intake.ingest_text(
            round_id=RUN_ID,
            input_id=input_id,
            kind=kind,
            content="Seeded operator document content.",
            origin_type="user",
            origin_locator="conversation:bind-fixture",
            role=role,
            expected_revision=ledger.get_revision(RUN_ID),
        )
    model = CanonicalIntentModelCompiler(ledger).compile(
        round_id=RUN_ID,
        intent_id="intent-model",
        context_bundle_ids=(),
        input_ids=("input-brief", "input-constraint"),
        analysis=_resolved_analysis(),
        expected_revision=ledger.get_revision(RUN_ID),
    )
    brief = CanonicalWorkingBriefCompiler(ledger).compile(
        round_id=RUN_ID,
        brief_id="working-brief",
        intent_model=model,
        triggers=[{"kind": "initial_request", "text": "Bind fixture.", "input_ids": ["input-brief"]}],
        context_bundle_ids=(),
        selected_input_ids=("input-brief", "input-constraint"),
        input_roles={"input-brief": "primary", "input-constraint": "constraint"},
        material_conflicts=[],
        working_interpretation="Bind fixture interpretation.",
        technical_outcome="Bind fixture outcome.",
        assumptions=["fixture assumption"],
        expected_revision=ledger.get_revision(RUN_ID),
    )
    _confirm_alignment_graph(workspace)
    initialize_research_from_alignment(
        ledger,
        round_id=RUN_ID,
        tree_id="tree-" + RUN_ID,
        alignment_database=database_path(workspace, RUN_ID, PROJECT_ID),
        expected_revision=ledger.get_revision(RUN_ID),
    )
    handoff = next(item for item in ledger.load_run(RUN_ID).artifacts if item.kind == "alignment-handoff")
    return ledger, brief, handoff


def test_compile_binds_alignment_handoff_parent(tmp_path: Path) -> None:
    ledger, brief, handoff = _seed_bound_fixture(tmp_path)
    compiler = CanonicalBlueprintTargetCompiler(ledger)
    target = compiler.compile(
        round_id=RUN_ID,
        target_id="blueprint-target",
        working_brief=brief,
        slots=_blueprint_document()["slots"],
        change=_blueprint_document()["change"],
        alignment_handoff=handoff,
        expected_revision=ledger.get_revision(RUN_ID),
    )
    parent_ids = {ref.artifact_id for ref in target.parent_refs}
    assert {"working-brief", "intent-model", handoff.id} <= parent_ids


def test_compile_rejects_foreign_handoff(tmp_path: Path) -> None:
    from research_tree.domain import ArtifactRevision

    ledger, brief, _handoff = _seed_bound_fixture(tmp_path)
    compiler = CanonicalBlueprintTargetCompiler(ledger)
    stranger = ArtifactRevision.create(
        artifact_id="not-a-handoff",
        round_id=RUN_ID,
        revision=1,
        kind="alignment-handoff",
        payload={"confirmed": True},
        parent_refs=(),
    )
    with pytest.raises(Exception, match="alignment-handoff"):
        compiler.compile(
            round_id=RUN_ID,
            target_id="blueprint-target",
            working_brief=brief,
            slots=_blueprint_document()["slots"],
            change=_blueprint_document()["change"],
            alignment_handoff=stranger,
            expected_revision=ledger.get_revision(RUN_ID),
        )


def test_cli_initialize_unconfirmed_alignment_is_named_error(capsys, workspace: Path) -> None:
    """HIGH-1: an unconfirmed alignment graph surfaces as a named rt:error, never a traceback."""

    _prepare_run(capsys, workspace)
    docs = _write_docs(workspace)
    rc = cli_main(
        [
            "initialize",
            *_common_args(workspace),
            "--brief",
            str(docs["brief"]),
            "--blueprint",
            str(docs["blueprint"]),
        ]
    )
    out = capsys.readouterr().out
    assert rc == 2, out
    assert "<rt:error" in out
    assert '"code": "alignment_not_confirmed"' in out
    assert '"category": "invalid_input"' in out
    assert '"retryability": false' in out
    assert "Traceback" not in out
    assert "sqlite" not in out.lower()


def test_cli_initialize_retry_is_convergence_safe(capsys, workspace: Path) -> None:
    """HIGH-2: an identical initialize retry must leave the ledger byte-identical."""

    _prepare_run(capsys, workspace)
    _confirm_alignment_graph(workspace)
    docs = _write_docs(workspace)
    initialize_args = (
        "initialize",
        *_common_args(workspace),
        "--brief",
        str(docs["brief"]),
        "--blueprint",
        str(docs["blueprint"]),
        "--frame",
        str(docs["frame"]),
        "--idempotency-key",
        "init-retry",
    )
    rc, payload = run_cli(capsys, *initialize_args)
    assert rc == 0, payload
    ledger = RunLedger(workspace)
    revision_before = ledger.get_revision(RUN_ID)
    count_before = len(ledger.load_run(RUN_ID).artifacts)

    rc, payload = run_cli(capsys, *initialize_args)
    assert rc == 0, payload
    assert payload["run"]["authority_revision"] == revision_before
    assert ledger.get_revision(RUN_ID) == revision_before
    assert len(ledger.load_run(RUN_ID).artifacts) == count_before
    frames = [item for item in ledger.load_run(RUN_ID).artifacts if item.kind == "decision-frame"]
    assert len(frames) == 1


def test_cli_propose_requires_verification_id(capsys, workspace: Path) -> None:
    """M4: the alignment-verification document must carry an explicit id."""

    _prepare_run(capsys, workspace)
    _confirm_alignment_graph(workspace)
    docs = _write_docs(workspace)
    rc, _payload = run_cli(
        capsys,
        "initialize",
        *_common_args(workspace),
        "--brief",
        str(docs["brief"]),
        "--blueprint",
        str(docs["blueprint"]),
        "--frame",
        str(docs["frame"]),
    )
    assert rc == 0
    artifacts = RunLedger(workspace).load_run(RUN_ID).artifacts
    target = next(item for item in artifacts if item.kind == "blueprint-target")
    handoff = next(item for item in artifacts if item.kind == "alignment-handoff")
    frame = next(item for item in artifacts if item.kind == "decision-frame")
    projection = {
        "projection_id": "strategy-no-id",
        "run_id": RUN_ID,
        "decision_frame_ref": {"round_id": RUN_ID, "artifact_id": frame.id, "revision": frame.revision},
        "alignment_handoff_ref": {"round_id": RUN_ID, "artifact_id": handoff.id, "revision": handoff.revision},
        "target_ref": {"round_id": RUN_ID, "artifact_id": target.id, "revision": target.revision},
        "current_understanding": "Confirm the verification id gate.",
        "assumptions": ["receipts"],
        "decision_targets": [{"id": "decision-operator-cli", "oracle_ids": ["oracle-cli-confirmation"]}],
        "tracks": [{"id": "track-operator"}],
        "method_hypotheses": [{"method": "operator-cli-chain"}],
        "depth": "deep",
        "evidence_expectations": ["canonical receipts"],
        "autonomy_envelope": {"allowed": ["research"], "authority": "research_owner"},
        "replanning_policy": {"same_round": ["depth"]},
        "success_oracles": [{"id": "oracle-cli-confirmation", "evidence_standard_ids": ["standard-cli"]}],
        "delivery_contract": {"technical": "package", "human": "report"},
        "stop_rule": "the confirmed strategy satisfies the oracle",
        "preference_influences": [],
        "revision": 1,
        "status": "draft",
    }
    projection_path = workspace / "docs" / "projection-no-id.json"
    projection_path.write_text(json.dumps(projection), encoding="utf-8")
    verification = {
        "schema": 1,
        "round_id": RUN_ID,
        "projection_ref": {"round_id": RUN_ID, "artifact_id": "strategy-no-id", "revision": 1},
        "authority_fingerprint": "computed-by-the-cli",
        "verifier_identity": "agent-verifier-support",
        "session_context": "session-main",
        "understood": {
            "outcome": "Independently restated outcome.",
            "scope": "Independently restated scope.",
            "authority": "Independently restated authority.",
            "success_oracles": [{"id": "oracle-cli-confirmation", "understanding": "Restated."}],
        },
        "discrepancies": [],
    }
    verification_path = workspace / "docs" / "verification-no-id.json"
    verification_path.write_text(json.dumps(verification), encoding="utf-8")
    rc, payload = run_cli(
        capsys,
        "strategy",
        *_common_args(workspace),
        "propose",
        "--projection",
        str(projection_path),
        "--alignment-verification",
        str(verification_path),
    )
    assert rc == 2, payload
    assert payload["code"] == "alignment_verification_id_required"


def test_cli_operating_model_json_envelope_is_consistent(capsys, workspace: Path) -> None:
    """M1: the --json envelope derives status from run state and carries the revision."""

    _prepare_run(capsys, workspace)
    rc, payload = run_cli(capsys, "operating-model", "--json", *_common_args(workspace))
    assert rc == 0, payload
    assert payload["status"] == "prepared"
    assert isinstance(payload["run"]["authority_revision"], int)
    assert payload["readiness"]["ready"] is False
    assert payload["readiness"]["failure_reasons"] == ["run_not_initialized"]
