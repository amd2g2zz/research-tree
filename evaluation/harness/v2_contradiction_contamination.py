"""senior-user-ux-v2 Track B supplements: contradiction detection + contamination gate.

Two coverage gaps in the governed run, closed in-process against real runtime
mechanisms:

1. Contradiction detection: genuine value conflicts between overlapping
   claims must be detected as authority-blocking packets, scope-separated
   pairs must stay authority-conferring, and packets must survive canonical
   ledger persistence.
2. Contamination gate: reads of active outputs require sealing, discovery
   excludes unsealed active outputs, dispositions are fresh/cached/replayed,
   and an exhausted declared budget produces a resumable checkpoint that
   blocks further reads — cost telemetry never becomes completion.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from context_ledger_contract import (  # noqa: E402
    ContextBudget,
    ContextLedgerError,
    ContextReadLedger,
)

from research_tree.contradictions import (  # noqa: E402
    ContradictionStatus,
    claim_from_mapping,
    detect_contradictions,
    unresolved_claim_ids,
)
from research_tree.domain import thaw_json  # noqa: E402
from research_tree.run_ledger import RunLedger  # noqa: E402

RUN_NAME = "senior-user-ux-v2"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_contradiction_supplement(workspace: Path) -> dict[str, Any]:
    """Detect, persist, and authority-check real claim contradictions."""

    claims = [
        claim_from_mapping(
            {
                "claim_id": "claim-contested-a",
                "subject": "completion gate slot-closure verdicts",
                "predicate": "passed count at final checkpoint",
                "value": "3",
                "polarity": "positive",
                "scope": "the governed track-b run",
                "version": "current",
                "time_range": "2026-09-01/2026-09-01",
                "conditions": [],
            }
        ),
        claim_from_mapping(
            {
                "claim_id": "claim-contested-b",
                "subject": "completion gate slot-closure verdicts",
                "predicate": "passed count at final checkpoint",
                "value": "5",
                "polarity": "positive",
                "scope": "the governed track-b run",
                "version": "current",
                "time_range": "2026-09-01/2026-09-01",
                "conditions": [],
            }
        ),
        claim_from_mapping(
            {
                "claim_id": "claim-separated-a",
                "subject": "delivery manifest digest basis",
                "predicate": "digest algorithm",
                "value": "sha256 over canonical pair payload",
                "polarity": "positive",
                "scope": "delivery compile",
                "version": "1.x",
                "time_range": "2026-01-01/2026-12-31",
                "conditions": [],
            }
        ),
        claim_from_mapping(
            {
                "claim_id": "claim-separated-b",
                "subject": "delivery manifest digest basis",
                "predicate": "digest algorithm",
                "value": "md5 over concatenated bytes",
                "polarity": "positive",
                "scope": "delivery compile",
                "version": "2.x",
                "time_range": "2026-01-01/2026-12-31",
                "conditions": [],
            }
        ),
    ]
    packets = detect_contradictions(claims)
    by_status: dict[str, list[list[str]]] = {}
    for packet in packets:
        by_status.setdefault(str(packet.status.value), []).append(list(packet.claim_ids))
    contested = by_status.get(ContradictionStatus.CONTESTED.value, [])
    separated = by_status.get(ContradictionStatus.SCOPE_SEPARATED.value, [])
    authority_blocked = unresolved_claim_ids(claims)
    contested_pair = {"claim-contested-a", "claim-contested-b"}
    separated_pair = {"claim-separated-a", "claim-separated-b"}
    checks = {
        "contested_pair_detected": any(contested_pair <= set(group) for group in contested),
        "contested_pair_lacks_decision_authority": contested_pair <= set(authority_blocked),
        "scope_separated_pair_detected": any(separated_pair <= set(group) for group in separated),
        "scope_separated_pair_keeps_authority": separated_pair.isdisjoint(authority_blocked),
    }
    ledger = RunLedger(workspace)
    run_id = "run-v2-contradiction"
    ledger.create_run(run_id)
    payload = {
        "id": "pack-contradiction-packets",
        "round_id": run_id,
        "contradiction_packets": [
            {
                "claim_ids": list(packet.claim_ids),
                "status": str(packet.status.value),
                "reason": packet.reason,
                "conflicting_values": list(packet.conflicting_values),
                "unresolved_dimensions": list(packet.unresolved_dimensions),
                "decision_authority": packet.decision_authority,
            }
            for packet in packets
        ],
        "unresolved_claim_ids": sorted(authority_blocked),
        "recorded_at": _now(),
    }
    ledger.append_artifact(
        run_id,
        "pack-contradiction-packets",
        "finding-pack",
        payload,
        expected_revision=ledger.get_revision(run_id),
    )
    stored = next(item for item in ledger.load_run(run_id).artifacts if item.id == "pack-contradiction-packets")
    round_trip = json.loads(json.dumps(thaw_json(stored.payload["contradiction_packets"])))
    expected = json.loads(json.dumps(payload["contradiction_packets"]))
    persisted = {
        "artifact_id": stored.id,
        "packet_count": len(stored.payload.get("contradiction_packets", [])),
        "round_trip_identical": round_trip == expected,
    }
    checks["packets_survive_ledger_round_trip"] = bool(persisted["round_trip_identical"]) and persisted[
        "packet_count"
    ] == len(packets)
    passed = all(checks.values())
    return {
        "stage": "contradiction-detection",
        "checks": checks,
        "packets": {status: groups for status, groups in sorted(by_status.items())},
        "unresolved_claim_ids": sorted(authority_blocked),
        "persistence": persisted,
        "status": "passed" if passed else "failed",
    }


def run_contamination_supplement(workspace: Path) -> dict[str, Any]:
    """Prove the contamination gate: sealing, discovery exclusion, budget checkpoint."""

    sources = workspace / "sources"
    active = workspace / ".research-tree-hooks"
    sources.mkdir(parents=True, exist_ok=True)
    active.mkdir(parents=True, exist_ok=True)
    report = sources / "report.md"
    report.write_text("# bounded source\n\nReal content for the contamination probe.\n", encoding="utf-8")
    live_log = active / "live.log"
    live_log.write_text("growing active output\n" * 20, encoding="utf-8")
    other_log = active / "other.log"
    other_log.write_text("unsealed active output\n", encoding="utf-8")
    run_root = workspace / "run-v2-contam"
    ledger = ContextReadLedger(workspace, run_root, "run-v2-contam")
    checks: dict[str, Any] = {}

    try:
        ledger.record_read(live_log, consumer="probe", phase="recon")
        checks["unsealed_active_output_rejected"] = {"ok": False, "detail": "no rejection raised"}
    except ContextLedgerError as error:
        checks["unsealed_active_output_rejected"] = {
            "ok": "active_output_unsealed" in str(error),
            "detail": str(error),
        }

    ledger.seal_source(live_log)
    first = ledger.record_read(live_log, consumer="probe-a", phase="recon")
    dispositions = [entry["disposition"] for entry in first["records"]]
    checks["sealed_active_output_readable"] = {"ok": dispositions == ["fresh"], "detail": str(dispositions)}
    second = ledger.record_read(live_log, consumer="probe-a", phase="execute")
    third = ledger.record_read(live_log, consumer="probe-b", phase="execute")
    checks["dispositions_fresh_cached_replayed"] = {
        "ok": (
            first["records"][-1]["disposition"] == "fresh"
            and second["records"][-1]["disposition"] == "cached"
            and third["records"][-1]["disposition"] == "replayed"
        ),
        "detail": (
            f"first={first['records'][-1]['disposition']}, "
            f"second={second['records'][-1]['disposition']}, "
            f"third={third['records'][-1]['disposition']}"
        ),
    }

    discovered = {path.relative_to(workspace).as_posix() for path in ledger.discover_sources()}
    checks["discovery_excludes_unsealed_active_output"] = {
        "ok": other_log.relative_to(workspace).as_posix() not in discovered
        and live_log.relative_to(workspace).as_posix() in discovered
        and report.relative_to(workspace).as_posix() in discovered,
        "detail": f"discovered={sorted(discovered)}",
    }

    checks["exhausted_budget_blocks_further_reads"] = {"ok": False, "detail": "budget never exceeded"}
    budget_ledger = ContextReadLedger(
        workspace,
        workspace / "run-v2-contam-budget",
        "run-v2-contam-budget",
        budget=ContextBudget(max_duplicate_read_ratio=0.1),
    )
    budget_ledger.seal_source(live_log)
    budget_ledger.record_read(live_log, consumer="probe-a", phase="recon")
    try:
        budget_ledger.record_read(live_log, consumer="probe-a", phase="execute")
        budget_ledger.record_read(live_log, consumer="probe-a", phase="verify")
    except ContextLedgerError as error:
        checks["exhausted_budget_blocks_further_reads"] = {"ok": "budget_exceeded" in str(error), "detail": str(error)}
    budget_receipt = budget_ledger.receipt()
    exceeded = budget_receipt["status"] == "budget_exceeded"
    checkpoint = budget_receipt["checkpoint"] or {}
    checks["declared_budget_exceeded_is_resumable_checkpoint"] = {
        "ok": (
            exceeded
            and bool(checkpoint.get("resumable"))
            and "duplicate_read_ratio_exceeded" in (checkpoint.get("reasons") or [])
        ),
        "detail": f"status={budget_receipt['status']} checkpoint={checkpoint}",
    }
    checks["ledger_receipt_claims_no_completion_authority"] = {
        "ok": budget_receipt["completion_authority"] == "none" and budget_receipt["authoritative"] is False,
        "detail": "cost telemetry never becomes completion",
    }
    budget_ledger.resume()
    resumed = budget_ledger.receipt()
    checks["resume_reopens_next_wave"] = {
        "ok": resumed["status"] == "active" and resumed["wave"] == 2 and resumed["checkpoint"] is None,
        "detail": f"wave={resumed['wave']} status={resumed['status']}",
    }
    passed = all(entry["ok"] if isinstance(entry, dict) else bool(entry) for entry in checks.values())
    return {
        "stage": "contamination-gate",
        "checks": checks,
        "duplicate_read_ratio_at_exceed": budget_receipt["duplicate_read_ratio"],
        "declared_max_duplicate_read_ratio": 0.1,
        "read_counts": budget_receipt["read_counts"],
        "status": "passed" if passed else "failed",
    }


def run_supplements(workspace: Path) -> dict[str, Any]:
    workspace.mkdir(parents=True, exist_ok=True)
    contradiction = run_contradiction_supplement(workspace / "contradiction")
    contamination = run_contamination_supplement(workspace)
    return {
        "schema_version": 1,
        "run_name": RUN_NAME,
        "case_id": "senior-user-ux-v2-track-b-supplements",
        "mode": "supplements",
        "stages": [contradiction, contamination],
        "status": (
            "passed" if all(stage["status"] == "passed" for stage in (contradiction, contamination)) else "failed"
        ),
        "disclosures": {
            "host_process_invoked": False,
            "in_process_only": (
                "these probes exercise runtime mechanisms directly; operator-surface reachability is judged by Track A"
            ),
        },
        "blocker": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="senior-user-ux-v2 Track B supplements")
    default_root = Path.cwd() / ".research-tree" / "evaluation-runs" / RUN_NAME / "track-b"
    parser.add_argument("--workspace", type=Path, default=default_root / "supplement-workspace")
    parser.add_argument("--receipt", type=Path, default=default_root / "supplements-receipt.json")
    args = parser.parse_args(argv)
    receipt = run_supplements(args.workspace)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"receipt": str(args.receipt), "status": receipt["status"]}))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
