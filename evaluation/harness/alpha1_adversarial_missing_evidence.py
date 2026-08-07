"""Replay Alpha1 completing a task after reviewing a missing evidence anchor."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import shutil
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
FIXTURE_RELATIVE = Path("evaluation/fixtures/alpha1-adversarial-v1/missing-evidence")
EVIDENCE_REF = "evidence/missing-experiment.json"
ATTEMPT_PLACEHOLDERS = {"ATTEMPT_ID_FILLED_BY_HARNESS", "__ATTEMPT_ID__"}


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
        "verify",
        "status",
        "complete",
    }
    name = next((value for value in receipt["argv"] if value in command_names), "unknown")
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


def _load_json_output(completed: Any, description: str) -> dict[str, Any]:
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise Alpha1ReplayError(f"historical {description} did not emit JSON") from error
    if not isinstance(value, dict):
        raise Alpha1ReplayError(f"historical {description} emitted a non-object JSON value")
    return value


def _load_missing_evidence_finding(path: Path) -> dict[str, Any]:
    """Load a Finding Pack that cannot borrow forged-validation semantics."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        raise Alpha1ReplayError("missing-evidence fixture finding is invalid") from error
    if not isinstance(value, dict):
        raise Alpha1ReplayError("missing-evidence fixture finding must be an object")
    if "validation_result" in value:
        raise Alpha1ReplayError(
            "missing-evidence fixture must not contain validation_result"
        )
    return value


def replay_missing_evidence(
    *,
    repository_root: str | Path,
    work_root: str | Path,
    keep_workspace: bool = False,
) -> dict[str, Any]:
    """Replay task verification and run completion with an absent review anchor.

    This predicate is independent of forged validation: the fixture has no
    ``validation_result``. Instead, Alpha1's native adapter accepts a reviewer
    supplied anchor string, marks the task completed, and completes the run
    without resolving the referenced evidence artifact.
    """

    repository = Path(repository_root).resolve()
    root = Path(work_root).resolve()
    checkout = root / "alpha1-checkout"
    workspace = root / "missing-evidence-workspace"
    if root.exists() and any(root.iterdir()):
        raise Alpha1ReplayError("work_root must be empty")
    root.mkdir(parents=True, exist_ok=True)

    try:
        _materialize_clean_alpha1(repository, checkout)
        fixture = repository / FIXTURE_RELATIVE
        names = ("handoff.json", "finding.json", "technical.md", "human.md")
        if not fixture.is_dir() or any(not (fixture / name).is_file() for name in names):
            raise Alpha1ReplayError("missing-evidence fixture is incomplete")
        workspace.mkdir(parents=True, exist_ok=True)
        files: dict[str, Path] = {}
        for name in names:
            destination = workspace / name
            shutil.copyfile(fixture / name, destination)
            files[name] = destination

        finding_template_receipt = _input_receipt(files["finding.json"])
        finding_payload = _load_missing_evidence_finding(files["finding.json"])
        finding_validation_result_present = "validation_result" in finding_payload
        observation_refs = {
            observation.get("anchor", {}).get("ref")
            for observation in finding_payload.get("observations", [])
            if isinstance(observation, dict)
            and isinstance(observation.get("anchor"), dict)
        }
        if observation_refs != {EVIDENCE_REF}:
            raise Alpha1ReplayError("missing-evidence fixture has an unexpected anchor")
        evidence_path = (workspace / EVIDENCE_REF).resolve()
        if not _inside(workspace, evidence_path):
            raise Alpha1ReplayError("missing-evidence anchor leaves workspace")
        if evidence_path.exists():
            raise Alpha1ReplayError("missing-evidence artifact unexpectedly resolves")

        adapter = checkout / CLAUDE_PACKAGE / "scripts" / "native_execution_adapter.py"
        package = checkout / CLAUDE_PACKAGE
        if not adapter.is_file():
            raise Alpha1ReplayError("pinned Claude native adapter does not exist")
        commands: list[dict[str, Any]] = []
        run_id = "alpha1-missing-evidence"
        task_id = finding_payload.get("work_item_id")
        decision_slot = finding_payload.get("decision_slot_id")
        phase = finding_payload.get("phase")
        if not all(
            isinstance(value, str) and value
            for value in (task_id, decision_slot, phase)
        ):
            raise Alpha1ReplayError("missing-evidence fixture task identity is invalid")

        def invoke(*arguments: str) -> Any:
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
                    "historical native completion command failed: "
                    + " ".join(arguments)
                    + ": "
                    + completed.stdout
                    + completed.stderr
                )
            return completed

        invoke(
            "init",
            "--run-id",
            run_id,
            "--handoff",
            str(files["handoff.json"]),
        )
        invoke(
            "add-task",
            "--run-id",
            run_id,
            "--task-id",
            task_id,
            "--decision-slot",
            decision_slot,
            "--phase",
            phase,
            "--artifact",
            str(files["finding.json"]),
        )
        started = _load_json_output(
            invoke(
                "start",
                "--run-id",
                run_id,
                "--task-id",
                task_id,
                "--worker-id",
                "worker-missing-evidence",
            ),
            "task start",
        )
        attempt_id = started.get("attempt_id")
        if not isinstance(attempt_id, str) or not attempt_id:
            raise Alpha1ReplayError("historical task start omitted attempt_id")
        if finding_payload.get("attempt_id") not in ATTEMPT_PLACEHOLDERS:
            raise Alpha1ReplayError("missing-evidence fixture has no attempt placeholder")
        finding_payload["attempt_id"] = attempt_id
        files["finding.json"].write_text(
            json.dumps(finding_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        submitted = _load_json_output(
            invoke("finish", "--run-id", run_id, "--task-id", task_id, "--result", "submitted"),
            "task finish",
        )
        if submitted.get("status") != "submitted":
            raise Alpha1ReplayError("historical task finish did not submit the finding")

        reviewed = _load_json_output(
            invoke(
                "verify",
                "--run-id",
                run_id,
                "--task-id",
                task_id,
                "--reviewer-id",
                "reviewer-missing-evidence",
                "--review-note",
                "Checked the declared experiment anchor.",
                "--checked-anchor",
                EVIDENCE_REF,
            ),
            "task verification",
        )
        if reviewed.get("status") != "completed" or reviewed.get("verified") is not True:
            raise Alpha1ReplayError("historical task verification did not complete the task")
        if evidence_path.exists():
            raise Alpha1ReplayError("missing-evidence artifact resolved during review")

        precomplete = _load_json_output(
            invoke("status", "--run-id", run_id), "pre-completion status"
        )
        if precomplete.get("counts", {}).get("completed") != 1:
            raise Alpha1ReplayError("historical status did not record the reviewed task")
        if precomplete.get("integrity_errors"):
            raise Alpha1ReplayError("historical status reported an integrity error")

        completed = _load_json_output(
            invoke(
                "complete",
                "--run-id",
                run_id,
                "--technical-report",
                str(files["technical.md"]),
                "--human-report",
                str(files["human.md"]),
            ),
            "run completion",
        )
        if evidence_path.exists():
            raise Alpha1ReplayError("missing-evidence artifact resolved after completion")
        evidence_resolves = evidence_path.is_file()
        if evidence_resolves:
            raise Alpha1ReplayError("missing-evidence artifact unexpectedly resolved")
        if completed.get("status") != "complete" or completed.get("complete") is not True:
            raise Alpha1ReplayError("historical run did not complete")

        return {
            "schema_version": 1,
            "case_id": "missing-evidence",
            "status": "vulnerability_reproduced",
            "semantic_predicate": (
                "legacy_native_adapter_completed_run_after_unresolvable_review_anchor"
            ),
            "baseline": {"tag": ALPHA1_TAG, "commit": ALPHA1_COMMIT},
            "host": "claude",
            "host_package": {"path": CLAUDE_PACKAGE, "sha256": _tree_digest(package)},
            "inputs": {
                "handoff": _input_receipt(files["handoff.json"]),
                "finding_template": finding_template_receipt,
                "finding": _input_receipt(files["finding.json"]),
                "technical": _input_receipt(files["technical.md"]),
                "human": _input_receipt(files["human.md"]),
            },
            "environment": {
                "python": sys.version.split()[0],
                "implementation": sys.implementation.name,
                "platform": sys.platform,
                "network": "disabled-by-design; local Git object and fixture only",
            },
            "commands": [
                _redact_native_command(command, checkout=checkout, workspace=workspace)
                for command in commands
            ],
            "observed": {
                "evidence_anchor": EVIDENCE_REF,
                "evidence_resolves": evidence_resolves,
                "finding_validation_result_present": finding_validation_result_present,
                "reviewed_task_status": reviewed["status"],
                "reviewed_task_verified": reviewed["verified"],
                "run_complete": completed["complete"],
                "run_status": completed["status"],
            },
            "limitations": ["baseline reproduction is not fix confirmation"],
        }
    finally:
        try:
            _remove_worktree(repository, checkout)
        finally:
            if not keep_workspace:
                _remove_workspace(workspace)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay Alpha1 missing-evidence task completion."
    )
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--keep-workspace", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    repository_root = arguments.repository_root.expanduser().resolve()
    work_root = arguments.work_root.expanduser().resolve()
    receipt_path = arguments.receipt.expanduser().resolve()
    if not arguments.keep_workspace and _inside(work_root, receipt_path):
        print(
            json.dumps(
                {"error": "--receipt must be outside --work-root unless --keep-workspace is used"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    try:
        receipt = replay_missing_evidence(
            repository_root=repository_root,
            work_root=work_root,
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
