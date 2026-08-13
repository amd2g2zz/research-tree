from __future__ import annotations

import json
import os
import shutil
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


def run_isolated_script(
    script: Path,
    working_directory: Path,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    return subprocess.run(
        [sys.executable, "-B", "-E", "-S", str(script), *arguments],
        cwd=working_directory,
        env=environment,
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
    for relative in result["validation"]["executable_closure"]:
        assert (target / relative).is_file()
    actual_files = {path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file()}
    assert actual_files == {
        "SKILL.md",
        "scripts/hermes_executable_closure.json",
        *result["validation"]["resources"],
        *result["validation"]["executable_closure"],
    }


def test_staged_bundle_cold_starts_every_documented_entrypoint(tmp_path: Path) -> None:
    completed = run_adapter("stage", str(tmp_path / "stage"))

    assert completed.returncode == 0, completed.stderr or completed.stdout
    result = json.loads(completed.stdout)
    target = Path(result["staged_to"])
    isolated_working_directory = tmp_path / "unrelated-working-directory"
    isolated_working_directory.mkdir()

    for entrypoint in result["validation"]["executable_entrypoints"]:
        cold_start = run_isolated_script(
            target / entrypoint["path"],
            isolated_working_directory,
            *entrypoint["arguments"],
        )
        assert cold_start.returncode == 0, cold_start.stderr or cold_start.stdout


def test_missing_transitive_executable_dependency_fails_closed(tmp_path: Path) -> None:
    staged = run_adapter("stage", str(tmp_path / "stage"))

    assert staged.returncode == 0, staged.stderr or staged.stdout
    target = Path(json.loads(staged.stdout)["staged_to"])
    missing_dependency = target / "scripts" / "hermes_event_adapter.py"
    assert missing_dependency.is_file()
    missing_dependency.unlink()

    validated = run_adapter(
        "validate",
        "--skill-dir",
        str(target),
        "--mode",
        "github-bundle",
    )

    assert validated.returncode == 1
    result = json.loads(validated.stdout)
    assert result["compatible"] is False
    assert "missing executable dependency: scripts/hermes_event_adapter.py" in result["errors"]


def test_staging_fails_closed_when_an_executable_entrypoint_is_omitted(tmp_path: Path) -> None:
    source = tmp_path / "source"
    shutil.copytree(ROOT / "packages" / "hermes" / "research-tree", source)
    manifest = source / "scripts" / "hermes_executable_closure.json"
    closure = json.loads(manifest.read_text(encoding="utf-8"))
    closure["entrypoints"] = [
        entrypoint
        for entrypoint in closure["entrypoints"]
        if entrypoint["path"] != "scripts/hermes_execution_adapter.py"
    ]
    manifest.write_text(json.dumps(closure), encoding="utf-8")

    staged = run_adapter("stage", "--skill-dir", str(source), str(tmp_path / "stage"))

    assert staged.returncode == 1
    assert "Hermes executable closure is missing entrypoint: scripts/hermes_execution_adapter.py" in staged.stderr


def test_staging_fails_closed_before_copying_missing_executable_dependency(tmp_path: Path) -> None:
    source = tmp_path / "source"
    shutil.copytree(ROOT / "packages" / "hermes" / "research-tree", source)
    (source / "scripts" / "native_workflow_contract.py").unlink()

    staged = run_adapter("stage", "--skill-dir", str(source), str(tmp_path / "stage"))

    assert staged.returncode == 1
    assert "missing executable dependency: scripts/native_workflow_contract.py" in staged.stderr


def test_staged_provider_failure_and_recovery_path_runs_without_repository_source(tmp_path: Path) -> None:
    staged = run_adapter("stage", str(tmp_path / "stage"))

    assert staged.returncode == 0, staged.stderr or staged.stdout
    target = Path(json.loads(staged.stdout)["staged_to"])
    workspace = tmp_path / "isolated-workspace"
    workspace.mkdir()
    snapshot = workspace / "attempt.json"
    snapshot.write_text(
        json.dumps(
            {
                "run_id": "hermes-run",
                "action_id": "action-1",
                "attempt_id": "attempt-1",
                "expected_revision": 12,
                "next_sequence": 3,
                "authorized_methods": ["documentation"],
            }
        ),
        encoding="utf-8",
    )
    provider_failure = workspace / "provider-failure.json"
    provider_failure.write_text(
        json.dumps(
            {
                "provider": "openrouter",
                "model": "glm-5.2",
                "retry_category": "transient",
                "error_code": "gateway_timeout",
                "attempt": 2,
                "gateway_log_path": "logs/gateway/attempt-2.jsonl",
            }
        ),
        encoding="utf-8",
    )

    failed = run_isolated_script(
        target / "scripts" / "hermes_execution_adapter.py",
        workspace,
        "--workspace",
        str(workspace),
        "emit-event",
        "--event-id",
        "provider-failure-1",
        "--kind",
        "provider_failure",
        "--run-id",
        "hermes-run",
        "--attempt-id",
        "attempt-1",
        "--expected-revision",
        "12",
        "--sequence",
        "3",
        "--created-at",
        "2026-08-11T00:00:00+00:00",
        "--payload",
        str(provider_failure),
    )

    assert failed.returncode == 0, failed.stderr or failed.stdout
    assert json.loads(failed.stdout)["kind"] == "provider_failure"

    recovered = run_isolated_script(
        target / "scripts" / "hermes_execution_adapter.py",
        workspace,
        "--workspace",
        str(workspace),
        "recover",
        "--run-id",
        "hermes-run",
        "--canonical-attempt",
        str(snapshot),
        "--unknown-event-id",
        "unknown-1",
        "--retry-event-id",
        "retry-1",
        "--retry-category",
        "transient",
        "--method",
        "documentation",
        "--created-at",
        "2026-08-11T00:00:00+00:00",
    )

    assert recovered.returncode == 0, recovered.stderr or recovered.stdout
    events = json.loads(recovered.stdout)["events"]
    assert [event["kind"] for event in events] == ["unknown_outcome", "retry"]


def test_native_contract_uses_current_delegate_semantics() -> None:
    contract = (ROOT / "references" / "hermes-native-orchestration.md").read_text(encoding="utf-8")

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
    package_hook = (ROOT / "packages" / "hermes" / "research-tree" / "scripts" / "hermes_runtime_hook.py").resolve()
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
