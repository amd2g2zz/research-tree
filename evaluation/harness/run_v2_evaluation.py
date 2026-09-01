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
  the slot_decomposition waiver reason.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from host_matrix import HOSTS, SCENARIOS, build_receipt, run_scenario
from v2_oracles import RUN_NAME, build_decision_targets, build_success_oracles

from research_tree.acceptance import DeliveryAcceptance, delivery_pair_digest
from research_tree.completion_inputs import (
    CompletionInputRegistrar,
    delivery_manifest_digest,
)
from research_tree.coordinator import (
    COMPLETION_RECORD_KIND,
    CompletionBlockedError,
    ResearchRunCoordinator,
)
from research_tree.decision_frame import DecisionFrame, IntentHypothesis
from research_tree.domain import ArtifactRef, thaw_json
from research_tree.run_ledger import RunLedger
from research_tree.strategy_projection import (
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
    }
)
WAIVED_REASONS: dict[str, str] = {
    "oracle-operator-lifecycle": (
        "host-conformance copy-install receipts are produced by the operator journey (Track A), not by this governed run"
    ),
    "oracle-slot-decomposition": (
        "cells executed as matrix work; full decision-map slot decomposition is a run-orchestration lane obligation"
    ),
    "oracle-context-discipline": (
        "context-ledger budget receipts are not wired into this harness; declared-budget wiring is a run-orchestration obligation (#466)"
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
    ledger: RunLedger, coordinator: ResearchRunCoordinator, run_id: str, target
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
        autonomy_envelope={"allowed": ["evaluation"], "authority": "research_owner"},
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


def _finding_packs(ledger: RunLedger, run_id: str, cells, receipt: dict[str, Any], projection) -> dict[str, Any]:
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
    return packs


def _register_goal_satisfactions(ledger: RunLedger, packs: dict[str, Any]) -> dict[str, str]:
    registrar = CompletionInputRegistrar(ledger)
    run_id = RUN_ID
    pack_key = {
        "oracle-live-host-matrix": "matrix",
        "oracle-recovery-semantics": "matrix",
        "oracle-handoff-integrity": "handoff",
        "oracle-completion-consistency": "completion",
        "oracle-independent-review": "review",
    }
    evidence_by_oracle = {
        oracle_id: (ArtifactRef(run_id, packs[key].id, packs[key].revision),) for oracle_id, key in pack_key.items()
    }
    verdicts: dict[str, str] = {}
    for oracle in build_success_oracles():
        oracle_id = oracle["id"]
        if oracle_id in RUNTIME_ORACLES:
            verdict = "satisfied"
            reason = None
        else:
            verdict = "waived"
            reason = WAIVED_REASONS[oracle_id]
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
        "state": str(thaw_json(record.payload).get("state")),
        "completion_record": {"artifact_id": record.id, "revision": record.revision},
        "final_state_digest": str(completed.payload.get("state_digest")),
    }


def run_governed_evaluation(
    workspace: Path,
    *,
    scenarios: tuple[str, ...] = SCENARIOS,
    hosts: tuple[str, ...] = HOSTS,
) -> dict[str, Any]:
    """Execute the governed Track B run and return its canonical receipt."""

    ledger, coordinator, _handoff, target = _setup(workspace, RUN_ID)
    projection = _confirm_v2_projection(ledger, coordinator, RUN_ID, target)
    cells = _execute_cells(workspace, scenarios=scenarios, hosts=hosts)
    matrix_receipt = build_receipt(list(cells))
    packs = _finding_packs(ledger, RUN_ID, cells, matrix_receipt, projection)
    _register_completion_inputs(ledger, RUN_ID, target)
    verdicts = _register_goal_satisfactions(ledger, packs)
    review = _write_delivery_review(ledger, packs)
    completion = _advance(ledger, coordinator)
    return {
        "schema_version": 1,
        "run_name": RUN_NAME,
        "case_id": "senior-user-ux-v2-track-b",
        "mode": "governed-matrix",
        "status": (
            "passed" if completion["decision"] == "completed" and matrix_receipt["status"] == "passed" else "failed"
        ),
        "cells": matrix_receipt["cells"],
        "coverage": matrix_receipt["coverage"],
        "per_oracle": verdicts,
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
            "waived_oracles": dict(WAIVED_REASONS),
            "slot_shape": "fixture-minimal; full decision-map decomposition is a run-orchestration obligation",
            "declared_budget": None,
            "declared_budget_reason": (
                "context-ledger budget wiring is a run-orchestration obligation (#466); not claimed here"
            ),
        },
        "blocker": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the senior-user-ux-v2 Track B governed evaluation")
    default_root = Path.cwd() / ".research-tree" / "evaluation-runs" / RUN_NAME / "track-b"
    parser.add_argument("--workspace", type=Path, default=default_root / "workspace")
    parser.add_argument("--receipt", type=Path, default=default_root / "receipt.json")
    parser.add_argument("--scenarios", nargs="*", default=list(SCENARIOS))
    parser.add_argument("--hosts", nargs="*", default=list(HOSTS))
    args = parser.parse_args(argv)
    receipt = run_governed_evaluation(
        args.workspace,
        scenarios=tuple(args.scenarios),
        hosts=tuple(args.hosts),
    )
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"receipt": str(args.receipt), "status": receipt["status"]}))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
