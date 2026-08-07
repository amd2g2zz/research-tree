"""Replay Alpha1 accepting a forged validation with no resolvable evidence."""

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
FIXTURE_RELATIVE = Path(
    "evaluation/fixtures/alpha1-adversarial-v1/forged-validation/finding.json"
)


def _redact_validation_command(
    receipt: dict[str, Any], *, checkout: Path, workspace: Path
) -> dict[str, Any]:
    adapter = checkout / CLAUDE_PACKAGE / "scripts" / "native_execution_adapter.py"
    finding = workspace / "finding.json"
    rendered: list[str] = []
    for value in receipt["argv"]:
        if value == sys.executable:
            rendered.append("<python>")
        elif value == str(adapter):
            rendered.append(f"{CLAUDE_PACKAGE}/scripts/native_execution_adapter.py")
        elif value == str(workspace):
            rendered.append("<workspace>")
        elif value == str(finding):
            rendered.append("<workspace>/finding.json")
        else:
            rendered.append(value)

    def redact_output(value: str) -> str:
        return value.replace(str(workspace), "<workspace>").replace(
            str(checkout), "<alpha1-checkout>"
        )

    redacted_stdout = redact_output(receipt["stdout"])
    redacted_stderr = redact_output(receipt["stderr"])
    return {
        "command": shlex.join(rendered),
        "name": "validate-finding",
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


def replay_forged_validation(
    *,
    repository_root: str | Path,
    work_root: str | Path,
    keep_workspace: bool = False,
) -> dict[str, Any]:
    """Run Alpha1's native Finding Pack validator against absent evidence.

    The unsafe predicate is independently executable: the fixture's evidence
    reference is resolved below the isolated workspace and proven absent before
    and after the historical validator returns success.
    """

    repository = Path(repository_root).resolve()
    root = Path(work_root).resolve()
    checkout = root / "alpha1-checkout"
    workspace = root / "forged-validation-workspace"
    if root.exists() and any(root.iterdir()):
        raise Alpha1ReplayError("work_root must be empty")
    root.mkdir(parents=True, exist_ok=True)

    try:
        _materialize_clean_alpha1(repository, checkout)
        fixture = repository / FIXTURE_RELATIVE
        if not fixture.is_file():
            raise Alpha1ReplayError("forged-validation fixture is missing")
        workspace.mkdir(parents=True, exist_ok=True)
        finding = workspace / "finding.json"
        shutil.copyfile(fixture, finding)

        try:
            payload = json.loads(finding.read_text(encoding="utf-8"))
            validation = payload["validation_result"]
            evidence_ref = validation["evidence_ref"]
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise Alpha1ReplayError("forged-validation fixture is invalid") from error
        if not isinstance(evidence_ref, str) or not evidence_ref:
            raise Alpha1ReplayError("forged-validation evidence_ref is invalid")
        evidence_path = (workspace / evidence_ref).resolve()
        if not _inside(workspace, evidence_path):
            raise Alpha1ReplayError("forged-validation evidence_ref leaves workspace")
        if evidence_path.exists():
            raise Alpha1ReplayError("forged-validation evidence unexpectedly resolves")

        adapter = checkout / CLAUDE_PACKAGE / "scripts" / "native_execution_adapter.py"
        package = checkout / CLAUDE_PACKAGE
        if not adapter.is_file():
            raise Alpha1ReplayError("pinned Claude native adapter does not exist")
        completed, command = _command(
            [
                sys.executable,
                str(adapter),
                "--host",
                "claude",
                "--workspace",
                str(workspace),
                "validate-finding",
                str(finding),
            ],
            cwd=workspace,
        )
        if completed.returncode:
            raise Alpha1ReplayError(
                "historical native validation command failed: "
                + completed.stdout
                + completed.stderr
            )
        try:
            observed = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise Alpha1ReplayError(
                "historical native validation did not emit JSON"
            ) from error
        observed_validation = observed.get("validation_result")
        if not isinstance(observed_validation, dict):
            raise Alpha1ReplayError("historical native validation omitted its result")
        evidence_resolves = evidence_path.is_file()
        if observed_validation.get("status") != "passed" or evidence_resolves:
            raise Alpha1ReplayError("forged validation predicate was not reproduced")

        return {
            "schema_version": 1,
            "case_id": "forged-validation",
            "status": "vulnerability_reproduced",
            "semantic_predicate": (
                "legacy_native_adapter_accepted_passed_validation_with_unresolvable_evidence"
            ),
            "baseline": {"tag": ALPHA1_TAG, "commit": ALPHA1_COMMIT},
            "host": "claude",
            "host_package": {"path": CLAUDE_PACKAGE, "sha256": _tree_digest(package)},
            "inputs": {"finding": _input_receipt(finding)},
            "environment": {
                "python": sys.version.split()[0],
                "implementation": sys.implementation.name,
                "platform": sys.platform,
                "network": "disabled-by-design; local Git object and fixture only",
            },
            "commands": [
                _redact_validation_command(
                    command, checkout=checkout, workspace=workspace
                )
            ],
            "observed": {
                "validation_status": observed_validation["status"],
                "evidence_ref": evidence_ref,
                "evidence_resolves": evidence_resolves,
            },
            "limitations": [
                "baseline reproduction is not fix confirmation",
                "missing-evidence remains a separate pending corpus case",
            ],
        }
    finally:
        try:
            _remove_worktree(repository, checkout)
        finally:
            if not keep_workspace:
                _remove_workspace(workspace)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay Alpha1 forged validation acceptance."
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
        receipt = replay_forged_validation(
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
