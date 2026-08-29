from __future__ import annotations


def _claim(*, claim_id: str, value: str, polarity: str = "positive", scope: str = "release"):
    from research_tree.claims import Claim

    return Claim(
        claim_id=claim_id,
        subject="research-tree",
        predicate="supports",
        value=value,
        polarity=polarity,
        scope=scope,
        version="2",
        time_range="2026-08",
        platform="macos",
        modality="production",
        conditions=("default",),
    )


def _claim_payload(*, claim_id: str, polarity: str) -> dict[str, object]:
    claim = _claim(claim_id=claim_id, value="feature-x", polarity=polarity)
    return {
        "claim_id": claim.claim_id,
        "subject": claim.subject,
        "predicate": claim.predicate,
        "value": claim.value,
        "polarity": claim.polarity,
        "scope": claim.scope,
        "version": claim.version,
        "time_range": claim.time_range,
        "conditions": list(claim.conditions),
        "platform": claim.platform,
        "modality": claim.modality,
    }


def test_non_overlapping_scope_is_recorded_without_false_retraction() -> None:
    from research_tree.contradictions import ContradictionStatus, derive_contradiction_packets

    packets = derive_contradiction_packets(
        (
            _claim(claim_id="claim-stable", value="feature-x", polarity="positive", scope="stable"),
            _claim(claim_id="claim-preview", value="feature-x", polarity="negative", scope="preview"),
        )
    )

    assert len(packets) == 1
    assert packets[0].status is ContradictionStatus.SCOPE_SEPARATED


def test_non_overlapping_numeric_bounds_are_a_material_conflict() -> None:
    from research_tree.contradictions import ContradictionStatus, derive_contradiction_packets

    packets = derive_contradiction_packets(
        (
            _claim(claim_id="claim-upper", value="<=10"),
            _claim(claim_id="claim-lower", value=">=20"),
        )
    )

    assert packets[0].status is ContradictionStatus.CONTESTED
    assert packets[0].conflicting_values == ("<=10", ">=20")


def test_many_derivative_claims_do_not_outvote_one_counterexample() -> None:
    from research_tree.contradictions import ContradictionStatus, derive_contradiction_packets

    claims = tuple(_claim(claim_id=f"claim-positive-{index}", value="feature-x") for index in range(10)) + (
        _claim(claim_id="claim-counterexample", value="feature-x", polarity="negative"),
    )

    packets = derive_contradiction_packets(claims)

    assert len(packets) == 1
    assert packets[0].status is ContradictionStatus.CONTESTED
    assert packets[0].claim_ids == tuple(sorted(claim.claim_id for claim in claims))


def test_slot_detection_selects_each_conflict_when_findings_contain_multiple_groups(tmp_path) -> None:
    from test_feedback_rounds import correction_context

    from research_tree.domain import ArtifactRef

    ledger, coordinator, state, _, _ = correction_context(tmp_path)
    first = ledger.append_artifact(
        "run-correction",
        "finding-multiple-positive",
        "finding-pack",
        {
            "blueprint_target_id": "target-multiple",
            "decision_slot_id": "slot-1",
            "claims": [
                _claim_payload(claim_id="claim-multiple-a-positive", polarity="positive"),
                {**_claim_payload(claim_id="claim-multiple-b-positive", polarity="positive"), "subject": "second"},
            ],
        },
        parent_refs=(ArtifactRef(state.round_id, state.id, state.revision),),
        expected_revision=ledger.get_revision("run-correction"),
    )
    ledger.append_artifact(
        "run-correction",
        "finding-multiple-negative",
        "finding-pack",
        {
            "blueprint_target_id": "target-multiple",
            "decision_slot_id": "slot-1",
            "claims": [
                _claim_payload(claim_id="claim-multiple-a-negative", polarity="negative"),
                {**_claim_payload(claim_id="claim-multiple-b-negative", polarity="negative"), "subject": "second"},
            ],
        },
        parent_refs=(ArtifactRef(first.round_id, first.id, first.revision),),
        expected_revision=ledger.get_revision("run-correction"),
    )

    applied = coordinator.detect_and_apply_contradictions(
        run_id="run-correction",
        blueprint_target_id="target-multiple",
        decision_slot_id="slot-1",
        expected_revision=ledger.get_revision("run-correction"),
    )

    assert len(applied) == 2
    packets = [item for item in ledger.load_run("run-correction").artifacts if item.kind == "contradiction-packet"]
    assert {tuple(item.payload["claim_ids"]) for item in packets} == {
        ("claim-multiple-a-negative", "claim-multiple-a-positive"),
        ("claim-multiple-b-negative", "claim-multiple-b-positive"),
    }


def test_conflict_quarantine_survives_restart_and_recovers_lease(tmp_path) -> None:
    from test_feedback_rounds import correction_context

    from research_tree import ResearchRunCoordinator, RunLedger
    from research_tree.domain import ArtifactRef

    ledger, coordinator, state, _, _ = correction_context(tmp_path)
    first = ledger.append_artifact(
        "run-correction",
        "finding-restart-a",
        "finding-pack",
        {"claims": [_claim_payload(claim_id="claim-restart-a", polarity="positive")]},
        parent_refs=(ArtifactRef(state.round_id, state.id, state.revision),),
        expected_revision=ledger.get_revision("run-correction"),
    )
    second = ledger.append_artifact(
        "run-correction",
        "finding-restart-b",
        "finding-pack",
        {"claims": [_claim_payload(claim_id="claim-restart-b", polarity="negative")]},
        parent_refs=(ArtifactRef(first.round_id, first.id, first.revision),),
        expected_revision=ledger.get_revision("run-correction"),
    )
    lease = ledger.append_artifact(
        "run-correction",
        "lease-behind-conflict",
        "attempt-lease",
        {"attempt_id": "attempt-behind-conflict", "status": "active"},
        parent_refs=(ArtifactRef(second.round_id, second.id, second.revision),),
        expected_revision=ledger.get_revision("run-correction"),
    )
    coordinator.apply_contradiction(
        run_id="run-correction",
        contradiction_id="contradiction-restart",
        finding_refs=(
            ArtifactRef(first.round_id, first.id, first.revision),
            ArtifactRef(second.round_id, second.id, second.revision),
        ),
        reason="The evidence directly conflicts.",
        expected_revision=ledger.get_revision("run-correction"),
    )

    restarted = ResearchRunCoordinator(RunLedger(ledger.workspace))

    assert ArtifactRef(lease.round_id, lease.id, lease.revision) in restarted._quarantined_refs("run-correction")
    assert restarted.recover("run-correction")["quarantined_attempts"] == ["attempt-behind-conflict"]


def test_packet_retracts_durable_beliefs_and_pending_actions(tmp_path) -> None:
    from test_feedback_rounds import correction_context

    from research_tree.domain import ArtifactRef
    from research_tree.durable_interaction_state import DurableInteractionController
    from research_tree.interaction_state import InteractionEvent

    controller = DurableInteractionController.initialize(
        tmp_path / "project", project_id="topic", run_id="run-correction"
    )
    controller.submit(
        InteractionEvent.agent_assumption(
            event_id="assume-positive",
            assumption_id="claim-durable-positive",
            statement="Use the positive claim.",
            pending_actions=("publish",),
        ),
        expected_revision=0,
    )
    controller.propose_evidence("claim-durable-positive", "Positive claim.", admitted=True, expected_revision=1)
    ledger, coordinator, state, _, _ = correction_context(tmp_path / "ledger")
    first = ledger.append_artifact(
        "run-correction",
        "finding-durable-positive",
        "finding-pack",
        {"claims": [_claim_payload(claim_id="claim-durable-positive", polarity="positive")]},
        parent_refs=(ArtifactRef(state.round_id, state.id, state.revision),),
        expected_revision=ledger.get_revision("run-correction"),
    )
    second = ledger.append_artifact(
        "run-correction",
        "finding-durable-negative",
        "finding-pack",
        {"claims": [_claim_payload(claim_id="claim-durable-negative", polarity="negative")]},
        parent_refs=(ArtifactRef(first.round_id, first.id, first.revision),),
        expected_revision=ledger.get_revision("run-correction"),
    )

    coordinator.apply_contradiction(
        run_id="run-correction",
        contradiction_id="contradiction-durable",
        finding_refs=(
            ArtifactRef(first.round_id, first.id, first.revision),
            ArtifactRef(second.round_id, second.id, second.revision),
        ),
        reason="The evidence directly conflicts.",
        expected_revision=ledger.get_revision("run-correction"),
        durable_controller=controller,
    )

    durable = controller.load()
    assert durable.factual_beliefs == {}
    assert durable.state.agent.pending_actions == ()
    assert durable.pending_actions == {}


def test_packet_retry_recovers_after_durable_retraction_fault(tmp_path, monkeypatch) -> None:
    import pytest
    from test_feedback_rounds import correction_context

    from research_tree.domain import ArtifactRef
    from research_tree.durable_interaction_state import DurableInteractionController
    from research_tree.interaction_state import InteractionEvent

    controller = DurableInteractionController.initialize(
        tmp_path / "project", project_id="topic", run_id="run-correction"
    )
    controller.submit(
        InteractionEvent.agent_assumption(
            event_id="assume-retry",
            assumption_id="claim-retry-positive",
            statement="Use the positive claim.",
            pending_actions=("publish",),
        ),
        expected_revision=0,
    )
    ledger, coordinator, state, _, _ = correction_context(tmp_path / "ledger")
    first = ledger.append_artifact(
        "run-correction",
        "finding-retry-positive",
        "finding-pack",
        {"claims": [_claim_payload(claim_id="claim-retry-positive", polarity="positive")]},
        parent_refs=(ArtifactRef(state.round_id, state.id, state.revision),),
        expected_revision=ledger.get_revision("run-correction"),
    )
    second = ledger.append_artifact(
        "run-correction",
        "finding-retry-negative",
        "finding-pack",
        {"claims": [_claim_payload(claim_id="claim-retry-negative", polarity="negative")]},
        parent_refs=(ArtifactRef(first.round_id, first.id, first.revision),),
        expected_revision=ledger.get_revision("run-correction"),
    )
    original = controller.contest_evidence_set
    monkeypatch.setattr(
        controller, "contest_evidence_set", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("fault"))
    )
    with pytest.raises(RuntimeError, match="fault"):
        coordinator.apply_contradiction(
            run_id="run-correction",
            contradiction_id="contradiction-retry",
            finding_refs=(
                ArtifactRef(first.round_id, first.id, first.revision),
                ArtifactRef(second.round_id, second.id, second.revision),
            ),
            reason="The evidence directly conflicts.",
            expected_revision=ledger.get_revision("run-correction"),
            durable_controller=controller,
        )
    assert any(item.id == "contradiction-retry" for item in ledger.load_run("run-correction").artifacts)
    monkeypatch.setattr(controller, "contest_evidence_set", original)

    coordinator.apply_contradiction(
        run_id="run-correction",
        contradiction_id="contradiction-retry",
        finding_refs=(
            ArtifactRef(first.round_id, first.id, first.revision),
            ArtifactRef(second.round_id, second.id, second.revision),
        ),
        reason="The evidence directly conflicts.",
        expected_revision=ledger.get_revision("run-correction"),
        durable_controller=controller,
    )

    assert controller.load().state.agent.pending_actions == ()


def test_contradiction_retraction_rolls_back_as_one_ledger_transaction(tmp_path, monkeypatch) -> None:
    import pytest
    from test_feedback_rounds import correction_context

    from research_tree.domain import ArtifactRef

    ledger, coordinator, state, _, _ = correction_context(tmp_path)
    first = ledger.append_artifact(
        "run-correction",
        "finding-a",
        "finding-pack",
        {"claims": [_claim_payload(claim_id="claim-a", polarity="positive")]},
        parent_refs=(ArtifactRef(state.round_id, state.id, state.revision),),
        expected_revision=ledger.get_revision("run-correction"),
    )
    second = ledger.append_artifact(
        "run-correction",
        "finding-b",
        "finding-pack",
        {"claims": [_claim_payload(claim_id="claim-b", polarity="negative")]},
        parent_refs=(ArtifactRef(first.round_id, first.id, first.revision),),
        expected_revision=ledger.get_revision("run-correction"),
    )
    prior_revision = ledger.get_revision("run-correction")
    monkeypatch.setattr(ledger, "_before_commit", lambda: (_ for _ in ()).throw(RuntimeError("injected")))

    with pytest.raises(RuntimeError, match="injected"):
        coordinator.apply_contradiction(
            run_id="run-correction",
            contradiction_id="contradiction-rollback",
            finding_refs=(
                ArtifactRef(first.round_id, first.id, first.revision),
                ArtifactRef(second.round_id, second.id, second.revision),
            ),
            reason="The pair conflicts.",
            expected_revision=prior_revision,
        )

    assert ledger.get_revision("run-correction") == prior_revision
    assert not any(item.kind == "contradiction-packet" for item in ledger.load_run("run-correction").artifacts)
