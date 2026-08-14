from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from canonical_finding_fixture import canonical_context
from test_deliveries import (
    api as delivery_api,
    compile_deliveries,
    readiness as delivery_readiness,
    repository,
)

from research_tree import (
    ArtifactRef,
    CanonicalDecisionLedgerCompiler,
    CanonicalFindingPackCompiler,
    CanonicalReadinessVerifier,
    ContentAddressedStore,
    EvidenceAnchor,
    EvidenceArtifact,
    EvidenceRepository,
    EvidenceResolver,
    EvidenceValidationError,
    FindingPackCompiler,
    InvalidDecisionLedgerError,
    InvalidFindingPackError,
    InvalidReadinessError,
    ReadinessVerifier,
    RunLedger,
)
from research_tree.work_items import WORK_ITEM_KIND
from research_tree.domain import thaw_json
from research_tree.readiness import _strict_findings_are_authoritative


def _artifact(
    *, run_id: str, evidence_id: str, digest: str, size: int, locator: dict[str, str], revision: int = 1
) -> EvidenceArtifact:
    return EvidenceArtifact(
        evidence_id=evidence_id,
        run_id=run_id,
        revision=revision,
        media_type="text/plain",
        locator=locator,
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
        source_revision="source-a" if "path" in locator else None,
        evidence_class="source",
    )


def _anchor(reference: ArtifactRef, digest: str, *, selector: dict[str, int] | None = None) -> EvidenceAnchor:
    return EvidenceAnchor(
        artifact_ref=reference,
        artifact_digest=digest,
        artifact_revision=reference.revision,
        selector_type="line",
        selector_value=selector or {"start": 1, "end": 1},
        extractor_version="reader-1",
        applicability="direct support",
        confidence="high",
        limitations=(),
    )


def _environment(tmp_path: Path):
    ledger = RunLedger(tmp_path)
    ledger.initialize()
    ledger.create_run("run-strict")
    target = ledger.append_artifact(
        "run-strict",
        "target-one",
        "blueprint-target",
        {
            "slots": [
                {
                    "id": "slot-one",
                    "alternatives": ["option-a", "option-b"],
                    "priority": "P0",
                    "repository_touchpoints": [],
                }
            ]
        },
        expected_revision=0,
    )
    work = ledger.append_artifact(
        "run-strict",
        "work-one",
        WORK_ITEM_KIND,
        {"blueprint_target_id": target.id, "decision_slot_id": "slot-one"},
        parent_refs=(ArtifactRef("run-strict", target.id, target.revision),),
        expected_revision=1,
    )
    store = ContentAddressedStore(tmp_path)
    content = store.ingest(b"first line\nsecond line", "text/plain")
    evidence = _artifact(
        run_id="run-strict",
        evidence_id="source-one",
        digest=content.digest,
        size=content.byte_size,
        locator={"path": "src/module.py"},
    )
    reference = EvidenceRepository(ledger, store).record(
        evidence,
        content,
        expected_run_revision=2,
    )
    resolver = EvidenceResolver.from_ledger(
        ledger,
        store,
        workspace=tmp_path,
        repository_revisions={"src/module.py": "source-a"},
    )
    return ledger, store, target, work, content, evidence, reference, resolver


def _observation(anchor: EvidenceAnchor) -> dict[str, object]:
    return {
        "claim": "The bounded source supports option-a.",
        "anchor": anchor.to_dict(),
        "applicability": "direct support",
        "confidence": "high",
        "limitation": "fixture evidence only",
    }


def _converge(
    ledger,
    resolver,
    *,
    target,
    decision_id,
    findings,
    expected_revision,
    slot_id="slot-one",
    status="conditional",
    selected="option-a",
    change_tasks=(),
):
    return CanonicalDecisionLedgerCompiler(ledger, resolver).converge(
        round_id=target.round_id,
        decision_id=decision_id,
        blueprint_target=target,
        decision_slot_id=slot_id,
        finding_packs=findings,
        status=status,
        selected_option=selected,
        alternatives=[{"option": "option-b", "disposition": "deferred", "reason": "Needs further evidence."}],
        anchors=[{"kind": "finding", "ref": finding.id} for finding in findings],
        design_consequence="Use option-a behind a guard.",
        repository_touchpoints=[],
        validation={"kind": "test", "oracle": "fixture test passes"},
        change_tasks=change_tasks,
        assumptions=[],
        fallback="Keep option-b available.",
        reversal_condition="Contrary evidence appears.",
        revision_reason="Strict decision fixture.",
        expected_revision=expected_revision,
    )


def _raw_decision(ledger, decision_id, payload, parent_refs, expected_revision):
    return ledger.append_artifact(
        "run-strict",
        decision_id,
        "decision-ledger-entry",
        payload,
        parent_refs=parent_refs,
        expected_revision=expected_revision,
    )


def test_strict_resolver_requires_exact_current_lineage_and_source_revision(tmp_path: Path) -> None:
    ledger, store, _target, _work, content, evidence, reference, resolver = _environment(tmp_path)

    assert resolver.resolve(_anchor(reference, content.digest)).bytes == b"first line\nsecond line"
    restarted = EvidenceResolver.from_ledger(
        ledger,
        store,
        workspace=tmp_path,
        repository_revisions={"src/module.py": "source-a"},
    )
    assert restarted.resolve(_anchor(reference, content.digest)).artifact_ref == reference
    with pytest.raises(EvidenceValidationError, match="line count"):
        resolver.resolve(_anchor(reference, content.digest, selector={"start": 3, "end": 3}))

    second_content = store.ingest(b"replacement", "text/plain")
    EvidenceRepository(ledger, store).record(
        _artifact(
            run_id="run-strict",
            evidence_id=evidence.evidence_id,
            digest=second_content.digest,
            size=second_content.byte_size,
            locator={"path": "src/module.py"},
            revision=2,
        ),
        second_content,
        expected_run_revision=3,
    )
    with pytest.raises(EvidenceValidationError, match="stale"):
        resolver.resolve(_anchor(reference, content.digest))
    missing_revision_oracle = EvidenceResolver.from_ledger(ledger, store, workspace=tmp_path)
    with pytest.raises(EvidenceValidationError, match="source revision"):
        missing_revision_oracle.resolve(
            _anchor(ArtifactRef("run-strict", evidence.evidence_id, 2), second_content.digest)
        )


def test_strict_selector_rejects_reversed_fragments_and_repository_escape(tmp_path: Path) -> None:
    ledger, store, _target, _work, content, _evidence, reference, resolver = _environment(tmp_path)

    with pytest.raises(EvidenceValidationError, match="precedes"):
        EvidenceAnchor(
            artifact_ref=reference,
            artifact_digest=content.digest,
            artifact_revision=reference.revision,
            selector_type="fragment",
            selector_value={"start": 8, "end": 1},
            extractor_version="reader-1",
            applicability="direct support",
            confidence="high",
            limitations=(),
        )

    escaped = _artifact(
        run_id="run-strict",
        evidence_id="source-escape",
        digest=content.digest,
        size=content.byte_size,
        locator={"path": "../outside.py"},
    )
    escaped_ref = EvidenceRepository(ledger, store).record(
        escaped,
        content,
        expected_run_revision=3,
    )
    with pytest.raises(EvidenceValidationError, match="escapes workspace"):
        resolver.resolve(_anchor(escaped_ref, content.digest))

    with pytest.raises(EvidenceValidationError, match="metadata"):
        resolver.resolve(
            EvidenceAnchor(
                artifact_ref=reference,
                artifact_digest=content.digest,
                artifact_revision=reference.revision,
                selector_type="symbol",
                selector_value={"name": "missing"},
                extractor_version="reader-1",
                applicability="direct support",
                confidence="high",
                limitations=(),
            )
        )


def test_canonical_finding_and_decision_preserve_strict_evidence_parents(tmp_path: Path) -> None:
    ledger, _store, target, work, content, _evidence, reference, resolver = _environment(tmp_path)
    finding = CanonicalFindingPackCompiler(ledger, resolver).compile(
        round_id="run-strict",
        finding_id="finding-one",
        work_item=work,
        observations=[_observation(_anchor(reference, content.digest))],
        option_effects=[{"option": "option-a", "effect": "supports"}],
        implementation_implications=["Implement option-a."],
        remaining_uncertainties=[],
        expected_revision=3,
    )

    assert reference in finding.parent_refs
    decision = _converge(
        ledger,
        resolver,
        target=target,
        decision_id="decision-one",
        findings=[finding],
        expected_revision=4,
        change_tasks=[
            {
                "id": "task-one",
                "description": "Implement guard.",
                "acceptance_oracle": "fixture test passes",
                "repository_touchpoints": [],
            }
        ],
    )

    assert reference in decision.parent_refs
    replacement = _store.ingest(b"replacement evidence", "text/plain")
    EvidenceRepository(ledger, _store).record(
        _artifact(
            run_id="run-strict",
            evidence_id="source-one",
            digest=replacement.digest,
            size=replacement.byte_size,
            locator={"path": "src/module.py"},
            revision=2,
        ),
        replacement,
        expected_run_revision=5,
    )
    with pytest.raises(InvalidDecisionLedgerError, match="not resolvable"):
        _converge(
            ledger, resolver, target=target, decision_id="decision-stale", findings=[finding], expected_revision=6
        )


def test_canonical_selected_decision_requires_strict_finding_at_any_priority(tmp_path: Path) -> None:
    ledger, _store, _target, _work, _content, _evidence, _reference, resolver = _environment(tmp_path)
    low_target = ledger.append_artifact(
        "run-strict",
        "target-low",
        "blueprint-target",
        {
            "slots": [
                {
                    "id": "slot-low",
                    "alternatives": ["option-a", "option-b"],
                    "priority": "P1",
                    "repository_touchpoints": [],
                }
            ]
        },
        expected_revision=3,
    )
    with pytest.raises(InvalidDecisionLedgerError, match="requires at least one strict Finding Pack"):
        _converge(
            ledger,
            resolver,
            target=low_target,
            decision_id="decision-low",
            findings=[],
            expected_revision=4,
            slot_id="slot-low",
            status="selected",
        )


def test_strict_readiness_rejects_empty_finding_and_unlinked_selected_decision(tmp_path: Path) -> None:
    ledger, _store, target, work, content, _evidence, reference, resolver = _environment(tmp_path)
    empty_finding = ledger.append_artifact(
        "run-strict",
        "finding-empty",
        "finding-pack",
        {
            "blueprint_target_id": target.id,
            "decision_slot_id": "slot-one",
            "evidence_mode": "strict",
            "observations": [],
        },
        parent_refs=(ArtifactRef("run-strict", target.id, target.revision),),
        expected_revision=3,
    )
    unlinked_decision = _raw_decision(
        ledger,
        "decision-unlinked",
        {
            "blueprint_target_id": target.id,
            "decision_slot_id": "slot-one",
            "status": "selected",
        },
        (ArtifactRef("run-strict", target.id, target.revision),),
        4,
    )
    strict_finding = CanonicalFindingPackCompiler(ledger, resolver).compile(
        round_id="run-strict",
        finding_id="finding-valid",
        work_item=work,
        observations=[_observation(_anchor(reference, content.digest))],
        option_effects=[{"option": "option-a", "effect": "supports"}],
        implementation_implications=["Use the supported option."],
        remaining_uncertainties=[],
        expected_revision=5,
    )
    parent_refs = (
        ArtifactRef("run-strict", target.id, target.revision),
        ArtifactRef("run-strict", strict_finding.id, strict_finding.revision),
        reference,
    )
    mismatched_slot = _raw_decision(
        ledger,
        "decision-mismatched-slot",
        {
            "blueprint_target_id": target.id,
            "decision_slot_id": "slot-other",
            "status": "selected",
            "selected_option": "option-a",
        },
        parent_refs,
        6,
    )
    unsupported = _raw_decision(
        ledger,
        "decision-unsupported-option",
        {
            "blueprint_target_id": target.id,
            "decision_slot_id": "slot-one",
            "status": "conditional",
            "selected_option": "option-b",
        },
        parent_refs,
        7,
    )
    diagnostics: list[dict[str, object]] = []
    assert not _strict_findings_are_authoritative(
        [empty_finding, strict_finding],
        [unlinked_decision, mismatched_slot, unsupported],
        resolver,
        diagnostics,
        package_target=target,
    )
    assert any("no strict observations" in item["summary"] for item in diagnostics)
    assert any("strict Finding Pack parent lineage" in item["summary"] for item in diagnostics)
    assert any("do not share a Blueprint Target" in item["summary"] for item in diagnostics)
    assert any("support for its selected option" in item["summary"] for item in diagnostics)


def test_legacy_compiler_cannot_claim_strict_evidence_or_enter_canonical_decision(tmp_path: Path) -> None:
    ledger, _store, target, _work, _content, _evidence, _reference, _resolver = _environment(tmp_path)

    with pytest.raises(InvalidFindingPackError, match="CanonicalFindingPackCompiler"):
        FindingPackCompiler(object(), strict_evidence=True)

    legacy = ledger.append_artifact(
        "run-strict",
        "finding-legacy",
        "finding-pack",
        {
            "blueprint_target_id": target.id,
            "decision_slot_id": "slot-one",
            "evidence_mode": "legacy_unverified",
            "option_effects": [{"option": "option-a", "effect": "supports"}],
        },
        parent_refs=(ArtifactRef("run-strict", target.id, target.revision),),
        expected_revision=3,
    )
    with pytest.raises(InvalidDecisionLedgerError, match="strict evidence"):
        _converge(
            ledger, _resolver, target=target, decision_id="decision-legacy", findings=[legacy], expected_revision=4
        )


def test_canonical_ledger_cannot_use_non_strict_readiness_verifier(tmp_path: Path) -> None:
    ledger, _store, _target, _work, _content, _evidence, _reference, _resolver = _environment(tmp_path)

    with pytest.raises(InvalidReadinessError, match="matching ledger-backed"):
        ReadinessVerifier(ledger)


def _canonical_readiness_package(tmp_path: Path):
    repository(tmp_path / "repository")
    (
        ledger,
        resolver,
        round_record,
        _model,
        brief,
        target,
        work,
        finding,
        decision,
        _evidence,
        _anchor_value,
    ) = canonical_context(tmp_path)
    modules = delivery_api()
    modules["resolver"] = resolver
    readiness = delivery_readiness()
    readiness["gates"]["decision_closure"] = "pass"
    readiness["gates"]["implementation_readiness"] = "pass"
    package = compile_deliveries(
        modules,
        ledger,
        round_record,
        brief,
        target,
        [decision],
        readiness_input=readiness,
    ).technical_package
    return ledger, resolver, round_record, target, work, finding, decision, package


def test_strict_readiness_rejects_legacy_and_foreign_target_packages(tmp_path: Path) -> None:
    (
        ledger,
        resolver,
        round_record,
        target,
        work,
        finding,
        decision,
        strict_package,
    ) = _canonical_readiness_package(tmp_path)
    root = tmp_path / "repository"
    decision_data = thaw_json(decision.payload)
    strict_observation = thaw_json(finding.payload["observations"])[0]

    strict_readiness = CanonicalReadinessVerifier(ledger, resolver).verify(
        round_id=round_record.id,
        readiness_id="strict-readiness",
        technical_package=strict_package,
        repository_roots={"input-repository": root},
        expected_revision=ledger.get_revision(round_record.id),
    )
    strict_gates = strict_readiness.payload["delivery_readiness"]["gates"]
    assert strict_gates["decision_closure"] == "pass"
    assert strict_gates["implementation_readiness"] == "pass"

    legacy_finding_payload = thaw_json(finding.payload)
    legacy_finding_payload["evidence_mode"] = "legacy_unverified"
    legacy_finding = ledger.append_artifact(
        round_record.id,
        finding.id,
        finding.kind,
        legacy_finding_payload,
        parent_refs=finding.parent_refs,
        expected_revision=ledger.get_revision(round_record.id),
    )
    legacy_decision_payload = thaw_json(decision.payload)
    legacy_decision = ledger.append_artifact(
        round_record.id,
        decision.id,
        decision.kind,
        legacy_decision_payload,
        parent_refs=tuple(
            ArtifactRef(
                reference.round_id,
                reference.artifact_id,
                legacy_finding.revision if reference.artifact_id == legacy_finding.id else reference.revision,
            )
            for reference in decision.parent_refs
        ),
        expected_revision=ledger.get_revision(round_record.id),
    )
    legacy_document = deepcopy(thaw_json(strict_package.payload["document"]))
    legacy_document["research_findings"][0]["revision"] = legacy_finding.revision
    legacy_document["decision_records"][0]["revision"] = legacy_decision.revision
    legacy_document["traceability"]["finding_refs"][0]["revision"] = legacy_finding.revision
    legacy_document["traceability"]["decision_refs"][0]["revision"] = legacy_decision.revision
    legacy_package = ledger.append_artifact(
        round_record.id,
        strict_package.id,
        strict_package.kind,
        {"document": legacy_document, "markdown": strict_package.payload["markdown"]},
        parent_refs=tuple(
            ArtifactRef(
                reference.round_id,
                reference.artifact_id,
                legacy_finding.revision
                if reference.artifact_id == legacy_finding.id
                else legacy_decision.revision
                if reference.artifact_id == legacy_decision.id
                else reference.revision,
            )
            for reference in strict_package.parent_refs
        ),
        expected_revision=ledger.get_revision(round_record.id),
    )
    legacy_readiness = CanonicalReadinessVerifier(ledger, resolver).verify(
        round_id=round_record.id,
        readiness_id="legacy-readiness",
        technical_package=legacy_package,
        repository_roots={"input-repository": root},
        expected_revision=ledger.get_revision(round_record.id),
    )
    legacy_gates = legacy_readiness.payload["delivery_readiness"]["gates"]
    assert legacy_gates["decision_closure"] == "fail"
    assert legacy_gates["implementation_readiness"] == "fail"

    foreign_target_payload = deepcopy(thaw_json(target.payload))
    foreign_target_payload["id"] = "foreign-target"
    foreign_target = ledger.append_artifact(
        round_record.id,
        "foreign-target",
        "blueprint-target",
        foreign_target_payload,
        parent_refs=target.parent_refs,
        expected_revision=ledger.get_revision(round_record.id),
    )
    foreign_work_payload = thaw_json(work.payload)
    foreign_work_payload["id"] = "work-foreign"
    foreign_work_payload["blueprint_target_id"] = foreign_target.id
    foreign_work = ledger.append_artifact(
        round_record.id,
        "work-foreign",
        WORK_ITEM_KIND,
        foreign_work_payload,
        parent_refs=(ArtifactRef(round_record.id, foreign_target.id, foreign_target.revision),),
        expected_revision=ledger.get_revision(round_record.id),
    )
    foreign_finding = CanonicalFindingPackCompiler(ledger, resolver).compile(
        round_id=round_record.id,
        finding_id=finding.id,
        work_item=foreign_work,
        observations=[strict_observation],
        option_effects=thaw_json(finding.payload["option_effects"]),
        implementation_implications=["Create the isolated component."],
        remaining_uncertainties=[],
        expected_revision=ledger.get_revision(round_record.id),
    )
    foreign_decision = CanonicalDecisionLedgerCompiler(ledger, resolver).converge(
        round_id=round_record.id,
        decision_id=decision.id,
        blueprint_target=foreign_target,
        decision_slot_id=decision_data["decision_slot_id"],
        finding_packs=[foreign_finding],
        status=decision_data["status"],
        selected_option=decision_data["selected_option"],
        alternatives=decision_data["alternatives"],
        anchors=decision_data["anchors"],
        design_consequence=decision_data["design_consequence"],
        repository_touchpoints=decision_data["repository_touchpoints"],
        validation=decision_data["validation"],
        change_tasks=decision_data["change_tasks"],
        assumptions=decision_data["assumptions"],
        fallback=decision_data["fallback"],
        reversal_condition=decision_data["reversal_condition"],
        revision_reason="Foreign Target must not pass.",
        expected_revision=ledger.get_revision(round_record.id),
    )
    foreign_document = deepcopy(thaw_json(strict_package.payload["document"]))
    foreign_document["research_findings"][0]["revision"] = foreign_finding.revision
    foreign_document["decision_records"][0]["revision"] = foreign_decision.revision
    foreign_document["traceability"]["finding_refs"][0]["revision"] = foreign_finding.revision
    foreign_document["traceability"]["decision_refs"][0]["revision"] = foreign_decision.revision
    foreign_parent_refs = tuple(
        ArtifactRef(
            ref.round_id,
            ref.artifact_id,
            foreign_finding.revision
            if ref.artifact_id == foreign_finding.id
            else foreign_decision.revision
            if ref.artifact_id == foreign_decision.id
            else ref.revision,
        )
        for ref in strict_package.parent_refs
    )
    foreign_package = ledger.append_artifact(
        round_record.id,
        "technical-package",
        "technical-research-package",
        {"document": foreign_document, "markdown": strict_package.payload["markdown"]},
        parent_refs=foreign_parent_refs,
        expected_revision=ledger.get_revision(round_record.id),
    )
    foreign_readiness = CanonicalReadinessVerifier(ledger, resolver).verify(
        round_id=round_record.id,
        readiness_id="foreign-target-readiness",
        technical_package=foreign_package,
        repository_roots={"input-repository": root},
        expected_revision=ledger.get_revision(round_record.id),
    )
    foreign_gates = foreign_readiness.payload["delivery_readiness"]["gates"]
    assert foreign_gates["decision_closure"] == "fail"
    assert foreign_gates["implementation_readiness"] == "fail"

    forged_finding_payload = thaw_json(foreign_finding.payload)
    forged_finding_payload["blueprint_target_id"] = target.id
    forged_finding = ledger.append_artifact(
        round_record.id,
        foreign_finding.id,
        "finding-pack",
        forged_finding_payload,
        parent_refs=foreign_finding.parent_refs,
        expected_revision=ledger.get_revision(round_record.id),
    )
    forged_decision_payload = thaw_json(foreign_decision.payload)
    forged_decision_payload["blueprint_target_id"] = target.id
    forged_decision = ledger.append_artifact(
        round_record.id,
        foreign_decision.id,
        "decision-ledger-entry",
        forged_decision_payload,
        parent_refs=tuple(
            ArtifactRef(
                ref.round_id,
                ref.artifact_id,
                forged_finding.revision if ref.artifact_id == forged_finding.id else ref.revision,
            )
            for ref in foreign_decision.parent_refs
        ),
        expected_revision=ledger.get_revision(round_record.id),
    )
    forged_document = deepcopy(foreign_document)
    forged_document["research_findings"][0]["revision"] = forged_finding.revision
    forged_document["decision_records"][0]["revision"] = forged_decision.revision
    forged_document["traceability"]["finding_refs"][0]["revision"] = forged_finding.revision
    forged_document["traceability"]["decision_refs"][0]["revision"] = forged_decision.revision
    forged_package = ledger.append_artifact(
        round_record.id,
        "technical-package",
        "technical-research-package",
        {"document": forged_document, "markdown": strict_package.payload["markdown"]},
        parent_refs=tuple(
            ArtifactRef(
                ref.round_id,
                ref.artifact_id,
                forged_finding.revision
                if ref.artifact_id == forged_finding.id
                else forged_decision.revision
                if ref.artifact_id == forged_decision.id
                else ref.revision,
            )
            for ref in foreign_package.parent_refs
        ),
        expected_revision=ledger.get_revision(round_record.id),
    )
    forged_readiness = CanonicalReadinessVerifier(ledger, resolver).verify(
        round_id=round_record.id,
        readiness_id="forged-target-parent-readiness",
        technical_package=forged_package,
        repository_roots={"input-repository": root},
        expected_revision=ledger.get_revision(round_record.id),
    )
    forged_gates = forged_readiness.payload["delivery_readiness"]["gates"]
    assert forged_gates["decision_closure"] == "fail"
    assert forged_gates["implementation_readiness"] == "fail"
