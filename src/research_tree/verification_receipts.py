"""Generate source-bound OpenSpec task verification receipts."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any, Mapping


class VerificationReceiptError(ValueError):
    """The selected task group or receipt destination is invalid."""


LOCAL_VERIFICATION_ROOT = Path(".research-tree/verification-runs")
LOCAL_EVALUATION_ROOT = Path(".research-tree/evaluation-runs")
LOCAL_OUTPUT_ROOTS = (LOCAL_VERIFICATION_ROOT, LOCAL_EVALUATION_ROOT)


def generate_receipt(
    repository: str | Path,
    task_registry: str | Path,
    group: int,
    output_path: str | Path,
    *,
    source_revision: str | None = None,
) -> dict[str, Any]:
    """Run one registered acceptance command and retain its combined output."""

    repo = Path(repository).resolve()
    registry_path = Path(task_registry).resolve()
    output = local_verification_path(repo, output_path)
    command = _registered_command(registry_path, group)
    revision = source_revision or _source_revision(repo)
    _sha(revision, "source_revision", lengths={40, 64})

    completed = subprocess.run(
        _command_argv(command),
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(completed.stdout)
    environment = {
        "python": sys.version,
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
    }
    return {
        "command": command,
        "exit_code": completed.returncode,
        "environment_digest": _digest(json.dumps(environment, sort_keys=True).encode("utf-8")),
        "output_digest": _digest(completed.stdout),
        "source_revision": revision,
        "raw_output_ref": output.relative_to(repo).as_posix(),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }


def local_verification_path(repository: str | Path, candidate: str | Path) -> Path:
    """Resolve a generated receipt record within a registered local-only boundary."""

    repo = Path(repository).resolve()
    path = Path(candidate)
    output = path.resolve() if path.is_absolute() else (repo / path).resolve()
    _within(repo, output)
    if not any(_is_within(output, repo / root) for root in LOCAL_OUTPUT_ROOTS):
        raise VerificationReceiptError(
            "receipt output must be under the local verification boundary: "
            ".research-tree/verification-runs/ or .research-tree/evaluation-runs/"
        )
    return output


def _registered_command(path: Path, group: int) -> str:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise VerificationReceiptError("task registry is unreadable") from error
    if not isinstance(group, int) or isinstance(group, bool) or group < 1:
        raise VerificationReceiptError("group must be a positive integer")
    if not isinstance(payload, Mapping) or payload.get("schema_version") != 1:
        raise VerificationReceiptError("task registry has unsupported schema")
    groups = payload.get("groups")
    if not isinstance(groups, list):
        raise VerificationReceiptError("task registry groups must be a list")
    for definition in groups:
        if isinstance(definition, Mapping) and definition.get("group") == group:
            command = definition.get("acceptance_command")
            if isinstance(command, str) and command:
                return command
    raise VerificationReceiptError(f"unknown task group: {group}")


def _source_revision(repository: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode:
        raise VerificationReceiptError("repository has no resolvable git HEAD")
    return completed.stdout.decode("ascii", errors="strict").strip()


def _command_argv(command: str) -> list[str]:
    if os.name == "nt":
        if "&&" in command:
            return ["cmd.exe", "/d", "/c", command]
        return ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]
    return ["/bin/sh", "-c", command]


def _within(root: Path, candidate: Path) -> None:
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise VerificationReceiptError("receipt output path escapes repository") from error


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _sha(value: str, name: str, *, lengths: set[int]) -> None:
    if len(value) not in lengths or any(char not in "0123456789abcdef" for char in value):
        raise VerificationReceiptError(f"{name} must be lowercase hexadecimal")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
