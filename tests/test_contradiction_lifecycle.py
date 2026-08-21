from __future__ import annotations


def _typed_claim(claim_id, **overrides):
    from dataclasses import replace

    from test_canonical_contradictions import _claim

    fields = {"value": "feature-x", "polarity": "positive", "scope": "release"}
    claim_kwargs = {key: overrides.pop(key, value) for key, value in fields.items()}
    return replace(_claim(claim_id=claim_id, **claim_kwargs), **overrides)


def _real_objects(tmp_path):
    from research_tree import CanonicalDeliveryCompiler, CanonicalReadinessVerifier, ResearchRunCoordinator
    from test_deliveries import context, repository

    tmp_path.mkdir(parents=True, exist_ok=True)
    repository(tmp_path / "repository")
    modules, ledger, round_record, model, brief, target, finding, decision = context(tmp_path)
    return {
        "modules": modules,
        "ledger": ledger,
        "round": round_record,
        "brief": brief,
        "target": target,
        "finding": finding,
        "decision": decision,
        "coordinator": ResearchRunCoordinator(ledger),
        "readiness": CanonicalReadinessVerifier(ledger, modules["resolver"]),
        "delivery": CanonicalDeliveryCompiler(ledger, modules["resolver"]),
    }


def _conflicting_correction(tmp_path, label, *, extra=None):
    from research_tree.domain import ArtifactRef
    from test_canonical_contradictions import _claim_payload
    from test_feedback_rounds import correction_context

    ledger, coordinator, state, _, _ = correction_context(tmp_path / "correction")

    def finding(polarity, parent):
        suffix = "positive" if polarity == "positive" else "negative"
        return ledger.append_artifact(
            "run-correction",
            f"finding-{label}-{suffix}",
            "finding-pack",
            {"claims": [_claim_payload(claim_id=f"claim-{label}-{suffix}", polarity=polarity)], **(extra or {})},
            parent_refs=(parent,),
            expected_revision=ledger.get_revision("run-correction"),
        )

    first = finding("positive", ArtifactRef(state.round_id, state.id, state.revision))
    second = finding("negative", ArtifactRef(first.round_id, first.id, first.revision))
    return (
        ledger,
        coordinator,
        (
            ArtifactRef(first.round_id, first.id, first.revision),
            ArtifactRef(second.round_id, second.id, second.revision),
        ),
    )


def _passing_readiness():
    gates = dict.fromkeys(
        (
            "intent_alignment",
            "decision_closure",
            "traceability",
            "repository_fit",
            "implementation_readiness",
            "operational_quality",
        ),
        "pass",
    )
    return {"risk_tier": "medium", "gates": gates, "findings": [], "next_work_item_ids": []}


def _compile_delivery(objects, deliveries):
    return objects["delivery"].compile(
        round_id=objects["round"].id,
        technical_package_id=deliveries.technical_package.id,
        human_brief_id=deliveries.human_brief.id,
        working_brief=objects["brief"],
        blueprint_target=objects["target"],
        decision_entries=[objects["decision"]],
        readiness=_passing_readiness(),
        expected_revision=objects["ledger"].get_revision(objects["round"].id),
    )


def _negative_finding(objects):
    from dataclasses import replace

    from research_tree import CanonicalFindingPackCompiler
    from research_tree.claims import ClaimGrounding

    finding = objects["finding"]
    work_ref = next(
        reference for reference in finding.parent_refs if reference.artifact_id == finding.payload["work_item_id"]
    )
    anchors = [item["anchor"] for item in finding.payload["claim_groundings"]]
    negative = replace(
        _typed_claim(
            "claim-negative-boundary",
            polarity="negative",
            value="the isolated worker boundary",
            scope="fixture boundary",
            version="fixture-v1",
            platform="unspecified",
            time_range="fixture-time",
            conditions=(),
            modality="unspecified",
        ),
        subject="source",
    )
    return CanonicalFindingPackCompiler(objects["ledger"], objects["modules"]["resolver"]).compile(
        round_id=objects["round"].id,
        finding_id="finding-negative-boundary",
        work_item=objects["ledger"].get_artifact(work_ref),
        observations=[
            {
                "claim_id": negative.claim_id,
                "claim": "The source marks the isolated worker boundary negative.",
                "anchor": anchors[0],
                "applicability": "the fixture boundary",
                "confidence": "medium",
                "limitation": "The exact source revision must be compared directly.",
            }
        ],
        option_effects=[{"option": "isolated-worker", "effect": "contradicts", "claim_ids": [negative.claim_id]}],
        implementation_implications=["The prior boundary interpretation must be retested."],
        remaining_uncertainties=["Resolve the direct source disagreement."],
        claims=[negative],
        claim_groundings=[
            ClaimGrounding("grounding-negative-a", negative.claim_id, anchors[0]),
            ClaimGrounding("grounding-negative-b", negative.claim_id, anchors[1]),
        ],
        expected_revision=objects["ledger"].get_revision(objects["round"].id),
    )


def _compile_initial_outputs(objects, tmp_path):
    from research_tree.domain import ArtifactRef
    from test_deliveries import compile_deliveries

    deliveries = compile_deliveries(
        objects["modules"],
        objects["ledger"],
        objects["round"],
        objects["brief"],
        objects["target"],
        [objects["decision"]],
    )
    readiness = objects["readiness"].verify(
        round_id=objects["round"].id,
        readiness_id="readiness-before-contradiction",
        technical_package=deliveries.technical_package,
        repository_roots={"input-repository": tmp_path / "repository"},
        risk_tier="medium",
        expected_revision=objects["ledger"].get_revision(objects["round"].id),
    )
    technical = deliveries.technical_package
    objects["ledger"].append_artifact(
        objects["round"].id,
        "run-state",
        "research-run-state",
        {
            "state": "awaiting_acceptance",
            "lifecycle_revision": 0,
            "unmet_obligations": [],
            "legal_next_actions": ["delivery_accepted"],
            "authority_streams": {},
        },
        parent_refs=(ArtifactRef(technical.round_id, technical.id, technical.revision),),
        expected_revision=objects["ledger"].get_revision(objects["round"].id),
    )
    return deliveries, readiness


def test_typed_scope_normalization_separates_applicability() -> None:
    from research_tree.contradictions import ContradictionStatus, detect_contradictions

    claim = _typed_claim
    cases = {
        "version": claim("right", version="3", polarity="negative"),
        "platform": claim("right", platform="linux", polarity="negative"),
        "time_range": claim("right", time_range="2026-09", polarity="negative"),
        "condition_mode": claim("right", conditions=("optional",), polarity="negative"),
        "modality": claim("right", modality="benchmark", polarity="negative"),
    }
    for dimension, right in cases.items():
        packet = detect_contradictions((claim("left"), right), boundary="admission")[0]
        result = next(item for item in packet.scope_dimensions if item.dimension == dimension)
        assert packet.status is ContradictionStatus.SCOPE_SEPARATED, dimension
        assert result.overlap is False and result.explanation, dimension

    overlap = detect_contradictions(
        (
            claim("overlap-left", time_range="2026-01..2027-12"),
            claim("overlap-right", time_range="2027-01..2028-12", polarity="negative"),
        ),
        boundary="experiment",
    )[0]
    assert overlap.status is ContradictionStatus.CONTESTED
    assert "time_range" in overlap.unresolved_dimensions


def test_resolution_lifecycle_is_immutable_and_authority_scoped(tmp_path) -> None:
    from research_tree.contradictions import (
        ContradictionStatus,
        blocking_contradictions,
        detect_contradictions,
        render_contradiction_packet,
    )
    from research_tree.domain import ArtifactRef

    objects = _real_objects(tmp_path)
    packet = detect_contradictions(
        (_typed_claim("left"), _typed_claim("right", polarity="negative")),
        boundary="admission",
    )[0]
    payload = {
        "contradiction_id": "contradiction-lifecycle",
        "run_id": objects["round"].id,
        "claim_ids": list(packet.claim_ids),
        "status": ContradictionStatus.CONTESTED.value,
        "boundary": "admission",
        "normalized_claims": [dict(claim) for claim in packet.normalized_claims],
        "scope_dimensions": [item.to_dict() for item in packet.scope_dimensions],
        "source_refs": {
            "left": {"provenance_clusters": ["upstream:a"], "passages": ["line 1"]},
            "right": {"provenance_clusters": ["upstream:b"], "passages": ["line 2"]},
        },
        "invalidated_refs": [objects["decision"].id],
        "resolution_path": "independent method",
        "safe_fallback": "retain the reversible boundary",
    }
    artifact = objects["ledger"].append_artifact(
        objects["round"].id,
        payload["contradiction_id"],
        "contradiction-packet",
        payload,
        parent_refs=(ArtifactRef(objects["finding"].round_id, objects["finding"].id, objects["finding"].revision),),
        expected_revision=objects["ledger"].get_revision(objects["round"].id),
    )
    resolved = objects["coordinator"].resolve_contradiction(
        packet_ref=artifact,
        resolution_id="resolution-first",
        transition="resolved-a",
        resolver_ref={"actor": "human", "id": "resolver"},
        evidence_refs=(artifact,),
        selected_claim_ids=("left",),
        expected_revision=objects["ledger"].get_revision(objects["round"].id),
    )
    superseded = objects["coordinator"].resolve_contradiction(
        packet_ref=artifact,
        resolution_id="resolution-second",
        transition="superseded",
        prior_resolution=resolved,
        resolver_ref={"actor": "executable", "id": "oracle"},
        evidence_refs=(resolved,),
        selected_claim_ids=(),
        expected_revision=objects["ledger"].get_revision(objects["round"].id),
    )
    rendered = render_contradiction_packet(payload)
    expected = (("contradiction-lifecycle", ("left", "right")),)
    assert artifact.revision == 1 and artifact.payload["status"] == ContradictionStatus.CONTESTED.value
    assert list(resolved.payload["authorized_claim_ids"]) == ["left"]
    assert superseded.payload["prior_resolution_ref"]["artifact_id"] == resolved.id
    assert blocking_contradictions([payload], ("left",), resolution_payloads=[resolved.payload]) == ()
    assert blocking_contradictions([payload], ("right",), resolution_payloads=[resolved.payload]) == expected
    assert blocking_contradictions([payload], ("left",), resolution_payloads=[superseded.payload]) == expected
    assert all(value in rendered for value in ("left", "right", "upstream:a", "independent method"))


def test_contradictions_block_until_fresh_decision_lineage(tmp_path) -> None:
    import pytest

    from research_tree import InvalidDeliveryError, InvalidReadinessError, SlotClosureAssessor

    objects = _real_objects(tmp_path)
    deliveries, _readiness = _compile_initial_outputs(objects, tmp_path)
    closure = SlotClosureAssessor(objects["ledger"], core_evaluator_id="core").assess(
        round_id=objects["round"].id,
        assessment_id="closure-before",
        slot_id="slot-isolation",
        blueprint_target=objects["target"],
        decision=objects["decision"],
        findings=[objects["finding"]],
        oracle_runs=(),
        evaluator_id="core",
        expected_revision=objects["ledger"].get_revision(objects["round"].id),
    )
    _negative_finding(objects)
    packet = next(
        item
        for item in objects["ledger"].load_run(objects["round"].id).artifacts
        if item.kind == "contradiction-packet"
    )
    with pytest.raises(InvalidDeliveryError) as unresolved_error:
        _compile_delivery(objects, deliveries)
    assert packet.id in str(unresolved_error.value)
    assert "claim-isolation-delivery" in str(unresolved_error.value)
    assert "claim-negative-boundary" in str(unresolved_error.value)
    assert objects["coordinator"].why_not_complete(objects["round"].id)["unmet_obligations"]
    assert closure.kind == "slot-closure-assessment"
    selected = tuple(claim_id for claim_id in packet.payload["claim_ids"] if claim_id != "claim-negative-boundary")
    resolution = objects["coordinator"].resolve_contradiction(
        packet_ref=packet,
        resolution_id="resolution-positive",
        transition="resolved-a",
        resolver_ref={"actor": "executable", "id": "resolution-oracle"},
        evidence_refs=(packet,),
        selected_claim_ids=selected,
        expected_revision=objects["ledger"].get_revision(objects["round"].id),
    )
    with pytest.raises(InvalidReadinessError) as readiness_error:
        objects["readiness"].verify(
            round_id=objects["round"].id,
            readiness_id="readiness-after-resolution",
            technical_package=deliveries.technical_package,
            repository_roots={"input-repository": tmp_path / "repository"},
            risk_tier="medium",
            expected_revision=objects["ledger"].get_revision(objects["round"].id),
        )
    with pytest.raises(InvalidDeliveryError) as delivery_error:
        _compile_delivery(objects, deliveries)

    assert resolution.payload["transition"] == "resolved-a"
    assert objects["decision"].id in str(readiness_error.value)
    assert "fresh decision lineage" in str(readiness_error.value)
    assert objects["decision"].id in str(delivery_error.value)
    assert "fresh decision lineage" in str(delivery_error.value)


def test_all_claim_boundaries_use_one_detector(tmp_path, monkeypatch) -> None:
    from research_tree.contradictions import ContradictionDetector

    ledger, coordinator, _refs = _conflicting_correction(
        tmp_path,
        "boundary",
        extra={"blueprint_target_id": "decision-map-current", "decision_slot_id": "slot-target"},
    )
    original = ContradictionDetector.detect
    boundaries = []

    def traced(self, claims, *, boundary, **kwargs):
        boundaries.append(boundary)
        return original(self, claims, boundary=boundary, **kwargs)

    monkeypatch.setattr(ContradictionDetector, "detect", traced)
    for boundary in ("admission", "recall", "revision", "experiment", "feedback"):
        coordinator.detect_and_apply_contradictions(
            run_id="run-correction",
            blueprint_target_id="decision-map-current",
            decision_slot_id="slot-target",
            expected_revision=ledger.get_revision("run-correction"),
            boundary=boundary,
        )
    packets = [item for item in ledger.load_run("run-correction").artifacts if item.kind == "contradiction-packet"]
    assert [getattr(value, "value", value) for value in boundaries] == [
        "admission",
        "admission",
        "recall",
        "revision",
        "experiment",
        "feedback",
    ]
    assert len(packets) == 1 and packets[0].payload["boundary"] == "admission"


def test_contested_claims_revoke_readiness_and_delivery(tmp_path) -> None:
    objects = _real_objects(tmp_path)
    deliveries, readiness = _compile_initial_outputs(objects, tmp_path)
    revision = objects["decision"].revision
    _negative_finding(objects)
    artifacts = objects["ledger"].load_run(objects["round"].id).artifacts
    packet = next(item for item in artifacts if item.kind == "contradiction-packet")
    retraction = next(item for item in artifacts if item.kind == "contradiction-retraction")
    invalidated = {item["artifact_id"] for item in retraction.payload["invalidated_refs"]}

    assert list(packet.payload["claim_ids"]) == [
        "claim-isolated-worker",
        "claim-isolation-delivery",
        "claim-negative-boundary",
    ]
    assert {objects["decision"].id, readiness.id, deliveries.technical_package.id} <= invalidated
    assert {deliveries.technical_package.id, deliveries.human_brief.id} <= set(
        retraction.payload["stale_delivery_claims"]
    )
    state = objects["coordinator"].state(objects["round"].id).payload
    assert state["contradiction_id"] == packet.id
    assert "contradiction_resolution" in state["unmet_obligations"]
    assert objects["decision"].revision == revision
    assert state["state"] == "alignment"


def test_contested_claims_cancel_and_quarantine_execution(tmp_path) -> None:
    ledger, coordinator, finding_refs = _conflicting_correction(tmp_path, "execution")
    parent = (finding_refs[1],)
    unexecuted = ledger.append_artifact(
        "run-correction",
        "attempt-unexecuted",
        "attempt-lease",
        {"attempt_id": "attempt-unexecuted", "status": "active", "execution_status": "unexecuted"},
        parent_refs=parent,
        expected_revision=ledger.get_revision("run-correction"),
    )
    started = ledger.append_artifact(
        "run-correction",
        "attempt-started",
        "attempt-lease",
        {"attempt_id": "attempt-started", "status": "active", "execution_status": "started"},
        parent_refs=parent,
        expected_revision=ledger.get_revision("run-correction"),
    )
    coordinator.apply_contradiction(
        run_id="run-correction",
        contradiction_id="contradiction-execution",
        finding_refs=finding_refs,
        reason="The applicable execution evidence conflicts.",
        expected_revision=ledger.get_revision("run-correction"),
    )
    artifacts = ledger.load_run("run-correction").artifacts
    latest = {
        artifact_id: max((item for item in artifacts if item.id == artifact_id), key=lambda item: item.revision)
        for artifact_id in (unexecuted.id, started.id)
    }
    retraction = next(item for item in artifacts if item.kind == "contradiction-retraction")
    assert latest["attempt-unexecuted"].payload["status"] == "cancelled"
    assert latest["attempt-started"].payload["status"] == "quarantined"
    assert retraction.payload["execution_effects"] == {
        "attempt-unexecuted": "cancelled",
        "attempt-started": "quarantined",
    }


def test_retraction_retry_is_idempotent_after_durable_fault(tmp_path, monkeypatch) -> None:
    import pytest

    from research_tree.durable_interaction_state import DurableInteractionController
    from research_tree.interaction_state import InteractionEvent

    ledger, coordinator, finding_refs = _conflicting_correction(tmp_path, "idempotent")
    controller = DurableInteractionController.initialize(
        tmp_path / "durable", project_id="topic", run_id="run-correction"
    )
    controller.submit(
        InteractionEvent.agent_assumption(
            event_id="assume-idempotent",
            assumption_id="claim-idempotent-positive",
            statement="Use the positive claim.",
            pending_actions=("publish",),
        ),
        expected_revision=0,
    )
    controller.propose_evidence("claim-idempotent-positive", "Positive claim.", admitted=True, expected_revision=1)
    kwargs = {
        "run_id": "run-correction",
        "contradiction_id": "contradiction-idempotent",
        "finding_refs": finding_refs,
        "reason": "The applicable claims conflict.",
        "expected_revision": ledger.get_revision("run-correction"),
        "durable_controller": controller,
    }
    original = controller.contest_evidence_set
    monkeypatch.setattr(
        controller, "contest_evidence_set", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("fault"))
    )
    with pytest.raises(RuntimeError, match="fault"):
        coordinator.apply_contradiction(**kwargs)
    packet_count = sum(item.id == "contradiction-idempotent" for item in ledger.load_run("run-correction").artifacts)
    durable_revision = controller.load().revision
    monkeypatch.setattr(controller, "contest_evidence_set", original)
    coordinator.apply_contradiction(**kwargs | {"expected_revision": ledger.get_revision("run-correction")})
    coordinator.apply_contradiction(**kwargs | {"expected_revision": ledger.get_revision("run-correction")})

    artifacts = ledger.load_run("run-correction").artifacts
    assert sum(item.id == "contradiction-idempotent" for item in artifacts) == packet_count
    assert sum(item.kind == "contradiction-retraction" for item in artifacts) == 1
    assert controller.load().revision == durable_revision + 1
    assert controller.load().factual_beliefs == {}
