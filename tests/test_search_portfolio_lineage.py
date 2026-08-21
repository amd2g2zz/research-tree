from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from research_tree import ContentAddressedStore, DurableSourceCaptureService
from research_tree.coordinator import ResearchRunCoordinator
from research_tree.domain import ArtifactRef
from research_tree.feedback import CorrectionBinding, CorrectionEvent
from research_tree.host_events import HostEvent, payload_digest
from research_tree.run_ledger import RunLedger
from research_tree.search_portfolio import (
    BatchCoverageAssessment,
    MethodExecutionOutcome,
    MethodSelection,
    PortfolioBatch,
    PortfolioExecution,
    ReassessmentPolicy,
    SearchPortfolio,
    Subquestion,
)
from strategy_support import confirm_strategy


def _coordinator(tmp_path):
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-portfolio")
    intent = ledger.append_artifact(
        "run-portfolio",
        "intent-1",
        "intent-model",
        {"task_id": "task-1"},
        expected_revision=ledger.get_revision("run-portfolio"),
    )
    brief = ledger.append_artifact(
        "run-portfolio",
        "brief-1",
        "working-brief",
        {"task_id": "task-1", "domain_id": "domain-1"},
        parent_refs=(ArtifactRef("run-portfolio", intent.id, intent.revision),),
        expected_revision=ledger.get_revision("run-portfolio"),
    )
    strategy = ledger.append_artifact(
        "run-portfolio",
        "strategy-1",
        "research-strategy",
        {"subject": "portfolio lineage"},
        parent_refs=(ArtifactRef("run-portfolio", brief.id, brief.revision),),
        expected_revision=ledger.get_revision("run-portfolio"),
    )
    handoff = ledger.append_artifact(
        "run-portfolio",
        "handoff-1",
        "alignment-handoff",
        {"confirmed": True, "strategy_digest": strategy.content_hash},
        parent_refs=(ArtifactRef("run-portfolio", strategy.id, strategy.revision),),
        expected_revision=ledger.get_revision("run-portfolio"),
    )
    target = ledger.append_artifact(
        "run-portfolio",
        "target-1",
        "blueprint-target",
        {"decision_slots": [{"id": "slot-1", "priority": "P0"}]},
        parent_refs=(ArtifactRef("run-portfolio", handoff.id, handoff.revision),),
        expected_revision=ledger.get_revision("run-portfolio"),
    )
    coordinator = ResearchRunCoordinator(ledger)
    coordinator.initialize(
        run_id="run-portfolio",
        alignment_handoff=handoff,
        blueprint_target=target,
        expected_revision=ledger.get_revision("run-portfolio"),
    )
    confirm_strategy(ledger, coordinator, "run-portfolio")
    coordinator.dispatch(
        run_id="run-portfolio",
        work_item={"objective": "test the portfolio", "success_oracle": "oracle-1", "portfolio_id": "portfolio-1"},
        worker_id="worker-1",
        expected_revision=ledger.get_revision("run-portfolio"),
        attempt_id="attempt-1",
    )
    return (
        ledger,
        coordinator,
        {
            "intent_model": intent,
            "working_brief": brief,
            "strategy": strategy,
            "handoff": handoff,
            "decision_map": target,
        },
    )


def _parents(artifacts: dict[str, object]) -> dict[str, ArtifactRef]:
    return {
        "intent_ref": ArtifactRef("run-portfolio", artifacts["intent_model"].id, artifacts["intent_model"].revision),
        "brief_ref": ArtifactRef("run-portfolio", artifacts["working_brief"].id, artifacts["working_brief"].revision),
        "strategy_ref": ArtifactRef("run-portfolio", artifacts["strategy"].id, artifacts["strategy"].revision),
        "decision_map_ref": ArtifactRef(
            "run-portfolio", artifacts["decision_map"].id, artifacts["decision_map"].revision
        ),
    }


def _pivot_correction(artifacts: dict[str, object]) -> CorrectionEvent:
    bindings = {role: CorrectionBinding.from_artifact(role, artifact) for role, artifact in artifacts.items()}
    return CorrectionEvent.create(
        event_id="portfolio-pivot-correction",
        run_id="run-portfolio",
        kind="correction",
        actor="human",
        reason="The portfolio contradiction changes the strategy.",
        relation="supersedes",
        task_id="task-1",
        domain_id="domain-1",
        successor_task_id="task-1",
        successor_domain_id="domain-2",
        affected=bindings,
    )


def _append(ledger: RunLedger, artifact_id: str, kind: str, payload: dict, parents=()):
    return ledger.append_artifact(
        "run-portfolio",
        artifact_id,
        kind,
        payload,
        parent_refs=parents,
        expected_revision=ledger.get_revision("run-portfolio"),
    )


def durable_evidence(tmp_path: Path, ledger: RunLedger) -> tuple[ArtifactRef, ArtifactRef, ArtifactRef, ArtifactRef]:
    service = DurableSourceCaptureService(ledger, ContentAddressedStore(tmp_path / "capture-store"))
    capture = service.capture(
        run_id="run-portfolio",
        capture_id="capture-1",
        attempt_id="attempt-1",
        data=b"portfolio source",
        media_type="text/plain",
        method_id="web-search",
        provider_id="provider-a",
        expected_revision=ledger.get_revision("run-portfolio"),
    )
    receipt = service.receipt(
        run_id="run-portfolio",
        receipt_id="receipt-1",
        capture=capture,
        attempt_id="attempt-1",
        method_id="web-search",
        provider_id="provider-a",
        expected_revision=ledger.get_revision("run-portfolio"),
    )
    checkpoint = service.checkpoint(
        run_id="run-portfolio",
        checkpoint_id="checkpoint-1",
        attempt_id="attempt-1",
        action_id="action-1",
        source_capture_refs=(capture.artifact_ref,),
        facts=({"statement": "portfolio evidence", "evidence_refs": ["capture-1"]},),
        expected_revision=ledger.get_revision("run-portfolio"),
    )
    finding = _append(
        ledger,
        "finding-1",
        "finding-pack",
        {"attempt_id": "attempt-1", "status": "committed"},
        (checkpoint.artifact_ref,),
    )
    return (
        capture.artifact_ref,
        receipt.artifact_ref,
        checkpoint.artifact_ref,
        ArtifactRef("run-portfolio", finding.id, finding.revision),
    )


def _values(*, disposition: str = "stop", authority: str = "inside_confirmed_authority"):
    portfolio = SearchPortfolio(
        portfolio_id="portfolio-1",
        run_id="run-portfolio",
        slot_id="slot-1",
        intent_revision="intent-1",
        brief_revision="brief-1",
        subquestions=(Subquestion("question-1", "Which mechanism decides?", "implicit", "p1"),),
        selected_methods=(MethodSelection("web-search", "provider-a", "provider-a", ("query-1",), "primary-coverage"),),
        rejected_methods=(),
        reassessment_policy=ReassessmentPolicy(True, ("deepen", "validate")),
        status="active",
    )
    outcome = MethodExecutionOutcome(
        outcome_id="outcome-1",
        portfolio_id="portfolio-1",
        batch_id="batch-1",
        method_id="web-search",
        provider_id="provider-a",
        failure_boundary="provider-a",
        selection_reason="primary-coverage",
        disposition="captured",
        query_refs=("query-1",),
        capture_refs=("capture-1",),
        receipt_refs=("receipt-1",),
        checkpoint_refs=("checkpoint-1",),
        coverage="complete",
        novelty="new",
        source_quality="high",
        source_depth="full-source",
        unresolved_decision_risk="low",
    )
    assessment = BatchCoverageAssessment(
        assessment_id="assessment-1",
        portfolio_id="portfolio-1",
        batch_id="batch-1",
        coverage="complete",
        novelty="new",
        source_depth="full-source",
        provenance_independence="single-boundary",
        contradictions=("the initial mechanism is false",) if disposition == "pivot" else (),
        implementation_uncertainty="low",
        oracle_readiness="ready",
        unresolved_decision_risk="low",
        disposition=disposition,
        causal_refs=("outcome-1",),
        next_actions=("revise the research plan",),
        capture_refs=("capture-1",),
        receipt_refs=("receipt-1",),
        checkpoint_refs=("checkpoint-1",),
        authority_disposition=authority,
        superseded_strategy_revision="strategy-1" if disposition == "pivot" else None,
        successor_strategy_revision="strategy-2" if disposition == "pivot" else None,
        evidence_disposition="captured",
        source_quality="high",
        method_outcome_refs=("outcome-1",),
        decision_slot_id="slot-1",
        attempt_id="attempt-1",
    )
    return portfolio, PortfolioExecution(
        "portfolio-1",
        (PortfolioBatch("batch-1", "portfolio-1", (outcome,)),),
        (assessment,),
        (),
        False,
    )


def worker_finished_event(
    ledger: RunLedger,
    capture: ArtifactRef,
    receipt: ArtifactRef,
    checkpoint: ArtifactRef,
    finding: ArtifactRef,
    *,
    lineage: ArtifactRef | None = None,
    event_id: str = "finished-1",
) -> HostEvent:
    payload = {
        "outcome": "success",
        "capture_refs": [capture.to_dict()],
        "receipt_refs": [receipt.to_dict()],
        "checkpoint_ref": checkpoint.to_dict(),
        "finding_refs": [finding.to_dict()],
        "produced_artifact_refs": [],
    }
    if lineage is not None:
        payload["portfolio_lineage_ref"] = lineage.to_dict()
    return HostEvent.from_value(
        {
            "event_id": event_id,
            "kind": "worker_finished",
            "run_id": "run-portfolio",
            "attempt_id": "attempt-1",
            "expected_revision": ledger.get_revision("run-portfolio"),
            "sequence": 1,
            "actor": "worker-1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
            "payload_digest": payload_digest(payload),
        }
    )
