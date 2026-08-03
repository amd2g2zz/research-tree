from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "scripts" / "hermes_skill_adapter.py"


def run_adapter(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ADAPTER), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_external_directory_mode_is_hermes_compatible() -> None:
    completed = run_adapter("validate", "--mode", "external-dir")

    assert completed.returncode == 0, completed.stderr or completed.stdout
    result = json.loads(completed.stdout)
    assert result["compatible"] is True
    assert result["compact_description"].startswith("Use when ")
    assert result["resources"]


def test_direct_url_mode_reports_bundle_loss() -> None:
    completed = run_adapter("validate", "--mode", "single-file")

    assert completed.returncode == 1
    result = json.loads(completed.stdout)
    assert result["compatible"] is False
    assert any("single-file" in error for error in result["errors"])


def test_stage_creates_a_complete_github_bundle(tmp_path: Path) -> None:
    completed = run_adapter("stage", str(tmp_path))

    assert completed.returncode == 0, completed.stderr or completed.stdout
    result = json.loads(completed.stdout)
    target = Path(result["staged_to"])
    assert target == tmp_path / "skills" / "research-tree"
    assert (target / "SKILL.md").is_file()
    assert result["validation"]["compatible"] is True
    for relative in result["validation"]["resources"]:
        assert (target / relative).is_file()
