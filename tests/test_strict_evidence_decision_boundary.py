from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from test_readiness import greenfield_package

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


def _artifact(*, run_id: str, evidence_id: str, digest: str, size: int, locator: dict[str, str], revision: int = 1) -> EvidenceArtifact:
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
    decision = CanonicalDecisionLedgerCompiler(ledger, resolver).converge(
        round_id="run-strict",
        decision_id="decision-one",
        blueprint_target=target,
        decision_slot_id="slot-one",
        finding_packs=[finding],
        status="conditional",
        selected_option="option-a",
        alternatives=[{"option": "option-b", "disposition": "deferred", "reason": "Needs further evidence."}],
        anchors=[{"kind": "finding", "ref": finding.id}],
        design_consequence="Use option-a behind a guard.",
        repository_touchpoints=[],
        validation={"kind": "test", "oracle": "fixture test passes"},
        change_tasks=[{"id": "task-one", "description": "Implement guard.", "acceptance_oracle": "fixture test passes", "repository_touchpoints": []}],
        assumptions=[],
        fallback="Keep option-b available.",
        reversal_condition="Contrary evidence appears.",
        revision_reason="Initial strict decision.",
        expected_revision=4,
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
        CanonicalDecisionLedgerCompiler(ledger, resolver).converge(
            round_id="run-strict",
            decision_id="decision-stale",
            blueprint_target=target,
            decision_slot_id="slot-one",
            finding_packs=[finding],
            status="conditional",
            selected_option="option-a",
            alternatives=[{"option": "option-b", "disposition": "deferred", "reason": "Needs further evidence."}],
            anchors=[{"kind": "finding", "ref": finding.id}],
            design_consequence="Use option-a behind a guard.",
            repository_touchpoints=[],
            validation={"kind": "test", "oracle": "fixture test passes"},
            change_tasks=[{"id": "task-two", "description": "Retry guard.", "acceptance_oracle": "fixture test passes", "repository_touchpoints": []}],
            assumptions=[],
            fallback="Keep option-b available.",
            reversal_condition="Contrary evidence appears.",
            revision_reason="Stale evidence must fail.",
            expected_revision=6,
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
        CanonicalDecisionLedgerCompiler(ledger, resolver).converge(
            round_id="run-strict",
            decision_id="decision-low",
            blueprint_target=low_target,
            decision_slot_id="slot-low",
            finding_packs=[],
            status="selected",
            selected_option="option-a",
            alternatives=[{"option": "option-b", "disposition": "deferred", "reason": "Needs evidence."}],
            anchors=[],
            design_consequence="Use option-a.",
            repository_touchpoints=[],
            validation={"kind": "test", "oracle": "fixture test passes"},
            change_tasks=[],
            assumptions=[],
            fallback="Keep option-b available.",
            reversal_condition="Contrary evidence appears.",
            revision_reason="Missing strict evidence must fail.",
            expected_revision=4,
        )


def test_strict_readiness_rejects_empty_finding_and_unlinked_selected_decision(tmp_path: Path) -> None:
    ledger, _store, target, _work, _content, _evidence, _reference, resolver = _environment(tmp_path)
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
    decision = ledger.append_artifact(
        "run-strict",
        "decision-unlinked",
        "decision-ledger-entry",
        {"decision_slot_id": "slot-one", "status": "selected"},
        parent_refs=(ArtifactRef("run-strict", target.id, target.revision),),
        expected_revision=4,
    )
    diagnostics: list[dict[str, object]] = []
    assert not _strict_findings_are_authoritative(
        [empty_finding], [decision], resolver, diagnostics
    )
    assert any("no strict observations" in item["summary"] for item in diagnostics)
    assert any("strict Finding Pack parent lineage" in item["summary"] for item in diagnostics)


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
        CanonicalDecisionLedgerCompiler(ledger, _resolver).converge(
            round_id="run-strict",
            decision_id="decision-legacy",
            blueprint_target=target,
            decision_slot_id="slot-one",
            finding_packs=[legacy],
            status="conditional",
            selected_option="option-a",
            alternatives=[{"option": "option-b", "disposition": "deferred", "reason": "Needs further evidence."}],
            anchors=[{"kind": "finding", "ref": legacy.id}],
            design_consequence="Use option-a behind a guard.",
            repository_touchpoints=[],
            validation={"kind": "test", "oracle": "fixture test passes"},
            change_tasks=[{"id": "task-one", "description": "Implement guard.", "acceptance_oracle": "fixture test passes", "repository_touchpoints": []}],
            assumptions=[],
            fallback="Keep option-b available.",
            reversal_condition="Contrary evidence appears.",
            revision_reason="Must reject legacy evidence.",
            expected_revision=4,
        )


def test_canonical_ledger_cannot_use_non_strict_readiness_verifier(tmp_path: Path) -> None:
    ledger, _store, _target, _work, _content, _evidence, _reference, _resolver = _environment(tmp_path)

    with pytest.raises(InvalidReadinessError, match="matching ledger-backed"):
        ReadinessVerifier(ledger)


def test_strict_readiness_accepts_canonical_lineage_and_rejects_legacy_package(tmp_path: Path) -> None:
    source_store, round_record, legacy_package = greenfield_package(tmp_path / "legacy")
    ledger = RunLedger(tmp_path / "canonical")
    _migrate_run_store(source_store, round_record, ledger)
    store = ContentAddressedStore(tmp_path / "canonical")
    content = store.ingest(b"strict evidence", "text/plain")
    evidence = _artifact(
        run_id=round_record.id,
        evidence_id="strict-source",
        digest=content.digest,
        size=content.byte_size,
        locator={"url": "https://example.invalid/strict"},
    )
    reference = EvidenceRepository(ledger, store).record(
        evidence,
        content,
        expected_run_revision=ledger.get_revision(round_record.id),
    )
    resolver = EvidenceResolver.from_ledger(ledger, store, workspace=tmp_path / "canonical")
    target = ledger.get_artifact(ArtifactRef(round_record.id, "greenfield-target", 1))
    work = ledger.get_artifact(ArtifactRef(round_record.id, "work-greenfield", 1))
    legacy_decision = ledger.get_artifact(ArtifactRef(round_record.id, "decision-greenfield", 1))
    decision_data = thaw_json(legacy_decision.payload)
    finding = CanonicalFindingPackCompiler(ledger, resolver).compile(
        round_id=round_record.id,
        finding_id="finding-greenfield",
        work_item=work,
        observations=[_observation(_anchor(reference, content.digest))],
        option_effects=[{"option": "new-worker", "effect": "supports"}],
        implementation_implications=["Create the isolated component."],
        remaining_uncertainties=[],
        expected_revision=ledger.get_revision(round_record.id),
    )
    decision = CanonicalDecisionLedgerCompiler(ledger, resolver).converge(
        round_id=round_record.id,
        decision_id="decision-greenfield",
        blueprint_target=target,
        decision_slot_id="slot-greenfield",
        finding_packs=[finding],
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
        revision_reason="Canonical strict readiness fixture.",
        expected_revision=ledger.get_revision(round_record.id),
    )
    document = deepcopy(thaw_json(legacy_package.payload["document"]))
    document["research_findings"][0].update(
        {"revision": finding.revision, "observations": thaw_json(finding.payload["observations"])}
    )
    document["decision_records"][0]["revision"] = decision.revision
    document["traceability"]["finding_refs"][0]["revision"] = finding.revision
    document["traceability"]["decision_refs"][0]["revision"] = decision.revision
    parent_refs = tuple(
        ArtifactRef(
            ref.round_id,
            ref.artifact_id,
            finding.revision if ref.artifact_id == finding.id
            else decision.revision if ref.artifact_id == decision.id else ref.revision,
        )
        for ref in legacy_package.parent_refs
    )
    strict_package = ledger.append_artifact(
        round_record.id,
        "technical-package",
        "technical-research-package",
        {"document": document, "markdown": legacy_package.payload["markdown"]},
        parent_refs=parent_refs,
        expected_revision=ledger.get_revision(round_record.id),
    )
    strict_readiness = CanonicalReadinessVerifier(ledger, resolver).verify(
        round_id=round_record.id,
        readiness_id="strict-readiness",
        technical_package=strict_package,
        repository_roots={"input-repository": tmp_path / "legacy" / "repository"},
        expected_revision=ledger.get_revision(round_record.id),
    )
    strict_gates = strict_readiness.payload["delivery_readiness"]["gates"]
    assert strict_gates["decision_closure"] == "pass"
    assert strict_gates["implementation_readiness"] == "pass"

    legacy_readiness = CanonicalReadinessVerifier(ledger, resolver).verify(
        round_id=round_record.id,
        readiness_id="legacy-readiness",
        technical_package=ledger.get_artifact(ArtifactRef(round_record.id, "technical-package", 1)),
        repository_roots={"input-repository": tmp_path / "legacy" / "repository"},
        expected_revision=ledger.get_revision(round_record.id),
    )
    legacy_gates = legacy_readiness.payload["delivery_readiness"]["gates"]
    assert legacy_gates["decision_closure"] == "fail"
    assert legacy_gates["implementation_readiness"] == "fail"
