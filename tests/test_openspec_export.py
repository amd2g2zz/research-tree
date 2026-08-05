from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from test_deliveries import compile_deliveries, context, decision_kwargs, readiness


def complete_package(tmp_path: Path, *, verify_readiness: bool = True):
    modules, store, round_record, _model, brief, target, finding, _decision = context(tmp_path)
    from research_tree import DecisionLedgerCompiler, FindingPackCompiler

    isolation_kwargs = decision_kwargs(target, finding)
    isolation_kwargs.update(
        {
            "status": "selected",
            "alternatives": [
                {
                    "option": "in-process",
                    "disposition": "rejected",
                    "reason": "The isolated worker is selected for the first implementation.",
                }
            ],
            "revision_reason": "Close the isolation decision for implementation export.",
        }
    )
    isolation = DecisionLedgerCompiler(store).converge(
        round_id=round_record.id,
        decision_id="decision-isolation",
        **isolation_kwargs,
    )
    observability_work = next(
        artifact
        for artifact in store.load_round(round_record.id).artifacts
        if artifact.id == "work-observability"
    )
    observability_finding = FindingPackCompiler(store).compile(
        allow_legacy_evidence=True,
        round_id=round_record.id,
        finding_id="finding-observability",
        work_item=observability_work,
        observations=[
            {
                "claim": "The run boundary can emit a structured completion record.",
                "anchor": {"kind": "repository", "ref": "src/agent.py:run"},
                "applicability": "the supplied Python repository",
                "confidence": "high",
                "limitation": "Production metrics remain a later operational concern.",
            }
        ],
        option_effects=[{"option": "structured-logging", "effect": "supports"}],
        implementation_implications=["Emit a structured record at the run boundary."],
        remaining_uncertainties=[],
    )
    observability = DecisionLedgerCompiler(store).converge(
        round_id=round_record.id,
        decision_id="decision-observability",
        blueprint_target=target,
        decision_slot_id="slot-observability",
        finding_packs=[observability_finding],
        status="selected",
        selected_option="structured-logging",
        alternatives=[
            {
                "option": "minimal-logging",
                "disposition": "rejected",
                "reason": "It does not provide the recorded completion evidence.",
            }
        ],
        anchors=[{"kind": "finding", "ref": observability_finding.id}],
        design_consequence="Emit a structured completion record from src/agent.py:run.",
        repository_touchpoints=[{"path": "src/agent.py", "symbol": "run"}],
        validation={
            "kind": "test",
            "oracle": "The run fixture emits a structured completion record.",
        },
        change_tasks=[
            {
                "id": "change-structured-logging",
                "description": "Emit the structured completion record.",
                "acceptance_oracle": "The fixture records the selected completion fields.",
                "repository_touchpoints": [{"path": "src/agent.py", "symbol": "run"}],
            }
        ],
        assumptions=[],
        fallback="Keep minimal logging until the structured record is proven.",
        reversal_condition="The structured record leaks data required to remain private.",
        revision_reason="Close observability for the implementation export.",
    )
    ready = readiness()
    ready["gates"].update(
        {
            "decision_closure": "pass",
            "implementation_readiness": "pass",
            "operational_quality": "pass",
        }
    )
    ready["findings"] = []
    ready["next_work_item_ids"] = []
    deliveries = compile_deliveries(
        modules,
        store,
        round_record,
        brief,
        target,
        [isolation, observability],
        readiness_input=ready,
    )
    if verify_readiness:
        from research_tree import ReadinessVerifier

        ReadinessVerifier(store).verify(
            round_id=round_record.id,
            readiness_id="readiness-package",
            technical_package=deliveries.technical_package,
            repository_roots={"input-repository": tmp_path / "repository"},
            risk_tier="default",
        )
    return modules, store, round_record, deliveries.technical_package


def test_normal_export_requires_readiness_for_the_exact_package_revision(tmp_path: Path) -> None:
    _modules, store, round_record, technical_package = complete_package(
        tmp_path, verify_readiness=False
    )
    from research_tree import InvalidOpenSpecExportError, OpenSpecExporter

    output = tmp_path / "unverified-output"
    with pytest.raises(InvalidOpenSpecExportError, match="readiness"):
        OpenSpecExporter(store).export(
            round_id=round_record.id,
            technical_package=technical_package,
            openspec_root=output,
            change_name="unverified-package",
        )
    assert not output.exists()


def test_normal_export_rejects_readiness_for_an_older_package_revision(tmp_path: Path) -> None:
    _modules, store, round_record, technical_package = complete_package(tmp_path)
    from research_tree import InvalidOpenSpecExportError, OpenSpecExporter
    from research_tree.domain import thaw_json

    newer_package = store.append_artifact(
        round_record.id,
        technical_package.id,
        technical_package.kind,
        thaw_json(technical_package.payload),
        parent_refs=technical_package.parent_refs,
    )

    output = tmp_path / "stale-readiness-output"
    with pytest.raises(InvalidOpenSpecExportError, match="exact technical package revision"):
        OpenSpecExporter(store).export(
            round_id=round_record.id,
            technical_package=newer_package,
            openspec_root=output,
            change_name="stale-readiness-package",
        )
    assert not output.exists()


def test_normal_export_rejects_a_failing_exact_readiness_record(tmp_path: Path) -> None:
    _modules, store, round_record, technical_package = complete_package(tmp_path)
    from research_tree import InvalidOpenSpecExportError, OpenSpecExporter
    from research_tree.domain import thaw_json

    readiness = next(
        artifact
        for artifact in store.load_round(round_record.id).artifacts
        if artifact.id == "readiness-package"
    )
    payload = thaw_json(readiness.payload)
    payload["delivery_readiness"]["gates"]["implementation_readiness"] = "fail"
    store.append_artifact(
        round_record.id,
        readiness.id,
        readiness.kind,
        payload,
        parent_refs=readiness.parent_refs,
    )

    output = tmp_path / "failing-readiness-output"
    with pytest.raises(InvalidOpenSpecExportError, match="verified readiness"):
        OpenSpecExporter(store).export(
            round_id=round_record.id,
            technical_package=technical_package,
            openspec_root=output,
            change_name="failing-readiness-package",
        )
    assert not output.exists()


def test_explicit_export_emits_traceable_repository_delta(tmp_path: Path) -> None:
    modules, store, round_record, technical_package = complete_package(tmp_path)
    from research_tree import OpenSpecExporter

    openspec_root = tmp_path / "exported-openspec"
    assert not openspec_root.exists()
    export = OpenSpecExporter(store).export(
        round_id=round_record.id,
        technical_package=technical_package,
        openspec_root=openspec_root,
        change_name="add-isolated-worker",
    )

    change_dir = openspec_root / "changes" / "add-isolated-worker"
    proposal = (change_dir / "proposal.md").read_text(encoding="utf-8")
    design = (change_dir / "design.md").read_text(encoding="utf-8")
    tasks = (change_dir / "tasks.md").read_text(encoding="utf-8")
    isolation_spec = (change_dir / "specs" / "slot-isolation" / "spec.md").read_text(
        encoding="utf-8"
    )
    manifest = json.loads((change_dir / "research-tree-export.json").read_text(encoding="utf-8"))

    assert export.change_directory == change_dir
    assert export.technical_package_ref == modules["ArtifactRef"](
        round_record.id, technical_package.id, technical_package.revision
    )
    assert export.draft is False
    assert set(export.files) == {
        "proposal.md",
        "design.md",
        "tasks.md",
        "research-tree-export.json",
        "specs/slot-isolation/spec.md",
        "specs/slot-observability/spec.md",
    }
    assert "## Repository Delta" in proposal
    assert "src/agent.py:run" in proposal
    assert "## ADDED Requirements" in isolation_spec
    assert "isolated-worker" in isolation_spec
    assert "#### Scenario:" in isolation_spec
    assert "## Decisions and Alternatives" in design
    assert "in-process" in design
    assert "## Migration and Operational Handoff" in design
    assert "No migration decision was recorded" in design
    assert "- [ ] 1." in tasks
    assert "Validation:" in tasks
    assert manifest["technical_package_ref"] == {
        "round_id": round_record.id,
        "artifact_id": technical_package.id,
        "revision": technical_package.revision,
    }
    assert manifest["repository_baseline"]["state"] == "repository_backed"
    assert manifest["traceability"]["decision_refs"]


def test_incomplete_package_requires_explicit_draft_without_partial_output(tmp_path: Path) -> None:
    modules, store, round_record, _model, brief, target, _finding, decision = context(tmp_path)
    technical_package = compile_deliveries(
        modules, store, round_record, brief, target, [decision]
    ).technical_package
    from research_tree import InvalidOpenSpecExportError, OpenSpecExporter

    openspec_root = tmp_path / "exported-openspec"
    exporter = OpenSpecExporter(store)
    with pytest.raises(InvalidOpenSpecExportError, match="decision_closure"):
        exporter.export(
            round_id=round_record.id,
            technical_package=technical_package,
            openspec_root=openspec_root,
            change_name="incomplete-agent",
        )
    assert not openspec_root.exists()

    draft = exporter.export(
        round_id=round_record.id,
        technical_package=technical_package,
        openspec_root=openspec_root,
        change_name="incomplete-agent",
        draft=True,
    )
    draft_design = (draft.change_directory / "design.md").read_text(encoding="utf-8")
    draft_proposal = (draft.change_directory / "proposal.md").read_text(encoding="utf-8")
    assert draft.draft is True
    assert "> **DRAFT" in draft_design
    assert "slot-observability" in draft_design
    assert "decision_closure: fail" in draft_proposal


def test_exporter_refuses_to_overwrite_or_accept_an_unpersisted_package(tmp_path: Path) -> None:
    _modules, store, round_record, technical_package = complete_package(tmp_path)
    from research_tree import ArtifactRevision, InvalidOpenSpecExportError, OpenSpecExporter
    from research_tree.domain import thaw_json

    exporter = OpenSpecExporter(store)
    openspec_root = tmp_path / "exported-openspec"
    exporter.export(
        round_id=round_record.id,
        technical_package=technical_package,
        openspec_root=openspec_root,
        change_name="add-isolated-worker",
    )
    proposal_path = openspec_root / "changes" / "add-isolated-worker" / "proposal.md"
    existing_proposal = proposal_path.read_text(encoding="utf-8")
    with pytest.raises(InvalidOpenSpecExportError, match="already exists"):
        exporter.export(
            round_id=round_record.id,
            technical_package=technical_package,
            openspec_root=openspec_root,
            change_name="add-isolated-worker",
        )
    assert proposal_path.read_text(encoding="utf-8") == existing_proposal

    forged = ArtifactRevision.create(
        artifact_id="forged-package",
        round_id=round_record.id,
        revision=1,
        kind="technical-research-package",
        payload=thaw_json(technical_package.payload),
        parent_refs=(),
    )
    with pytest.raises(InvalidOpenSpecExportError, match="persisted"):
        exporter.export(
            round_id=round_record.id,
            technical_package=forged,
            openspec_root=tmp_path / "forged-output",
            change_name="forged-package",
        )
    assert not (tmp_path / "forged-output").exists()


def test_exporter_rejects_cross_section_decision_drift_before_output(tmp_path: Path) -> None:
    _modules, store, round_record, technical_package = complete_package(tmp_path)
    from research_tree import InvalidOpenSpecExportError, OpenSpecExporter
    from research_tree.domain import thaw_json

    malformed_payload = thaw_json(technical_package.payload)
    malformed_payload["document"]["decision_records"][0]["status"] = "conditional"
    malformed = store.append_artifact(
        round_record.id,
        "semantically-malformed-package",
        "technical-research-package",
        malformed_payload,
        parent_refs=technical_package.parent_refs,
    )

    output = tmp_path / "malformed-output"
    with pytest.raises(InvalidOpenSpecExportError, match="does not match blueprint closure"):
        OpenSpecExporter(store).export(
            round_id=round_record.id,
            technical_package=malformed,
            openspec_root=output,
            change_name="malformed-package",
        )
    assert not output.exists()


def test_exporter_preserves_generic_repository_baseline_facts(tmp_path: Path) -> None:
    _modules, store, round_record, technical_package = complete_package(tmp_path)
    from research_tree import OpenSpecExporter
    from research_tree.domain import thaw_json

    payload = thaw_json(technical_package.payload)
    payload["document"]["technical_baseline"]["repositories"][0]["facts"] = [
        "A bounded repository observation."
    ]
    generic_facts_package = store.append_artifact(
        round_record.id,
        "generic-facts-package",
        "technical-research-package",
        payload,
        parent_refs=technical_package.parent_refs,
    )
    from research_tree import ReadinessVerifier

    ReadinessVerifier(store).verify(
        round_id=round_record.id,
        readiness_id="readiness-generic-facts",
        technical_package=generic_facts_package,
        repository_roots={"input-repository": tmp_path / "repository"},
        risk_tier="default",
    )

    export = OpenSpecExporter(store).export(
        round_id=round_record.id,
        technical_package=generic_facts_package,
        openspec_root=tmp_path / "generic-facts-output",
        change_name="generic-facts",
    )
    proposal = (export.change_directory / "proposal.md").read_text(encoding="utf-8")
    assert '"A bounded repository observation."' in proposal


def test_delivery_compiler_has_no_default_openspec_export_argument() -> None:
    from research_tree import DeliveryCompiler

    assert "openspec" not in inspect.signature(DeliveryCompiler.compile).parameters
