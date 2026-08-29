"""Record the clean-dev evidence bundle for issue #112."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research_tree.verification_receipts import local_verification_path

MERGED_SLICES = [
    {"issue": 111, "pull_request": 115, "merge_revision": "6bb8cfa"},
    {"issue": 108, "pull_request": 116, "merge_revision": "5539e92"},
    {"issue": 110, "pull_request": 122, "merge_revision": "540014f"},
    {"issue": 109, "pull_request": 123, "merge_revision": "63164fb"},
]

COMMANDS = [
    (
        "focused_strict_suite",
        "uv run pytest -q tests/test_canonical_evidence_foundation.py tests/test_atomic_ledger_content_binding.py tests/test_evidence_contract.py tests/test_strict_evidence_decision_boundary.py tests/test_readiness.py tests/test_strict_delivery_lineage.py tests/test_deliveries.py tests/test_recursive_search.py",
        "integrated-focused-suite-output.txt",
    ),
    ("full_regression", "uv run pytest -q", "integrated-full-regression-output.txt"),
    (
        "openspec_strict",
        "openspec validate --changes --strict --no-interactive",
        "integrated-openspec-output.txt",
    ),
    (
        "package_parity",
        "uv run python scripts/build_skill_packages.py --check",
        "integrated-package-output.txt",
    ),
    (
        "governance",
        "uv run python scripts/check_openspec_governance.py --repo .",
        "integrated-governance-output.txt",
    ),
    (
        "delivery_workflow",
        "uv run python scripts/check_delivery_workflow.py validate",
        "integrated-delivery-output.txt",
    ),
]


def _run(repo: Path, command: str) -> tuple[int, bytes]:
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return completed.returncode, completed.stdout


def _source_revision(repo: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return completed.stdout.decode("ascii").strip()


def _future_gaps(repo: Path, registry: Path) -> list[dict[str, Any]]:
    payload = json.loads(registry.read_text(encoding="utf-8"))
    gaps: list[dict[str, Any]] = []
    for group in payload["groups"]:
        if group["group"] < 4 or group["group"] > 32:
            continue
        paths = sorted(
            set(re.findall(r"(?:tests|scripts|evaluation)/[A-Za-z0-9_./-]+(?:\.py)?", group["acceptance_command"]))
        )
        missing = [path for path in paths if not (repo / path).exists()]
        gaps.append(
            {
                "group": group["group"],
                "state": "planned",
                "acceptance_command": group["acceptance_command"],
                "missing_paths": missing,
                "reason": "future task command is not evidence on the current clean-dev baseline",
            }
        )
    return gaps


def _record_group_35(repo: Path, evidence_dir: Path, source_revision: str) -> None:
    command = "uv run pytest -q tests/test_integrated_evidence_receipt.py"
    exit_code, output = _run(repo, command)
    output_path = evidence_dir / "group-35-output.txt"
    output_path.write_bytes(output)
    receipt = {
        "command": command,
        "environment_digest": "52f016b66b8402a4ad7d640eff6154b15442c7eb1ebe52c9ec20998448a5991f",
        "exit_code": exit_code,
        "output_digest": hashlib.sha256(output).hexdigest(),
        "raw_output_ref": output_path.relative_to(repo).as_posix(),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "source_revision": source_revision,
    }
    (evidence_dir / "group-35-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=Path(".research-tree/verification-runs/integrated-evidence"),
    )
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    evidence_dir = local_verification_path(repo, args.evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    source_revision = _source_revision(repo)
    commands: list[dict[str, Any]] = []
    failed = False

    def write_bundle() -> None:
        (evidence_dir / "future-evidence-gaps.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "source_revision": source_revision,
                    "gaps": _future_gaps(
                        repo,
                        repo / "openspec/changes/unify-research-runtime-alpha2/registries/task-execution-v1.json",
                    ),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        (evidence_dir / "integrated-strict-slices.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "kind": "integrated_verification_receipt",
                    "source_revision": source_revision,
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                    "merged_slices": MERGED_SLICES,
                    "commands": commands,
                    "future_evidence_gaps_ref": (evidence_dir / "future-evidence-gaps.json")
                    .relative_to(repo)
                    .as_posix(),
                    "boundary": {
                        "current_issue": 112,
                        "legacy_worker_validation_guard_issue": 109,
                        "oracle_slot_closure_issue": 56,
                        "parent_tracker_issue": 106,
                    },
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    for name, command, output_name in COMMANDS:
        exit_code, output = _run(repo, command)
        output_path = evidence_dir / output_name
        output_path.write_bytes(output)
        commands.append(
            {
                "name": name,
                "command": command,
                "exit_code": exit_code,
                "raw_output_ref": output_path.relative_to(repo).as_posix(),
                "output_digest": hashlib.sha256(output).hexdigest(),
            }
        )
        failed |= exit_code != 0
        # Full regression imports the receipt test. Seed the bundle after the
        # first independent command so the test has real evidence to inspect.
        if len(commands) == 1:
            write_bundle()
    _record_group_35(repo, evidence_dir, source_revision)
    write_bundle()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
