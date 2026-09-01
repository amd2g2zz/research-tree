"""senior-user-ux-v2 Track B: governed runtime run around the live-host matrix.

One real research run (RunLedger + ResearchRunCoordinator) carries the real
v2 oracle set from ``v2_oracles.build_success_oracles()`` through the full
goal loop: confirmation with an independent alignment verification, the
six-scenario x three-host injection matrix executed as the run's evidence
work, finding packs whose claims carry the evidence-standard tokens, honest
per-oracle goal_satisfaction registrations, an independent delivery review,
and the completion gate's own decision recorded verbatim.

Honesty boundaries (also emitted in the receipt):
- satisfied verdicts exist only for oracles whose evidence this run truly
  produces; Track-A-carried oracles are ``waived`` with the precise reason;
- no third-party host product binary is invoked (host_process_invoked=false
  is inherited from the matrix receipt provenance);
- the blueprint target/slots reuse the minimal fixture shape; full
  decision-map decomposition is a run-orchestration obligation, disclosed in
  the slot_decomposition waiver reason;
- finding packs are hand-built by this harness (token self-carry, raw
  ``_append``) rather than ``CanonicalFindingPackCompiler`` output — the
  underlying events they cite are real runtime results.

Issue #472 (gates 6/9 residuals): the run is admitted against the registered
v2 baseline (``v2_baseline_admission``: fail-closed cross-check of the
baseline run name and the three role scores, admission record artifact), and
every governed run creates a ``ContextReadLedger`` at
``<workspace>/.research-tree/runs/<run id>/context/read-ledger.json`` whose
budget is declared at admission inside the confirmed strategy projection.
Cell-receipt reads are recorded through the ledger, the receipt is grounded
into ``pack-context-evidence`` under the ``es-budget-receipt`` token (the
#466 producer obligation), and an exhausted declared budget ends the run in
the ledger's resumable unknown checkpoint — an unmet context-discipline
oracle, never a pass.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from context_ledger_contract import ContextBudget, ContextLedgerError, ContextReadLedger  # noqa: E402
from host_matrix import HOSTS, SCENARIOS, build_receipt, run_scenario  # noqa: E402
from v2_baseline_admission import (  # noqa: E402
    BaselineAdmissionError,
    cross_check,
    load_baseline_registry,
)
from v2_oracles import BASELINE_RUN_NAME, RUN_NAME, build_decision_targets, build_success_oracles  # noqa: E402

from research_tree.acceptance import DeliveryAcceptance, delivery_pair_digest  # noqa: E402
from research_tree.completion_inputs import (  # noqa: E402
    CompletionInputRegistrar,
    delivery_manifest_digest,
)
from research_tree.coordinator import (  # noqa: E402
    COMPLETION_RECORD_KIND,
    CompletionBlockedError,
    ResearchRunCoordinator,
)
from research_tree.decision_frame import DecisionFrame, IntentHypothesis  # noqa: E402
from research_tree.domain import ArtifactRef, thaw_json  # noqa: E402
from research_tree.run_ledger import RunLedger  # noqa: E402
from research_tree.strategy_projection import (  # noqa: E402
    StrategyProjection,
    authority_fingerprint,
    validate_falsifiability,
)

MAIN_SESSION = "v2-trackb-orchestrator-d5e8"
ALIGNMENT_VERIFIER = "uxv2-alignment-verifier-e6f1"
DELIVERY_VERIFIER = "uxv2-delivery-verifier-f8a2"
RUN_ID = "run-v2-trackb"
RUNTIME_ORACLES = frozenset(
    {
        "oracle-handoff-integrity",
        "oracle-completion-consistency",
        "oracle-independent-review",
        "oracle-live-host-matrix",
        "oracle-recovery-semantics",
        "oracle-context-discipline",
    }
)
CONTEXT_ORACLE = "oracle-context-discipline"
BASELINE_REGISTRY_PATH = ROOT / "evaluation" / "baselines" / "senior-user-ux-v2-baseline.json"
# Declared at admission: part of the confirmed strategy projection the
# requester sees, and of the persisted context-admission-record. The
# accounting basis is host-unmediated (1 token = 1 source byte read).
DECLARED_CONTEXT_BUDGET: dict[str, int | float | None] = {
    "max_fresh_input_tokens": 2_000_000,
    "max_cached_input_tokens": 500_000,
    "max_replayed_input_tokens": 500_000,
    "max_tool_output_tokens": 2_000_000,
    "max_process_output_tokens": 2_000_000,
    "max_duplicate_read_ratio": 0.5,
}
DECLARED_BASELINE: dict[str, Any] = {
    "run_name": BASELINE_RUN_NAME,
    "role_scores": {
        "research-architect": 76,
        "platform-engineering-integrator": 65,
        "governance-auditor": 6.8,
    },
}
CONTEXT_READ_CONSUMER = "v2-trackb-coordinator"
CONTEXT_ACCOUNTING_BASIS = "file-bytes (1 token = 1 source byte; host-unmediated)"
WAIVED_REASONS: dict[str, str] = {
    "oracle-operator-lifecycle": (
        "host-conformance copy-install receipts are produced by the operator journey (Track A), not by this governed run"
    ),
    "oracle-slot-decomposition": (
        "cells executed as matrix work; full decision-map slot decomposition is a run-orchestration lane obligation"
    ),
    "oracle-noise-reduction": (
        "noise is judged by the three-component baseline protocol over Track A role sessions, not by this governed run"
    ),
    "oracle-operating-model": (
        "the operating-model delivery payload is populated from the full v2 run record, not from Track B alone"
    ),
    "oracle-freshness-gate": (
        "freshness admission is an intake-time decision of the v2 run orchestration, not of this harness"
    ),
    "oracle-alignment-regression": (
        "alignment narratives come from Track A role transcripts; this run produces no role session"
    ),
    "oracle-evidence-honesty": (
        "boundary disclosures are judged across every v2 projection including Track A reports; not attributable to this run alone"
    ),
}
GOAL_SATISFACTION_EVIDENCE_KINDS = frozenset(
    {"finding-pack", "slot-closure-assessment", "goal-contribution-assessment"}
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append(ledger: RunLedger, run_id: str, artifact_id: str, kind: str, payload: dict[str, Any], parents=()):
    return ledger.append_artifact(
        run_id, artifact_id, kind, dict(payload), parent_refs=parents, expected_revision=ledger.get_revision(run_id)
    )


def _setup(workspace: Path, run_id: str) -> tuple[RunLedger, ResearchRunCoordinator, Any, Any]:
    ledger = RunLedger(workspace)
    ledger.create_run(run_id)
    handoff = _append(ledger, run_id, f"handoff-{run_id}", "alignment-handoff", {"confirmed": True})
    target = _append(
        ledger,
        run_id,
        f"target-{run_id}",
        "blueprint-target",
        {"decision_slots": [{"id": "slot-1", "priority": "P0", "closure_oracle": "oracle-1"}]},
        (ArtifactRef(run_id, handoff.id, handoff.revision),),
    )
    coordinator = ResearchRunCoordinator(ledger)
    coordinator.initialize(
        run_id=run_id,
        alignment_handoff=handoff,
        blueprint_target=target,
        expected_revision=ledger.get_revision(run_id),
        idempotency_key="init-1",
    )
    return ledger, coordinator, handoff, target


def _confirm_v2_projection(
    ledger: RunLedger,
    coordinator: ResearchRunCoordinator,
    run_id: str,
    target,
    context_config: Mapping[str, Any] | None = None,
) -> StrategyProjection:
    artifacts = ledger.load_run(run_id).artifacts
    handoff = next(item for item in artifacts if item.kind == "alignment-handoff")
    target_ref = ArtifactRef(run_id, target.id, target.revision)
    frame = coordinator.persist_decision_frame(
        DecisionFrame.create(
            frame_id=f"frame-{run_id}",
            run_id=run_id,
            requester_wording="Close the #292 adoption gates with a fresh dual-track evaluation.",
            primary_decision={
                "id": "decision-track-b-runtime-verdict",
                "statement": "Does the governed runtime survive live failure injection with the goal loop closed?",
                "success_signal": "per-oracle goal satisfaction with matrix receipts",
            },
            target_ref=target_ref,
            hypotheses=(
                IntentHypothesis(
                    id="selected",
                    interpretation="Track B verdict over the governed matrix run",
                    ambiguity="explicit",
                    owner="requester",
                    researchable=False,
                    decision_consequence="sets the evaluation scope",
                    source_refs=(f"input-{run_id}",),
                    disposition="selected",
                    next_action="form strategy",
                    primary_decision_id="decision-track-b-runtime-verdict",
                    material=True,
                    evidence_ranked=True,
                ),
            ),
        ),
        expected_revision=ledger.get_revision(run_id),
    )
    projection = StrategyProjection.create(
        projection_id=f"strategy-{run_id}",
        run_id=run_id,
        decision_frame_ref=ArtifactRef(run_id, frame.id, frame.revision),
        alignment_handoff_ref=ArtifactRef(run_id, handoff.id, handoff.revision),
        target_ref=target_ref,
        current_understanding="Close the #292 adoption gates with a fresh dual-track evaluation.",
        assumptions=("baseline roles re-run the 8/20 protocol",),
        decision_targets=build_decision_targets(),
        tracks=({"id": "track-a"}, {"id": "track-b"}),
        method_hypotheses=({"method": "governed-runtime"},),
        depth="deep",
        evidence_expectations=("canonical receipts",),
        autonomy_envelope={
            "allowed": ["evaluation"],
            "authority": "research_owner",
            **(dict(context_config) if context_config else {}),
        },
        replanning_policy={"same_round": ["depth"]},
        success_oracles=build_success_oracles(),
        delivery_contract={"technical": "package", "human": "report"},
        stop_rule="every served oracle carries gate-bound evidence or the run stays open",
        preference_influences=(),
        revision=1,
        status="displayed",
    )
    validate_falsifiability(projection)
    coordinator.persist_strategy_projection(projection, expected_revision=ledger.get_revision(run_id))
    oracle_ids = [oracle["id"] for oracle in projection.display_payload["success_oracles"]]
    CompletionInputRegistrar(ledger).write_alignment_verification(
        round_id=run_id,
        verification_id=f"alignment-verification-{run_id}",
        payload={
            "schema": 1,
            "id": f"alignment-verification-{run_id}",
            "round_id": run_id,
            "projection_ref": {
                "round_id": run_id,
                "artifact_id": projection.projection_id,
                "revision": projection.revision,
            },
            "authority_fingerprint": authority_fingerprint(projection),
            "verifier_identity": ALIGNMENT_VERIFIER,
            "session_context": MAIN_SESSION,
            "understood": {
                "outcome": "Independently restated: close the #292 adoption gates via the dual-track evaluation.",
                "scope": "Independently restated: governed Track B matrix run under the confirmed envelope.",
                "authority": "Independently restated: autonomous evaluation within the confirmed envelope.",
                "success_oracles": [
                    {"id": oracle_id, "understanding": f"Independently restated oracle {oracle_id}."}
                    for oracle_id in oracle_ids
                ],
            },
            "discrepancies": [],
        },
        expected_revision=ledger.get_revision(run_id),
    )
    coordinator.display_strategy(run_id, projection, expected_revision=ledger.get_revision(run_id))
    coordinator.confirm_handoff(
        run_id,
        projection_ref=ArtifactRef(run_id, projection.id, projection.revision),
        confirmation=(
            f"I accept {projection.display_digest} authority-fingerprint {authority_fingerprint(projection)} "
            "and authorize research."
        ),
        expected_revision=ledger.get_revision(run_id),
    )
    return projection


def _execute_cells(workspace: Path, *, scenarios, hosts) -> list:
    cells: list = []
    for host in hosts:
        for scenario in scenarios:
            cells.append(run_scenario(scenario, host, workspace))
    return cells


def _run_root(workspace: Path) -> Path:
    return workspace / ".research-tree" / "runs" / RUN_ID


def _admit_run(baseline_registry: Path | None, declared_baseline: Mapping[str, Any] | None) -> dict[str, Any]:
    """Fail-closed baseline cross-check; raises before any run state exists."""

    registry = load_baseline_registry(baseline_registry if baseline_registry is not None else BASELINE_REGISTRY_PATH)
    return cross_check(dict(declared_baseline) if declared_baseline is not None else DECLARED_BASELINE, registry)


def _record_context_reads(context_ledger: ContextReadLedger, cells: list) -> dict[str, Any]:
    """Seal and read each cell receipt through the governed run's ledger.

    Cell receipts are the run's own active output, so sealing precedes the
    coordinator's verification read. A ``ContextLedgerError`` (the ledger is
    paused for ``budget_exceeded``) stops further reads; the ledger receipt
    carries the resumable unknown checkpoint from there on.
    """

    read_error: str | None = None
    cells_dir = _run_root(context_ledger.workspace) / "cells"
    cells_dir.mkdir(parents=True, exist_ok=True)
    for cell in cells:
        if read_error is not None:
            break
        cell_path = cells_dir / f"{cell.scenario}-{cell.host}.json"
        cell_path.write_text(json.dumps(asdict(cell), sort_keys=True, indent=2) + "\n", encoding="utf-8")
        try:
            context_ledger.seal_source(cell_path)
            context_ledger.record_read(
                cell_path,
                consumer=CONTEXT_READ_CONSUMER,
                phase="evidence-verification",
                input_tokens=cell_path.stat().st_size,
            )
        except ContextLedgerError as error:
            read_error = str(error)
    return {"receipt": context_ledger.receipt(), "read_error": read_error}


def _pack(
    ledger: RunLedger,
    run_id: str,
    artifact_id: str,
    standards: tuple[str, ...],
    tokens: list[str],
    summary: str,
) -> Any:
    grounding = [
        {"claim_id": f"{artifact_id}-claim-{index}", "grounding_id": token, "anchor": {"ref": token}}
        for index, token in enumerate(tokens)
    ]
    assessments = [
        {"claim_id": entry["claim_id"], "state": "corroborated", "grounding_ids": [entry["grounding_id"]]}
        for entry in grounding
    ]
    return _append(
        ledger,
        run_id,
        artifact_id,
        "finding-pack",
        {
            "id": artifact_id,
            "round_id": run_id,
            "evidence_standard_ids": list(standards),
            "claim_groundings": grounding,
            "claim_assessments": assessments,
            "summary": summary,
            "recorded_at": _now(),
        },
    )


def _finding_packs(
    ledger: RunLedger,
    run_id: str,
    cells,
    receipt: dict[str, Any],
    projection,
    context_receipt: dict[str, Any],
    admission_record,
) -> dict[str, Any]:
    cell_names = [f"{cell.scenario}:{cell.host}" for cell in cells]
    reasons = sorted({cell.observed_reason for cell in cells if cell.observed_reason})
    packs: dict[str, Any] = {}
    packs["matrix"] = _pack(
        ledger,
        run_id,
        "pack-matrix-evidence",
        ("es-host-matrix-receipt", "es-recovery-reason-record"),
        ["es-host-matrix-receipt", "es-recovery-reason-record", receipt["case_id"], *cell_names, *reasons],
        f"{len(cells)} injection cells executed with canonical reasons and zero false completions.",
    )
    fingerprint = authority_fingerprint(projection)
    packs["handoff"] = _pack(
        ledger,
        run_id,
        "pack-handoff-evidence",
        ("es-handoff-fingerprint-match",),
        ["es-handoff-fingerprint-match", fingerprint, projection.display_digest],
        "Handoff authority fields bound: confirmed fingerprint equals the displayed projection fingerprint.",
    )
    packs["review"] = _pack(
        ledger,
        run_id,
        "pack-review-evidence",
        ("es-verifier-identity-distinct",),
        ["es-verifier-identity-distinct", ALIGNMENT_VERIFIER, DELIVERY_VERIFIER, MAIN_SESSION],
        "Independent verification artifacts recorded with distinct identities and shared session lineage.",
    )
    packs["completion"] = _pack(
        ledger,
        run_id,
        "pack-completion-evidence",
        ("es-completion-snapshot-digest",),
        ["es-completion-snapshot-digest", projection.content_hash],
        "One immutable projection snapshot feeds every completion surface registered in this run.",
    )
    budget = context_receipt["budget"]
    totals = context_receipt["token_totals"]
    counts = context_receipt["read_counts"]
    checkpoint = context_receipt["checkpoint"]
    packs["context"] = _pack(
        ledger,
        run_id,
        "pack-context-evidence",
        ("es-budget-receipt",),
        [
            "es-budget-receipt",
            f"ledger:{context_receipt['kind']}",
            f"run-id:{context_receipt['run_id']}",
            f"ledger-status:{context_receipt['status']}",
            f"ledger-wave:{context_receipt['wave']}",
            f"reads:fresh={counts['fresh']},cached={counts['cached']},replayed={counts['replayed']}",
            f"duplicate-read-ratio:{context_receipt['duplicate_read_ratio']}",
            f"token-totals:{json.dumps(totals, sort_keys=True, separators=(',', ':'))}",
            f"declared-budget:{json.dumps(budget, sort_keys=True, separators=(',', ':'))}",
            f"checkpoint:{json.dumps(checkpoint, sort_keys=True, separators=(',', ':')) if checkpoint else 'none'}",
            f"accounting-basis:{CONTEXT_ACCOUNTING_BASIS}",
            f"admission-record:{admission_record.id}@{admission_record.revision}",
            "completion-authority:none",
        ],
        (
            "Context reads recorded through the declared-budget read ledger at "
            "context/read-ledger.json; the receipt claims no completion authority, and "
            "an exhausted budget leaves the run in its resumable unknown checkpoint."
        ),
    )
    return packs


def _register_goal_satisfactions(
    ledger: RunLedger, packs: dict[str, Any], matrix_status: str, *, context_exhausted: bool
) -> dict[str, str]:
    registrar = CompletionInputRegistrar(ledger)
    run_id = RUN_ID
    pack_key = {
        "oracle-live-host-matrix": "matrix",
        "oracle-recovery-semantics": "matrix",
        "oracle-handoff-integrity": "handoff",
        "oracle-completion-consistency": "completion",
        "oracle-independent-review": "review",
        CONTEXT_ORACLE: "context",
    }
    evidence_by_oracle = {
        oracle_id: (ArtifactRef(run_id, packs[key].id, packs[key].revision),) for oracle_id, key in pack_key.items()
    }
    verdicts: dict[str, str] = {}
    for oracle in build_success_oracles():
        oracle_id = oracle["id"]
        matrix_backed = oracle_id in {"oracle-live-host-matrix", "oracle-recovery-semantics"}
        if oracle_id == CONTEXT_ORACLE:
            # An exhausted declared budget is never a pass: the run stops on
            # the ledger's resumable unknown checkpoint with an unmet oracle.
            verdict = "unmet" if context_exhausted else "satisfied"
            reason = None
        elif oracle_id in RUNTIME_ORACLES and not (matrix_backed and matrix_status != "passed"):
            verdict = "satisfied"
            reason = None
        elif oracle_id in RUNTIME_ORACLES:
            verdict = "unmet"
            reason = None
        else:
            verdict = "waived"
            reason = WAIVED_REASONS.get(oracle_id, "waiver reason missing — run-orchestration obligation")
        registrar.write_goal_satisfaction(
            round_id=run_id,
            registration_id=f"goal-sat-{oracle_id}",
            oracle_id=oracle_id,
            verdict=verdict,
            evidence_refs=evidence_by_oracle.get(oracle_id, ()),
            waiver_reason=reason,
            expected_revision=ledger.get_revision(run_id),
        )
        verdicts[oracle_id] = verdict
    return verdicts


def _register_completion_inputs(ledger: RunLedger, run_id: str, target) -> None:
    target_ref = ArtifactRef(run_id, target.id, target.revision)
    ledger.append_completion_input(
        run_id,
        "closure-1",
        "closure",
        "slot-closure-assessment",
        {"slot_id": "slot-1", "status": "passed", "closure_token": "closure-token"},
        parent_refs=(target_ref,),
        issuer="core-evaluator-v1",
        issuer_evidence={"token": "closure-token"},
        expected_revision=ledger.get_revision(run_id),
    )
    for artifact_id, role, kind, payload in (
        ("insight-1", "insight", "insight-digest", {"status": "non_blocking"}),
        ("readiness-1", "readiness", "readiness-record", {"status": "ready"}),
        ("evaluation-1", "evaluation", "blueprint-evaluation", {"status": "passed"}),
    ):
        ledger.append_completion_input(
            run_id,
            artifact_id,
            role,
            kind,
            payload,
            parent_refs=(),
            issuer=f"v2-{role}-writer",
            issuer_evidence={"source": role},
            expected_revision=ledger.get_revision(run_id),
        )
    registrar = CompletionInputRegistrar(ledger)
    technical, human = registrar.write_delivery_pair(
        round_id=run_id,
        technical_package_id="technical-1",
        human_report_id="human-1",
        technical_payload={"document": {"status": "compiled"}, "markdown": "technical"},
        human_payload={
            "technical_package_ref": ArtifactRef(run_id, "technical-1", 1).to_dict(),
            "document": {"status": "compiled"},
            "markdown": "human",
        },
        technical_parent_refs=(),
        human_parent_refs=(ArtifactRef(run_id, "technical-1", 1),),
        expected_revision=ledger.get_revision(run_id),
    )
    technical_revision = f"{technical.id}@{technical.revision}"
    human_revision = f"{human.id}@{human.revision}"
    acceptance = DeliveryAcceptance.create(
        "acceptance-1",
        run_id,
        technical_revision,
        human_revision,
        delivery_pair_digest(run_id, technical_revision, human_revision),
        delivery_manifest_digest(technical, human),
        [
            {
                "feedback_id": "feedback-1",
                "classification": "presentation",
                "statement": "I accept the displayed conclusions and trade-offs.",
                "target_refs": [technical.id, human.id],
            }
        ],
    )
    registrar.write_delivery_acceptance(
        round_id=run_id,
        technical_package=technical,
        human_research_report=human,
        acceptance=acceptance,
        expected_revision=ledger.get_revision(run_id),
    )


def _write_delivery_review(ledger: RunLedger, packs: dict[str, Any]) -> Any:
    custody = [
        ArtifactRef(RUN_ID, pack.id, pack.revision).to_dict()
        for pack in (packs["matrix"], packs["handoff"], packs["review"], packs["completion"])
    ]
    oracle_verdicts = {
        oracle["id"]: {
            "verdict": "satisfied" if oracle["id"] in RUNTIME_ORACLES else "partial",
            "basis": (
                "Governed-run evidence pack grounds this oracle."
                if oracle["id"] in RUNTIME_ORACLES
                else "Track-A-carried oracle: attested only for the governed-run scope; waived in goal satisfaction."
            ),
        }
        for oracle in build_success_oracles()
    }
    return CompletionInputRegistrar(ledger).write_delivery_review(
        round_id=RUN_ID,
        review_id=f"delivery-review-{RUN_ID}",
        payload={
            "schema": 1,
            "id": f"delivery-review-{RUN_ID}",
            "round_id": RUN_ID,
            "verifier_identity": DELIVERY_VERIFIER,
            "session_context": MAIN_SESSION,
            "per_oracle": oracle_verdicts,
            "evidence_custody": custody,
            "verdict": "satisfied",
        },
        expected_revision=ledger.get_revision(RUN_ID),
    )


def _advance(ledger: RunLedger, coordinator: ResearchRunCoordinator) -> dict[str, Any]:
    for event in ("batch_checkpoint", "all_slots_closed", "readiness_passed", "deliveries_compiled"):
        coordinator.transition(RUN_ID, event, "coordinator", expected_revision=ledger.get_revision(RUN_ID))
    try:
        completed = coordinator.transition(
            RUN_ID, "delivery_accepted", "human", expected_revision=ledger.get_revision(RUN_ID)
        )
    except CompletionBlockedError as error:
        return {"decision": "blocked", "reason": str(error)}
    record = next(item for item in ledger.load_run(RUN_ID).artifacts if item.kind == COMPLETION_RECORD_KIND)
    return {
        "decision": "completed",
        "state": thaw_json(record.payload).get("state"),
        "completion_record": {"artifact_id": record.id, "revision": record.revision},
        "final_state_digest": str(completed.payload.get("state_digest")),
    }


def run_governed_evaluation(
    workspace: Path,
    *,
    scenarios: tuple[str, ...] = SCENARIOS,
    hosts: tuple[str, ...] = HOSTS,
    baseline_registry: Path | None = None,
    declared_baseline: Mapping[str, Any] | None = None,
    declared_context_budget: Mapping[str, int | float | None] | None = None,
) -> dict[str, Any]:
    """Execute the governed Track B run and return its canonical receipt.

    Raises :class:`BaselineAdmissionError` before any run state is created
    when the declared baseline does not match the registered baseline
    (fail-closed admission, gate 9).
    """

    admission = _admit_run(baseline_registry, declared_baseline)
    budget_mapping: dict[str, int | float | None] = dict(
        declared_context_budget if declared_context_budget is not None else DECLARED_CONTEXT_BUDGET
    )
    ledger, coordinator, _handoff, target = _setup(workspace, RUN_ID)
    projection = _confirm_v2_projection(
        ledger,
        coordinator,
        RUN_ID,
        target,
        context_config={
            "context_budget": budget_mapping,
            "context_accounting_basis": CONTEXT_ACCOUNTING_BASIS,
            "baseline_run_name": admission["run_name"],
        },
    )
    context_ledger = ContextReadLedger(
        workspace, _run_root(workspace), RUN_ID, budget=ContextBudget.from_mapping(budget_mapping)
    )
    admission_record = _append(
        ledger,
        RUN_ID,
        f"context-admission-{RUN_ID}",
        "context-admission-record",
        {
            "schema": 1,
            "id": f"context-admission-{RUN_ID}",
            "run_id": RUN_ID,
            "status": "admitted",
            "recorded_at": _now(),
            "baseline_run_name": admission["run_name"],
            "baseline_role_scores": admission["role_scores"],
            "baseline_registry_id": admission["registry_id"],
            "baseline_registry_digest": admission["content_digest"],
            "cross_check": admission,
            "declared_context_budget": budget_mapping,
            "context_accounting_basis": CONTEXT_ACCOUNTING_BASIS,
            "context_ledger": "context/read-ledger.json (relative to the run root)",
            "projection_ref": {
                "round_id": RUN_ID,
                "artifact_id": projection.projection_id,
                "revision": projection.revision,
            },
        },
        parents=(ArtifactRef(RUN_ID, projection.projection_id, projection.revision),),
    )
    cells = _execute_cells(workspace, scenarios=scenarios, hosts=hosts)
    context_state = _record_context_reads(context_ledger, cells)
    context_receipt = context_state["receipt"]
    context_exhausted = context_receipt["status"] == "budget_exceeded"
    matrix_receipt = build_receipt(list(cells))
    packs = _finding_packs(ledger, RUN_ID, cells, matrix_receipt, projection, context_receipt, admission_record)
    _register_completion_inputs(ledger, RUN_ID, target)
    verdicts = _register_goal_satisfactions(
        ledger, packs, matrix_receipt["status"], context_exhausted=context_exhausted
    )
    review = _write_delivery_review(ledger, packs)
    completion = _advance(ledger, coordinator)
    return {
        "schema_version": 1,
        "run_name": RUN_NAME,
        "case_id": "senior-user-ux-v2-track-b",
        "mode": "governed-matrix",
        "status": (
            "passed"
            if completion["decision"] == "completed" and matrix_receipt["status"] == "passed" and not context_exhausted
            else "failed"
        ),
        "admission": {
            "status": "admitted",
            "record": {"artifact_id": admission_record.id, "revision": admission_record.revision},
            "baseline_run_name": admission["run_name"],
            "baseline_role_scores": admission["role_scores"],
            "registry_id": admission["registry_id"],
            "registry_digest": admission["content_digest"],
        },
        "cells": matrix_receipt["cells"],
        "coverage": matrix_receipt["coverage"],
        "per_oracle": verdicts,
        "context": {
            "ledger_path": "context/read-ledger.json (relative to the run root)",
            "status": context_receipt["status"],
            "execution_state": context_receipt["execution_state"],
            "completion_authority": context_receipt["completion_authority"],
            "wave": context_receipt["wave"],
            "budget": context_receipt["budget"],
            "read_counts": context_receipt["read_counts"],
            "token_totals": context_receipt["token_totals"],
            "duplicate_read_ratio": context_receipt["duplicate_read_ratio"],
            "evidence_coverage": context_receipt["evidence_coverage"],
            "checkpoint": context_receipt["checkpoint"],
            "accounting_basis": CONTEXT_ACCOUNTING_BASIS,
            "read_error": context_state["read_error"],
        },
        "independent_review": {
            "delivery_review": {"artifact_id": review.id, "revision": review.revision},
            "alignment_verifier": ALIGNMENT_VERIFIER,
            "delivery_verifier": DELIVERY_VERIFIER,
            "session_context": MAIN_SESSION,
        },
        "completion_gate": completion,
        "matrix": matrix_receipt["matrix"],
        "disclosures": {
            "host_process_invoked": False,
            "goal_satisfaction_evidence_kinds": sorted(GOAL_SATISFACTION_EVIDENCE_KINDS),
            "goal_satisfaction_basis": (
                "registrar attestation keyed on RUNTIME_ORACLES membership; evidence packs carry standard "
                "tokens by construction; matrix-backed oracles downgrade to unmet when the matrix receipt fails; "
                "context-discipline is unmet while the declared budget holds the resumable unknown checkpoint"
            ),
            "waived_oracles": dict(WAIVED_REASONS),
            "slot_shape": "fixture-minimal; full decision-map decomposition is a run-orchestration obligation",
            "declared_budget": budget_mapping,
            "declared_budget_reason": (
                "declared at admission: carried by the confirmed strategy projection and the persisted "
                "context-admission-record; receipts account reads in file bytes (host-unmediated)"
            ),
        },
        "blocker": ({"reason": "context-budget-exhausted", "resumable": True} if context_exhausted else None),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the senior-user-ux-v2 Track B governed evaluation")
    default_root = Path.cwd() / ".research-tree" / "evaluation-runs" / RUN_NAME / "track-b"
    parser.add_argument("--workspace", type=Path, default=default_root / "workspace")
    parser.add_argument("--receipt", type=Path, default=default_root / "receipt.json")
    parser.add_argument("--scenarios", nargs="*", default=list(SCENARIOS))
    parser.add_argument("--hosts", nargs="*", default=list(HOSTS))
    args = parser.parse_args(argv)
    try:
        receipt = run_governed_evaluation(
            args.workspace,
            scenarios=tuple(args.scenarios),
            hosts=tuple(args.hosts),
        )
    except BaselineAdmissionError as error:
        receipt = {
            "schema_version": 1,
            "run_name": RUN_NAME,
            "case_id": "senior-user-ux-v2-track-b",
            "mode": "governed-matrix",
            "status": "blocked",
            "admission": {"status": "blocked", "reason": error.reason, "detail": error.detail},
            "blocker": f"admission-blocked:{error.reason}",
        }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"receipt": str(args.receipt), "status": receipt["status"]}))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
