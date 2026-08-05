"""Explicit local command boundary for the runtime foundation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import application
from .domain import ArtifactRevision, RuntimeStoreError, thaw_json
from .recursive_search import RecursiveResearchCoordinator
from .alignment_handoff import initialize_research_from_alignment
from .storage import RunStore
from .coordinator import CoordinatorError, ResearchRunCoordinator
from .migrations import MigrationManager


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-tree",
        description=(
            "Manage persisted research rounds and recursive research-tree state."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    create_round = commands.add_parser("create-round", help="create an isolated research round")
    create_round.add_argument("--store", type=Path, required=True, help="explicit run-store root")
    create_round.add_argument("--round-id", help="stable round identifier")
    create_round.add_argument("--parent-round", help="existing parent round identifier")

    show_round = commands.add_parser("show-round", help="show a reconstructed round")
    show_round.add_argument("--store", type=Path, required=True, help="explicit run-store root")
    show_round.add_argument("--round-id", required=True, help="stored round identifier")

    tree_init = commands.add_parser("tree-init", help="initialize a persisted recursive tree")
    tree_init.add_argument("--store", type=Path, required=True)
    tree_init.add_argument("--round-id", required=True)
    tree_init.add_argument("--tree-id", default="research-tree")
    tree_init.add_argument("--decision-slots", type=Path, required=True)
    tree_init.add_argument("--baseline-finding", action="append", default=[])

    alignment_init = commands.add_parser(
        "tree-init-alignment",
        help=(
            "compile a confirmed alignment graph into tree revision zero; "
            "the round must already exist (run create-round first)"
        ),
    )
    alignment_init.add_argument(
        "--store", type=Path, required=True, help="run-store root created with create-round"
    )
    alignment_init.add_argument(
        "--round-id", required=True, help="existing round identifier from create-round"
    )
    alignment_init.add_argument("--tree-id", default="research-tree")
    alignment_init.add_argument("--alignment-db", type=Path, required=True)

    tree_next = commands.add_parser("tree-next", help="show the highest-value active frontier")
    tree_next.add_argument("--store", type=Path, required=True)
    tree_next.add_argument("--round-id", required=True)
    tree_next.add_argument("--tree-id", default="research-tree")
    tree_next.add_argument("--max-parallelism", type=int, default=4)

    tree_ingest = commands.add_parser("tree-ingest", help="ingest persisted Finding Packs")
    tree_ingest.add_argument("--store", type=Path, required=True)
    tree_ingest.add_argument("--round-id", required=True)
    tree_ingest.add_argument("--tree-id", default="research-tree")
    tree_ingest.add_argument("--finding", action="append", required=True)

    tree_recover = commands.add_parser(
        "tree-recover", help="replay Finding Packs created after the last checkpoint"
    )
    tree_recover.add_argument("--store", type=Path, required=True)
    tree_recover.add_argument("--round-id", required=True)
    tree_recover.add_argument("--tree-id", default="research-tree")

    tree_deliver = commands.add_parser(
        "tree-deliver",
        help="verify and register both deep research reports before completion",
    )
    tree_deliver.add_argument("--store", type=Path, required=True)
    tree_deliver.add_argument("--round-id", required=True)
    tree_deliver.add_argument("--tree-id", default="research-tree")
    tree_deliver.add_argument("--technical-report", type=Path, required=True)
    tree_deliver.add_argument("--human-report", type=Path, required=True)

    run = commands.add_parser("run", help="canonical alpha2 coordinator commands")
    run_commands = run.add_subparsers(dest="run_command", required=True)
    run_init = run_commands.add_parser("init")
    run_init.add_argument("--workspace", type=Path, required=True)
    run_init.add_argument("--run-id", required=True)
    run_init.add_argument("--task-identity", type=Path)
    for name in ("status", "next", "replay", "explain", "why-action", "why-not-complete", "recover", "reconcile-host", "export-audit"):
        command = run_commands.add_parser(name)
        command.add_argument("--workspace", type=Path, required=True)
        command.add_argument("--run-id", required=True)
    transition = run_commands.add_parser("transition")
    transition.add_argument("--workspace", type=Path, required=True)
    transition.add_argument("--run-id", required=True)
    transition.add_argument("--event", required=True)
    transition.add_argument("--actor", required=True)
    transition.add_argument("--expected-revision", type=int, required=True)
    transition.add_argument("--payload", type=Path)
    feedback = run_commands.add_parser("feedback")
    feedback.add_argument("--workspace", type=Path, required=True)
    feedback.add_argument("--event", type=Path, required=True)
    feedback.add_argument("--expected-revision", type=int, required=True)
    ingest = run_commands.add_parser("ingest")
    ingest.add_argument("--workspace", type=Path, required=True)
    ingest.add_argument("--event", type=Path, required=True)
    deliver = run_commands.add_parser("deliver")
    deliver.add_argument("--workspace", type=Path, required=True)
    deliver.add_argument("--run-id", required=True)
    deliver.add_argument("--expected-revision", type=int, required=True)
    deliver.add_argument("--technical-digest", required=True)
    deliver.add_argument("--human-digest", required=True)
    accept = run_commands.add_parser("accept")
    accept.add_argument("--workspace", type=Path, required=True)
    accept.add_argument("--run-id", required=True)
    accept.add_argument("--expected-revision", type=int, required=True)
    accept.add_argument("--displayed-digest", required=True)
    accept.add_argument("--technical-revision", required=True)
    accept.add_argument("--human-revision", required=True)
    accept.add_argument("--feedback", required=True)
    obligation = run_commands.add_parser("satisfy")
    obligation.add_argument("--workspace", type=Path, required=True)
    obligation.add_argument("--run-id", required=True)
    obligation.add_argument("--obligation", required=True)
    obligation.add_argument("--evidence-ref", required=True)
    obligation.add_argument("--expected-revision", type=int, required=True)
    migrate = run_commands.add_parser("migrate")
    migrate.add_argument("--workspace", type=Path, required=True)
    migrate.add_argument("--source", action="append", required=True)
    migrate.add_argument("--destination-root", default=".research-tree/imported")
    migrate.add_argument("--mode", choices=("inventory", "dry-run", "apply", "verify", "rollback", "status"), default="dry-run")
    migrate.add_argument("--confirm")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "run":
        try:
            if arguments.run_command == "feedback":
                value = json.loads(arguments.event.read_text(encoding="utf-8"))
                run_id = str(value.get("run_id", ""))
                output = ResearchRunCoordinator(arguments.workspace).record_feedback(
                    value, expected_revision=arguments.expected_revision
                )
            elif arguments.run_command == "ingest":
                value = json.loads(arguments.event.read_text(encoding="utf-8"))
                output = ResearchRunCoordinator(arguments.workspace).ingest_host_event(value)
            elif arguments.run_command == "migrate":
                manager = MigrationManager(arguments.workspace)
                if arguments.mode == "inventory":
                    output = manager.inventory(arguments.source, destination_root=arguments.destination_root)
                elif arguments.mode == "dry-run":
                    output = manager.dry_run(arguments.source, destination_root=arguments.destination_root)
                elif arguments.mode == "apply":
                    output = manager.apply(arguments.source, destination_root=arguments.destination_root, confirmation=arguments.confirm)
                elif arguments.mode == "verify":
                    output = manager.verify()
                elif arguments.mode == "rollback":
                    output = manager.rollback()
                else:
                    output = manager.status()
            else:
                coordinator = ResearchRunCoordinator(arguments.workspace)
                if arguments.run_command == "init":
                    identity = {}
                    if arguments.task_identity:
                        identity = json.loads(arguments.task_identity.read_text(encoding="utf-8"))
                    output = coordinator.create(arguments.run_id, task_identity=identity)
                elif arguments.run_command == "status":
                    output = coordinator.status(arguments.run_id)
                elif arguments.run_command == "next":
                    output = coordinator.next_actions(arguments.run_id)
                elif arguments.run_command == "satisfy":
                    output = coordinator.record_obligation(arguments.run_id, arguments.obligation, evidence_ref=arguments.evidence_ref, expected_revision=arguments.expected_revision)
                elif arguments.run_command == "replay":
                    output = coordinator.replay(arguments.run_id)
                elif arguments.run_command in {"explain", "why-action"}:
                    output = coordinator.why_action(arguments.run_id)
                elif arguments.run_command == "why-not-complete":
                    output = coordinator.why_not_complete(arguments.run_id)
                elif arguments.run_command == "export-audit":
                    output = coordinator.audit(arguments.run_id)
                elif arguments.run_command == "recover":
                    output = coordinator.recover(arguments.run_id)
                elif arguments.run_command == "reconcile-host":
                    output = coordinator.reconcile_host(arguments.run_id)
                elif arguments.run_command == "deliver":
                    output = coordinator.deliver(arguments.run_id, expected_revision=arguments.expected_revision, technical_digest=arguments.technical_digest, human_digest=arguments.human_digest)
                elif arguments.run_command == "accept":
                    output = coordinator.accept(arguments.run_id, expected_revision=arguments.expected_revision, displayed_digest=arguments.displayed_digest, technical_revision=arguments.technical_revision, human_revision=arguments.human_revision, feedback=arguments.feedback)
                else:
                    payload = {}
                    if arguments.payload:
                        payload = json.loads(arguments.payload.read_text(encoding="utf-8"))
                    output = coordinator.transition(arguments.run_id, event=arguments.event, actor=arguments.actor, expected_revision=arguments.expected_revision, payload=payload)
            print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        except (CoordinatorError, OSError, ValueError, json.JSONDecodeError) as error:
            parser.error(str(error))
    store = RunStore(arguments.store)
    try:
        if arguments.command == "create-round":
            record = application.create_round(
                store,
                arguments.round_id,
                parent_round_id=arguments.parent_round,
            )
            output = record.to_dict()
        elif arguments.command == "show-round":
            output = application.load_round(store, arguments.round_id).to_dict()
        elif arguments.command == "tree-init":
            slots = _read_decision_slots(arguments.decision_slots)
            baseline = _latest_findings(
                store,
                arguments.round_id,
                arguments.baseline_finding,
            )
            artifact = RecursiveResearchCoordinator(store).initialize(
                round_id=arguments.round_id,
                tree_id=arguments.tree_id,
                decision_slots=slots,
                baseline_findings=baseline,
            )
            output = artifact.to_dict()
        elif arguments.command == "tree-init-alignment":
            artifact = initialize_research_from_alignment(
                store,
                round_id=arguments.round_id,
                tree_id=arguments.tree_id,
                alignment_database=arguments.alignment_db,
            )
            output = artifact.to_dict()
        elif arguments.command == "tree-next":
            output = {
                "tree_id": arguments.tree_id,
                "actions": [
                    thaw_json(action)
                    for action in RecursiveResearchCoordinator(store).next_actions(
                        round_id=arguments.round_id,
                        tree_id=arguments.tree_id,
                        max_parallelism=arguments.max_parallelism,
                    )
                ],
            }
        elif arguments.command == "tree-ingest":
            findings = _latest_findings(
                store,
                arguments.round_id,
                arguments.finding,
            )
            artifact = RecursiveResearchCoordinator(store).ingest(
                round_id=arguments.round_id,
                tree_id=arguments.tree_id,
                finding_packs=findings,
            )
            output = artifact.to_dict()
        elif arguments.command == "tree-deliver":
            artifact = RecursiveResearchCoordinator(store).finalize_delivery(
                round_id=arguments.round_id,
                tree_id=arguments.tree_id,
                technical_report=arguments.technical_report,
                human_report=arguments.human_report,
            )
            output = artifact.to_dict()
        else:
            artifact = RecursiveResearchCoordinator(store).recover(
                round_id=arguments.round_id,
                tree_id=arguments.tree_id,
            )
            output = artifact.to_dict()
    except (RuntimeStoreError, OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _read_decision_slots(path: Path) -> Mapping[str, Mapping[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, Mapping) and isinstance(value.get("decision_slots"), Mapping):
        value = value["decision_slots"]
    if not isinstance(value, Mapping):
        raise ValueError("decision-slots JSON must be an object")
    result: dict[str, Mapping[str, Any]] = {}
    for slot_id, slot in value.items():
        if not isinstance(slot_id, str) or not isinstance(slot, Mapping):
            raise ValueError("decision-slots JSON values must be objects")
        result[slot_id] = slot
    return result


def _latest_findings(
    store: RunStore,
    round_id: str,
    finding_ids: Sequence[str],
) -> tuple[ArtifactRevision, ...]:
    snapshot = store.load_round(round_id)
    findings: list[ArtifactRevision] = []
    for finding_id in finding_ids:
        candidates = [
            artifact
            for artifact in snapshot.artifacts
            if artifact.id == finding_id and artifact.kind == "finding-pack"
        ]
        if not candidates:
            raise ValueError(f"Finding Pack does not exist: {finding_id}")
        findings.append(max(candidates, key=lambda artifact: artifact.revision))
    return tuple(findings)
