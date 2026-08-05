from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "scripts" / "hermes_execution_adapter.py"


def run_adapter(workspace: Path, command: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ADAPTER), "--workspace", str(workspace), command, *args],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=False,
    )


def write_fixture(workspace: Path) -> tuple[Path, Path, Path]:
    handoff = workspace / "handoff.json"
    handoff.write_text(
        json.dumps(
            {
                "schema": 1,
                "kind": "alignment-handoff",
                "run_id": "alignment-hermes",
                "decision_slots": {"slot-a": {"question": "Bound the decision."}},
                "execution_context": {"authority": ["Autonomous research within scope."]},
            }
        ),
        encoding="utf-8",
    )
    finding = workspace / "finding.json"
    finding.write_text('{"id":"finding-1"}', encoding="utf-8")
    technical = workspace / "technical.md"
    technical.write_text("# Technical\n\n## Evidence\n\n## Validation\n" + "x" * 1100, encoding="utf-8")
    human = workspace / "human.md"
    human.write_text("# Human\n\n## Findings\n\n" + "x" * 600, encoding="utf-8")
    return handoff, finding, (technical, human)


def test_hermes_adapter_persists_waves_and_prepares_non_authoritative_delivery(
    tmp_path: Path,
) -> None:
    handoff, finding, reports = write_fixture(tmp_path)
    initialized = run_adapter(
        tmp_path,
        "init",
        "--run-id",
        "hermes-run",
        "--handoff",
        str(handoff),
    )
    assert initialized.returncode == 0, initialized.stderr
    running = run_adapter(
        tmp_path,
        "record-batch",
        "--run-id",
        "hermes-run",
        "--batch-id",
        "wave-1",
        "--status",
        "running",
        "--delegation-id",
        "delegation-1",
    )
    assert running.returncode == 0, running.stderr
    recovered = json.loads(run_adapter(tmp_path, "recover", "--run-id", "hermes-run").stdout)
    assert recovered["recovered_batches"] == ["wave-1"]
    verified = run_adapter(
        tmp_path,
        "record-batch",
        "--run-id",
        "hermes-run",
        "--batch-id",
        "wave-2",
        "--status",
        "verified",
        "--delegation-id",
        "delegation-2",
        "--finding",
        str(finding),
    )
    assert verified.returncode == 0, verified.stderr
    blocked = run_adapter(
        tmp_path,
        "prepare-delivery",
        "--run-id",
        "hermes-run",
        "--technical-report",
        str(reports[0]),
        "--human-report",
        str(reports[1]),
    )
    assert blocked.returncode == 1
    assert "verified" in blocked.stderr

    # A fresh run proves the terminal gate accepts only verified waves and both reports.
    run_id = "hermes-complete"
    assert run_adapter(
        tmp_path, "init", "--run-id", run_id, "--handoff", str(handoff)
    ).returncode == 0
    assert run_adapter(
        tmp_path,
        "record-batch",
        "--run-id",
        run_id,
        "--batch-id",
        "wave-1",
        "--status",
        "verified",
        "--finding",
        str(finding),
    ).returncode == 0
    prepared = run_adapter(
        tmp_path,
        "prepare-delivery",
        "--run-id",
        run_id,
        "--technical-report",
        str(reports[0]),
        "--human-report",
        str(reports[1]),
    )
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr
    prepared_state = json.loads(prepared.stdout)
    assert prepared_state["status"] == "delivery_pending"
    assert prepared_state["all_batches_verified"] is True
    assert prepared_state["canonical_complete"] is False

    legacy_complete = run_adapter(
        tmp_path,
        "complete",
        "--run-id",
        run_id,
        "--technical-report",
        str(reports[0]),
        "--human-report",
        str(reports[1]),
    )
    assert legacy_complete.returncode == 1
    assert "canonical coordinator" in legacy_complete.stderr
