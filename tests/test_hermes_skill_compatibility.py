from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "scripts" / "hermes_skill_adapter.py"
RUNTIME_HOOK = ROOT / "scripts" / "hermes_runtime_hook.py"


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
    assert result["hermes_version"] == "v2026.8.3"
    assert result["compact_description"].startswith("Use when ")
    assert result["resources"]
    assert result["prompt_risk"]["level"] == "low"
    assert result["prompt_risk"]["skill_chars"] <= 20_000


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


def test_native_contract_uses_current_delegate_semantics() -> None:
    contract = (ROOT / "references" / "hermes-native-orchestration.md").read_text(
        encoding="utf-8"
    )

    assert "delegate_task(tasks=[...])" in contract
    assert "in-flight attempt `unknown`" in contract
    assert "session_search" in contract
    assert "cronjob" in contract
    assert "delegate_task(background=" not in contract
    assert "delegate_task(toolsets=" not in contract
    assert "delegate_task(max_iterations=" not in contract


def test_render_hooks_uses_absolute_package_paths() -> None:
    completed = run_adapter("render-hooks", "--python", sys.executable)

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert "subagent_start:" in completed.stdout
    assert "subagent_stop:" in completed.stdout
    assert "post_tool_call:" in completed.stdout
    assert 'matcher: "^delegate_task$"' in completed.stdout
    package_hook = (
        ROOT
        / "packages"
        / "hermes"
        / "research-tree"
        / "scripts"
        / "hermes_runtime_hook.py"
    ).resolve()
    assert str(package_hook) in completed.stdout
    assert "hooks_auto_accept: false" in completed.stdout


def test_runtime_hook_records_metadata_without_task_content(tmp_path: Path) -> None:
    payload = {
        "hook_event_name": "post_tool_call",
        "tool_name": "delegate_task",
        "session_id": "session-1",
        "cwd": str(tmp_path),
        "tool_input": {
            "tasks": [
                {"task": "TOP SECRET RESEARCH QUESTION"},
                {"task": "another private task"},
            ]
        },
        "extra": {
            "delegation_id": "delegation-1",
            "status": "completed",
            "summary": "sensitive child summary",
        },
    }
    completed = subprocess.run(
        [sys.executable, str(RUNTIME_HOOK)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        cwd=tmp_path,
    )

    assert completed.returncode == 0
    assert json.loads(completed.stdout) == {}
    event_file = tmp_path / ".research-tree-hermes" / "events.jsonl"
    record = json.loads(event_file.read_text(encoding="utf-8"))
    assert record["event"] == "post_tool_call"
    assert record["task_count"] == 2
    assert record["delegation_id"] == "delegation-1"
    serialized = json.dumps(record)
    assert "TOP SECRET" not in serialized
    assert "sensitive child summary" not in serialized


def test_runtime_hook_ignores_unrelated_tool_calls(tmp_path: Path) -> None:
    payload = {
        "hook_event_name": "post_tool_call",
        "tool_name": "web_search",
        "cwd": str(tmp_path),
        "tool_input": {"query": "private query"},
    }
    completed = subprocess.run(
        [sys.executable, str(RUNTIME_HOOK)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        cwd=tmp_path,
    )

    assert completed.returncode == 0
    assert not (tmp_path / ".research-tree-hermes" / "events.jsonl").exists()


def test_doctor_classifies_context_failure_without_leaking_log(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    secret = "sk-example-secret-value"
    (log_dir / "gateway.log").write_text(
        "provider request failed: maximum context length exceeded " + secret,
        encoding="utf-8",
    )

    completed = run_adapter(
        "doctor",
        "--skill-dir",
        str(ROOT / "packages" / "hermes" / "research-tree"),
        "--hermes-home",
        str(tmp_path),
    )

    result = json.loads(completed.stdout)
    assert result["gateway_log"]["exists"] is True
    assert result["gateway_log"]["category"] == "context_limit"
    assert result["gateway_log"]["matched_marker"] in {
        "maximum context",
        "context length",
    }
    assert secret not in completed.stdout
