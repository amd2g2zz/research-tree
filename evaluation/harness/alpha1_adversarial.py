"""Evaluator-only replays for pinned Alpha1 adversarial fixtures.

This module deliberately lives outside ``src/research_tree`` and every host
package. It runs historical source from a temporary detached Git worktree, not
from the current checkout, and returns redacted command receipts.
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


ALPHA1_TAG = "0.0.1-a1"
ALPHA1_COMMIT = "8ab91ea4eb55c98441b5ee6001b80922a56ecdd1"
HERMES_PACKAGE = "packages/hermes/research-tree"
FIXTURE_RELATIVE = Path("evaluation/fixtures/alpha1-adversarial-v1/filler-report")


class Alpha1ReplayError(RuntimeError):
    """Raised when the pinned historical baseline cannot be replayed."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _command(argv: list[str], *, cwd: Path) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    receipt = {
        "argv": argv,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "stdout_sha256": _sha256_bytes(completed.stdout.encode("utf-8")),
        "stderr_sha256": _sha256_bytes(completed.stderr.encode("utf-8")),
    }
    return completed, receipt


def _git(repository_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository_root), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise Alpha1ReplayError(completed.stderr.strip() or "git command failed")
    return completed.stdout.strip()


def _materialize_clean_alpha1(repository_root: Path, checkout: Path) -> None:
    if checkout.exists():
        raise Alpha1ReplayError(f"checkout path already exists: {checkout}")
    if _git(repository_root, "rev-parse", f"{ALPHA1_TAG}^{{commit}}") != ALPHA1_COMMIT:
        raise Alpha1ReplayError("Alpha1 tag does not resolve to the pinned commit")
    _git(repository_root, "worktree", "add", "--detach", str(checkout), ALPHA1_COMMIT)
    if _git(checkout, "rev-parse", "HEAD") != ALPHA1_COMMIT:
        raise Alpha1ReplayError("materialized baseline HEAD does not match pinned commit")
    if _git(checkout, "status", "--porcelain=v1", "--untracked-files=all"):
        raise Alpha1ReplayError("materialized baseline checkout is not clean")


def _remove_worktree(repository_root: Path, checkout: Path) -> None:
    if checkout.exists():
        _git(repository_root, "worktree", "remove", "--force", str(checkout))


def _remove_workspace(workspace: Path) -> None:
    if workspace.exists():
        shutil.rmtree(workspace)


def _inside(parent: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(parent)
    except ValueError:
        return False
    return True


def _copy_fixture(repository_root: Path, workspace: Path) -> dict[str, Path]:
    fixture = repository_root / FIXTURE_RELATIVE
    names = ("handoff.json", "finding.json", "technical.md", "human.md")
    if not fixture.is_dir() or any(not (fixture / name).is_file() for name in names):
        raise Alpha1ReplayError("filler-report fixture is incomplete")
    workspace.mkdir(parents=True, exist_ok=True)
    copied: dict[str, Path] = {}
    for name in names:
        destination = workspace / name
        shutil.copyfile(fixture / name, destination)
        copied[name] = destination
    return copied


def _input_receipt(path: Path) -> dict[str, Any]:
    return {"sha256": _sha256_file(path), "bytes": path.stat().st_size}


def _redact_command(receipt: dict[str, Any], *, checkout: Path, workspace: Path) -> dict[str, Any]:
    """Keep replayable command/output evidence without leaking temp paths."""

    argv = list(receipt["argv"])
    adapter = checkout / HERMES_PACKAGE / "scripts" / "hermes_execution_adapter.py"
    rendered: list[str] = []
    for value in argv:
        if value == sys.executable:
            rendered.append("<python>")
        elif value == str(adapter):
            rendered.append(f"{HERMES_PACKAGE}/scripts/hermes_execution_adapter.py")
        elif value == str(workspace):
            rendered.append("<workspace>")
        elif value.startswith(str(workspace) + "/"):
            rendered.append("<workspace>/" + Path(value).relative_to(workspace).as_posix())
        else:
            rendered.append(value)

    def redact_output(value: str) -> str:
        return value.replace(str(workspace), "<workspace>").replace(str(checkout), "<alpha1-checkout>")

    redacted_stdout = redact_output(receipt["stdout"])
    redacted_stderr = redact_output(receipt["stderr"])
    command = next((item for item in argv if item in {"init", "record-batch", "complete"}), "unknown")
    return {
        "command": shlex.join(rendered),
        "name": command,
        "returncode": receipt["returncode"],
        "stdout": redacted_stdout,
        "stderr": redacted_stderr,
        "stdout_sha256": receipt["stdout_sha256"],
        "stderr_sha256": receipt["stderr_sha256"],
        "raw_stdout_sha256": receipt["stdout_sha256"],
        "raw_stderr_sha256": receipt["stderr_sha256"],
        "redacted_stdout_sha256": _sha256_bytes(redacted_stdout.encode("utf-8")),
        "redacted_stderr_sha256": _sha256_bytes(redacted_stderr.encode("utf-8")),
    }


def replay_filler_report(
    *,
    repository_root: str | Path,
    work_root: str | Path,
    keep_workspace: bool = False,
) -> dict[str, Any]:
    """Replay Alpha1 Hermes structural-only completion using only filler reports.

    A successful legacy completion is deliberately classified as a vulnerability
    reproduction. This is not candidate validation and cannot produce
    ``fix_confirmed``.

    The temporary execution workspace is removed on success and failure by
    default. Set ``keep_workspace`` only when the generated state is needed for
    inspection; a kept work root must be replaced or emptied before rerunning.
    """

    repository = Path(repository_root).resolve()
    root = Path(work_root).resolve()
    checkout = root / "alpha1-checkout"
    workspace = root / "filler-report-workspace"
    if root.exists() and any(root.iterdir()):
        raise Alpha1ReplayError("work_root must be empty")
    root.mkdir(parents=True, exist_ok=True)
    try:
        _materialize_clean_alpha1(repository, checkout)
        files = _copy_fixture(repository, workspace)
        adapter = checkout / HERMES_PACKAGE / "scripts" / "hermes_execution_adapter.py"
        package = checkout / HERMES_PACKAGE
        if not adapter.is_file():
            raise Alpha1ReplayError("pinned Hermes adapter does not exist")
        commands: list[dict[str, Any]] = []

        def invoke(*arguments: str) -> subprocess.CompletedProcess[str]:
            completed, receipt = _command(
                [sys.executable, str(adapter), "--workspace", str(workspace), *arguments],
                cwd=workspace,
            )
            commands.append(receipt)
            if completed.returncode:
                raise Alpha1ReplayError(
                    f"historical Hermes command failed: {' '.join(arguments)}: {completed.stdout}{completed.stderr}"
                )
            return completed

        invoke("init", "--run-id", "alpha1-filler", "--handoff", str(files["handoff.json"]))
        invoke(
            "record-batch",
            "--run-id",
            "alpha1-filler",
            "--batch-id",
            "batch-1",
            "--status",
            "verified",
            "--finding",
            str(files["finding.json"]),
        )
        completed = invoke(
            "complete",
            "--run-id",
            "alpha1-filler",
            "--technical-report",
            str(files["technical.md"]),
            "--human-report",
            str(files["human.md"]),
        )
        try:
            observed = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise Alpha1ReplayError("historical Hermes completion did not emit JSON") from error
        if observed.get("status") != "complete":
            raise Alpha1ReplayError("historical Hermes completion did not reach complete")

        return {
            "schema_version": 1,
            "case_id": "filler-report",
            "status": "vulnerability_reproduced",
            "semantic_predicate": "legacy_hermes_completed_heading_padding_reports",
            "baseline": {"tag": ALPHA1_TAG, "commit": ALPHA1_COMMIT},
            "host": "hermes",
            "host_package": {"path": HERMES_PACKAGE, "sha256": _tree_digest(package)},
            "inputs": {
                "handoff": _input_receipt(files["handoff.json"]),
                "finding": _input_receipt(files["finding.json"]),
                "technical": _input_receipt(files["technical.md"]),
                "human": _input_receipt(files["human.md"]),
            },
            "environment": {
                "python": sys.version.split()[0],
                "implementation": sys.implementation.name,
                "platform": sys.platform,
            },
            "commands": [
                _redact_command(receipt, checkout=checkout, workspace=workspace)
                for receipt in commands
            ],
            "observed": {"status": observed["status"]},
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
        description="Replay the pinned Alpha1 Hermes adversarial baseline."
    )
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
        help="caller-owned temporary execution root; generated contents are removed and the root is left empty after the replay by default",
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
                {"error": "--receipt must be outside --work-root unless --keep-workspace is used"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2

    try:
        receipt = replay_filler_report(
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
