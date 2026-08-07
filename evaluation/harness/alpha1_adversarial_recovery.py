"""Replay pinned Alpha1 provider-failure and crash-recovery behavior.

The harness executes only public Alpha1 native-adapter commands from a clean,
detached checkout. It records redacted command receipts and never classifies a
case as reproduced unless the lost-obligation predicate is actually observed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

from evaluation.harness.alpha1_adversarial import (
    ALPHA1_COMMIT,
    ALPHA1_TAG,
    Alpha1ReplayError,
    _command,
    _input_receipt,
    _inside,
    _materialize_clean_alpha1,
    _remove_workspace,
    _remove_worktree,
    _tree_digest,
)


CLAUDE_PACKAGE = "packages/claude-code/research-tree"
FIXTURE_RELATIVE = Path("evaluation/fixtures/alpha1-adversarial-v1/recovery")
CASE_IDS = ("provider-failure", "crash-recovery")


def _redact_native_command(
    receipt: dict[str, Any], *, checkout: Path, workspace: Path
) -> dict[str, Any]:
    adapter = checkout / CLAUDE_PACKAGE / "scripts" / "native_execution_adapter.py"
    rendered: list[str] = []
    for value in receipt["argv"]:
        if value == sys.executable:
            rendered.append("<python>")
        elif value == str(adapter):
            rendered.append(f"{CLAUDE_PACKAGE}/scripts/native_execution_adapter.py")
        elif value == str(workspace):
            rendered.append("<workspace>")
        elif value.startswith(str(workspace) + "/"):
            rendered.append(
                "<workspace>/" + Path(value).relative_to(workspace).as_posix()
            )
        else:
            rendered.append(value)

    def redact_output(value: str) -> str:
        return value.replace(str(workspace), "<workspace>").replace(
            str(checkout), "<alpha1-checkout>"
        )

    redacted_stdout = redact_output(receipt["stdout"])
    redacted_stderr = redact_output(receipt["stderr"])
    command_names = {
        "init",
        "add-task",
        "start",
        "finish",
        "recover",
        "status",
    }
    name = next(
        (value for value in receipt["argv"] if value in command_names),
        "unknown",
    )
    return {
        "command": shlex.join(rendered),
        "name": name,
        "returncode": receipt["returncode"],
        "stdout": redacted_stdout,
        "stderr": redacted_stderr,
        "stdout_sha256": receipt["stdout_sha256"],
        "stderr_sha256": receipt["stderr_sha256"],
        "raw_stdout_sha256": receipt["stdout_sha256"],
        "raw_stderr_sha256": receipt["stderr_sha256"],
        "redacted_stdout_sha256": hashlib.sha256(
            redacted_stdout.encode("utf-8")
        ).hexdigest(),
        "redacted_stderr_sha256": hashlib.sha256(
            redacted_stderr.encode("utf-8")
        ).hexdigest(),
    }


def _load_json_output(
    completed: subprocess.CompletedProcess[str], description: str
) -> dict[str, Any]:
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise Alpha1ReplayError(
            f"historical {description} did not emit JSON"
        ) from error
    if not isinstance(value, dict):
        raise Alpha1ReplayError(
            f"historical {description} emitted a non-object JSON value"
        )
    return value


def _load_case_fixture(repository: Path, case_id: str) -> tuple[dict[str, Path], dict[str, Any]]:
    if case_id not in CASE_IDS:
        raise Alpha1ReplayError(f"unknown recovery case: {case_id}")
    fixture = repository / FIXTURE_RELATIVE
    handoff = fixture / "handoff.json"
    case_path = fixture / f"{case_id}.json"
    if not handoff.is_file() or not case_path.is_file():
        raise Alpha1ReplayError(f"recovery fixture is incomplete for {case_id}")
    try:
        case = json.loads(case_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Alpha1ReplayError(f"recovery case fixture is invalid: {case_id}") from error
    if not isinstance(case, dict) or case.get("schema_version") != 1:
        raise Alpha1ReplayError(f"recovery case fixture is not schema version 1: {case_id}")
    if case.get("case_id") != case_id or not isinstance(case.get("predicates"), dict):
        raise Alpha1ReplayError(f"recovery case fixture is not case-bound: {case_id}")
    files = {"handoff.json": handoff, "case.json": case_path}
    return files, case


def _copy_fixture(
    repository: Path, workspace: Path, case_id: str
) -> tuple[dict[str, Path], dict[str, Any]]:
    source_files, case = _load_case_fixture(repository, case_id)
    workspace.mkdir(parents=True, exist_ok=True)
    copied: dict[str, Path] = {}
    for name, source in source_files.items():
        destination = workspace / name
        shutil.copyfile(source, destination)
        copied[name] = destination
    return copied, case


def _predicate_result(
    case: dict[str, Any], *, lost: bool, recovered: bool
) -> dict[str, dict[str, Any]]:
    predicates = case["predicates"]
    return {
        "lost_obligation": {
            "predicate": predicates["lost_obligation"]["predicate"],
            "holds": lost,
        },
        "recovered_obligation": {
            "predicate": predicates["recovered_obligation"]["predicate"],
            "holds": recovered,
        },
    }


def _base_receipt(
    *,
    case_id: str,
    case: dict[str, Any],
    files: dict[str, Path],
    package: Path,
    commands: list[dict[str, Any]],
    observed: dict[str, Any],
    predicates: dict[str, dict[str, Any]],
    reason: str,
) -> dict[str, Any]:
    status = "vulnerability_reproduced" if predicates["lost_obligation"]["holds"] else "pending"
    return {
        "schema_version": 1,
        "case_id": case_id,
        "status": status,
        "semantic_predicate": case["semantic_predicate"],
        "baseline": {"tag": ALPHA1_TAG, "commit": ALPHA1_COMMIT},
        "host": "claude",
        "host_package": {
            "path": CLAUDE_PACKAGE,
            "sha256": _tree_digest(package),
        },
        "inputs": {
            "handoff": _input_receipt(files["handoff.json"]),
            "case": _input_receipt(files["case.json"]),
        },
        "environment": {
            "python": sys.version.split()[0],
            "implementation": sys.implementation.name,
            "platform": sys.platform,
            "network": "disabled-by-design; local Git object and fixture only",
        },
        "commands": commands,
        "predicates": predicates,
        "observed": observed,
        "reason": reason,
        "limitations": [
            "pinned Alpha1 public behavior only; this is not fix confirmation",
            "pending means the lost-obligation predicate was not proven",
        ],
    }


def replay_recovery_case(
    *,
    repository_root: str | Path,
    work_root: str | Path,
    case_id: str,
    keep_workspace: bool = False,
) -> dict[str, Any]:
    """Replay one pinned Alpha1 recovery case with public native-adapter commands."""

    repository = Path(repository_root).resolve()
    root = Path(work_root).resolve()
    checkout = root / "alpha1-checkout"
    workspace = root / f"{case_id}-workspace"
    if root.exists() and any(root.iterdir()):
        raise Alpha1ReplayError("work_root must be empty")
    root.mkdir(parents=True, exist_ok=True)

    try:
        _materialize_clean_alpha1(repository, checkout)
        files, case = _copy_fixture(repository, workspace, case_id)
        adapter = checkout / CLAUDE_PACKAGE / "scripts" / "native_execution_adapter.py"
        package = checkout / CLAUDE_PACKAGE
        if not adapter.is_file():
            raise Alpha1ReplayError("pinned Alpha1 native adapter does not exist")
        commands: list[dict[str, Any]] = []

        def invoke(*arguments: str) -> subprocess.CompletedProcess[str]:
            completed, receipt = _command(
                [
                    sys.executable,
                    str(adapter),
                    "--host",
                    "claude",
                    "--workspace",
                    str(workspace),
                    *arguments,
                ],
                cwd=workspace,
            )
            commands.append(receipt)
            if completed.returncode:
                raise Alpha1ReplayError(
                    "historical native adapter command failed: "
                    + " ".join(arguments)
                    + f": {completed.stdout}{completed.stderr}"
                )
            return completed

        run_id = case["run_id"]
        task_id = case["task_id"]
        invoke("init", "--run-id", run_id, "--handoff", str(files["handoff.json"]))
        invoke(
            "add-task",
            "--run-id",
            run_id,
            "--task-id",
            task_id,
            "--decision-slot",
            case["decision_slot"],
            "--phase",
            case["phase"],
            "--artifact",
            case["artifact"],
        )
        first_started = _load_json_output(
            invoke(
                "start",
                "--run-id",
                run_id,
                "--task-id",
                task_id,
                "--worker-id",
                case["worker_id"],
            ),
            "initial task start",
        )
        first_attempt_id = first_started.get("attempt_id")
        if not isinstance(first_attempt_id, str) or not first_attempt_id:
            raise Alpha1ReplayError("initial task start omitted attempt_id")

        if case_id == "provider-failure":
            failed = _load_json_output(
                invoke(
                    "finish",
                    "--run-id",
                    run_id,
                    "--task-id",
                    task_id,
                    "--result",
                    "failed",
                    "--reason",
                    case["failure_reason"],
                ),
                "provider failure",
            )
            after_failure = _load_json_output(
                invoke("status", "--run-id", run_id),
                "status after provider failure",
            )
            retried = _load_json_output(
                invoke(
                    "start",
                    "--run-id",
                    run_id,
                    "--task-id",
                    task_id,
                    "--worker-id",
                    case["retry_worker_id"],
                ),
                "provider-failure retry",
            )
            retry_attempt_id = retried.get("attempt_id")
            if not isinstance(retry_attempt_id, str) or not retry_attempt_id:
                raise Alpha1ReplayError("provider-failure retry omitted attempt_id")
            failed_status = failed.get("status") == "failed"
            ready_after_failure = after_failure.get("ready") == [task_id]
            retry_started = (
                retried.get("status") == "running"
                and retried.get("attempt") == 2
            )
            recovered = failed_status and ready_after_failure and retry_started
            lost = not recovered
            predicates = _predicate_result(case, lost=lost, recovered=recovered)
            observed = {
                "failed_status": failed.get("status"),
                "failure_reason": failed.get("failure_reason"),
                "ready_after_failure": after_failure.get("ready"),
                "retry_status": retried.get("status"),
                "retry_attempt": retried.get("attempt"),
                "attempt_id_changed": retry_attempt_id != first_attempt_id,
            }
            reason = (
                "Pinned Alpha1 behavior preserved the failed obligation and allowed "
                "a new attempt; the lost-obligation predicate is not reproduced."
                if recovered
                else "Pinned Alpha1 behavior did not prove recovery of the failed obligation."
            )
        else:
            first_recovery = _load_json_output(
                invoke("recover", "--run-id", run_id),
                "first crash recovery",
            )
            second_recovery = _load_json_output(
                invoke("recover", "--run-id", run_id),
                "idempotent crash recovery",
            )
            after_recovery = _load_json_output(
                invoke("status", "--run-id", run_id),
                "status after crash recovery",
            )
            retried = _load_json_output(
                invoke(
                    "start",
                    "--run-id",
                    run_id,
                    "--task-id",
                    task_id,
                    "--worker-id",
                    case["retry_worker_id"],
                ),
                "crash-recovery retry",
            )
            retry_attempt_id = retried.get("attempt_id")
            if not isinstance(retry_attempt_id, str) or not retry_attempt_id:
                raise Alpha1ReplayError("crash-recovery retry omitted attempt_id")
            first_recovered = first_recovery.get("recovered_to_unknown") == [task_id]
            second_recovered = second_recovery.get("recovered_to_unknown") == []
            revision_stable = (
                second_recovery.get("revision") == first_recovery.get("revision")
            )
            ready_after_recovery = after_recovery.get("ready") == [task_id]
            retry_started = (
                retried.get("status") == "running"
                and retried.get("attempt") == 2
            )
            recovered = (
                first_recovered
                and second_recovered
                and revision_stable
                and after_recovery.get("status") == "running"
                and ready_after_recovery
                and retry_started
            )
            lost = not recovered
            predicates = _predicate_result(case, lost=lost, recovered=recovered)
            observed = {
                "first_recovery": first_recovery.get("recovered_to_unknown"),
                "second_recovery": second_recovery.get("recovered_to_unknown"),
                "recovery_revision_stable": revision_stable,
                "status_after_recovery": after_recovery.get("status"),
                "unknown_tasks_after_recovery": after_recovery.get("counts", {}).get("unknown"),
                "ready_after_recovery": after_recovery.get("ready"),
                "retry_status": retried.get("status"),
                "retry_attempt": retried.get("attempt"),
                "attempt_id_changed": retry_attempt_id != first_attempt_id,
            }
            reason = (
                "Pinned Alpha1 behavior reopened the in-flight obligation as unknown, "
                "made it ready, and allowed one retry; the lost-obligation predicate "
                "is not reproduced."
                if recovered
                else "Pinned Alpha1 behavior did not prove recovery of the in-flight obligation."
            )

        return _base_receipt(
            case_id=case_id,
            case=case,
            files=files,
            package=package,
            commands=[
                _redact_native_command(command, checkout=checkout, workspace=workspace)
                for command in commands
            ],
            observed=observed,
            predicates=predicates,
            reason=reason,
        )
    finally:
        try:
            _remove_worktree(repository, checkout)
        finally:
            if not keep_workspace:
                _remove_workspace(workspace)
                root.mkdir(parents=True, exist_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay pinned Alpha1 provider-failure or crash-recovery behavior."
    )
    parser.add_argument("--case", choices=CASE_IDS, required=True)
    parser.add_argument(
        "--repository-root",
        type=Path,
        required=True,
        help="repository containing tag 0.0.1-a1",
    )
    parser.add_argument(
        "--work-root",
        type=Path,
        required=True,
        help="caller-owned temporary execution root; generated contents are removed and the root is left empty after replay by default",
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        required=True,
        help="path for the redacted JSON receipt",
    )
    parser.add_argument(
        "--keep-workspace",
        action="store_true",
        help="retain the execution workspace for inspection; use a fresh work root for reruns",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    repository_root = arguments.repository_root.expanduser().resolve()
    work_root = arguments.work_root.expanduser().resolve()
    receipt_path = arguments.receipt.expanduser().resolve()

    if not arguments.keep_workspace and _inside(work_root, receipt_path):
        print(
            json.dumps(
                {
                    "error": "--receipt must be outside --work-root unless --keep-workspace is used"
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2

    try:
        receipt = replay_recovery_case(
            repository_root=repository_root,
            work_root=work_root,
            case_id=arguments.case,
            keep_workspace=arguments.keep_workspace,
        )
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (Alpha1ReplayError, OSError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
