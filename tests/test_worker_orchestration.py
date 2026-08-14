from pathlib import Path
from datetime import datetime, timezone

import pytest

from research_tree import (
    ArtifactRef,
    CaptureIncompleteError,
    ContentAddressedStore,
    DurableSourceCaptureService,
    HostEvent,
    MethodExecutionOutcome,
    MethodRegistry,
    MethodRegistration,
    MethodSelection,
    PortfolioBatch,
    ReassessmentPolicy,
    SearchPortfolio,
    SearchPortfolioService,
    Subquestion,
    RunLedger,
    assess_acquisition_batch,
)
from research_tree.coordinator import ResearchRunCoordinator


def test_worker_finished_requires_checkpoint(tmp_path: Path) -> None:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-1")
    service = DurableSourceCaptureService(ledger, ContentAddressedStore(tmp_path))
    with pytest.raises(CaptureIncompleteError, match="capture_incomplete"):
        service.validate_worker_finished(run_id="run-1", attempt_id="attempt-a", capture_refs=(), checkpoint_ref=None)


def test_worker_finished_requires_current_committed_capture_and_checkpoint_lineage(tmp_path: Path) -> None:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-2")
    service = DurableSourceCaptureService(ledger, ContentAddressedStore(tmp_path))
    capture = service.capture(
        run_id="run-2",
        capture_id="capture-2",
        attempt_id="attempt-2",
        data=b"durable evidence",
        media_type="text/plain",
        method_id="web-search",
        provider_id="provider-a",
        expected_revision=ledger.get_revision("run-2"),
    )
    checkpoint = service.checkpoint(
        run_id="run-2",
        checkpoint_id="checkpoint-2",
        attempt_id="attempt-2",
        action_id="action-2",
        source_capture_refs=(capture.artifact_ref,),
        facts=({"claim": "evidence is durable"},),
        expected_revision=ledger.get_revision("run-2"),
    )

    accepted = service.validate_worker_finished(
        run_id="run-2",
        attempt_id="attempt-2",
        capture_refs=(capture.artifact_ref,),
        checkpoint_ref=checkpoint.artifact_ref,
    )
    assert accepted["status"] == "accepted"

    superseded = ledger.append_artifact(
        "run-2",
        capture.capture_id,
        "source-capture",
        {**capture.to_dict(), "status": "superseded"},
        parent_refs=(capture.artifact_ref,),
        expected_revision=ledger.get_revision("run-2"),
    )
    assert superseded.payload["status"] == "superseded"
    with pytest.raises(CaptureIncompleteError, match="capture_incomplete"):
        service.validate_worker_finished(
            run_id="run-2",
            attempt_id="attempt-2",
            capture_refs=(capture.artifact_ref,),
            checkpoint_ref=checkpoint.artifact_ref,
        )


def test_acquisition_worker_finish_requires_canonical_recorded_assessment(tmp_path: Path) -> None:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-3")
    handoff = ledger.append_artifact(
        "run-3",
        "handoff-3",
        "alignment-handoff",
        {"confirmed": True},
        expected_revision=ledger.get_revision("run-3"),
    )
    target = ledger.append_artifact(
        "run-3",
        "target-3",
        "blueprint-target",
        {"decision_slots": [{"id": "slot-3"}]},
        parent_refs=(ArtifactRef("run-3", handoff.id, handoff.revision),),
        expected_revision=ledger.get_revision("run-3"),
    )
    coordinator = ResearchRunCoordinator(ledger)
    coordinator.initialize(
        run_id="run-3",
        alignment_handoff=handoff,
        blueprint_target=target,
        expected_revision=ledger.get_revision("run-3"),
    )
    registry = MethodRegistry(
        registry_id="registry-3",
        registrations=(
            MethodRegistration(
                method_id="web-search",
                provider_id="provider-a",
                capability="web-search",
                failure_boundary="provider-a-boundary",
                availability="available",
            ),
        ),
    )
    service = SearchPortfolioService(ledger)
    registry_artifact = service.register_methods(
        run_id="run-3",
        registry=registry,
        expected_revision=ledger.get_revision("run-3"),
    )
    portfolio = SearchPortfolio(
        portfolio_id="portfolio-3",
        run_id="run-3",
        slot_id="slot-3",
        intent_revision="intent-3",
        brief_revision="brief-3",
        subquestions=(Subquestion("subquestion-3", "What is the boundary?", "explicit", "p0"),),
        selected_methods=(
            MethodSelection(
                method_id="web-search",
                provider_id="provider-a",
                failure_boundary="provider-a-boundary",
                query_refs=("query-3",),
                selection_reason="primary-coverage",
            ),
        ),
        rejected_methods=(),
        reassessment_policy=ReassessmentPolicy(after_batch=True, allowed_dispositions=("validate",)),
        status="active",
    )
    portfolio_payload = {
        **portfolio.to_dict(),
        "run_id": "run-3",
        "status": "active",
        "method_registry_ref": ArtifactRef("run-3", registry_artifact.id, registry_artifact.revision).to_dict(),
        "lineage": {
            "strategy_ref": ArtifactRef("run-3", target.id, target.revision).to_dict(),
            "decision_map_ref": ArtifactRef("run-3", target.id, target.revision).to_dict(),
        },
        "query_variants": [
            {"query_ref": "query-3", "query_id": "query-3", "method_id": "web-search", "provider_id": "provider-a"}
        ],
        "method_selection": [{**portfolio.selected_methods[0].to_dict(), "status": "accepted"}],
    }
    portfolio_artifact = ledger.append_artifact(
        "run-3",
        "portfolio-3",
        "search-portfolio",
        portfolio_payload,
        parent_refs=(
            ArtifactRef("run-3", target.id, target.revision),
            ArtifactRef("run-3", registry_artifact.id, registry_artifact.revision),
        ),
        expected_revision=ledger.get_revision("run-3"),
    )
    lease = ledger.append_artifact(
        "run-3",
        "attempt-3",
        "attempt-lease",
        {
            "attempt_id": "attempt-3",
            "status": "active",
            "work_item": {
                "acquisition": True,
                "search_portfolio_ref": ArtifactRef(
                    "run-3", portfolio_artifact.id, portfolio_artifact.revision
                ).to_dict(),
                "query_id": "query-3",
                "method_id": "web-search",
            },
        },
        parent_refs=(ArtifactRef("run-3", portfolio_artifact.id, portfolio_artifact.revision),),
        expected_revision=ledger.get_revision("run-3"),
    )
    capture_service = DurableSourceCaptureService(ledger, ContentAddressedStore(tmp_path))
    capture = capture_service.capture(
        run_id="run-3",
        capture_id="capture-3",
        attempt_id=lease.id,
        data=b"canonical capture",
        media_type="text/plain",
        method_id="web-search",
        provider_id="provider-a",
        expected_revision=ledger.get_revision("run-3"),
    )
    receipt = capture_service.receipt(
        run_id="run-3",
        receipt_id="receipt-3",
        capture=capture,
        attempt_id=lease.id,
        method_id="web-search",
        provider_id="provider-a",
        expected_revision=ledger.get_revision("run-3"),
    )
    checkpoint = capture_service.checkpoint(
        run_id="run-3",
        checkpoint_id="checkpoint-3",
        attempt_id=lease.id,
        action_id="action-3",
        source_capture_refs=(capture.artifact_ref,),
        facts=({"claim": "capture is committed"},),
        expected_revision=ledger.get_revision("run-3"),
    )
    finding = ledger.append_artifact(
        "run-3",
        "finding-3",
        "finding-pack",
        {"attempt_id": lease.id, "status": "committed"},
        parent_refs=(checkpoint.artifact_ref,),
        expected_revision=ledger.get_revision("run-3"),
    )
    outcome = MethodExecutionOutcome(
        outcome_id="outcome-3",
        portfolio_id=portfolio.portfolio_id,
        batch_id="batch-3",
        method_id="web-search",
        provider_id="provider-a",
        failure_boundary="provider-a-boundary",
        selection_reason="primary-coverage",
        disposition="captured",
        query_refs=("query-3",),
        capture_refs=("capture-3@1",),
        receipt_refs=("receipt-3@1",),
        checkpoint_refs=("checkpoint-3@1",),
        coverage="complete",
        novelty="new",
        source_depth="full-source",
        source_quality="high",
        unresolved_decision_risk="low",
    )
    batch_artifact = service.record_batch(
        run_id="run-3",
        batch=PortfolioBatch("batch-3", portfolio.portfolio_id, (outcome,)),
        portfolio_ref=ArtifactRef("run-3", portfolio_artifact.id, portfolio_artifact.revision),
        finding_artifacts=(finding,),
        expected_revision=ledger.get_revision("run-3"),
    )
    assessment = service.record_assessment(
        run_id="run-3",
        assessment=assess_acquisition_batch(
            assessment_id="assessment-3",
            portfolio_id=portfolio.portfolio_id,
            batch_id="batch-3",
            outcomes=(outcome,),
            decision_slot_id="slot-3",
            attempt_id=lease.id,
            disposition="stop",
            next_actions=("submit-for-closure-assessment",),
        ),
        portfolio_ref=ArtifactRef("run-3", portfolio_artifact.id, portfolio_artifact.revision),
        batch_ref=ArtifactRef("run-3", batch_artifact.id, batch_artifact.revision),
        capture_artifacts=(ledger.get_artifact(capture.artifact_ref),),
        receipt_artifacts=(ledger.get_artifact(receipt.artifact_ref),),
        checkpoint_artifacts=(ledger.get_artifact(checkpoint.artifact_ref),),
        finding_artifacts=(finding,),
        expected_revision=ledger.get_revision("run-3"),
    )
    output = ledger.append_artifact(
        "run-3",
        "output-3",
        "analysis-output",
        {"attempt_id": lease.id, "status": "committed"},
        expected_revision=ledger.get_revision("run-3"),
    )
    event_payload = {
        "outcome": {"assessment_ref": ArtifactRef("run-3", assessment.id, assessment.revision).to_dict()},
        "capture_refs": [capture.artifact_ref.to_dict()],
        "receipt_refs": [receipt.artifact_ref.to_dict()],
        "checkpoint_ref": checkpoint.artifact_ref.to_dict(),
        "finding_refs": [
            finding.artifact_ref.to_dict()
            if hasattr(finding, "artifact_ref")
            else ArtifactRef("run-3", finding.id, finding.revision).to_dict()
        ],
        "produced_artifact_refs": [ArtifactRef("run-3", output.id, output.revision).to_dict()],
    }
    event = HostEvent.from_value(
        {
            "event_id": "worker-finished-3",
            "kind": "worker_finished",
            "run_id": "run-3",
            "attempt_id": lease.id,
            "expected_revision": ledger.get_revision("run-3"),
            "sequence": 1,
            "actor": "codex",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "payload": event_payload,
        }
    )

    accepted = coordinator.ingest_host_event(event)
    assert accepted.payload["kind"] == "worker_finished"
