"""senior-user-ux-v2 Track B supplement: prove the in-process alignment chain (#468).

One real research run (RunLedger + SQLite alignment graph) drives the full
alignment and compilation chain through the same runtime APIs the CLI wraps:
canonical intake -> intent model with a clarifying question -> resolved intent
model -> working brief -> blueprint target (decision_map) -> confirmed SQLite
alignment graph -> alignment handoff compilation -> research tree -> strategy
projection with an independent alignment verification -> digest/authority-
fingerprint confirmation (with one tampered attempt recorded verbatim) ->
strict finding pack + decision convergence over REAL repository evidence ->
real Technical Research Package / Human Research Report compilation through
``CanonicalDeliveryCompiler`` (which itself persists the pair through
``CompletionInputRegistrar.write_delivery_pair``) -> real delivery acceptance.

Honesty boundaries:
- every stage below calls the real compiler / coordinator / store; nothing is
  hand-built where a public compiler exists (unlike the run_v2_evaluation
  fixture path, which hand-appends the handoff, target, and delivery payloads);
- the isolated operator/CLI defect (a ``prepared`` run cannot reach
  ``initialized``) is NOT re-tested here: this supplement exercises the
  in-process API path only;
- the repository input, evidence bytes, claim anchors, and blueprint slot
  touchpoints name real files and real top-level symbols of THIS repository.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from run_v2_evaluation import ALIGNMENT_VERIFIER, MAIN_SESSION
from v2_oracles import EVIDENCE_STANDARDS

from research_tree import (
    CanonicalBlueprintTargetCompiler,
    CanonicalDecisionLedgerCompiler,
    CanonicalDeliveryCompiler,
    CanonicalFindingPackCompiler,
    CanonicalInputIntakeService,
    CanonicalIntentModelCompiler,
    CanonicalWorkingBriefCompiler,
    CanonicalWorkItemCompiler,
    ContentAddressedStore,
    DeliveryAcceptance,
    EvidenceAnchor,
    EvidenceArtifact,
    EvidenceRepository,
    EvidenceResolver,
    QuestionPolicy,
    RunLedger,
)
from research_tree.acceptance import delivery_pair_digest
from research_tree.alignment_graph import AlignmentGraphError, AlignmentGraphStore, database_path
from research_tree.alignment_handoff import initialize_research_from_alignment
from research_tree.claims import Claim, ClaimGrounding
from research_tree.completion_inputs import (
    CompletionInputRegistrar,
    delivery_manifest_digest,
)
from research_tree.coordinator import CoordinatorError, ResearchRunCoordinator
from research_tree.decision_frame import DecisionFrame, IntentHypothesis
from research_tree.domain import ArtifactRef, thaw_json
from research_tree.strategy_projection import (
    StrategyProjection,
    authority_fingerprint,
    validate_falsifiability,
)

RUN_ID = "run-v2-trackb-alignment-chain"
CASE_ID = "senior-user-ux-v2-track-b-alignment-chain"
SCHEMA_VERSION = 1

# Real repository surface this chain grounds its claims against. The worktree
# root is two directories above this harness module.
REPO_ROOT = Path(__file__).resolve().parents[2]
HANDOFF_MODULE = "src/research_tree/alignment_handoff.py"
CLI_MODULE = "src/research_tree/cli.py"
GROUNDED_PATH = HANDOFF_MODULE
GROUNDED_SYMBOL = "initialize_research_from_alignment"

# Claim vocabulary must be byte-grounded: the normalized claim statement is a
# literal substring of BOTH selected real source lines, so claim admission
# corroborates it across two distinct provenance clusters (two different real
# files, two different canonical upstream identities).
CLAIM_VERSION = "worktree-v1"
CLAIM_TIME_RANGE = "static-window-2026-09"
CLAIM_SCOPE = "src/research_tree"
GROUNDING_CLI = {"evidence_id": "evd-chain-cli", "path": CLI_MODULE, "line": 13}
GROUNDING_FRAME = {
    "evidence_id": "evd-chain-goal-wiring",
    "path": "tests/test_goal_wiring.py",
    "line": 24,
}

REQUIRED_STAGES = (
    "intake",
    "intent_model_question",
    "intent_model_resolution",
    "working_brief",
    "alignment_graph_confirmation",
    "handoff_compilation",
    "blueprint_target_compile",
    "coordinator_initialization_bind",
    "coordinator_initialization",
    "strategy_projection_display",
    "strategy_confirmation_tamper",
    "strategy_confirmation",
    "work_item",
    "finding_pack_evidence",
    "finding_pack",
    "decision_convergence",
    "delivery_compilation",
    "delivery_acceptance",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append(ledger: RunLedger, run_id: str, artifact_id: str, kind: str, payload: dict[str, Any], parents=()):
    return ledger.append_artifact(
        run_id, artifact_id, kind, dict(payload), parent_refs=parents, expected_revision=ledger.get_revision(run_id)
    )


class _Chain:
    """Sequential stage driver; a failed stage records the blocker honestly."""

    def __init__(self) -> None:
        self.stages: list[dict[str, Any]] = []
        self.blocked: str | None = None

    def stage(self, name: str, detail: str, ok: bool = True) -> None:
        self.stages.append({"stage": name, "ok": ok, "detail": detail})
        if not ok:
            self.blocked = f"{name}: {detail}"

    def run(self, name: str, driver):
        """Drive one stage; an exception records ok=False and stops the chain."""

        if self.blocked is not None:
            self.stages.append({"stage": name, "ok": False, "detail": f"not reached: blocked by {self.blocked}"})
            return None
        try:
            result = driver()
        except Exception as error:  # noqa: BLE001 - recorded verbatim as the stage blocker
            self.stage(name, f"{type(error).__name__}: {error}", ok=False)
            return None
        detail = result
        if isinstance(result, tuple):
            detail = result[1]
        self.stage(name, str(detail))
        return result[0] if isinstance(result, tuple) else result


def _intake_inputs(ledger: RunLedger) -> None:
    intake = CanonicalInputIntakeService(ledger)
    for input_id, kind, content, role in (
        (
            "input-brief",
            "brief",
            (
                "Prove the senior-user-ux-v2 governed run can reach strategy gates through the in-process "
                "alignment chain, grounded in this repository's own alignment bridge."
            ),
            "signal",
        ),
        (
            "input-clarify",
            "note",
            "The chain must run in-process through real runtime APIs; the operator CLI surface is out of scope.",
            "constraint",
        ),
        (
            "input-contrast",
            "note",
            "The chain must instead be driven exclusively through the CLI subprocess surface.",
            "constraint",
        ),
    ):
        intake.ingest_text(
            round_id=RUN_ID,
            input_id=input_id,
            kind=kind,
            content=content,
            origin_type="user",
            origin_locator="conversation:alignment-chain",
            role=role,
            expected_revision=ledger.get_revision(RUN_ID),
        )
    intake.ingest_repository(
        round_id=RUN_ID,
        input_id="input-repository",
        repository_root=REPO_ROOT,
        include_paths=(HANDOFF_MODULE, CLI_MODULE),
        origin_type="workspace",
        role="baseline",
        expected_revision=ledger.get_revision(RUN_ID),
    )


def _ambiguous_analysis() -> dict[str, Any]:
    return {
        "signals": [
            {
                "input_id": "input-brief",
                "observation": "The chain must prove the alignment bridge through real runtime APIs.",
                "kind": "stated_goal",
                "authority_boundary": "It does not select the driving surface.",
            },
            {
                "input_id": "input-clarify",
                "observation": "One constraint requires the in-process API surface.",
                "kind": "constraint",
                "authority_boundary": "It conflicts with the CLI-surface note.",
            },
            {
                "input_id": "input-contrast",
                "observation": "One note requires the CLI subprocess surface.",
                "kind": "constraint",
                "authority_boundary": "It conflicts with the in-process note.",
            },
            {
                "input_id": "input-repository",
                "observation": (
                    "The repository has initialize_research_from_alignment in "
                    "src/research_tree/alignment_handoff.py bridging a confirmed graph to a tree."
                ),
                "kind": "repository_fact",
                "authority_boundary": "It records current structure, not a future design decision.",
            },
        ],
        "hypotheses": [
            {
                "id": "intent-in-process",
                "interpretation": "Drive the chain through real in-process runtime APIs.",
                "status": "leading",
                "signal_refs": ["input-brief", "input-clarify"],
                "confidence": "medium",
                "decision_consequence": "Exercises coordinators and compilers directly in one governed run.",
                "validation": "repository_inspection",
            },
            {
                "id": "intent-cli",
                "interpretation": "Drive the chain through the CLI subprocess surface.",
                "status": "viable",
                "signal_refs": ["input-brief", "input-contrast"],
                "confidence": "low",
                "decision_consequence": "Changes the surface to operator commands and exit codes.",
                "validation": "alignment_research",
            },
        ],
        "desired_outcomes": ["a governed run whose strategy gates are mechanically reachable in-process"],
        "success_signals": ["the compiled handoff binds outcome, scope, authority, and success oracles"],
        "decision_drivers": [
            {
                "dimension": "technical",
                "statement": "The proof must reuse the exact call sequence the strategy gates require.",
                "signal_refs": ["input-brief"],
            }
        ],
        "hard_constraints": ["Do not modify orchestrator-owned evaluation or runtime files."],
        "non_goals": ["Do not drive host subprocesses."],
        "unresolved_interpretations": [
            {
                "hypothesis_ids": ["intent-in-process", "intent-cli"],
                "question": "Should the alignment chain be driven in-process or through the operator CLI surface?",
                "consequential": True,
                "non_recoverable": True,
                "rankable": False,
            }
        ],
    }


def _resolved_analysis() -> dict[str, Any]:
    analysis = _ambiguous_analysis()
    analysis["signals"].append(
        {
            "input_id": "input-answer",
            "observation": "The requester resolved the ambiguity: drive in-process; the CLI surface is out of scope.",
            "kind": "constraint",
            "authority_boundary": "It settles the driving surface for this run.",
        }
    )
    leading = analysis["hypotheses"][0]
    leading["signal_refs"] = ["input-brief", "input-clarify", "input-answer"]
    leading["confidence"] = "high"
    rejected = analysis["hypotheses"][1]
    rejected["status"] = "rejected"
    rejected["signal_refs"] = ["input-contrast"]
    analysis["unresolved_interpretations"] = []
    return analysis


def _compile_alignment_graph(workspace: Path) -> tuple[Path, str]:
    """Initialize, merge, plan, tamper, and confirm the real alignment graph."""

    database = database_path(workspace, RUN_ID)
    store = AlignmentGraphStore(database)
    store.initialize(RUN_ID)
    required = {
        "goal": ("outcome", "Reach the v2 strategy gates from a fully compiled alignment handoff."),
        "use": ("intended_use", "Authorize the governed v2 run lane through real runtime APIs."),
        "scope": ("scope_boundary", "In-process API surface only; no operator CLI subprocess is in scope."),
        "delivery": ("delivery", "Deliver a compiled Technical Research Package and Human Research Report."),
        "authority": ("authority", "The agent owns autonomous research after the explicit handoff confirmation."),
        "success": (
            "success_oracle",
            "The compiled handoff binds outcome, scope, authority, and success oracle fields end to end.",
        ),
        "feasibility": (
            "feasibility",
            "Every stage has a real public compiler or coordinator API proven by this repository's tests.",
        ),
        "strategy": (
            "strategy",
            "Use the confirmed handoff bridge to compile the research tree, then converge bounded decisions.",
        ),
    }
    nodes = [
        {
            "id": node_id,
            "type": node_type,
            "statement": statement,
            "status": "supported",
            "impact": 5,
            "human_only": False,
            "confidence": "high",
            "source": "joint",
        }
        for node_id, (node_type, statement) in required.items()
    ]
    nodes.extend(
        [
            {
                "id": "question-handoff-bridge",
                "type": "research_question",
                "statement": "Does the compiled handoff bridge reach the strategy gates through the in-process chain?",
                "status": "candidate",
                "impact": 5,
                "human_only": False,
                "confidence": "low",
                "source": "joint",
                "oracle": "The compiled handoff compiles a research tree whose strategy confirmation succeeds.",
            },
            {
                "id": "evidence-handoff-bridge",
                "type": "evidence",
                "statement": (
                    "Repository reconnaissance found initialize_research_from_alignment bridging a confirmed "
                    "alignment graph to a persisted research tree."
                ),
                "status": "supported",
                "impact": 3,
                "human_only": False,
                "confidence": "medium",
                "source": "repository",
                "attributes": {"anchor": {"kind": "source", "ref": f"{HANDOFF_MODULE}:{GROUNDED_SYMBOL}"}},
            },
        ]
    )
    edges = [
        {
            "id": "edge-evidence-question",
            "source_id": "evidence-handoff-bridge",
            "target_id": "question-handoff-bridge",
            "relation": "supports",
            "status": "active",
            "confidence": "medium",
            "provenance": "alignment reconnaissance of src/research_tree/alignment_handoff.py",
        }
    ]
    decision = store.plan({"nodes": nodes, "edges": edges})
    if decision["action"] != "await_human_confirmation":
        raise AlignmentGraphError(f"alignment plan did not reach the handoff draft: {decision}")
    try:
        store.confirm(
            "I confirm the stated outcome and authorize autonomous research within that scope.",
            expected_digest="0" * 64,
        )
        raise AssertionError("wrong-digest confirmation was not rejected")
    except AlignmentGraphError as error:
        digest_rejection = str(error)
    confirmed = store.confirm(
        "I confirm the stated outcome and authorize autonomous research within that scope.",
        decision["alignment_digest"],
    )
    if confirmed["status"] != "autonomous" or confirmed["phase"] != "research":
        raise AlignmentGraphError(f"handoff confirmation did not reach autonomous research: {confirmed}")
    return database, digest_rejection


def run_alignment_chain_supplement(workspace: Path) -> dict[str, Any]:
    """Drive one governed run through the full in-process alignment chain."""

    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    chain = _Chain()
    tamper = {"attempted": False, "canonical_reason": None}
    delivery: dict[str, Any] = {}

    def build():
        ledger = RunLedger(workspace)
        ledger.initialize()
        ledger.create_run(RUN_ID)

        def do_intake():
            _intake_inputs(ledger)
            return (
                None,
                "canonical inputs ingested: 3 notes, 1 human answer, and 1 real repository baseline scoped to "
                f"{HANDOFF_MODULE} + {CLI_MODULE}",
            )

        chain.run("intake", do_intake)

        def do_question():
            model = CanonicalIntentModelCompiler(ledger).compile(
                round_id=RUN_ID,
                intent_id="intent-model",
                context_bundle_ids=(),
                input_ids=("input-brief", "input-clarify", "input-contrast", "input-repository"),
                analysis=_ambiguous_analysis(),
                expected_revision=ledger.get_revision(RUN_ID),
            )
            question = QuestionPolicy().recommend(model)
            if question is None:
                raise AssertionError("QuestionPolicy emitted no clarifying question for the staged ambiguity")
            return model, f"clarifying question emitted: {question.question}"

        chain.run("intent_model_question", do_question)

        def do_resolution():
            CanonicalInputIntakeService(ledger).ingest_text(
                round_id=RUN_ID,
                input_id="input-answer",
                kind="note",
                content=(
                    "Answer: drive the alignment chain in-process through real runtime APIs; the operator "
                    "CLI surface is out of scope for this supplement."
                ),
                origin_type="user",
                origin_locator="conversation:alignment-chain",
                role="constraint",
                expected_revision=ledger.get_revision(RUN_ID),
            )
            model = CanonicalIntentModelCompiler(ledger).compile(
                round_id=RUN_ID,
                intent_id="intent-model",
                context_bundle_ids=(),
                input_ids=("input-brief", "input-clarify", "input-contrast", "input-answer", "input-repository"),
                analysis=_resolved_analysis(),
                expected_revision=ledger.get_revision(RUN_ID),
            )
            if QuestionPolicy().recommend(model) is not None:
                raise AssertionError("resolved intent model still requests a clarifying question")
            return model, "human answer ingested as input-answer; intent-model revision 2 has no open question"

        model_resolved = chain.run("intent_model_resolution", do_resolution)

        def do_brief():
            brief = CanonicalWorkingBriefCompiler(ledger).compile(
                round_id=RUN_ID,
                brief_id="working-brief",
                intent_model=model_resolved,
                triggers=[
                    {"kind": "initial_request", "text": "Prove the alignment chain", "input_ids": ["input-brief"]}
                ],
                context_bundle_ids=(),
                selected_input_ids=(
                    "input-brief",
                    "input-clarify",
                    "input-contrast",
                    "input-answer",
                    "input-repository",
                ),
                input_roles={
                    "input-brief": "primary",
                    "input-clarify": "constraint",
                    "input-contrast": "counterexample",
                    "input-answer": "constraint",
                    "input-repository": "baseline",
                },
                material_conflicts=[
                    {
                        "input_ids": ["input-clarify", "input-contrast"],
                        "status": "resolved",
                        "note": "Settled by the human answer input-answer.",
                    }
                ],
                working_interpretation="In-process API proof is the leading, resolved intent.",
                technical_outcome="Compile the v2 alignment chain end to end inside one governed run.",
                assumptions=["The repository baseline covers the two grounded source files."],
                expected_revision=ledger.get_revision(RUN_ID),
            )
            return brief, f"working brief {brief.id}@{brief.revision} compiled from the resolved intent model"

        brief = chain.run("working_brief", do_brief)

        def do_graph():
            database, digest_rejection = _compile_alignment_graph(workspace)
            return database, f"graph confirmed (wrong-digest tamper rejected: {digest_rejection})"

        chain.run("alignment_graph_confirmation", do_graph)

        def do_handoff():
            compiled = AlignmentGraphStore(database_path(workspace, RUN_ID)).compile_handoff()
            context = compiled["execution_context"]
            missing = [
                key for key in ("scope_boundaries", "authority", "success_oracles", "strategy") if not context.get(key)
            ]
            if missing or not compiled.get("objective"):
                raise AssertionError(f"compiled handoff does not bind {missing or 'objective'}")
            initialize_research_from_alignment(
                ledger,
                round_id=RUN_ID,
                tree_id=f"tree-{RUN_ID}",
                alignment_database=database_path(workspace, RUN_ID),
                expected_revision=ledger.get_revision(RUN_ID),
            )
            snapshot = ledger.load_run(RUN_ID)
            handoff = next(item for item in snapshot.artifacts if item.kind == "alignment-handoff")
            tree = next(item for item in snapshot.artifacts if item.id == f"tree-{RUN_ID}")
            return handoff, (
                f"handoff {handoff.id}@{handoff.revision} and tree {tree.id}@{tree.revision} persisted; "
                f"objective='{compiled['objective'][:48]}...'; {len(compiled['decision_slots'])} decision slot(s); "
                f"{len(compiled['baseline_findings'])} baseline finding pack(s)"
            )

        handoff = chain.run("handoff_compilation", do_handoff)

        def do_target():
            target = CanonicalBlueprintTargetCompiler(ledger).compile(
                round_id=RUN_ID,
                target_id="blueprint-target",
                working_brief=brief,
                slots=[
                    {
                        "id": "slot-alignment-chain",
                        "kind": "validation",
                        "question": "Does the in-process chain reach the strategy gates from the compiled handoff?",
                        "intent_hypothesis_ids": ["intent-in-process"],
                        "priority": "P0",
                        "impact": "high",
                        "uncertainty": "high",
                        "irreversibility": "low",
                        "constraints": [
                            {
                                "kind": "repository",
                                "ref": f"{HANDOFF_MODULE}:{GROUNDED_SYMBOL}",
                                "statement": (
                                    "The chain grounds on the real alignment bridge "
                                    f"{HANDOFF_MODULE}:{GROUNDED_SYMBOL}."
                                ),
                            }
                        ],
                        "alternatives": ["in-process-chain", "operator-cli-chain"],
                        "repository_touchpoints": [{"path": HANDOFF_MODULE, "symbol": GROUNDED_SYMBOL}],
                        "greenfield_assumptions": [],
                        "depends_on": [],
                        "evidence_standard": "repository inspection of the real alignment bridge",
                        "validation": {
                            "kind": "test",
                            "oracle": "one governed run completes strategy confirmation in-process",
                        },
                        "closure_rule": "select, conditionally select, defer with fallback, or block",
                        "status": "open",
                        "bounded_research_need": "prove the compiled handoff reaches the confirmed strategy",
                        "fallback": "the run stays open instead of declaring a pass",
                        "serves": {
                            "target_id": "decision-alignment-chain",
                            "oracle_ids": ["oracle-handoff-integrity"],
                        },
                    }
                ],
                change={
                    "kind": "initial",
                    "reason": "Map the implementation decision implied by the resolved Working Brief.",
                    "from_slot_ids": [],
                    "to_slot_ids": ["slot-alignment-chain"],
                },
                expected_revision=ledger.get_revision(RUN_ID),
            )
            return target, f"blueprint target {target.id}@{target.revision} compiled with the grounded touchpoint"

        target_rev1 = chain.run("blueprint_target_compile", do_target)

        def do_bind():
            payload = thaw_json(target_rev1.payload)
            handoff_ref = ArtifactRef(RUN_ID, handoff.id, handoff.revision)
            bound = _append(
                ledger,
                RUN_ID,
                target_rev1.id,
                "blueprint-target",
                payload,
                (*target_rev1.parent_refs, handoff_ref),
            )
            return bound, f"target bound to the compiled handoff lineage at revision {bound.revision}"

        target = chain.run("coordinator_initialization_bind", do_bind)

        coordinator = ResearchRunCoordinator(ledger)

        def do_initialize():
            state = coordinator.initialize(
                run_id=RUN_ID,
                alignment_handoff=handoff,
                blueprint_target=target,
                expected_revision=ledger.get_revision(RUN_ID),
                idempotency_key="init-alignment-chain",
            )
            return state, f"coordinator run-state {state.id}@{state.revision} reached state 'alignment'"

        chain.run("coordinator_initialization", do_initialize)

        def do_frame_projection():
            frame = coordinator.persist_decision_frame(
                DecisionFrame.create(
                    frame_id=f"frame-{RUN_ID}",
                    run_id=RUN_ID,
                    requester_wording=(
                        "Prove the governed v2 run reaches its strategy gates through the in-process alignment chain."
                    ),
                    primary_decision={
                        "id": "decision-alignment-chain",
                        "statement": "Does the in-process chain carry a compiled handoff to a confirmed strategy?",
                        "success_signal": "confirmed handoff plus compiled delivery pair in one governed run",
                    },
                    target_ref=ArtifactRef(RUN_ID, target.id, target.revision),
                    hypotheses=(
                        IntentHypothesis(
                            id="selected",
                            interpretation="In-process chain verdict over one governed run",
                            ambiguity="explicit",
                            owner="requester",
                            researchable=False,
                            decision_consequence="sets the supplement scope",
                            source_refs=("input-brief", "input-answer"),
                            disposition="selected",
                            next_action="form strategy",
                            primary_decision_id="decision-alignment-chain",
                            material=True,
                            evidence_ranked=True,
                        ),
                    ),
                ),
                expected_revision=ledger.get_revision(RUN_ID),
            )
            projection = StrategyProjection.create(
                projection_id=f"strategy-{RUN_ID}",
                run_id=RUN_ID,
                decision_frame_ref=ArtifactRef(RUN_ID, frame.id, frame.revision),
                alignment_handoff_ref=ArtifactRef(RUN_ID, handoff.id, handoff.revision),
                target_ref=ArtifactRef(RUN_ID, target.id, target.revision),
                current_understanding=(
                    "Prove the governed v2 run reaches its strategy gates through the in-process alignment chain."
                ),
                assumptions=("the repository baseline covers the grounded files",),
                decision_targets=({"id": "decision-alignment-chain", "oracle_ids": ("oracle-handoff-integrity",)},),
                tracks=({"id": "track-b"},),
                method_hypotheses=({"method": "governed-in-process-chain"},),
                depth="deep",
                evidence_expectations=("canonical receipts",),
                autonomy_envelope={"allowed": ["evaluation"], "authority": "research_owner"},
                replanning_policy={"same_round": ["depth"]},
                success_oracles=(
                    {
                        "id": "oracle-handoff-integrity",
                        "statement": (
                            "The compiled handoff binds outcome, scope, authority, and success oracle fields, "
                            "and confirmation re-materializes each field."
                        ),
                        "gate_ids": (),
                        "evidence_standard_ids": ("es-handoff-fingerprint-match",),
                    },
                    {
                        "id": "oracle-delivery-pair-integrity",
                        "statement": (
                            "The delivery pair is compiled by the real canonical delivery compiler from strict "
                            "finding packs grounded in real repository evidence."
                        ),
                        "gate_ids": (),
                        "evidence_standard_ids": ("es-completion-snapshot-digest",),
                    },
                ),
                delivery_contract={"technical": "package", "human": "report"},
                stop_rule="every served oracle carries gate-bound evidence or the run stays open",
                preference_influences=(),
                revision=1,
                status="displayed",
            )
            unknown_standards = {
                standard
                for oracle in projection.success_oracles
                for standard in oracle.get("evidence_standard_ids", ())
                if standard not in EVIDENCE_STANDARDS
            }
            if unknown_standards:
                raise AssertionError(f"oracles cite unknown v2 evidence standards: {sorted(unknown_standards)}")
            validate_falsifiability(projection)
            coordinator.persist_strategy_projection(projection, expected_revision=ledger.get_revision(RUN_ID))
            oracle_ids = [oracle["id"] for oracle in projection.display_payload["success_oracles"]]
            CompletionInputRegistrar(ledger).write_alignment_verification(
                round_id=RUN_ID,
                verification_id=f"alignment-verification-{RUN_ID}",
                payload={
                    "schema": 1,
                    "id": f"alignment-verification-{RUN_ID}",
                    "round_id": RUN_ID,
                    "projection_ref": {
                        "round_id": RUN_ID,
                        "artifact_id": projection.projection_id,
                        "revision": projection.revision,
                    },
                    "authority_fingerprint": authority_fingerprint(projection),
                    "verifier_identity": ALIGNMENT_VERIFIER,
                    "session_context": MAIN_SESSION,
                    "understood": {
                        "outcome": "Independently restated: prove the in-process chain reaches the strategy gates.",
                        "scope": "Independently restated: one governed run over real runtime APIs, no CLI subprocess.",
                        "authority": "Independently restated: autonomous evaluation inside the confirmed envelope.",
                        "success_oracles": [
                            {"id": oracle_id, "understanding": f"Independently restated oracle {oracle_id}."}
                            for oracle_id in oracle_ids
                        ],
                    },
                    "discrepancies": [],
                },
                expected_revision=ledger.get_revision(RUN_ID),
            )
            coordinator.display_strategy(
                run_id=RUN_ID, projection=projection, expected_revision=ledger.get_revision(RUN_ID)
            )
            return projection, (
                f"projection {projection.id}@{projection.revision} displayed after independent alignment "
                f"verification by {ALIGNMENT_VERIFIER}"
            )

        projection = chain.run("strategy_projection_display", do_frame_projection)

        def do_tamper():
            tampered = f"I accept {projection.display_digest} authority-fingerprint {'f' * 64} and authorize research."
            try:
                coordinator.confirm_handoff(
                    RUN_ID,
                    projection_ref=ArtifactRef(RUN_ID, projection.id, projection.revision),
                    confirmation=tampered,
                    expected_revision=ledger.get_revision(RUN_ID),
                    actor="human",
                )
            except CoordinatorError as error:
                reason = str(error)
                if reason != "authority_fingerprint_mismatch":
                    raise AssertionError(f"unexpected tamper rejection reason: {reason}") from error
                tamper["attempted"] = True
                tamper["canonical_reason"] = reason
                return reason, f"tampered confirmation rejected with canonical reason '{reason}'"
            raise AssertionError("tampered confirmation was accepted")

        chain.run("strategy_confirmation_tamper", do_tamper)

        def do_confirm():
            confirmed_state = coordinator.confirm_handoff(
                RUN_ID,
                projection_ref=ArtifactRef(RUN_ID, projection.id, projection.revision),
                confirmation=(
                    f"I accept {projection.display_digest} authority-fingerprint "
                    f"{authority_fingerprint(projection)} and authorize research."
                ),
                expected_revision=ledger.get_revision(RUN_ID),
                actor="human",
            )
            return confirmed_state, (
                "handoff confirmed: state="
                f"{confirmed_state.payload.get('state')}; display digest bound and authority fingerprint re-verified"
            )

        chain.run("strategy_confirmation", do_confirm)

        def do_work():
            work = CanonicalWorkItemCompiler(ledger).compile(
                round_id=RUN_ID,
                work_item_id="work-alignment-chain",
                blueprint_target=target,
                decision_slot_id="slot-alignment-chain",
                kind="repository_analysis",
                scope=(f"Inspect {HANDOFF_MODULE}:{GROUNDED_SYMBOL} and prove the in-process chain reaches the gates."),
                exclusions="Do not modify runtime files; do not drive operator CLI subprocesses.",
                decision_change_reason="The compiled handoff makes the in-process chain the bounded research need.",
                depends_on=(),
                methods=("repository_inspection",),
                budget={"tool_calls": 8, "time": "bounded"},
                completion_rule="Return a strict Finding Pack grounded in real repository evidence.",
                expected_revision=ledger.get_revision(RUN_ID),
            )
            return work, f"work item {work.id}@{work.revision} compiled with serves validated against the projection"

        work = chain.run("work_item", do_work)

        def do_finding():
            store = ContentAddressedStore(workspace / "content-store")
            resolver = EvidenceResolver.from_ledger(ledger, store, workspace=workspace / "content-store")
            anchors: dict[str, EvidenceAnchor] = {}
            statement_words = "alignment handoff import goal decomposition initialize research from alignment"
            for spec in (GROUNDING_CLI, GROUNDING_FRAME):
                source_lines = (REPO_ROOT / spec["path"]).read_text(encoding="utf-8").splitlines()
                selected = "\n".join(source_lines[spec["line"] - 1 : spec["line"] + 2])
                normalized = " ".join(re.findall(r"[a-z0-9]+", selected.casefold()))
                if statement_words not in normalized:
                    raise AssertionError(f"grounding text at {spec['path']}:{spec['line']} no longer carries the claim")
                content = store.ingest(selected.encode("utf-8") + b"\n", "text/plain")
                evidence = EvidenceRepository(ledger, store).record(
                    EvidenceArtifact(
                        evidence_id=spec["evidence_id"],
                        run_id=RUN_ID,
                        revision=1,
                        media_type="text/plain",
                        locator={"file": spec["path"], "kind": "repository-file", "line": str(spec["line"])},
                        content_digest=content.digest,
                        size_bytes=content.byte_size,
                        acquired_at=_now(),
                        acquisition_method="repository-read",
                        provenance_group=f"repo:{spec['path']}",
                        applicability="direct support",
                        confidence="high",
                        limitations=(),
                        status="active",
                        extractor_version="alignment-chain-reader-v1",
                        evidence_class="source",
                        metadata={
                            "canonical_upstream_id": f"repo:{spec['path']}",
                            "claim_version": CLAIM_VERSION,
                            "claim_time_range": CLAIM_TIME_RANGE,
                            "claim_scope": CLAIM_SCOPE,
                            "claim_conditions": [],
                        },
                    ),
                    content,
                    expected_run_revision=ledger.get_revision(RUN_ID),
                )
                anchors[spec["evidence_id"]] = EvidenceAnchor(
                    artifact_ref=evidence,
                    artifact_digest=content.digest,
                    artifact_revision=evidence.revision,
                    selector_type="line",
                    selector_value={"start": 1, "end": 3},
                    extractor_version="alignment-chain-reader-v1",
                    applicability="direct support",
                    confidence="high",
                    limitations=(),
                )
            return (resolver, anchors), (
                "evidence grounded from two real repository files with distinct provenance clusters: "
                f"{CLI_MODULE} and tests/test_goal_wiring.py"
            )

        finding_context = chain.run("finding_pack_evidence", do_finding)
        resolver, anchors = finding_context if finding_context else (None, {})

        def do_finding_pack():
            finding = CanonicalFindingPackCompiler(ledger, resolver).compile(
                round_id=RUN_ID,
                finding_id="finding-alignment-chain",
                work_item=work,
                observations=[
                    {
                        "claim_id": "claim-handoff-bridge-imported",
                        "claim": (
                            "The governed run imports its handoff bridge: "
                            f"{CLI_MODULE} line {GROUNDING_CLI['line']} imports {GROUNDED_SYMBOL} from "
                            f"{HANDOFF_MODULE}, and the goal-wiring suite anchors the same import."
                        ),
                        "anchor": anchors[GROUNDING_CLI["evidence_id"]].to_dict(),
                        "applicability": "the in-process chain surface",
                        "confidence": "high",
                        "limitation": "static repository evidence only; no process was executed",
                    }
                ],
                option_effects=[
                    {"option": "in-process-chain", "effect": "supports", "claim_ids": ["claim-handoff-bridge-imported"]}
                ],
                implementation_implications=[f"Bind the v2 run lane at {HANDOFF_MODULE}:{GROUNDED_SYMBOL}."],
                remaining_uncertainties=["The operator CLI surface remains unproven (out of scope)."],
                claims=[
                    Claim(
                        claim_id="claim-handoff-bridge-imported",
                        subject="alignment_handoff",
                        predicate="import",
                        value="goal_decomposition initialize_research_from_alignment",
                        polarity="positive",
                        scope=CLAIM_SCOPE,
                        version=CLAIM_VERSION,
                        time_range=CLAIM_TIME_RANGE,
                        claim_kind="repository_fact",
                        authority="repository",
                    )
                ],
                claim_groundings=[
                    ClaimGrounding(
                        "grounding-chain-cli",
                        "claim-handoff-bridge-imported",
                        anchors[GROUNDING_CLI["evidence_id"]].to_dict(),
                    ),
                    ClaimGrounding(
                        "grounding-chain-goal-wiring",
                        "claim-handoff-bridge-imported",
                        anchors[GROUNDING_FRAME["evidence_id"]].to_dict(),
                    ),
                ],
                expected_revision=ledger.get_revision(RUN_ID),
            )
            return finding, (
                f"strict finding pack {finding.id}@{finding.revision} compiled with a corroborated claim over "
                f"{CLI_MODULE} and tests/test_goal_wiring.py (two provenance clusters)"
            )

        finding = chain.run("finding_pack", do_finding_pack)

        def do_decision():
            resolver = EvidenceResolver.from_ledger(
                ledger, ContentAddressedStore(workspace / "content-store"), workspace=workspace / "content-store"
            )
            decision = CanonicalDecisionLedgerCompiler(ledger, resolver).converge(
                round_id=RUN_ID,
                decision_id="decision-alignment-chain",
                blueprint_target=target,
                decision_slot_id="slot-alignment-chain",
                finding_packs=[finding],
                status="selected",
                selected_option="in-process-chain",
                alternatives=[
                    {
                        "option": "operator-cli-chain",
                        "disposition": "deferred",
                        "reason": "The isolated operator surface defect is tracked outside this supplement.",
                    }
                ],
                anchors=[{"kind": "finding", "ref": finding.id}],
                design_consequence=(
                    f"Bind the v2 run lane at {HANDOFF_MODULE}:{GROUNDED_SYMBOL} and keep the operator "
                    "surface on its own remediation lane."
                ),
                repository_touchpoints=[{"path": HANDOFF_MODULE, "symbol": GROUNDED_SYMBOL}],
                validation={
                    "kind": "test",
                    "oracle": "tests/test_v2_alignment_chain.py passes over one governed run",
                },
                change_tasks=[
                    {
                        "id": "change-in-process-chain-proof",
                        "description": f"Drive {GROUNDED_SYMBOL} ({HANDOFF_MODULE}) inside the governed run.",
                        "acceptance_oracle": "The strategy confirmation and delivery pair compile in one run.",
                        "repository_touchpoints": [{"path": HANDOFF_MODULE, "symbol": GROUNDED_SYMBOL}],
                    }
                ],
                assumptions=["Real repository evidence grounds every claim."],
                fallback="The run stays open if any compiler rejects the chain.",
                reversal_condition="A compiler rejects the real chain before the delivery pair exists.",
                revision_reason="Canonical decision for the alignment-chain supplement.",
                expected_revision=ledger.get_revision(RUN_ID),
            )
            return decision, f"decision ledger entry {decision.id}@{decision.revision} converged as selected"

        decision = chain.run("decision_convergence", do_decision)

        def do_delivery():
            resolver = EvidenceResolver.from_ledger(
                ledger, ContentAddressedStore(workspace / "content-store"), workspace=workspace / "content-store"
            )
            pair = CanonicalDeliveryCompiler(ledger, resolver).compile(
                round_id=RUN_ID,
                technical_package_id="technical-alignment-chain",
                human_brief_id="human-alignment-chain",
                working_brief=brief,
                blueprint_target=target,
                decision_entries=[decision],
                readiness={
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
                expected_revision=ledger.get_revision(RUN_ID),
            )
            technical_lines = len(str(pair.technical_package.payload.get("markdown", "")).splitlines())
            human_lines = len(str(pair.human_research_report.payload.get("markdown", "")).splitlines())
            tech_revision = f"{pair.technical_package.id}@{pair.technical_package.revision}"
            human_revision = f"{pair.human_research_report.id}@{pair.human_research_report.revision}"
            pair_digest = delivery_pair_digest(RUN_ID, tech_revision, human_revision)
            delivery.update(
                {
                    "technical_lines": technical_lines,
                    "human_lines": human_lines,
                    "pair_digest": pair_digest,
                    "technical_artifact": tech_revision,
                    "human_artifact": human_revision,
                    "grounded_symbols": [f"{HANDOFF_MODULE}:{GROUNDED_SYMBOL}"],
                }
            )
            return pair, (
                f"real CanonicalDeliveryCompiler compiled technical ({technical_lines} lines) and human "
                f"({human_lines} lines) payloads; pair digest {pair_digest[:16]}..."
            )

        pair = chain.run("delivery_compilation", do_delivery)

        def do_acceptance():
            registrar = CompletionInputRegistrar(ledger)
            technical = pair.technical_package
            human = pair.human_research_report
            tech_revision = f"{technical.id}@{technical.revision}"
            human_revision = f"{human.id}@{human.revision}"
            acceptance = DeliveryAcceptance.create(
                "acceptance-alignment-chain",
                RUN_ID,
                tech_revision,
                human_revision,
                delivery_pair_digest(RUN_ID, tech_revision, human_revision),
                delivery_manifest_digest(technical, human),
                [
                    {
                        "feedback_id": "feedback-alignment-chain",
                        "classification": "presentation",
                        "statement": "I accept the compiled conclusions and the in-process trade-offs.",
                        "target_refs": [technical.id, human.id],
                    }
                ],
            )
            registrar.write_delivery_acceptance(
                round_id=RUN_ID,
                technical_package=technical,
                human_research_report=human,
                acceptance=acceptance,
                expected_revision=ledger.get_revision(RUN_ID),
            )
            return acceptance, f"real delivery acceptance {acceptance.acceptance_id} registered on the compiled pair"

        chain.run("delivery_acceptance", do_acceptance)

    try:
        build()
    except Exception as error:  # noqa: BLE001 - receipt must stay honest on unexpected scaffolding faults
        chain.stage("run", f"{type(error).__name__}: {error}", ok=False)

    stage_names = {stage["stage"] for stage in chain.stages}
    missing = [name for name in REQUIRED_STAGES if name not in stage_names]
    if chain.blocked is None and missing:
        chain.blocked = f"stages not recorded: {missing}"
    all_ok = all(stage["ok"] for stage in chain.stages) and tamper["attempted"] and bool(delivery.get("pair_digest"))
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": CASE_ID,
        "run_id": RUN_ID,
        "workspace": str(workspace),
        "chain_stages": chain.stages,
        "tamper_rejection": tamper,
        "delivery_compile": delivery or {"technical_lines": 0, "human_lines": 0, "pair_digest": None},
        "status": "passed" if all_ok else "failed",
        "blocker": chain.blocked,
    }


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Run the senior-user-ux-v2 alignment-chain supplement")
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    receipt = run_alignment_chain_supplement(args.workspace)
    print(json.dumps(receipt, ensure_ascii=True, indent=2, sort_keys=True))
    raise SystemExit(0 if receipt["status"] == "passed" else 1)
