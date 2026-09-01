"""Track B alignment-chain supplement tests (#468, senior-user-ux-v2).

Mirrors tests/test_v2_evaluation.py: one module-scoped governed run over a
temporary workspace, then contract assertions on the canonical receipt and the
artifacts it leaves in the ledger.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evaluation" / "harness"))

from v2_alignment_chain import RUN_ID, run_alignment_chain_supplement  # noqa: E402

from research_tree import RunLedger  # noqa: E402
from research_tree.domain import thaw_json  # noqa: E402


@pytest.fixture(scope="module")
def receipt(tmp_path_factory):
    workspace = tmp_path_factory.mktemp("v2-alignment-chain") / "workspace"
    return workspace, run_alignment_chain_supplement(workspace)


def test_alignment_chain_completes_end_to_end(receipt):
    _workspace, payload = receipt
    assert payload["schema_version"] == 1
    assert payload["case_id"] == "senior-user-ux-v2-track-b-alignment-chain"
    assert payload["run_id"] == RUN_ID
    assert payload["status"] == "passed"
    assert payload["blocker"] is None


def test_every_chain_stage_ok(receipt):
    _workspace, payload = receipt
    stages = payload["chain_stages"]
    assert stages, "chain stages must be recorded"
    assert all(stage["ok"] is True for stage in stages), [s for s in stages if not s["ok"]]
    names = [stage["stage"] for stage in stages]
    # The full mechanical chain, in drive order.
    assert names == [
        "intake",
        "intent_model_question",
        "intent_model_resolution",
        "working_brief",
        "alignment_graph_confirmation",
        "handoff_compilation",
        "blueprint_target_compile",
        "coordinator_initialization_bind",
        "coordinator_initialization",
        "strategy_projection_display",
        "strategy_confirmation_tamper",
        "strategy_confirmation",
        "work_item",
        "finding_pack_evidence",
        "finding_pack",
        "decision_convergence",
        "delivery_compilation",
        "delivery_acceptance",
    ]
    # The compiled handoff binds the alignment authority fields before the
    # strategy gates run: the handoff stage detail records the persisted
    # objective, and the stage that precedes confirmation records the
    # clarification question the requester answered.
    handoff_stage = next(stage for stage in stages if stage["stage"] == "handoff_compilation")
    assert "objective=" in handoff_stage["detail"]
    question_stage = next(stage for stage in stages if stage["stage"] == "intent_model_question")
    assert question_stage["detail"].startswith("clarifying question emitted:")


def test_tampered_confirmation_rejected_with_named_reason(receipt):
    _workspace, payload = receipt
    tamper = payload["tamper_rejection"]
    assert tamper["attempted"] is True
    assert tamper["canonical_reason"] == "authority_fingerprint_mismatch"
    # The graph-level digest gate rejects its own tamper attempt inside the
    # confirmation stage detail.
    graph_stage = next(stage for stage in payload["chain_stages"] if stage["stage"] == "alignment_graph_confirmation")
    assert "alignment graph changed after the displayed handoff draft" in graph_stage["detail"]


def test_delivery_payloads_are_non_trivial(receipt):
    workspace, payload = receipt
    delivery = payload["delivery_compile"]
    assert delivery["technical_lines"] >= 40
    assert delivery["human_lines"] >= 40
    assert isinstance(delivery["pair_digest"], str) and len(delivery["pair_digest"]) == 64
    # The payloads were compiled from real packs: the ledger's technical
    # package must name the real repository symbol the chain grounded.
    ledger = RunLedger(workspace)
    artifacts = ledger.load_run(RUN_ID).artifacts
    technical = next(item for item in artifacts if item.kind == "technical-research-package")
    human = next(item for item in artifacts if item.kind == "human-research-report")
    technical_markdown = thaw_json(technical.payload)["markdown"]
    human_markdown = thaw_json(human.payload)["markdown"]
    assert "src/research_tree/alignment_handoff.py" in technical_markdown
    assert "initialize_research_from_alignment" in technical_markdown
    assert "initialize_research_from_alignment" in human_markdown
    finding = next(
        item
        for item in artifacts
        if item.kind == "finding-pack" and item.payload.get("work_item_id") == "work-alignment-chain"
    )
    assessments = thaw_json(finding.payload)["claim_assessments"]
    assert [entry["state"] for entry in assessments] == ["corroborated"]
