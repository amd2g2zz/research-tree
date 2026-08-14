from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from research_tree import (
    ArtifactRef,
    CanonicalDecisionLedgerCompiler,
    CanonicalFindingPackCompiler,
    ContentAddressedStore,
    EvidenceAnchor,
    EvidenceArtifact,
    EvidenceRepository,
    EvidenceResolver,
    RunLedger,
)
from research_tree.work_items import WORK_ITEM_KIND


RUN_ID = "round-canonical"


@dataclass(frozen=True)
class RoundRecord:
    id: str = RUN_ID


def _append(
    ledger: RunLedger,
    artifact_id: str,
    kind: str,
    payload: dict[str, object],
    parent_refs: tuple[ArtifactRef, ...] = (),
):
    return ledger.append_artifact(
        RUN_ID,
        artifact_id,
        kind,
        payload,
        parent_refs=parent_refs,
        expected_revision=ledger.get_revision(RUN_ID),
    )


def _slot() -> dict[str, object]:
    return {
        "id": "slot-isolation",
        "kind": "architecture",
        "question": "Which isolation boundary should the first agent use?",
        "intent_hypothesis_ids": ["intent-agent"],
        "priority": "P0",
        "impact": "high",
        "uncertainty": "high",
        "irreversibility": "high",
        "constraints": [
            {
                "kind": "input",
                "ref": "input-brief",
                "statement": "The first implementation must remain safe.",
            }
        ],
        "alternatives": ["isolated-worker", "in-process"],
        "repository_touchpoints": [{"path": "src/agent.py", "symbol": "run"}],
        "greenfield_assumptions": [],
        "depends_on": [],
        "evidence_standard": "repository inspection plus a bounded spike",
        "validation": {"kind": "spike", "oracle": "one fixture crosses the selected boundary"},
        "closure_rule": "select, conditionally select, defer with fallback, or block",
        "status": "open",
        "bounded_research_need": "compare both alternatives against the current boundary",
        "fallback": "retain the current boundary until this decision closes",
    }


def _evidence(run_id: str, digest: str, size: int) -> EvidenceArtifact:
    return EvidenceArtifact(
        evidence_id="strict-source",
        run_id=run_id,
        revision=1,
        media_type="text/plain",
        locator={"url": "https://example.invalid/source-isolation"},
        content_digest=digest,
        size_bytes=size,
        acquired_at=datetime.now(timezone.utc).isoformat(),
        acquisition_method="fixture",
        provenance_group="fixture-source",
        applicability="direct support",
        confidence="high",
        limitations=(),
        status="active",
        extractor_version="fixture-reader-v1",
        evidence_class="source",
    )


def canonical_context(tmp_path: Path, *, include_decision: bool = True):
    ledger = RunLedger(tmp_path / "ledger")
    ledger.initialize()
    ledger.create_run(RUN_ID)
    brief_input = _append(
        ledger,
        "input-brief",
        "input-ledger-entry",
        {
            "id": "input-brief",
            "kind": "brief",
            "material": {"kind": "inline-text", "content": "Build a safe implementation-ready agent."},
            "origin": {"type": "user", "locator": "conversation:1"},
            "role": "signal",
        },
    )
    repository_input = _append(
        ledger,
        "input-repository",
        "input-ledger-entry",
        {
            "id": "input-repository",
            "kind": "repository",
            "origin": {"type": "workspace", "locator": "fixture"},
            "role": "baseline",
            "repository_baseline": {
                "revision": {"commit": "fixture"},
                "anchors": [{"path": "src/agent.py", "symbol": "run"}],
                "facts": [],
                "unreadable": [],
            },
        },
    )
    context_input = _append(
        ledger,
        "input-context",
        "input-ledger-entry",
        {
            "id": "input-context",
            "kind": "context_bundle",
            "origin": {"type": "user", "locator": "conversation:1"},
            "role": "baseline",
        },
        (
            ArtifactRef(RUN_ID, brief_input.id, brief_input.revision),
            ArtifactRef(RUN_ID, repository_input.id, repository_input.revision),
        ),
    )
    model = _append(
        ledger,
        "intent-model",
        "intent-model",
        {
            "id": "intent-model",
            "round_id": RUN_ID,
            "signals": [],
            "hypotheses": [
                {
                    "id": "intent-agent",
                    "interpretation": "Deliver a safe agent path.",
                    "status": "leading",
                    "signal_refs": ["input-brief"],
                    "confidence": "medium",
                    "decision_consequence": "Choose an isolation boundary.",
                    "validation": "repository_inspection",
                }
            ],
            "decision_drivers": [],
        },
        (
            ArtifactRef(RUN_ID, context_input.id, context_input.revision),
            ArtifactRef(RUN_ID, brief_input.id, brief_input.revision),
            ArtifactRef(RUN_ID, repository_input.id, repository_input.revision),
        ),
    )
    brief = _append(
        ledger,
        "working-brief",
        "working-brief",
        {
            "id": "working-brief",
            "round_id": RUN_ID,
            "intent_model_id": model.id,
            "intent_hypothesis_ids": ["intent-agent"],
            "viable_intent_hypothesis_ids": [],
            "selected_input_ids": [brief_input.id, repository_input.id],
            "context_bundle_ids": [context_input.id],
            "working_interpretation": "A safe implementation-ready agent path is leading.",
            "technical_outcome": "Choose the first agent architecture and integration boundary.",
            "triggers": [],
            "input_roles": {brief_input.id: "primary", repository_input.id: "baseline"},
            "material_conflicts": [],
            "non_goals": [],
            "retained_hard_constraints": [],
            "assumptions": [],
        },
        (
            ArtifactRef(RUN_ID, model.id, model.revision),
            ArtifactRef(RUN_ID, context_input.id, context_input.revision),
            ArtifactRef(RUN_ID, brief_input.id, brief_input.revision),
            ArtifactRef(RUN_ID, repository_input.id, repository_input.revision),
        ),
    )
    target = _append(
        ledger,
        "blueprint-target",
        "blueprint-target",
        {
            "id": "blueprint-target",
            "round_id": RUN_ID,
            "brief_id": brief.id,
            "intent_model_id": model.id,
            "slots": [_slot()],
        },
        (ArtifactRef(RUN_ID, brief.id, brief.revision), ArtifactRef(RUN_ID, model.id, model.revision)),
    )
    work = _append(
        ledger,
        "work-isolation",
        WORK_ITEM_KIND,
        {
            "id": "work-isolation",
            "round_id": RUN_ID,
            "blueprint_target_id": target.id,
            "decision_slot_id": "slot-isolation",
        },
        (ArtifactRef(RUN_ID, target.id, target.revision),),
    )
    store = ContentAddressedStore(tmp_path / "content")
    content = store.ingest(b"The source supports the isolated worker boundary.\n", "text/plain")
    evidence = EvidenceRepository(ledger, store).record(
        _evidence(RUN_ID, content.digest, content.byte_size),
        content,
        expected_run_revision=ledger.get_revision(RUN_ID),
    )
    resolver = EvidenceResolver.from_ledger(ledger, store, workspace=tmp_path / "content")
    anchor = EvidenceAnchor(
        artifact_ref=evidence,
        artifact_digest=content.digest,
        artifact_revision=evidence.revision,
        selector_type="line",
        selector_value={"start": 1, "end": 1},
        extractor_version="fixture-reader-v1",
        applicability="direct support",
        confidence="high",
        limitations=(),
    )
    if not include_decision:
        return ledger, resolver, RoundRecord(), model, brief, target, work, None, None, evidence, anchor
    finding = CanonicalFindingPackCompiler(ledger, resolver).compile(
        round_id=RUN_ID,
        finding_id="finding-isolation",
        work_item=work,
        observations=[
            {
                "claim": "The source supports an isolated worker.",
                "anchor": anchor.to_dict(),
                "applicability": "the fixture boundary",
                "confidence": "high",
                "limitation": "fixture evidence only",
            }
        ],
        option_effects=[{"option": "isolated-worker", "effect": "supports"}],
        implementation_implications=["Introduce an isolated worker boundary."],
        remaining_uncertainties=["Measure startup overhead."],
        expected_revision=ledger.get_revision(RUN_ID),
    )
    decision = CanonicalDecisionLedgerCompiler(ledger, resolver).converge(
        round_id=RUN_ID,
        decision_id="decision-isolation",
        blueprint_target=target,
        decision_slot_id="slot-isolation",
        finding_packs=[finding],
        status="selected",
        selected_option="isolated-worker",
        alternatives=[
            {
                "option": "in-process",
                "disposition": "deferred",
                "reason": "Startup cost needs a bounded validation spike.",
            }
        ],
        anchors=[{"kind": "finding", "ref": finding.id}],
        design_consequence="Add a worker adapter at src/agent.py:run.",
        repository_touchpoints=[{"path": "src/agent.py", "symbol": "run"}],
        validation={"kind": "spike", "oracle": "one fixture completes through the worker adapter"},
        change_tasks=[
            {
                "id": "change-worker-adapter",
                "description": "Introduce the selected isolation adapter.",
                "acceptance_oracle": "The fixture crosses the adapter.",
                "repository_touchpoints": [{"path": "src/agent.py", "symbol": "run"}],
            }
        ],
        assumptions=["The local worker boundary is sufficient for the fixture."],
        fallback="Keep the in-process boundary available.",
        reversal_condition="A spike shows worker startup overhead breaks the workflow.",
        revision_reason="Canonical fixture decision.",
        expected_revision=ledger.get_revision(RUN_ID),
    )
    return ledger, resolver, RoundRecord(), model, brief, target, work, finding, decision, evidence, anchor
