"""Goal-contribution contracts: coordinator contribution verdicts, retry, escalation (#428)."""

from __future__ import annotations

from pathlib import Path

from canonical_finding_fixture import _evidence
from test_goal_wiring import RUN_ID, goal_run, slot, work_item_arguments

from research_tree import (
    CanonicalFindingPackCompiler,
    CanonicalRecursiveResearchCoordinator,
    CanonicalWorkItemCompiler,
    ContentAddressedStore,
    EvidenceAnchor,
    EvidenceRepository,
    EvidenceResolver,
    RunLedger,
)
from research_tree.claims import Claim, ClaimGrounding
from research_tree.coordinator import (
    GOAL_CONTRIBUTION_ASSESSMENT_KIND,
    ResearchRunCoordinator,
    assess_goal_contribution,
)
from research_tree.domain import ArtifactRef
from research_tree.feedback import CanonicalFeedbackRoundService
from research_tree.policy import AdaptiveResearchPolicy
from research_tree.tree_state import CanonicalResearchTreeStateService


def ref(artifact) -> ArtifactRef:
    return ArtifactRef(artifact.round_id, artifact.id, artifact.revision)


def init_run_state(ledger: RunLedger, coordinator: ResearchRunCoordinator, target) -> None:
    handoff = next(item for item in ledger.load_run(RUN_ID).artifacts if item.id == "handoff-1")
    coordinator.initialize(
        run_id=RUN_ID,
        alignment_handoff=handoff,
        blueprint_target=target,
        expected_revision=ledger.get_revision(RUN_ID),
        idempotency_key="init-goal",
    )


# ---------------------------------------------------------------------------
# Pure-function fixtures (payload-level; the truth table never touches a ledger)
# ---------------------------------------------------------------------------

PROJECTION = {
    "projection_id": "projection-1",
    "revision": 1,
    "display_digest": "digest-1",
    "decision_targets": ({"id": "decision-1"},),
    "success_oracles": ({"id": "oracle-1", "evidence_standard_ids": ("standard-1",)},),
}


def pack(
    option_effects=(),
    claim_assessments=(),
    validation_result=None,
    **extra,
) -> dict:
    payload = {
        "id": "finding-1",
        "decision_slot_id": "slot-1",
        "blueprint_target_id": "blueprint-target",
        "option_effects": list(option_effects),
        "claim_assessments": list(claim_assessments),
        "validation_result": validation_result,
    }
    payload.update(extra)
    return payload


def test_verdict_truth_table_advances() -> None:
    # Rule 2: a supports effect on a slot alternative advances the served target.
    verdict, reason = assess_goal_contribution(
        pack([{"option": "isolated-worker", "effect": "supports", "claim_ids": ["claim-1"]}]),
        slot("slot-1"),
        PROJECTION,
    )
    assert verdict == "advances"
    assert "isolated-worker" in reason
    assert "decision-1" in reason

    # Rule 3: a corroborated claim advances even without a supporting effect.
    verdict, reason = assess_goal_contribution(
        pack(
            [{"option": "isolated-worker", "effect": "limits", "claim_ids": ["claim-1"]}],
            claim_assessments=[{"claim_id": "claim-1", "state": "corroborated"}],
        ),
        slot("slot-1"),
        PROJECTION,
    )
    assert verdict == "advances"
    assert "claim-1" in reason
    assert "oracle-1" in reason


def test_verdict_truth_table_partial() -> None:
    # A limits effect touches the slot without advancing an alternative.
    verdict, _ = assess_goal_contribution(
        pack(
            [{"option": "isolated-worker", "effect": "limits", "claim_ids": ["claim-1"]}],
        ),
        slot("slot-1"),
        PROJECTION,
    )
    assert verdict == "partial"

    # Claims bound to the served slot with no corroborated admission only partially touch it.
    verdict, _ = assess_goal_contribution(
        pack((), claim_assessments=[{"claim_id": "claim-1", "state": "candidate"}]),
        slot("slot-1"),
        PROJECTION,
    )
    assert verdict == "partial"


def test_verdict_truth_table_no_contribution() -> None:
    # Effects on options outside the slot alternatives touch nothing.
    verdict, reason = assess_goal_contribution(
        pack([{"option": "quantum", "effect": "supports", "claim_ids": ["claim-1"]}]),
        slot("slot-1"),
        PROJECTION,
    )
    assert verdict == "no_contribution"
    assert "quantum" not in reason  # foreign options are not the defect; the absence is

    # A pack with no effects and no claims contributes nothing even under a valid serves link.
    verdict, _ = assess_goal_contribution(pack(), slot("slot-1"), PROJECTION)
    assert verdict == "no_contribution"


def test_verdict_truth_table_contradicts() -> None:
    verdict, reason = assess_goal_contribution(
        pack([{"option": "isolated-worker", "effect": "contradicts", "claim_ids": ["claim-1"]}]),
        slot("slot-1"),
        PROJECTION,
    )
    assert verdict == "contradicts"
    assert "isolated-worker" in reason

    # Rule 1 short-circuits rule 2: a contradicts effect wins over a supports effect.
    verdict, _ = assess_goal_contribution(
        pack(
            [
                {"option": "isolated-worker", "effect": "supports", "claim_ids": ["claim-1"]},
                {"option": "in-process", "effect": "contradicts", "claim_ids": ["claim-1"]},
            ]
        ),
        slot("slot-1"),
        PROJECTION,
    )
    assert verdict == "contradicts"


def test_high_confidence_without_effects_is_no_contribution() -> None:
    verdict, reason = assess_goal_contribution(
        pack(
            [],
            observations=[{"claim_id": "claim-1", "claim": "text", "confidence": "high"}],
            confidence="high",
        ),
        slot("slot-1"),
        PROJECTION,
    )
    assert verdict == "no_contribution"
    assert "confidence" not in reason.lower()


# ---------------------------------------------------------------------------
# Ingestion-wiring fixtures (goal-wired ledger run + compile/coordinator paths)
# ---------------------------------------------------------------------------


def _evidence_setup(tmp_path: Path, ledger: RunLedger):
    store = ContentAddressedStore(tmp_path / "content")
    content = store.ingest(b"The source supports the isolated worker boundary.\n", "text/plain")
    evidence = EvidenceRepository(ledger, store).record(
        _evidence(RUN_ID, content.digest, content.byte_size),
        content,
        expected_run_revision=ledger.get_revision(RUN_ID),
    )
    independent_content = store.ingest(
        b"An independent fixture confirms the source supports the isolated worker boundary.\n",
        "text/plain",
    )
    independent = EvidenceRepository(ledger, store).record(
        _evidence(
            RUN_ID,
            independent_content.digest,
            independent_content.byte_size,
            evidence_id="strict-source-independent",
            upstream="fixture-independent-source",
        ),
        independent_content,
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
    independent_anchor = EvidenceAnchor(
        artifact_ref=independent,
        artifact_digest=independent_content.digest,
        artifact_revision=independent.revision,
        selector_type="line",
        selector_value={"start": 1, "end": 1},
        extractor_version="fixture-reader-v1",
        applicability="direct support",
        confidence="high",
        limitations=(),
    )
    return resolver, anchor, independent_anchor


def _compile_pack(ledger: RunLedger, work, resolver, anchor, independent_anchor, finding_id: str):
    return CanonicalFindingPackCompiler(ledger, resolver).compile(
        round_id=RUN_ID,
        finding_id=finding_id,
        work_item=work,
        observations=[
            {
                "claim_id": "claim-isolated-worker",
                "claim": "The source supports an isolated worker.",
                "anchor": anchor.to_dict(),
                "applicability": "the fixture boundary",
                "confidence": "high",
                "limitation": "fixture evidence only",
            }
        ],
        option_effects=[{"option": "isolated-worker", "effect": "supports", "claim_ids": ["claim-isolated-worker"]}],
        implementation_implications=["Introduce an isolated worker boundary."],
        remaining_uncertainties=["Measure startup overhead."],
        claims=[
            Claim(
                claim_id="claim-isolated-worker",
                subject="source",
                predicate="supports",
                value="the isolated worker boundary",
                polarity="positive",
                scope="fixture boundary",
                version="fixture-v1",
                time_range="fixture-time",
            )
        ],
        claim_groundings=[
            ClaimGrounding("grounding-isolated-worker", "claim-isolated-worker", anchor.to_dict()),
            ClaimGrounding(
                "grounding-isolated-worker-independent",
                "claim-isolated-worker",
                independent_anchor.to_dict(),
            ),
        ],
        expected_revision=ledger.get_revision(RUN_ID),
    )


def _raw_pack(ledger: RunLedger, finding_id: str, option: str = "quantum") -> object:
    """A persisted pack whose effects touch a foreign option: verdict no_contribution."""

    return ledger.append_artifact(
        RUN_ID,
        finding_id,
        "finding-pack",
        {
            "id": finding_id,
            "decision_slot_id": "slot-1",
            "blueprint_target_id": "blueprint-target",
            "observations": [{"claim": "An off-target observation.", "anchor": {"kind": "source", "ref": "source:1"}}],
            "option_effects": [{"option": option, "effect": "supports", "claim_ids": []}],
            "remaining_uncertainties": [],
            "research_continuations": [],
            "validation_result": None,
        },
        expected_revision=ledger.get_revision(RUN_ID),
    )


def _tree(ledger: RunLedger) -> CanonicalRecursiveResearchCoordinator:
    recursive = CanonicalRecursiveResearchCoordinator(ledger)
    recursive.initialize(
        round_id=RUN_ID,
        tree_id="research-tree",
        decision_slots={
            "slot-1": {
                "status": "open",
                "priority": "P0",
                "uncertainty": "high",
                "question": "Which boundary should slot-1 use?",
                "validation": {"oracle": "one fixture crosses the selected boundary"},
            }
        },
        expected_revision=ledger.get_revision(RUN_ID),
    )
    return recursive


def _assessments(ledger: RunLedger) -> list:
    return [item for item in ledger.load_run(RUN_ID).artifacts if item.kind == GOAL_CONTRIBUTION_ASSESSMENT_KIND]


def _projection_artifact(ledger: RunLedger):
    return next(item for item in ledger.load_run(RUN_ID).artifacts if item.kind == "strategy-projection")


def _successor_works(ledger: RunLedger) -> list:
    return [
        item
        for item in ledger.load_run(RUN_ID).artifacts
        if item.kind == "work-item" and item.payload.get("guidance_defect")
    ]


def test_no_contribution_excluded_from_tree_consumption(tmp_path: Path) -> None:
    ledger, target = goal_run(tmp_path, slots=(slot("slot-1"),))
    work = CanonicalWorkItemCompiler(ledger).compile(
        **work_item_arguments(target), expected_revision=ledger.get_revision(RUN_ID)
    )
    resolver, anchor, independent_anchor = _evidence_setup(tmp_path, ledger)

    # The compile hook assesses every compile-passed pack: this one advances.
    advancing_pack = _compile_pack(ledger, work, resolver, anchor, independent_anchor, "finding-advancing")
    assessments = _assessments(ledger)
    assert len(assessments) == 1
    assert assessments[0].payload["verdict"] == "advances"
    assert assessments[0].payload["finding_pack_id"] == "finding-advancing"
    assert assessments[0].payload["finding_pack_revision"] == advancing_pack.revision
    assert assessments[0].payload["slot_id"] == "slot-1"
    assert assessments[0].payload["projection_digest"] == _projection_artifact(ledger).payload["display_digest"]
    assert assessments[0].parent_refs == (
        ref(advancing_pack),
        ref(_projection_artifact(ledger)),
    )

    # A pack whose effects touch a foreign option is judged no_contribution by the coordinator.
    non_contributing_pack = _raw_pack(ledger, "finding-non-contributing")
    coordinator = ResearchRunCoordinator(ledger)
    init_run_state(ledger, coordinator, target)
    assessment = coordinator.assess_finding_pack_contribution(
        RUN_ID, non_contributing_pack, expected_revision=ledger.get_revision(RUN_ID)
    )
    assert assessment is not None and assessment.payload["verdict"] == "no_contribution"

    recursive = _tree(ledger)
    recursive.ingest(
        round_id=RUN_ID,
        tree_id="research-tree",
        finding_packs=(advancing_pack, non_contributing_pack),
        expected_revision=ledger.get_revision(RUN_ID),
    )
    state = CanonicalResearchTreeStateService(ledger).latest(round_id=RUN_ID, tree_id="research-tree")
    consumed = state.payload["consumed_finding_ids"]
    assert "finding-advancing" in consumed
    assert "finding-non-contributing" not in consumed

    # Restart recovery must not resurrect the excluded pack either.
    recovered = CanonicalRecursiveResearchCoordinator(ledger).recover(
        round_id=RUN_ID,
        tree_id="research-tree",
        expected_revision=ledger.get_revision(RUN_ID),
    )
    consumed_after = recovered.payload["consumed_finding_ids"]
    assert "finding-advancing" in consumed_after
    assert "finding-non-contributing" not in consumed_after


def test_retry_successor_records_guidance_defect(tmp_path: Path) -> None:
    ledger, target = goal_run(tmp_path, slots=(slot("slot-1"),))
    CanonicalWorkItemCompiler(ledger).compile(
        **work_item_arguments(target), expected_revision=ledger.get_revision(RUN_ID)
    )
    non_contributing_pack = _raw_pack(ledger, "finding-drift")
    coordinator = ResearchRunCoordinator(ledger)
    init_run_state(ledger, coordinator, target)

    assessment = coordinator.assess_finding_pack_contribution(
        RUN_ID, non_contributing_pack, expected_revision=ledger.get_revision(RUN_ID)
    )
    assert assessment.payload["verdict"] == "no_contribution"
    defect = assessment.payload["reason"]
    assert assessment.parent_refs == (ref(non_contributing_pack), ref(_projection_artifact(ledger)))

    snapshot = ledger.load_run(RUN_ID)
    replan = [item for item in snapshot.artifacts if item.kind == "same-round-replan"][-1]
    assert replan.payload["affected_slot_ids"] == ("slot-1",)
    assert replan.payload["guidance_defect"] == defect

    successors = _successor_works(ledger)
    assert len(successors) == 1
    successor = successors[0]
    assert successor.payload["guidance_defect"] == defect
    assert defect in successor.payload["scope"] or defect in successor.payload["exclusions"]
    assert successor.payload["decision_slot_id"] == "slot-1"
    # First retry adjusts guidance; re-decomposition is reserved for escalation.
    assert not successor.payload.get("redecomposition_flagged")


def test_second_no_contribution_triggers_method_switch(tmp_path: Path) -> None:
    ledger, target = goal_run(tmp_path, slots=(slot("slot-1"),))
    CanonicalWorkItemCompiler(ledger).compile(
        **work_item_arguments(target), expected_revision=ledger.get_revision(RUN_ID)
    )
    coordinator = ResearchRunCoordinator(ledger, policy=AdaptiveResearchPolicy())
    init_run_state(ledger, coordinator, target)

    first_pack = _raw_pack(ledger, "finding-drift-1")
    second_pack = _raw_pack(ledger, "finding-drift-2")
    first = coordinator.assess_finding_pack_contribution(
        RUN_ID, first_pack, expected_revision=ledger.get_revision(RUN_ID)
    )
    second = coordinator.assess_finding_pack_contribution(
        RUN_ID, second_pack, expected_revision=ledger.get_revision(RUN_ID)
    )
    assert first.payload["verdict"] == "no_contribution"
    assert second.payload["verdict"] == "no_contribution"

    successors = _successor_works(ledger)
    assert len(successors) == 2
    escalated = successors[-1]
    assert escalated.payload["redecomposition_flagged"] is True
    assert escalated.payload["policy_proposal_kind"] == "method_switch"
    assert escalated.payload["policy_proposal_id"]
    assert escalated.payload["guidance_defect"] == second.payload["reason"]
    # The first retry stays a plain guidance adjustment.
    assert not successors[0].payload.get("redecomposition_flagged")

    replans = [item for item in ledger.load_run(RUN_ID).artifacts if item.kind == "same-round-replan"]
    assert len(replans) == 2
    assert replans[-1].payload["affected_slot_ids"] == ("slot-1",)
    assert replans[-1].payload["guidance_defect"] == second.payload["reason"]


def test_same_round_replan_accepts_slot_granularity(tmp_path: Path) -> None:
    ledger = RunLedger(tmp_path / "ledger")
    ledger.create_run("round-feedback")
    service = CanonicalFeedbackRoundService(ledger)
    common = {
        "round_id": "round-feedback",
        "feedback_input_id": "input-slot-feedback",
        "feedback_text": "Redirect the slot, not the round.",
        "feedback_origin_locator": "conversation:3",
    }

    replan = service.record_same_round_replan(
        replan_id="replan-slot",
        reason="The slot boundary misread the served target.",
        expected_revision=ledger.get_revision("round-feedback"),
        affected_slot_ids=("slot-1",),
        guidance_defect="serves.target_id drift against the confirmed projection",
        **common,
    )
    assert replan.payload["affected_slot_ids"] == ("slot-1",)
    assert replan.payload["guidance_defect"] == "serves.target_id drift against the confirmed projection"

    legacy = service.record_same_round_replan(
        replan_id="replan-legacy",
        reason="Only the work allocation changes.",
        expected_revision=ledger.get_revision("round-feedback"),
        **common,
    )
    assert legacy.payload["affected_slot_ids"] == ()
    assert legacy.payload["guidance_defect"] is None
