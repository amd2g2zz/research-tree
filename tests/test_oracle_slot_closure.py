from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from research_tree.closure import ASSESSMENT_KIND, ClosureAssessmentError, SlotClosureAssessment, SlotClosureAssessor
from research_tree.content_store import ContentAddressedStore
from research_tree.domain import ArtifactRef, thaw_json
from research_tree.evidence import EVIDENCE_ARTIFACT_KIND, EvidenceAnchor, EvidenceArtifact, EvidenceRepository
from research_tree.oracles import (
    ORACLE_ATTEMPT_KIND,
    ORACLE_RUN_KIND,
    ORACLE_SPEC_KIND,
    OracleRun,
    OracleService,
    OracleSpec,
)
from research_tree.run_ledger import RunLedger
from research_tree.source_capture import (
    ACQUISITION_RECEIPT_KIND,
    SOURCE_CAPTURE_KIND,
    AcquisitionReceipt,
    DurableSourceCaptureService,
    SourceCapture,
)

RUN_ID = "run-oracle"
CAPTURED_AT = "2026-08-13T00:00:00+00:00"
ROOT = Path(__file__).resolve().parents[1]


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _ref(item) -> ArtifactRef:
    return ArtifactRef(item.round_id, item.id, item.revision)


def _append(ledger: RunLedger, artifact_id: str, kind: str, payload: dict, parents=(), *, round_id: str = RUN_ID):
    return ledger.append_artifact(
        round_id,
        artifact_id,
        kind,
        payload,
        parent_refs=parents,
        expected_revision=ledger.get_revision(round_id),
    )


def _service(tmp_path):
    ledger = RunLedger(tmp_path)
    ledger.create_run(RUN_ID)
    return ledger, OracleService(ledger)


def _spec() -> OracleSpec:
    return OracleSpec(
        oracle_spec_id="oracle-spec-1",
        version=1,
        objective="verify generated artifact",
        input_schema_digest=_digest("input-schema"),
        invocation_adapter="pytest",
        permissions={"read_roots": ["workspace"], "write_roots": [], "network": "none", "commands": ["pytest"]},
        resource_limits={"cpu_seconds": 60, "memory_bytes": 1024, "output_bytes": 4096},
        timeout_seconds=60,
        expected_result_schema_digest=_digest("result-schema"),
        retry_policy={"max_attempts": 2, "backoff_seconds": [0, 1], "switch_method_after": 2},
        flaky_policy="repeat_once_then_inconclusive",
        isolation_profile="sandbox",
        human_only=False,
    )


def _oracle_run(
    service: OracleService,
    ledger: RunLedger,
    *,
    verdict: str = "passed",
    input_refs: tuple[ArtifactRef, ...] | None = None,
):
    if input_refs is None:
        input_artifact = _append(ledger, "input-1", "input", {"value": "current"})
        input_refs = (_ref(input_artifact),)
    result_artifact = _append(ledger, "result-1", "result", {"value": "ok"})
    event_artifact = _append(ledger, "event-1", "tool-event", {"exit": 0})
    spec = service.create_spec(
        round_id=RUN_ID,
        spec_id="oracle-spec-1",
        spec=_spec(),
        expected_revision=ledger.get_revision(RUN_ID),
    )
    attempt = service.start_attempt(
        round_id=RUN_ID,
        attempt_id="oracle-attempt-1",
        spec=spec,
        input_refs=input_refs,
        method="pytest",
        environment_digest=_digest("environment"),
        expected_revision=ledger.get_revision(RUN_ID),
    )
    run = service.record_run(
        round_id=RUN_ID,
        run=OracleRun(
            oracle_run_id="oracle-run-1",
            oracle_spec_ref=_ref(spec),
            attempt_ref=_ref(attempt),
            input_refs=input_refs,
            method="pytest",
            environment_digest=_digest("environment"),
            toolchain_digest=_digest("toolchain"),
            tool_event_refs=(_ref(event_artifact),),
            result_artifact_refs=(_ref(result_artifact),),
            verdict=verdict,
            exit_code=0 if verdict == "passed" else 1,
            timed_out=False,
            evaluator="independent-evaluator",
            limitations=(),
            reproducibility_status="reproducible",
        ),
        expected_revision=ledger.get_revision(RUN_ID),
    )
    return spec, attempt, run


def _source_graph(
    ledger: RunLedger,
    *,
    capture_id: str,
    evidence_id: str,
    attempt_id: str,
    origin_capture_id: str | None = None,
    forged_capture: bool = False,
    forged_evidence: bool = False,
    round_id: str = RUN_ID,
    method_id: str = "web-fetch",
    provider_id: str = "fixture-provider",
    provenance_group: str = "fixture-source",
):
    store = ContentAddressedStore(ledger.workspace)
    capture_data = f"capture:{capture_id}".encode()
    if forged_capture:
        capture_content = store.ingest(capture_data, "text/plain")
        capture = _append(
            ledger,
            capture_id,
            SOURCE_CAPTURE_KIND,
            SourceCapture(
                capture_id=capture_id,
                run_id=round_id,
                attempt_id=attempt_id,
                locator={"url": f"https://{capture_id}.test/report"},
                content_digest=capture_content.digest,
                media_type=capture_content.media_type,
                size_bytes=capture_content.byte_size,
                captured_at=CAPTURED_AT,
                method_id=method_id,
                provider_id=provider_id,
                provenance_group=provenance_group,
                origin_capture_id=origin_capture_id,
            ).to_dict(),
            round_id=round_id,
        )
        receipt = _append(
            ledger,
            f"receipt-{capture_id}",
            ACQUISITION_RECEIPT_KIND,
            AcquisitionReceipt(
                receipt_id=f"receipt-{capture_id}",
                capture_id=capture_id,
                attempt_id=attempt_id,
                method_id=method_id,
                provider_id=provider_id,
                requested_at=CAPTURED_AT,
                completed_at=CAPTURED_AT,
                status="succeeded",
            ).to_dict(),
            (_ref(capture),),
            round_id=round_id,
        )
    else:
        capture_service = DurableSourceCaptureService(ledger, store)
        capture_value = capture_service.capture(
            run_id=round_id,
            capture_id=capture_id,
            attempt_id=attempt_id,
            data=capture_data,
            media_type="text/plain",
            method_id=method_id,
            provider_id=provider_id,
            provenance_group=provenance_group,
            locator={"url": f"https://{capture_id}.test/report"},
            origin_capture_id=origin_capture_id,
            expected_revision=ledger.get_revision(round_id),
        )
        assert capture_value.artifact_ref is not None
        capture = ledger.get_artifact(capture_value.artifact_ref)
        receipt_value = capture_service.receipt(
            run_id=round_id,
            receipt_id=f"receipt-{capture_id}",
            capture=capture_value,
            attempt_id=attempt_id,
            method_id=method_id,
            provider_id=provider_id,
            expected_revision=ledger.get_revision(round_id),
        )
        assert receipt_value.artifact_ref is not None
        receipt = ledger.get_artifact(receipt_value.artifact_ref)

    evidence_content = store.ingest(f"evidence:{evidence_id}".encode(), "text/plain")
    evidence_value = EvidenceArtifact(
        evidence_id=evidence_id,
        run_id=round_id,
        revision=1,
        media_type=evidence_content.media_type,
        locator={"url": f"https://{capture_id}.test/report"},
        content_digest=evidence_content.digest,
        size_bytes=evidence_content.byte_size,
        acquired_at=CAPTURED_AT,
        acquisition_method=method_id,
        provenance_group=provenance_group,
        applicability="direct support",
        confidence="high",
        limitations=(),
        status="active",
        extractor_version="fixture-reader",
        evidence_class="source",
    )
    if forged_evidence:
        evidence = _append(
            ledger,
            evidence_id,
            EVIDENCE_ARTIFACT_KIND,
            evidence_value.to_dict(),
            (_ref(receipt),),
            round_id=round_id,
        )
    else:
        evidence_ref = EvidenceRepository(ledger, store).record(
            evidence_value,
            evidence_content,
            expected_run_revision=ledger.get_revision(round_id),
            parent_refs=(_ref(receipt),),
        )
        evidence = ledger.get_artifact(evidence_ref)
    return evidence, EvidenceAnchor(
        artifact_ref=_ref(evidence),
        artifact_digest=evidence_value.content_digest,
        artifact_revision=evidence.revision,
        selector_type="line",
        selector_value={"start": 1, "end": 1},
        extractor_version="fixture-reader",
        applicability="direct support",
        confidence="high",
        limitations=(),
    )


def _finding(
    ledger: RunLedger,
    *,
    finding_id: str,
    target,
    anchor: EvidenceAnchor,
    effect: str,
    option: str = "a",
    slot_id: str = "slot-1",
):
    assert anchor.artifact_ref is not None
    return _append(
        ledger,
        finding_id,
        "finding-pack",
        {
            "blueprint_target_id": target.id,
            "decision_slot_id": slot_id,
            "evidence_mode": "strict",
            "observations": [{"anchor": anchor.to_dict()}],
            "option_effects": [{"option": option, "effect": effect}],
        },
        (_ref(target), anchor.artifact_ref),
    )


def _assessment_inputs(
    ledger: RunLedger,
    *,
    forgery: str | None = None,
    hidden_contradiction: bool = False,
    include_origin: bool = False,
    independent: bool = False,
    independent_provenance_group: str = "fixture-independent",
    contradiction_option: str = "a",
    target_slot_id: str = "slot-1",
    decision_slot_id: str = "slot-1",
    decision_status: str = "selected",
    selected_option: str | None = "a",
):
    target = _append(
        ledger,
        "target-1",
        "blueprint-target",
        {"slots": [{"id": target_slot_id, "priority": "P0", "alternatives": ["a", "b"]}]},
    )
    if forgery == "origin":
        forged_origin_content = ContentAddressedStore(ledger.workspace).ingest(b"forged-origin", "text/plain")
        _append(
            ledger,
            "capture-origin",
            SOURCE_CAPTURE_KIND,
            SourceCapture(
                capture_id="capture-origin",
                run_id=RUN_ID,
                attempt_id="attempt-origin",
                locator={"url": "https://origin.test/report"},
                content_digest=forged_origin_content.digest,
                media_type=forged_origin_content.media_type,
                size_bytes=forged_origin_content.byte_size,
                captured_at=CAPTURED_AT,
                method_id="web-fetch",
                provider_id="fixture-provider",
                provenance_group="fixture-origin",
            ).to_dict(),
        )
    elif include_origin:
        _source_graph(
            ledger,
            capture_id="capture-origin",
            evidence_id="evidence-origin",
            attempt_id="attempt-origin",
        )
    evidence, anchor = _source_graph(
        ledger,
        capture_id="capture-support",
        evidence_id="evidence-support",
        attempt_id="attempt-support",
        origin_capture_id="capture-origin" if forgery == "origin" or include_origin else None,
        forged_capture=forgery == "capture",
        forged_evidence=forgery == "evidence",
    )
    finding = _finding(
        ledger,
        finding_id="finding-support",
        target=target,
        anchor=anchor,
        effect="supports",
        slot_id=decision_slot_id,
    )
    findings = [finding]
    if independent:
        _, independent_anchor = _source_graph(
            ledger,
            capture_id="capture-independent",
            evidence_id="evidence-independent",
            attempt_id="attempt-independent",
            method_id="repository-read",
            provider_id="fixture-repository",
            provenance_group=independent_provenance_group,
        )
        findings.append(
            _finding(
                ledger,
                finding_id="finding-independent",
                target=target,
                anchor=independent_anchor,
                effect="supports",
                slot_id=decision_slot_id,
            )
        )
    if hidden_contradiction:
        _, contradiction_anchor = _source_graph(
            ledger,
            capture_id="capture-contradiction",
            evidence_id="evidence-contradiction",
            attempt_id="attempt-contradiction",
        )
        findings.append(
            _finding(
                ledger,
                finding_id="finding-contradiction",
                target=target,
                anchor=contradiction_anchor,
                effect="contradicts",
                option=contradiction_option,
                slot_id=decision_slot_id,
            )
        )
    decision = _append(
        ledger,
        "decision-1",
        "decision-ledger-entry",
        {
            "blueprint_target_id": target.id,
            "decision_slot_id": decision_slot_id,
            "status": decision_status,
            "selected_option": selected_option,
            "fallback": "use option b",
            "reversal_condition": "new counterevidence",
        },
        (
            _ref(target),
            *(_ref(item) for item in findings),
        ),
    )
    return target, decision, tuple(findings)


def _assess(assessor: SlotClosureAssessor, ledger: RunLedger, target, decision, findings, *, oracle_runs=(), **kwargs):
    return assessor.assess(
        round_id=RUN_ID,
        assessment_id=kwargs.pop("assessment_id", "assessment-1"),
        slot_id="slot-1",
        blueprint_target=target,
        decision=decision,
        findings=findings,
        oracle_runs=oracle_runs,
        evaluator_id=kwargs.pop("evaluator_id", "core-evaluator"),
        expected_revision=ledger.get_revision(RUN_ID),
        **kwargs,
    )


def test_oracle_artifacts_are_persisted_with_exact_lineage(tmp_path) -> None:
    ledger, service = _service(tmp_path)
    spec, attempt, run = _oracle_run(service, ledger)

    assert (spec.kind, attempt.kind, run.kind) == (
        ORACLE_SPEC_KIND,
        ORACLE_ATTEMPT_KIND,
        ORACLE_RUN_KIND,
    )
    assert _ref(spec) in attempt.parent_refs
    assert _ref(attempt) in run.parent_refs


def test_oracle_run_rejects_stale_or_cross_attempt_reference(tmp_path) -> None:
    ledger, service = _service(tmp_path)
    spec, attempt, _ = _oracle_run(service, ledger)
    with pytest.raises(ClosureAssessmentError, match="attempt"):
        service.record_run(
            round_id="run-oracle",
            run=OracleRun(
                oracle_run_id="bad-run",
                oracle_spec_ref=_ref(spec),
                attempt_ref=ArtifactRef(RUN_ID, attempt.id, attempt.revision + 1),
                input_refs=(),
                method="pytest",
                environment_digest=_digest("environment"),
                toolchain_digest=_digest("toolchain"),
                tool_event_refs=(),
                result_artifact_refs=(),
                verdict="passed",
                exit_code=0,
                timed_out=False,
                evaluator="independent-evaluator",
                limitations=(),
                reproducibility_status="reproducible",
            ),
            expected_revision=ledger.get_revision(RUN_ID),
        )


def test_forged_worker_pass_cannot_issue_closure_token(tmp_path) -> None:
    ledger, service = _service(tmp_path)
    target, decision, findings = _assessment_inputs(ledger)
    forged_run = _append(ledger, "oracle-run-forged", ORACLE_RUN_KIND, {"verdict": "passed"})
    assessor = SlotClosureAssessor(ledger, core_evaluator_id="core-evaluator")

    assessment = _assess(assessor, ledger, target, decision, findings, oracle_runs=(forged_run,))

    assert assessment.kind == ASSESSMENT_KIND
    assert assessment.payload["status"] == "inconclusive"
    assert assessment.payload["closure_token"] is None
    assert "validation" in assessment.payload["successor_kinds"]


def test_core_evaluator_issues_revision_bound_closure_token(tmp_path) -> None:
    ledger, service = _service(tmp_path)
    _, _, run = _oracle_run(service, ledger)
    target, decision, findings = _assessment_inputs(ledger, independent=True)
    assessor = SlotClosureAssessor(ledger, core_evaluator_id="core-evaluator")

    assessment = _assess(
        assessor, ledger, target, decision, findings, oracle_runs=(run,), assessment_id="assessment-passed"
    )

    assert assessment.payload["status"] == "passed"
    assert isinstance(assessment.payload["closure_token"], str)
    assert assessment.payload["closure_token"].startswith("closure-")
    assert SlotClosureAssessment.from_dict(assessment.payload).closure_token == assessment.payload["closure_token"]


def test_distinct_methods_do_not_substitute_for_independent_provenance(tmp_path) -> None:
    ledger, service = _service(tmp_path)
    _, _, run = _oracle_run(service, ledger)
    target, decision, findings = _assessment_inputs(
        ledger, independent=True, independent_provenance_group="fixture-source"
    )
    assessor = SlotClosureAssessor(ledger, core_evaluator_id="core-evaluator")

    for finding in findings:
        lineage = assessor._finding_evidence_lineage(finding, RUN_ID)
        assert lineage is not None
        assert lineage["provenance_groups"] == ["fixture-source"]

    assessment = _assess(assessor, ledger, target, decision, findings, oracle_runs=(run,))

    assert assessment.payload["status"] == "inconclusive"
    assert assessment.payload["checks"]["provenance_independence"] is False


def test_non_core_evaluator_cannot_manually_close_slot(tmp_path) -> None:
    ledger, service = _service(tmp_path)
    _, _, run = _oracle_run(service, ledger)
    target, decision, findings = _assessment_inputs(ledger)
    assessor = SlotClosureAssessor(ledger, core_evaluator_id="core-evaluator")

    with pytest.raises(ClosureAssessmentError, match="core evaluator"):
        _assess(assessor, ledger, target, decision, findings, oracle_runs=(run,), evaluator_id="worker-claims-close")


def test_deferred_decision_cannot_issue_a_closure_token(tmp_path) -> None:
    ledger, service = _service(tmp_path)
    _, _, run = _oracle_run(service, ledger)
    target, decision, findings = _assessment_inputs(
        ledger,
        decision_status="deferred",
        selected_option=None,
    )
    assessor = SlotClosureAssessor(ledger, core_evaluator_id="core-evaluator")

    with pytest.raises(ClosureAssessmentError, match="selected or conditional"):
        _assess(assessor, ledger, target, decision, findings, oracle_runs=(run,))


def test_decision_slot_must_exist_in_the_canonical_blueprint_target(tmp_path) -> None:
    ledger, service = _service(tmp_path)
    _, _, run = _oracle_run(service, ledger)
    target, decision, findings = _assessment_inputs(ledger, target_slot_id="other-slot")
    assessor = SlotClosureAssessor(ledger, core_evaluator_id="core-evaluator")

    with pytest.raises(ClosureAssessmentError, match="absent from the exact Blueprint Target"):
        _assess(assessor, ledger, target, decision, findings, oracle_runs=(run,))


def test_selected_option_must_belong_to_the_decision_slot(tmp_path) -> None:
    ledger, service = _service(tmp_path)
    _, _, run = _oracle_run(service, ledger)
    target, decision, findings = _assessment_inputs(ledger, selected_option="outside-slot")
    assessor = SlotClosureAssessor(ledger, core_evaluator_id="core-evaluator")

    with pytest.raises(ClosureAssessmentError, match="selected_option is absent from the Decision Slot"):
        _assess(assessor, ledger, target, decision, findings, oracle_runs=(run,))


def test_assessment_rejects_removed_caller_quality_arguments(tmp_path) -> None:
    ledger, service = _service(tmp_path)
    _, _, run = _oracle_run(service, ledger)
    target, decision, findings = _assessment_inputs(ledger)
    assessor = SlotClosureAssessor(ledger, core_evaluator_id="core-evaluator")

    with pytest.raises(TypeError, match="provenance_groups"):
        _assess(
            assessor,
            ledger,
            target,
            decision,
            findings,
            oracle_runs=(run,),
            provenance_groups=("claimed-one", "claimed-two"),
        )


def test_graph_derived_assessment_is_idempotent(tmp_path) -> None:
    ledger, service = _service(tmp_path)
    _, _, run = _oracle_run(service, ledger)
    target, decision, findings = _assessment_inputs(ledger, independent=True)
    assessor = SlotClosureAssessor(ledger, core_evaluator_id="core-evaluator")
    arguments = dict(
        oracle_runs=(run,),
        assessment_id="assessment-derived",
    )

    first = _assess(assessor, ledger, target, decision, findings, **arguments)
    replay = _assess(assessor, ledger, target, decision, findings, **arguments)

    assert first.payload["status"] == "passed"
    assert replay == first
    assert "provenance_groups" not in first.payload
    assert "counterevidence_disposition" not in first.payload
    assert "active_contradiction" not in first.payload


def test_selected_option_contradiction_requires_an_exact_passed_oracle_witness(tmp_path) -> None:
    ledger, service = _service(tmp_path)
    _, _, unrelated_run = _oracle_run(service, ledger)
    target, decision, findings = _assessment_inputs(
        ledger,
        independent=True,
        hidden_contradiction=True,
    )
    assessor = SlotClosureAssessor(ledger, core_evaluator_id="core-evaluator")

    unresolved = _assess(
        assessor,
        ledger,
        target,
        decision,
        findings,
        oracle_runs=(unrelated_run,),
        assessment_id="assessment-unresolved-contradiction",
    )
    _, _, witnessed_run = _oracle_run(
        service,
        ledger,
        input_refs=(_ref(findings[-1]),),
    )
    witnessed = _assess(
        assessor,
        ledger,
        target,
        decision,
        findings,
        oracle_runs=(witnessed_run,),
        assessment_id="assessment-witnessed-contradiction",
    )

    assert unresolved.payload["status"] == "inconclusive"
    assert "adversarial" in unresolved.payload["successor_kinds"]
    assert witnessed.payload["status"] == "passed"


def test_canonical_claim_conflict_cannot_be_cleared_by_an_oracle_witness(tmp_path) -> None:
    from test_canonical_contradictions import _claim_payload

    ledger, service = _service(tmp_path)
    target, decision, findings = _assessment_inputs(ledger, independent=True)
    positive = _append(
        ledger,
        "finding-canonical-positive",
        "finding-pack",
        {
            "blueprint_target_id": target.id,
            "decision_slot_id": "slot-1",
            "claims": [_claim_payload(claim_id="canonical-positive", polarity="positive")],
        },
        (_ref(target),),
    )
    negative = _append(
        ledger,
        "finding-canonical-negative",
        "finding-pack",
        {
            "blueprint_target_id": target.id,
            "decision_slot_id": "slot-1",
            "claims": [_claim_payload(claim_id="canonical-negative", polarity="negative")],
        },
        (_ref(target),),
    )
    _, _, witnessed_run = _oracle_run(service, ledger, input_refs=(_ref(positive), _ref(negative)))
    assessor = SlotClosureAssessor(ledger, core_evaluator_id="core-evaluator")

    assessment = _assess(
        assessor,
        ledger,
        target,
        decision,
        findings,
        oracle_runs=(witnessed_run,),
        assessment_id="assessment-canonical-conflict",
    )

    assert assessment.payload["status"] == "inconclusive"
    assert assessment.payload["closure_token"] is None
    assert assessment.payload["checks"]["no_selected_option_contradiction"] is False
    assert "adversarial" in assessment.payload["successor_kinds"]


def test_unselected_option_contradiction_does_not_create_an_adversarial_obligation(tmp_path) -> None:
    ledger, service = _service(tmp_path)
    _, _, run = _oracle_run(service, ledger)
    target, decision, findings = _assessment_inputs(
        ledger,
        independent=True,
        hidden_contradiction=True,
        contradiction_option="b",
    )
    assessor = SlotClosureAssessor(ledger, core_evaluator_id="core-evaluator")

    assessment = _assess(assessor, ledger, target, decision, findings, oracle_runs=(run,))

    assert assessment.payload["status"] == "passed"
    assert "adversarial" not in assessment.payload["successor_kinds"]


def _passed_v2_assessment(tmp_path, *, include_origin: bool = False):
    ledger, service = _service(tmp_path)
    spec, attempt, run = _oracle_run(service, ledger)
    target, decision, findings = _assessment_inputs(
        ledger,
        independent=True,
        include_origin=include_origin,
    )
    assessor = SlotClosureAssessor(ledger, core_evaluator_id="core-evaluator")
    assessment = _assess(
        assessor,
        ledger,
        target,
        decision,
        findings,
        oracle_runs=(run,),
        assessment_id="assessment-currentness",
    )
    assert assessment.payload["status"] == "passed"
    return ledger, assessor, assessment, target, decision, findings, spec, attempt, run


def test_currentness_replays_an_exact_derived_v2_assessment(tmp_path) -> None:
    _, assessor, assessment, *_ = _passed_v2_assessment(tmp_path)

    assert assessment.payload["assessment_revision"] == 2
    assert assessor.is_current(assessment) is True


def test_current_schema_and_fixture_match_the_runtime_assessment_envelope(tmp_path) -> None:
    _, _, assessment, *_ = _passed_v2_assessment(tmp_path)
    schema_root = ROOT / "openspec" / "changes" / "unify-research-runtime-alpha2" / "schemas"
    schema = json.loads((schema_root / "slot-closure-assessment-v2.json").read_text(encoding="utf-8"))
    examples = json.loads((schema_root / "examples" / "index-v1.json").read_text(encoding="utf-8"))
    fixture = next(item for item in examples["entries"] if item["schema"] == "slot-closure-assessment-v2.json")

    assert not (schema_root / "slot-closure-assessment-v1.json").exists()
    assert all(item["schema"] != "slot-closure-assessment-v1.json" for item in examples["entries"])
    assert set(schema["required"]) == set(assessment.payload)
    assert set(schema["required"]) == set(fixture["valid"])
    assert schema["additionalProperties"] is False
    with pytest.raises(ClosureAssessmentError, match="unsupported fields"):
        SlotClosureAssessment.from_dict({**thaw_json(assessment.payload), "extra": True})


@pytest.mark.parametrize(
    "lineage_item",
    [
        "target",
        "decision",
        "finding",
        "oracle_run",
        "oracle_spec",
        "oracle_attempt",
        "oracle_input",
        "oracle_result",
        "oracle_event",
    ],
)
def test_currentness_rejects_a_superseded_direct_oracle_or_decision_input(tmp_path, lineage_item: str) -> None:
    ledger, assessor, assessment, target, decision, findings, spec, attempt, run = _passed_v2_assessment(tmp_path)
    oracle = OracleRun.from_revision(_ref(run), run)
    items = {
        "target": target,
        "decision": decision,
        "finding": findings[0],
        "oracle_run": run,
        "oracle_spec": spec,
        "oracle_attempt": attempt,
        "oracle_input": ledger.get_artifact(oracle.input_refs[0]),
        "oracle_result": ledger.get_artifact(oracle.result_artifact_refs[0]),
        "oracle_event": ledger.get_artifact(oracle.tool_event_refs[0]),
    }
    item = items[lineage_item]
    _append(ledger, item.id, item.kind, thaw_json(item.payload), item.parent_refs)

    assert assessor.is_current(assessment) is False


@pytest.mark.parametrize("artifact_kind", ["evidence", "receipt", "capture", "origin"])
def test_currentness_rejects_a_superseded_strict_evidence_chain_input(tmp_path, artifact_kind: str) -> None:
    ledger, assessor, assessment, _, _, findings, *_ = _passed_v2_assessment(tmp_path, include_origin=True)
    item = _bound_source_artifact(ledger, findings[0], artifact_kind)
    _append(ledger, item.id, item.kind, thaw_json(item.payload), item.parent_refs)

    assert assessor.is_current(assessment) is False


def test_currentness_rejects_raw_legacy_and_tampered_assessments(tmp_path) -> None:
    ledger, assessor, assessment, *_ = _passed_v2_assessment(tmp_path)
    raw = _append(ledger, "assessment-raw", ASSESSMENT_KIND, {"status": "passed"})
    v1_payload = thaw_json(assessment.payload)
    v1_payload["assessment_id"] = "assessment-v1"
    v1_payload["assessment_revision"] = 1
    legacy = _append(
        ledger,
        "assessment-v1",
        ASSESSMENT_KIND,
        v1_payload,
        assessment.parent_refs,
    )
    tampered_payload = thaw_json(assessment.payload)
    tampered_payload["assessment_id"] = "assessment-tampered"
    tampered_payload["checks"]["oracle"] = False
    tampered = _append(
        ledger,
        "assessment-tampered",
        ASSESSMENT_KIND,
        tampered_payload,
        assessment.parent_refs,
    )

    assert assessor.is_current(raw) is False
    assert assessor.is_current(legacy) is False
    assert assessor.is_current(tampered) is False


@pytest.mark.parametrize("forgery", ["capture", "evidence", "origin"])
def test_shape_correct_unbound_source_graph_cannot_issue_a_token(tmp_path, forgery: str) -> None:
    ledger, service = _service(tmp_path)
    _, _, run = _oracle_run(service, ledger)
    target, decision, findings = _assessment_inputs(ledger, forgery=forgery)
    assessor = SlotClosureAssessor(ledger, core_evaluator_id="core-evaluator")

    assessment = _assess(assessor, ledger, target, decision, findings, oracle_runs=(run,))

    assert assessment.payload["status"] == "inconclusive"
    assert assessment.payload["closure_token"] is None
    assert assessment.payload["checks"]["evidence"] is False


def _bound_source_artifact(ledger: RunLedger, finding, artifact_kind: str):
    anchor = EvidenceAnchor.from_dict(finding.payload["observations"][0]["anchor"])
    assert anchor.artifact_ref is not None
    evidence = ledger.get_artifact(anchor.artifact_ref)
    if artifact_kind == "evidence":
        return evidence
    receipt = next(
        ledger.get_artifact(reference)
        for reference in evidence.parent_refs
        if ledger.get_artifact(reference).kind == ACQUISITION_RECEIPT_KIND
    )
    capture = next(
        ledger.get_artifact(reference)
        for reference in receipt.parent_refs
        if ledger.get_artifact(reference).kind == SOURCE_CAPTURE_KIND
    )
    if artifact_kind == "capture":
        return capture
    origin_id = SourceCapture.from_dict(capture.payload).origin_capture_id
    assert origin_id is not None
    return next(
        artifact
        for artifact in ledger.list_artifacts(RUN_ID)
        if artifact.id == origin_id and artifact.kind == SOURCE_CAPTURE_KIND
    )


@pytest.mark.parametrize("artifact_kind", ["evidence", "capture", "origin"])
@pytest.mark.parametrize("mutation", ["tamper", "delete"])
def test_changed_or_missing_bound_content_cannot_issue_a_token(tmp_path, artifact_kind: str, mutation: str) -> None:
    ledger, service = _service(tmp_path)
    _, _, run = _oracle_run(service, ledger)
    target, decision, findings = _assessment_inputs(ledger, include_origin=artifact_kind == "origin")
    artifact = _bound_source_artifact(ledger, findings[0], artifact_kind)
    content = ledger.get_bound_content(_ref(artifact))
    object_path = ContentAddressedStore(ledger.workspace)._object_path(content.digest)
    if mutation == "tamper":
        object_path.write_bytes(b"tampered")
    else:
        object_path.unlink()
    assessor = SlotClosureAssessor(ledger, core_evaluator_id="core-evaluator")

    assessment = _assess(assessor, ledger, target, decision, findings, oracle_runs=(run,))

    assert assessment.payload["status"] == "inconclusive"
    assert assessment.payload["closure_token"] is None
    assert assessment.payload["checks"]["evidence"] is False


def test_raw_bound_legacy_evidence_cannot_issue_a_token(tmp_path) -> None:
    ledger, service = _service(tmp_path)
    _, _, run = _oracle_run(service, ledger)
    target, decision, findings = _assessment_inputs(ledger)
    anchor = EvidenceAnchor.from_dict(findings[0].payload["observations"][0]["anchor"])
    assert anchor.artifact_ref is not None
    evidence = ledger.get_artifact(anchor.artifact_ref)
    content = ledger.get_bound_content(anchor.artifact_ref)
    legacy_payload = thaw_json(evidence.payload)
    legacy_payload["evidence_id"] = "evidence-legacy"
    legacy_payload["evidence_class"] = "legacy_unspecified"
    legacy = ledger.append_artifact_with_content(
        RUN_ID,
        "evidence-legacy",
        EVIDENCE_ARTIFACT_KIND,
        legacy_payload,
        content,
        ContentAddressedStore(ledger.workspace),
        parent_refs=evidence.parent_refs,
        expected_revision=ledger.get_revision(RUN_ID),
    )
    legacy_anchor = EvidenceAnchor(
        artifact_ref=_ref(legacy),
        artifact_digest=content.digest,
        artifact_revision=legacy.revision,
        selector_type=anchor.selector_type,
        selector_value=anchor.selector_value,
        extractor_version=anchor.extractor_version,
        applicability=anchor.applicability,
        confidence=anchor.confidence,
        limitations=anchor.limitations,
    )
    legacy_finding = _finding(
        ledger,
        finding_id="finding-legacy",
        target=target,
        anchor=legacy_anchor,
        effect="supports",
    )
    legacy_decision = _append(
        ledger,
        "decision-1",
        "decision-ledger-entry",
        dict(decision.payload),
        (_ref(target), _ref(legacy_finding)),
    )
    assessor = SlotClosureAssessor(ledger, core_evaluator_id="core-evaluator")

    assessment = _assess(assessor, ledger, target, legacy_decision, (legacy_finding,), oracle_runs=(run,))

    assert assessment.payload["status"] == "inconclusive"
    assert assessment.payload["closure_token"] is None
    assert assessment.payload["checks"]["evidence"] is False


def test_out_of_bounds_strict_anchor_cannot_issue_a_token(tmp_path) -> None:
    ledger, service = _service(tmp_path)
    _, _, run = _oracle_run(service, ledger)
    target, decision, findings = _assessment_inputs(ledger)
    anchor = EvidenceAnchor.from_dict(findings[0].payload["observations"][0]["anchor"])
    assert anchor.artifact_ref is not None
    invalid_anchor = EvidenceAnchor(
        artifact_ref=anchor.artifact_ref,
        artifact_digest=anchor.artifact_digest,
        artifact_revision=anchor.artifact_revision,
        selector_type="line",
        selector_value={"start": 99, "end": 99},
        extractor_version=anchor.extractor_version,
        applicability=anchor.applicability,
        confidence=anchor.confidence,
        limitations=anchor.limitations,
    )
    invalid_finding = _finding(
        ledger,
        finding_id="finding-out-of-bounds",
        target=target,
        anchor=invalid_anchor,
        effect="supports",
    )
    invalid_decision = _append(
        ledger,
        "decision-1",
        "decision-ledger-entry",
        thaw_json(decision.payload),
        (_ref(target), _ref(invalid_finding)),
    )
    assessor = SlotClosureAssessor(ledger, core_evaluator_id="core-evaluator")

    assessment = _assess(assessor, ledger, target, invalid_decision, (invalid_finding,), oracle_runs=(run,))

    assert assessment.payload["status"] == "inconclusive"
    assert assessment.payload["closure_token"] is None
    assert assessment.payload["checks"]["evidence"] is False


def test_escaped_strict_evidence_locator_cannot_issue_a_token(tmp_path) -> None:
    ledger, service = _service(tmp_path)
    _, _, run = _oracle_run(service, ledger)
    target, decision, findings = _assessment_inputs(ledger)
    anchor = EvidenceAnchor.from_dict(findings[0].payload["observations"][0]["anchor"])
    assert anchor.artifact_ref is not None
    evidence = ledger.get_artifact(anchor.artifact_ref)
    content = ledger.get_bound_content(anchor.artifact_ref)
    escaped_payload = thaw_json(evidence.payload)
    escaped_payload["evidence_id"] = "evidence-escaped"
    escaped_payload["locator"] = {"path": "../outside.py"}
    escaped = ledger.append_artifact_with_content(
        RUN_ID,
        "evidence-escaped",
        EVIDENCE_ARTIFACT_KIND,
        escaped_payload,
        content,
        ContentAddressedStore(ledger.workspace),
        parent_refs=evidence.parent_refs,
        expected_revision=ledger.get_revision(RUN_ID),
    )
    escaped_anchor = EvidenceAnchor(
        artifact_ref=_ref(escaped),
        artifact_digest=content.digest,
        artifact_revision=escaped.revision,
        selector_type=anchor.selector_type,
        selector_value=anchor.selector_value,
        extractor_version=anchor.extractor_version,
        applicability=anchor.applicability,
        confidence=anchor.confidence,
        limitations=anchor.limitations,
    )
    escaped_finding = _finding(
        ledger,
        finding_id="finding-escaped",
        target=target,
        anchor=escaped_anchor,
        effect="supports",
    )
    escaped_decision = _append(
        ledger,
        "decision-1",
        "decision-ledger-entry",
        thaw_json(decision.payload),
        (_ref(target), _ref(escaped_finding)),
    )
    assessor = SlotClosureAssessor(ledger, core_evaluator_id="core-evaluator")

    assessment = _assess(assessor, ledger, target, escaped_decision, (escaped_finding,), oracle_runs=(run,))

    assert assessment.payload["status"] == "inconclusive"
    assert assessment.payload["closure_token"] is None
    assert assessment.payload["checks"]["evidence"] is False


def test_unverifiable_repository_revision_cannot_issue_a_token(tmp_path) -> None:
    ledger, service = _service(tmp_path)
    _, _, run = _oracle_run(service, ledger)
    target, decision, findings = _assessment_inputs(ledger)
    anchor = EvidenceAnchor.from_dict(findings[0].payload["observations"][0]["anchor"])
    assert anchor.artifact_ref is not None
    evidence = ledger.get_artifact(anchor.artifact_ref)
    content = ledger.get_bound_content(anchor.artifact_ref)
    repository_payload = thaw_json(evidence.payload)
    repository_payload["evidence_id"] = "evidence-repository"
    repository_payload["locator"] = {"path": "src/module.py"}
    repository_payload["source_revision"] = "commit-a"
    repository_evidence = ledger.append_artifact_with_content(
        RUN_ID,
        "evidence-repository",
        EVIDENCE_ARTIFACT_KIND,
        repository_payload,
        content,
        ContentAddressedStore(ledger.workspace),
        parent_refs=evidence.parent_refs,
        expected_revision=ledger.get_revision(RUN_ID),
    )
    repository_anchor = EvidenceAnchor(
        artifact_ref=_ref(repository_evidence),
        artifact_digest=content.digest,
        artifact_revision=repository_evidence.revision,
        selector_type=anchor.selector_type,
        selector_value=anchor.selector_value,
        extractor_version=anchor.extractor_version,
        applicability=anchor.applicability,
        confidence=anchor.confidence,
        limitations=anchor.limitations,
    )
    repository_finding = _finding(
        ledger,
        finding_id="finding-repository",
        target=target,
        anchor=repository_anchor,
        effect="supports",
    )
    repository_decision = _append(
        ledger,
        "decision-1",
        "decision-ledger-entry",
        thaw_json(decision.payload),
        (_ref(target), _ref(repository_finding)),
    )
    assessor = SlotClosureAssessor(ledger, core_evaluator_id="core-evaluator")

    assessment = _assess(
        assessor,
        ledger,
        target,
        repository_decision,
        (repository_finding,),
        oracle_runs=(run,),
    )

    assert assessment.payload["status"] == "inconclusive"
    assert assessment.payload["closure_token"] is None
    assert assessment.payload["checks"]["evidence"] is False


def test_caller_cannot_omit_a_current_decision_bound_contradiction(tmp_path) -> None:
    ledger, service = _service(tmp_path)
    _, _, run = _oracle_run(service, ledger)
    target, decision, findings = _assessment_inputs(ledger, hidden_contradiction=True)
    assessor = SlotClosureAssessor(ledger, core_evaluator_id="core-evaluator")

    with pytest.raises(ClosureAssessmentError, match="complete decision Finding set"):
        _assess(assessor, ledger, target, decision, findings[:1], oracle_runs=(run,))


def test_caller_cannot_supply_an_unrelated_current_finding(tmp_path) -> None:
    ledger, service = _service(tmp_path)
    _, _, run = _oracle_run(service, ledger)
    target, decision, findings = _assessment_inputs(ledger)
    _, anchor = _source_graph(
        ledger,
        capture_id="capture-unrelated",
        evidence_id="evidence-unrelated",
        attempt_id="attempt-unrelated",
    )
    unrelated = _finding(ledger, finding_id="finding-unrelated", target=target, anchor=anchor, effect="supports")
    assessor = SlotClosureAssessor(ledger, core_evaluator_id="core-evaluator")

    with pytest.raises(ClosureAssessmentError, match="complete decision Finding set"):
        _assess(assessor, ledger, target, decision, (*findings, unrelated), oracle_runs=(run,))


def test_decision_cannot_silently_ignore_a_current_wrong_slot_finding(tmp_path) -> None:
    ledger, service = _service(tmp_path)
    _, _, run = _oracle_run(service, ledger)
    target, decision, findings = _assessment_inputs(ledger)
    _, anchor = _source_graph(
        ledger,
        capture_id="capture-wrong-slot",
        evidence_id="evidence-wrong-slot",
        attempt_id="attempt-wrong-slot",
    )
    wrong_slot = _append(
        ledger,
        "finding-wrong-slot",
        "finding-pack",
        {
            "blueprint_target_id": target.id,
            "decision_slot_id": "other-slot",
            "evidence_mode": "strict",
            "observations": [{"anchor": anchor.to_dict()}],
            "option_effects": [{"option": "a", "effect": "supports"}],
        },
        (_ref(target), anchor.artifact_ref),
    )
    malformed_decision = _append(
        ledger,
        "decision-1",
        "decision-ledger-entry",
        thaw_json(decision.payload),
        (_ref(target), _ref(findings[0]), _ref(wrong_slot)),
    )
    assessor = SlotClosureAssessor(ledger, core_evaluator_id="core-evaluator")

    with pytest.raises(ClosureAssessmentError, match="exact target and slot"):
        _assess(assessor, ledger, target, malformed_decision, findings, oracle_runs=(run,))


def test_stale_direct_decision_finding_parent_is_rejected(tmp_path) -> None:
    ledger, service = _service(tmp_path)
    _, _, run = _oracle_run(service, ledger)
    target, decision, findings = _assessment_inputs(ledger)
    current_finding = _append(
        ledger,
        findings[0].id,
        findings[0].kind,
        thaw_json(findings[0].payload),
        findings[0].parent_refs,
    )
    assessor = SlotClosureAssessor(ledger, core_evaluator_id="core-evaluator")

    with pytest.raises(ClosureAssessmentError, match="finding-pack reference is stale or mismatched"):
        _assess(assessor, ledger, target, decision, (current_finding,), oracle_runs=(run,))


@pytest.mark.parametrize("foreign_parent", ["evidence", "receipt", "capture"])
def test_foreign_evidence_lineage_cannot_issue_a_token(tmp_path, foreign_parent: str) -> None:
    ledger, service = _service(tmp_path)
    _, _, run = _oracle_run(service, ledger)
    target, _, _ = _assessment_inputs(ledger)
    ledger.create_run("run-foreign")
    evidence, anchor = _source_graph(
        ledger,
        capture_id="capture-foreign",
        evidence_id="evidence-foreign",
        attempt_id="attempt-foreign",
        round_id="run-foreign",
    )
    if foreign_parent != "evidence":
        content = ledger.get_bound_content(_ref(evidence))
        payload = thaw_json(evidence.payload)
        payload.update(evidence_id="evidence-foreign-receipt", run_id=RUN_ID)
        receipt_ref = evidence.parent_refs[0]
        if foreign_parent == "capture":
            receipt = ledger.get_artifact(receipt_ref)
            payload = thaw_json(receipt.payload)
            payload["receipt_id"] = "receipt-foreign-capture"
            receipt_ref = _ref(
                _append(
                    ledger,
                    "receipt-foreign-capture",
                    ACQUISITION_RECEIPT_KIND,
                    payload,
                    (receipt.parent_refs[0],),
                )
            )
        evidence = ledger.append_artifact_with_content(
            RUN_ID,
            "evidence-foreign-receipt",
            EVIDENCE_ARTIFACT_KIND,
            payload,
            content,
            ContentAddressedStore(ledger.workspace),
            parent_refs=(receipt_ref,),
            expected_revision=ledger.get_revision(RUN_ID),
        )
        anchor = EvidenceAnchor(
            artifact_ref=_ref(evidence),
            artifact_digest=content.digest,
            artifact_revision=evidence.revision,
            selector_type=anchor.selector_type,
            selector_value=anchor.selector_value,
            extractor_version=anchor.extractor_version,
            applicability=anchor.applicability,
            confidence=anchor.confidence,
            limitations=anchor.limitations,
        )
    finding = _finding(
        ledger,
        finding_id="finding-foreign-lineage",
        target=target,
        anchor=anchor,
        effect="supports",
    )
    decision = _append(
        ledger,
        "decision-1",
        "decision-ledger-entry",
        {
            "blueprint_target_id": target.id,
            "decision_slot_id": "slot-1",
            "status": "selected",
            "selected_option": "a",
            "fallback": "use option b",
            "reversal_condition": "new counterevidence",
        },
        (_ref(target), _ref(finding)),
    )
    assessor = SlotClosureAssessor(ledger, core_evaluator_id="core-evaluator")

    assessment = _assess(assessor, ledger, target, decision, (finding,), oracle_runs=(run,))

    assert assessment.payload["status"] == "inconclusive"
    assert assessment.payload["closure_token"] is None
    assert assessment.payload["checks"]["evidence"] is False
