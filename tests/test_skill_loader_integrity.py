from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import pytest

from research_tree.lifecycle_hook import observe
from research_tree.skill_activation import (
    build_loader_receipt,
    loader_integrity_status,
    validate_loader_receipt,
)


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


def test_static_validation_is_not_presented_as_loader_verification() -> None:
    completed = run_adapter("validate", "--mode", "external-dir")

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["static_compatible"] is True
    assert result["loader_integrity"]["state"] == "unverified_loader_integrity"
    assert result["compatible"] is True


@pytest.mark.parametrize("host", ["codex", "claude", "hermes"])
def test_loader_receipt_is_host_neutral_and_session_bound(host: str, tmp_path: Path) -> None:
    package = tmp_path / "research-tree"
    shutil.copytree(ROOT / "packages" / "hermes" / "research-tree", package)
    receipt = build_loader_receipt(package, host=host, session_id="session-1")
    assert loader_integrity_status(package, host=host, receipt=receipt, session_id="session-1")["state"] == (
        "package_attested"
    )
    with pytest.raises(ValueError, match="session"):
        validate_loader_receipt(receipt, package, host=host, session_id="session-2", require_verified=False)
    package.joinpath("SKILL.md").write_text(
        package.joinpath("SKILL.md").read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8"
    )
    assert loader_integrity_status(package, host=host, receipt=receipt)["state"] == "invalid_loader_receipt"


@pytest.mark.parametrize(
    "host,event",
    [("codex", "SessionStart"), ("claude", "SessionStart"), ("hermes", "on_session_start")],
)
def test_shared_lifecycle_observer_records_skill_load_for_each_host(
    host: str, event: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    (project / "packages").mkdir(parents=True)
    (project / "skill-src").mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    skill_dir = project / "packages" / "research-tree"
    shutil.copytree(ROOT / "packages" / "hermes" / "research-tree", skill_dir)
    run_root = project / ".research-tree" / "projects" / "p1" / "runs" / "r1"
    run_root.mkdir(parents=True)
    (run_root / "manifest.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("RESEARCH_TREE_SKILL_DIR", str(skill_dir))
    payload = {"cwd": str(project), "session_id": "session-1", "project_id": "p1", "run_id": "r1"}
    observed = observe(payload, host=host, event=event, project_root=project, process_cwd=project)
    assert observed["skill_load"]["host"] == host
    assert observed["skill_load"]["session_id"] == "session-1"


def test_receipt_binds_exact_skill_bytes_and_session(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"
    created = run_adapter(
        "receipt",
        "--skill-dir",
        "packages/hermes/research-tree",
        "--session-id",
        "session-1",
        "--output",
        str(receipt_path),
    )

    assert created.returncode == 0, created.stderr
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    skill = ROOT / "packages" / "hermes" / "research-tree" / "SKILL.md"
    assert receipt["skill_body_digest"] == hashlib.sha256(skill.read_bytes()).hexdigest()
    assert receipt["session_id"] == "session-1"
    assert receipt["line_count"] == len(skill.read_text(encoding="utf-8").splitlines())

    verified = run_adapter(
        "validate",
        "--mode",
        "external-dir",
        "--loader-receipt",
        str(receipt_path),
        "--session-id",
        "session-1",
    )
    assert verified.returncode == 0, verified.stderr
    assert json.loads(verified.stdout)["loader_integrity"]["state"] == "host_message_verified"

    receipt["skill_body_digest"] = "0" * 64
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    tampered = run_adapter(
        "validate",
        "--mode",
        "external-dir",
        "--loader-receipt",
        str(receipt_path),
        "--session-id",
        "session-1",
    )
    assert tampered.returncode == 1
    assert json.loads(tampered.stdout)["loader_integrity"]["state"] == "invalid_loader_receipt"


def test_installed_hook_records_one_sanitized_skill_load_event(tmp_path: Path) -> None:
    package = tmp_path / "skills" / "research-tree"
    shutil.copytree(ROOT / "packages" / "hermes" / "research-tree", package)
    workspace = tmp_path / "workspace"
    run_root = workspace / ".research-tree" / "projects" / "project-1" / "runs" / "run-1"
    run_root.mkdir(parents=True)
    (run_root / "manifest.json").write_text("{}", encoding="utf-8")
    payload = {"hook_event_name": "on_session_start", "session_id": "session-1", "cwd": str(workspace)}
    environment = os.environ | {
        "RESEARCH_TREE_PROJECT_ID": "project-1",
        "RESEARCH_TREE_RUN_ID": "run-1",
    }

    completed = subprocess.run(
        [sys.executable, str(package / "scripts" / "hermes_runtime_hook.py")],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )

    assert completed.returncode == 0
    records = [json.loads(path.read_text(encoding="utf-8")) for path in (run_root / "events").glob("*.json")]
    receipt = next(record for record in records if record["event"] == "skill-load")
    skill = package / "SKILL.md"
    assert receipt["session_id"] == "session-1"
    assert receipt["skill_body_digest"] == hashlib.sha256(skill.read_bytes()).hexdigest()
    assert receipt["byte_count"] == skill.stat().st_size
    assert receipt["line_count"] == len(skill.read_text(encoding="utf-8").splitlines())
    assert "content" not in receipt


def test_official_hermes_loader_preserves_start_middle_and_tail_of_skill(tmp_path: Path) -> None:
    if shutil.which("docker") is None:
        return
    home = tmp_path / "hermes-home"
    package = home / "skills" / "research-tree"
    shutil.copytree(ROOT / "packages" / "hermes" / "research-tree", package)
    skill = package / "SKILL.md"
    source = skill.read_text(encoding="utf-8")
    sentinels = ("# research-tree", "## Phase 2: autonomous plan-to-execute research", "## Completion standard")
    assert all(value in source for value in sentinels)
    script = (
        "import json; from agent.skill_commands import build_preloaded_skills_prompt; "
        "prompt, loaded, missing = build_preloaded_skills_prompt(['research-tree']); "
        "print(json.dumps({'prompt': prompt, 'loaded': loaded, 'missing': missing}))"
    )
    completed = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-e",
            "HERMES_HOME=/opt/data",
            "-v",
            f"{home}:/opt/data",
            "--entrypoint",
            "/opt/hermes/.venv/bin/python3",
            "nousresearch/hermes-agent:v2026.8.3",
            "-c",
            script,
        ],
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    observed = json.loads(completed.stdout)
    assert observed["loaded"] == ["research-tree"]
    assert observed["missing"] == []
    assert all(value in observed["prompt"] for value in sentinels)
