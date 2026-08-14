from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def run_recorder(*arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    source_root = str(ROOT / "src")
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = source_root if not existing else f"{source_root}{os.pathsep}{existing}"
    return subprocess.run(
        [sys.executable, *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


def test_task_recorder_rejects_tracked_receipt_destination(tmp_path: Path) -> None:
    result = run_recorder(
        "scripts/record_task_verification.py",
        "--repo",
        str(tmp_path),
        "--group",
        "1",
        "--receipt",
        "openspec/changes/change/evidence/group-1-receipt.json",
        "--output",
        ".research-tree/verification-runs/group-1-output.txt",
    )

    assert result.returncode != 0
    assert "local verification boundary" in result.stderr


def test_integrated_recorder_rejects_tracked_evidence_directory(tmp_path: Path) -> None:
    result = run_recorder(
        "scripts/record_integrated_evidence.py",
        "--repo",
        str(tmp_path),
        "--evidence-dir",
        "openspec/changes/change/evidence",
    )

    assert result.returncode != 0
    assert "local verification boundary" in result.stderr
