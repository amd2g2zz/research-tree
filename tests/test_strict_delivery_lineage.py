from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from test_readiness import greenfield_package

from research_tree import (
    ArtifactRef,
    CanonicalDecisionLedgerCompiler,
    CanonicalDeliveryCompiler,
    CanonicalFindingPackCompiler,
    ContentAddressedStore,
    EvidenceAnchor,
    EvidenceArtifact,
    EvidenceRepository,
    EvidenceResolver,
    DeliveryCompiler,
    InvalidDeliveryError,
    LedgerConflictError,
    LedgerIntegrityError,
    RunLedger,
)
from research_tree.domain import thaw_json
from research_tree.work_items import WORK_ITEM_KIND
def _migrate_run_store(source_store, round_record, ledger: RunLedger) -> None:
    ledger.create_run(round_record.id)
    source = source_store.load_round(round_record.id).artifacts
    copied: set[tuple[str, int]] = set()
    while len(copied) < len(source):
        progressed = False
        for artifact in source:
            key = (artifact.id, artifact.revision)
            if key in copied or any(
                (parent.artifact_id, parent.revision) not in copied
                and parent.round_id == round_record.id
                for parent in artifact.parent_refs
            ):
                continue
            result = ledger.append_artifact(
                artifact.round_id,
                artifact.id,
                artifact.kind,
                thaw_json(artifact.payload),
                parent_refs=artifact.parent_refs,
                expected_revision=ledger.get_revision(round_record.id),
            )
            assert result.revision == artifact.revision
            copied.add(key)
            progressed = True
        assert progressed, "source artifact graph must be topologically copyable"
def _evidence_artifact(
    run_id: str,
    evidence_id: str,
    digest: str,
    size: int,
    *,
    revision: int = 1,
) -> EvidenceArtifact:
    return EvidenceArtifact(
        evidence_id=evidence_id,
        run_id=run_id,
        revision=revision,
        media_type="text/plain",
        locator={"url": "https://example.invalid/strict-source"},
        content_digest=digest,
        size_bytes=size,
        acquired_at=datetime.now(timezone.utc).isoformat(),
        acquisition_method="fixture",
        provenance_group="fixture-source",
        applicability="direct support",
        confidence="high",
        limitations=(),
        status="active",
        extractor_version="reader-1",
        evidence_class="source",
    )
def _strict_anchor(reference: ArtifactRef, digest: str) -> EvidenceAnchor:
    return EvidenceAnchor(
        artifact_ref=reference,
        artifact_digest=digest,
        artifact_revision=reference.revision,
        selector_type="line",
        selector_value={"start": 1, "end": 1},
        extractor_version="reader-1",
        applicability="direct support",
        confidence="high",
        limitations=(),
    )
def _readiness_payload(package: ArtifactRef) -> dict[str, object]:
    return {
        "technical_package_ref": package.to_dict(),
        "delivery_readiness": {
            "risk_tier": "default",
            "gates": {
                "intent_alignment": "pass",
                "decision_closure": "pass",
                "traceability": "pass",
                "repository_fit": "not_applicable",
                "implementation_readiness": "pass",
                "operational_quality": "pass",
            },
            "findings": [],
            "next_work_item_ids": [],
        },
        "diagnostics": [],
        "repository_anchor_checks": [],
        "source_refs": [],
    }
def _ref(fixture, key: str) -> ArtifactRef:
    artifact = fixture[key]
    if isinstance(artifact, ArtifactRef):
        return artifact
    return ArtifactRef(fixture["round_id"], artifact.id, artifact.revision)
def _append(fixture, artifact_id: str, kind: str, payload, parent_refs=()):
    ledger = fixture["ledger"]
    return ledger.append_artifact(
        fixture["round_id"],
        artifact_id,
        kind,
        payload,
        parent_refs=parent_refs,
        expected_revision=ledger.get_revision(fixture["round_id"]),
    )
def _append_finding(fixture, finding_id: str, payload, parent_refs):
    return _append(fixture, finding_id, "finding-pack", payload, parent_refs)
def _append_decision(fixture, decision_id: str, payload, parent_refs):
    return _append(fixture, decision_id, "decision-ledger-entry", payload, parent_refs)
def _forged_finding_decision(
    fixture, name: str, *, finding_has_evidence: bool, decision_has_evidence: bool
):
    target_ref, evidence_ref = _ref(fixture, "target"), _ref(fixture, "evidence")
    finding_payload = thaw_json(fixture["finding"].payload)
    finding_payload["id"] = f"finding-{name}"
    finding = _append_finding(
        fixture,
        finding_payload["id"],
        finding_payload,
        (target_ref, evidence_ref) if finding_has_evidence else (target_ref,),
    )
    decision_payload = thaw_json(fixture["decision"].payload)
    decision_payload.update(
        {"id": f"decision-{name}", "anchors": [{"kind": "finding", "ref": finding.id}]}
    )
    parents = (target_ref, ArtifactRef(finding.round_id, finding.id, finding.revision))
    return _append_decision(
        fixture, decision_payload["id"], decision_payload, parents + ((evidence_ref,) if decision_has_evidence else ())
    )
def _assert_no_outputs(fixture, name: str) -> None:
    assert not any(
        item.id in {f"technical-{name}", f"human-{name}"}
        for item in fixture["ledger"].load_run(fixture["round_id"]).artifacts
    )
def _new_batch_ledger(tmp_path: Path, name: str) -> RunLedger:
    ledger = RunLedger(tmp_path / name)
    ledger.initialize()
    ledger.create_run("batch-run")
    return ledger
def _fixture(tmp_path: Path):
    source_store, round_record, seed_package = greenfield_package(tmp_path / "source")
    ledger = RunLedger(tmp_path / "canonical")
    _migrate_run_store(source_store, round_record, ledger)
    traceability = seed_package.payload["document"]["traceability"]
    brief = ledger.get_artifact(ArtifactRef.from_dict(traceability["working_brief"]))
    model = ledger.get_artifact(ArtifactRef.from_dict(traceability["intent_model"]))
    target = ledger.get_artifact(ArtifactRef.from_dict(traceability["blueprint_target"]))
    work = next(
        item
        for item in ledger.load_run(round_record.id).artifacts
        if item.kind == WORK_ITEM_KIND and item.payload.get("blueprint_target_id") == target.id
    )
    legacy_decision = ledger.get_artifact(ArtifactRef(round_record.id, "decision-greenfield", 1))

    cas = ContentAddressedStore(tmp_path / "cas")
    content = cas.ingest(b"strict source line\n", "text/plain")
    evidence = EvidenceRepository(ledger, cas).record(
        _evidence_artifact(round_record.id, "strict-source", content.digest, content.byte_size),
        content,
        expected_run_revision=ledger.get_revision(round_record.id),
    )
    resolver = EvidenceResolver.from_ledger(ledger, cas, workspace=tmp_path / "cas")
    finding = CanonicalFindingPackCompiler(ledger, resolver).compile(
        round_id=round_record.id,
        finding_id="finding-strict",
        work_item=work,
        observations=[
            {
                "claim": "The strict source supports the selected option.",
                "anchor": _strict_anchor(evidence, content.digest).to_dict(),
                "applicability": "the selected fixture option",
                "confidence": "high",
                "limitation": "fixture evidence only",
            }
        ],
        option_effects=[{"option": "new-worker", "effect": "supports"}],
        implementation_implications=["Create the isolated component."],
        remaining_uncertainties=[],
        expected_revision=ledger.get_revision(round_record.id),
    )
    decision_data = thaw_json(legacy_decision.payload)
    decision = CanonicalDecisionLedgerCompiler(ledger, resolver).converge(
        round_id=round_record.id,
        decision_id="decision-strict",
        blueprint_target=target,
        decision_slot_id=decision_data["decision_slot_id"],
        finding_packs=[finding],
        status=decision_data["status"],
        selected_option=decision_data["selected_option"],
        alternatives=decision_data["alternatives"],
        anchors=[{"kind": "finding", "ref": finding.id}],
        design_consequence=decision_data["design_consequence"],
        repository_touchpoints=decision_data["repository_touchpoints"],
        validation=decision_data["validation"],
        change_tasks=decision_data["change_tasks"],
        assumptions=decision_data["assumptions"],
        fallback=decision_data["fallback"],
        reversal_condition=decision_data["reversal_condition"],
        revision_reason="Strict delivery fixture.",
        expected_revision=ledger.get_revision(round_record.id),
    )
    seed_ref = ArtifactRef(round_record.id, seed_package.id, seed_package.revision)
    readiness = _readiness_payload(seed_ref)["delivery_readiness"]
    return {
        "ledger": ledger,
        "resolver": resolver,
        "round_id": round_record.id,
        "brief": brief,
        "model": model,
        "target": target,
        "decision": decision,
        "finding": finding,
        "readiness": readiness,
        "evidence": evidence,
        "expected_revision": ledger.get_revision(round_record.id),
    }
def _append_p1_target(fixture):
    target_payload = thaw_json(fixture["target"].payload)
    p1_slot = thaw_json(target_payload["slots"][0])
    p1_slot.update(
        {
            "id": "slot-observability",
            "priority": "P1",
            "alternatives": ["structured-logging", "minimal-logging"],
        }
    )
    target_payload["slots"].append(p1_slot)
    target = _append(
        fixture,
        fixture["target"].id,
        "blueprint-target",
        target_payload,
        fixture["target"].parent_refs,
    )
    target_ref = ArtifactRef(fixture["round_id"], target.id, target.revision)
    evidence_ref = _ref(fixture, "evidence")
    return target, target_ref, evidence_ref
def _compile(
    fixture,
    name: str,
    *,
    decision_entries=None,
    blueprint_target=None,
    readiness=None,
    expected_revision=None,
):
    ledger = fixture["ledger"]
    return CanonicalDeliveryCompiler(ledger, fixture["resolver"]).compile(
        round_id=fixture["round_id"],
        technical_package_id=f"technical-{name}",
        human_brief_id=f"human-{name}",
        working_brief=fixture["brief"],
        blueprint_target=fixture["target"] if blueprint_target is None else blueprint_target,
        decision_entries=[fixture["decision"]] if decision_entries is None else decision_entries,
        readiness=fixture["readiness"] if readiness is None else readiness,
        expected_revision=(
            ledger.get_revision(fixture["round_id"])
            if expected_revision is None
            else expected_revision
        ),
    )
def test_canonical_delivery_preserves_exact_evidence_lineage(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    result = _compile(fixture, "strict", expected_revision=fixture["expected_revision"])
    evidence_ref = _ref(fixture, "evidence")
    assert evidence_ref in result.technical_package.parent_refs
    assert evidence_ref in result.human_brief.parent_refs
    assert "evidence:round-delivery/strict-source@1#line" in result.technical_package.payload["markdown"]
def test_canonical_delivery_rejects_stale_evidence_before_any_output(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    ledger = fixture["ledger"]
    stale_revision = ledger.get_revision(fixture["round_id"])
    content_store = fixture["resolver"].store
    replacement = content_store.ingest(b"replacement source\n", "text/plain")
    EvidenceRepository(ledger, content_store).record(
        _evidence_artifact(
            fixture["round_id"],
            "strict-source",
            replacement.digest,
            replacement.byte_size,
            revision=2,
        ),
        replacement,
        expected_run_revision=ledger.get_revision(fixture["round_id"]),
    )

    with pytest.raises(InvalidDeliveryError, match="stale|evidence"):
        _compile(fixture, "stale", expected_revision=stale_revision)
    _assert_no_outputs(fixture, "stale")
def test_canonical_delivery_rejects_foreign_resolver(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    foreign_ledger = RunLedger(tmp_path / "foreign")
    foreign_ledger.initialize()
    foreign_cas = ContentAddressedStore(tmp_path / "foreign-cas")
    foreign_resolver = EvidenceResolver.from_ledger(foreign_ledger, foreign_cas)
    with pytest.raises(InvalidDeliveryError, match="matching|ledger"):
        CanonicalDeliveryCompiler(fixture["ledger"], foreign_resolver)
def test_canonical_delivery_rejects_malformed_readiness_before_any_output(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    with pytest.raises(InvalidDeliveryError, match="readiness"):
        _compile(
            fixture,
            "bad-readiness",
            readiness={"risk_tier": "default"},
            expected_revision=fixture["expected_revision"],
        )
    _assert_no_outputs(fixture, "bad-readiness")
@pytest.mark.parametrize(
    ("field", "value", "message", "suffix"),
    (
        ("blueprint_target_id", "foreign-target", "exact Blueprint Target", "target"),
        ("decision_slot_id", "foreign-slot", "absent Decision Slot", "slot"),
    ),
)
def test_canonical_delivery_rejects_foreign_target_or_slot_before_any_output(
    tmp_path: Path,
    field: str,
    value: str,
    message: str,
    suffix: str,
) -> None:
    fixture = _fixture(tmp_path)
    decision_payload = thaw_json(fixture["decision"].payload)
    decision_payload["id"] = f"decision-{suffix}"
    decision_payload[field] = value
    forged = _append_decision(fixture, f"decision-{suffix}", decision_payload, fixture["decision"].parent_refs)

    with pytest.raises(InvalidDeliveryError, match=message):
        _compile(
            fixture,
            suffix,
            decision_entries=[forged],
            expected_revision=fixture["ledger"].get_revision(fixture["round_id"]),
        )
    _assert_no_outputs(fixture, suffix)
def test_canonical_delivery_rejects_finding_without_direct_evidence_parent(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    ledger = fixture["ledger"]
    forged_decision = _forged_finding_decision(
        fixture, "missing-parent", finding_has_evidence=False, decision_has_evidence=True
    )

    with pytest.raises(InvalidDeliveryError, match="parent lineage"):
        _compile(
            fixture,
            "missing-parent",
            decision_entries=[forged_decision],
            expected_revision=ledger.get_revision(fixture["round_id"]),
        )
    _assert_no_outputs(fixture, "missing-parent")
def test_canonical_delivery_rejects_decision_without_direct_evidence_parent(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    ledger = fixture["ledger"]
    decision = _forged_finding_decision(
        fixture, "missing-decision-evidence", finding_has_evidence=True, decision_has_evidence=False
    )

    with pytest.raises(InvalidDeliveryError, match="lacks evidence parent"):
        _compile(
            fixture,
            "missing-decision-evidence",
            decision_entries=[decision],
            expected_revision=ledger.get_revision(fixture["round_id"]),
        )
def test_canonical_delivery_rejects_cross_run_finding_with_a_colliding_identity(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    ledger = fixture["ledger"]
    ledger.create_run("foreign-round")
    foreign_finding = ledger.append_artifact(
        "foreign-round",
        fixture["finding"].id,
        "finding-pack",
        {"foreign": True},
        expected_revision=0,
    )
    target_ref, evidence_ref = _ref(fixture, "target"), _ref(fixture, "evidence")
    payload = thaw_json(fixture["decision"].payload)
    payload["id"] = "decision-foreign-parent"
    forged = _append_decision(
        fixture,
        "decision-foreign-parent",
        payload,
        (
            target_ref,
            ArtifactRef(foreign_finding.round_id, foreign_finding.id, foreign_finding.revision),
            evidence_ref,
        ),
    )

    with pytest.raises(InvalidDeliveryError, match="foreign parent lineage"):
        _compile(
            fixture,
            "foreign-parent",
            decision_entries=[forged],
            expected_revision=ledger.get_revision(fixture["round_id"]),
        )
def test_canonical_delivery_rejects_finding_from_a_different_p1_slot(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    ledger = fixture["ledger"]
    target, target_ref, evidence_ref = _append_p1_target(fixture)
    finding_payload = thaw_json(fixture["finding"].payload)
    finding_payload["id"] = "finding-slot-mismatch"
    finding = _append_finding(fixture, "finding-slot-mismatch", finding_payload, (target_ref, evidence_ref))
    payload = thaw_json(fixture["decision"].payload)
    payload.update(
        {
            "id": "decision-observability",
            "decision_slot_id": "slot-observability",
            "blueprint_target_id": target.id,
            "selected_option": "structured-logging",
            "alternatives": [
                {
                    "option": "minimal-logging",
                    "disposition": "deferred",
                    "reason": "The isolated finding cannot decide observability.",
                }
            ],
            "anchors": [{"kind": "finding", "ref": finding.id}],
        }
    )
    forged = _append_decision(
        fixture,
        "decision-observability",
        payload,
        (
            target_ref,
            ArtifactRef(finding.round_id, finding.id, finding.revision),
            evidence_ref,
        ),
    )

    with pytest.raises(InvalidDeliveryError, match="different Decision Slot"):
        _compile(
            fixture,
            "slot-mismatch",
            blueprint_target=target,
            decision_entries=[forged],
            expected_revision=ledger.get_revision(fixture["round_id"]),
        )
def test_canonical_delivery_rejects_strict_finding_without_observations(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    ledger = fixture["ledger"]
    target_ref, evidence_ref = _ref(fixture, "target"), _ref(fixture, "evidence")
    finding_payload = thaw_json(fixture["finding"].payload)
    finding_payload.update({"id": "finding-empty", "observations": []})
    finding = _append_finding(fixture, "finding-empty", finding_payload, (target_ref, evidence_ref))
    decision_payload = thaw_json(fixture["decision"].payload)
    decision_payload.update(
        {"id": "decision-empty", "anchors": [{"kind": "finding", "ref": finding.id}]}
    )
    decision = _append_decision(
        fixture,
        "decision-empty",
        decision_payload,
        (target_ref, ArtifactRef(finding.round_id, finding.id, finding.revision), evidence_ref),
    )

    with pytest.raises(InvalidDeliveryError, match="requires at least one strict observation"):
        _compile(
            fixture,
            "empty-finding",
            decision_entries=[decision],
            expected_revision=ledger.get_revision(fixture["round_id"]),
        )
def test_canonical_delivery_rejects_selected_p1_decision_without_a_finding(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    ledger = fixture["ledger"]
    target, target_ref, _ = _append_p1_target(fixture)
    payload = thaw_json(fixture["decision"].payload)
    payload.update(
        {
            "id": "decision-p1-empty",
            "decision_slot_id": "slot-observability",
            "blueprint_target_id": target.id,
            "selected_option": "structured-logging",
            "alternatives": [
                {
                    "option": "minimal-logging",
                    "disposition": "deferred",
                    "reason": "Evidence has not yet been collected.",
                }
            ],
            "anchors": [],
        }
    )
    decision = _append_decision(fixture, "decision-p1-empty", payload, (target_ref,))

    with pytest.raises(InvalidDeliveryError, match="requires a linked strict Finding Pack"):
        _compile(
            fixture,
            "p1-empty",
            blueprint_target=target,
            decision_entries=[decision],
            expected_revision=ledger.get_revision(fixture["round_id"]),
        )
def test_canonical_delivery_rejects_selected_p1_decision_without_anchor_or_support(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    ledger = fixture["ledger"]
    target, target_ref, evidence_ref = _append_p1_target(fixture)
    finding_payload = thaw_json(fixture["finding"].payload)
    finding_payload.update(
        {
            "id": "finding-p1",
            "decision_slot_id": "slot-observability",
            "option_effects": [{"option": "minimal-logging", "effect": "supports"}],
        }
    )
    finding = _append_finding(fixture, "finding-p1", finding_payload, (target_ref, evidence_ref))
    parent_refs = (target_ref, ArtifactRef(finding.round_id, finding.id, finding.revision), evidence_ref)
    base = thaw_json(fixture["decision"].payload)
    base.update(
        {
            "decision_slot_id": "slot-observability",
            "blueprint_target_id": target.id,
            "selected_option": "structured-logging",
            "alternatives": [
                {
                    "option": "minimal-logging",
                    "disposition": "deferred",
                    "reason": "The finding only supports the unselected option.",
                }
            ],
        }
    )
    no_anchor_payload = thaw_json(base)
    no_anchor_payload.update({"id": "decision-p1-no-anchor", "anchors": []})
    no_anchor = _append_decision(fixture, "decision-p1-no-anchor", no_anchor_payload, parent_refs)
    with pytest.raises(InvalidDeliveryError, match="requires a linked Finding Pack anchor"):
        _compile(
            fixture,
            "p1-no-anchor",
            blueprint_target=target,
            decision_entries=[no_anchor],
            expected_revision=ledger.get_revision(fixture["round_id"]),
        )
    no_support_payload = thaw_json(base)
    no_support_payload.update(
        {
            "id": "decision-p1-no-support",
            "anchors": [{"kind": "finding", "ref": finding.id}],
        }
    )
    no_support = _append_decision(fixture, "decision-p1-no-support", no_support_payload, parent_refs)
    with pytest.raises(InvalidDeliveryError, match="support effect for selected_option"):
        _compile(
            fixture,
            "p1-no-support",
            blueprint_target=target,
            decision_entries=[no_support],
            expected_revision=ledger.get_revision(fixture["round_id"]),
        )
@pytest.mark.parametrize(
    ("artifact_key", "kind", "message"),
    (
        ("target", "blueprint-target", "Blueprint Target revision is stale"),
        ("finding", "finding-pack", "Finding Pack revision is stale"),
    ),
)
def test_canonical_delivery_rejects_stale_target_or_finding_revision(
    tmp_path: Path,
    artifact_key: str,
    kind: str,
    message: str,
) -> None:
    fixture = _fixture(tmp_path)
    source = fixture[artifact_key]
    _append(fixture, source.id, kind, thaw_json(source.payload), source.parent_refs)

    with pytest.raises(InvalidDeliveryError, match=message):
        _compile(
            fixture,
            f"stale-{artifact_key}",
            expected_revision=fixture["ledger"].get_revision(fixture["round_id"]),
        )
def test_canonical_delivery_rejects_stale_run_revision_without_output_pair(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    ledger = fixture["ledger"]
    stale_revision = fixture["expected_revision"]
    _append(fixture, "concurrent-note", "fixture", {"event": "concurrent writer"})
    current_revision = ledger.get_revision(fixture["round_id"])

    with pytest.raises(InvalidDeliveryError, match="stale run revision"):
        _compile(fixture, "stale-revision", expected_revision=stale_revision)
    assert ledger.get_revision(fixture["round_id"]) == current_revision
    _assert_no_outputs(fixture, "stale-revision")
def test_legacy_delivery_compiler_does_not_accept_canonical_storage(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    with pytest.raises(InvalidDeliveryError, match="RunStore"):
        DeliveryCompiler(fixture["ledger"])
def test_ledger_batch_append_rolls_back_both_outputs_on_commit_failure(tmp_path: Path, monkeypatch) -> None:
    ledger = _new_batch_ledger(tmp_path, "batch")
    before_events = ledger.load_run("batch-run").lineage_events
    first_ref = ArtifactRef("batch-run", "first", 1)

    def fail_commit() -> None:
        raise RuntimeError("injected batch failure")

    monkeypatch.setattr(RunLedger, "_before_commit", staticmethod(fail_commit))
    with pytest.raises(RuntimeError, match="injected batch failure"):
        ledger.append_artifact_batch(
            "batch-run",
            (
                ("first", "fixture", {"value": 1}, ()),
                ("second", "fixture", {"value": 2}, (first_ref,)),
            ),
            expected_revision=0,
        )

    snapshot = ledger.load_run("batch-run")
    assert snapshot.artifacts == ()
    assert snapshot.lineage_events == before_events
    assert ledger.get_revision("batch-run") == 0
def test_ledger_batch_append_supports_ordered_parents_and_advances_once_per_artifact(
    tmp_path: Path,
) -> None:
    ledger = _new_batch_ledger(tmp_path, "ordered-batch")

    first, second = ledger.append_artifact_batch(
        "batch-run",
        (
            ("first", "fixture", {"value": 1}, ()),
            ("second", "fixture", {"value": 2}, (ArtifactRef("batch-run", "first", 1),)),
        ),
        expected_revision=0,
    )

    assert (first.id, first.revision) == ("first", 1)
    assert second.parent_refs == (ArtifactRef("batch-run", "first", 1),)
    assert ledger.get_revision("batch-run") == 2
def test_ledger_batch_append_assigns_distinct_revisions_for_repeated_artifact_id(
    tmp_path: Path,
) -> None:
    ledger = _new_batch_ledger(tmp_path, "repeated-batch")

    first, second = ledger.append_artifact_batch(
        "batch-run",
        (
            ("note", "fixture", {"value": 1}, ()),
            ("note", "fixture", {"value": 2}, ()),
        ),
        expected_revision=0,
    )

    assert ArtifactRef("batch-run", first.id, first.revision) != ArtifactRef(
        "batch-run", second.id, second.revision
    )
    assert (first.revision, second.revision) == (1, 2)
    assert ledger.get_revision("batch-run") == 2
def test_ledger_batch_append_rolls_back_when_second_entry_validation_fails(tmp_path: Path) -> None:
    ledger = _new_batch_ledger(tmp_path, "second-entry-failure")
    before_events = ledger.load_run("batch-run").lineage_events

    with pytest.raises(LedgerIntegrityError, match="parent does not exist"):
        ledger.append_artifact_batch(
            "batch-run",
            (
                ("first", "fixture", {"value": 1}, ()),
                ("second", "fixture", {"value": 2}, (ArtifactRef("batch-run", "missing", 1),)),
            ),
            expected_revision=0,
        )

    assert ledger.load_run("batch-run").artifacts == ()
    assert ledger.load_run("batch-run").lineage_events == before_events
    assert ledger.get_revision("batch-run") == 0
def test_ledger_batch_append_rejects_forward_parent_and_stale_revision(tmp_path: Path) -> None:
    ledger = _new_batch_ledger(tmp_path, "invalid-batch")

    with pytest.raises(LedgerIntegrityError, match="parent does not exist"):
        ledger.append_artifact_batch(
            "batch-run",
            (
                ("first", "fixture", {"value": 1}, (ArtifactRef("batch-run", "second", 1),)),
                ("second", "fixture", {"value": 2}, ()),
            ),
            expected_revision=0,
        )
    assert ledger.load_run("batch-run").artifacts == ()
    assert ledger.get_revision("batch-run") == 0

    ledger.append_artifact("batch-run", "existing", "fixture", {}, expected_revision=0)
    with pytest.raises(LedgerConflictError, match="stale run revision"):
        ledger.append_artifact_batch(
            "batch-run",
            (("third", "fixture", {"value": 3}, ()),),
            expected_revision=0,
        )
    assert [item.id for item in ledger.load_run("batch-run").artifacts] == ["existing"]
