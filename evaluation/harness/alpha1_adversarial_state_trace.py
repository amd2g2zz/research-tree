"""Replay pinned Alpha1 state/trace adversarial cases.

The evaluator materializes tag ``0.0.1-a1`` in a detached temporary worktree
and invokes only public Alpha1 functions or command-line adapters. A successful
command is not enough to classify a defect as reproduced: each case has a
separate semantic predicate over persisted state and fixture semantics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


ALPHA1_TAG = "0.0.1-a1"
ALPHA1_COMMIT = "8ab91ea4eb55c98441b5ee6001b80922a56ecdd1"
FIXTURE_RELATIVE = Path("evaluation/fixtures/alpha1-adversarial-v1/state-trace")
HERMES_PACKAGE = Path("packages/hermes/research-tree")
CASE_IDS = (
    "empty-frontier",
    "active-contradiction",
    "repeated-reconnaissance",
    "adapter-only-completion",
)

_STATE_PROBE = r'''from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

sys.path.insert(0, sys.argv[1])

from research_tree import (  # noqa: E402
    apply_research_results,
    initialize_research_state,
    select_research_actions,
)

case_id = sys.argv[2]
spec = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))

if case_id == "empty-frontier":
    state = initialize_research_state(
        round_id=spec["round_id"],
        tree_id=spec["tree_id"],
        decision_slots=spec["decision_slots"],
    )
    slot = state["decision_slots"].get("slot-architecture")
    observed = {
        "status": state["status"],
        "slot_status": slot["status"] if slot is not None else "filtered_out",
        "frontier_node_ids": state["frontier_node_ids"],
        "stop_reason": state["stop_reason"],
        "consumed_finding_ids": state["consumed_finding_ids"],
    }
elif case_id == "active-contradiction":
    state = initialize_research_state(
        round_id=spec["round_id"],
        tree_id=spec["tree_id"],
        decision_slots=spec["decision_slots"],
        baseline_findings=[spec["baseline_finding"]],
    )
    actions = select_research_actions(state, max_parallelism=1)
    if len(actions) != 1:
        raise RuntimeError("Alpha1 did not expose one triangulation action")
    contradictory = copy.deepcopy(spec["contradictory_finding"])
    contradictory["research_node_id"] = actions[0]["id"]
    state = apply_research_results(state, [contradictory])
    slot = state["decision_slots"]["slot-architecture"]
    delta = state["delta_history"][-1]
    observed = {
        "status": state["status"],
        "slot_status": slot["status"],
        "frontier_node_ids": state["frontier_node_ids"],
        "stop_reason": state["stop_reason"],
        "contradiction_count": delta["contradiction_count"],
        "consumed_finding_ids": state["consumed_finding_ids"],
        "finding_ids": slot["finding_ids"],
        "anchor_count": len(slot["anchor_fingerprints"]),
        "research_node_id": actions[0]["id"],
    }
else:
    raise RuntimeError(f"unsupported state probe case: {case_id}")

print(json.dumps(observed, ensure_ascii=False, sort_keys=True))
'''


class Alpha1StateTraceError(RuntimeError):
    """Raised when the pinned state/trace baseline cannot be replayed."""


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


def _input_receipt(path: Path) -> dict[str, Any]:
    return {"bytes": path.stat().st_size, "sha256": _sha256_file(path)}


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Alpha1StateTraceError(f"invalid {label}: {error}") from error
    if not isinstance(value, dict):
        raise Alpha1StateTraceError(f"{label} must be a JSON object")
    return value


def _command(
    argv: list[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=dict(env) if env is not None else None,
        text=True,
        capture_output=True,
        check=False,
    )
    return completed, {
        "argv": argv,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "stdout_sha256": _sha256_bytes(completed.stdout.encode("utf-8")),
        "stderr_sha256": _sha256_bytes(completed.stderr.encode("utf-8")),
    }


def _git(repository_root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository_root), *arguments],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise Alpha1StateTraceError(
            completed.stderr.strip() or "git command failed"
        )
    return completed.stdout.strip()


def _materialize_clean_alpha1(repository_root: Path, checkout: Path) -> None:
    if checkout.exists():
        raise Alpha1StateTraceError(f"checkout path already exists: {checkout}")
    if _git(repository_root, "rev-parse", f"{ALPHA1_TAG}^{{commit}}") != ALPHA1_COMMIT:
        raise Alpha1StateTraceError("Alpha1 tag does not resolve to the pinned commit")
    _git(repository_root, "worktree", "add", "--detach", str(checkout), ALPHA1_COMMIT)
    if _git(checkout, "rev-parse", "HEAD") != ALPHA1_COMMIT:
        raise Alpha1StateTraceError(
            "materialized baseline HEAD does not match pinned commit"
        )
    if _git(checkout, "status", "--porcelain=v1", "--untracked-files=all"):
        raise Alpha1StateTraceError("materialized baseline checkout is not clean")


def _remove_worktree(repository_root: Path, checkout: Path) -> None:
    if checkout.exists():
        _git(repository_root, "worktree", "remove", "--force", str(checkout))


def _inside(parent: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(parent)
    except ValueError:
        return False
    return True


def _redact_command(
    receipt: Mapping[str, Any],
    *,
    checkout: Path,
    workspace: Path,
    name: str,
) -> dict[str, Any]:
    def redact_value(value: str) -> str:
        if value == sys.executable:
            return "<python>"
        return (
            value.replace(str(workspace), "<workspace>")
            .replace(str(checkout), "<alpha1-checkout>")
        )

    argv = [redact_value(str(value)) for value in receipt["argv"]]
    stdout = redact_value(str(receipt["stdout"]))
    stderr = redact_value(str(receipt["stderr"]))
    return {
        "command": shlex.join(argv),
        "name": name,
        "returncode": receipt["returncode"],
        "stdout": stdout,
        "stderr": stderr,
        "raw_stdout_sha256": receipt["stdout_sha256"],
        "raw_stderr_sha256": receipt["stderr_sha256"],
        "redacted_stdout_sha256": _sha256_bytes(stdout.encode("utf-8")),
        "redacted_stderr_sha256": _sha256_bytes(stderr.encode("utf-8")),
    }


def _parse_json_output(
    completed: subprocess.CompletedProcess[str], label: str
) -> dict[str, Any]:
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise Alpha1StateTraceError(f"{label} did not emit JSON") from error
    if not isinstance(value, dict):
        raise Alpha1StateTraceError(f"{label} output must be a JSON object")
    return value


def _copy_fixture(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return destination


def _base_receipt(case_id: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "case_id": case_id,
        "baseline": {"tag": ALPHA1_TAG, "commit": ALPHA1_COMMIT},
        "environment": {
            "python": sys.version.split()[0],
            "implementation": sys.implementation.name,
            "platform": sys.platform,
            "network": "disabled-by-design; local Git object and fixtures only",
        },
    }


def _run_state_probe(
    *,
    case_id: str,
    fixture: Path,
    checkout: Path,
    workspace: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    workspace.mkdir(parents=True, exist_ok=True)
    copied_fixture = _copy_fixture(fixture, workspace / fixture.name)
    probe = workspace / "state_probe.py"
    probe.write_text(_STATE_PROBE, encoding="utf-8")
    completed, raw_receipt = _command(
        [
            sys.executable,
            str(probe),
            str(checkout / "src"),
            case_id,
            str(copied_fixture),
        ],
        cwd=workspace,
    )
    if completed.returncode:
        raise Alpha1StateTraceError(
            f"historical {case_id} state probe failed: "
            f"{completed.stdout}{completed.stderr}"
        )
    observed = _parse_json_output(completed, f"historical {case_id} state probe")
    command = _redact_command(
        raw_receipt,
        checkout=checkout,
        workspace=workspace,
        name="state-probe",
    )
    return observed, [command]


def _replay_empty_frontier(
    *, fixture: Path, checkout: Path, workspace: Path
) -> dict[str, Any]:
    observed, commands = _run_state_probe(
        case_id="empty-frontier",
        fixture=fixture,
        checkout=checkout,
        workspace=workspace,
    )
    predicate_satisfied = (
        observed.get("status") == "blocked"
        and observed.get("frontier_node_ids") == []
    )
    return {
        **_base_receipt("empty-frontier"),
        "status": "pending",
        "semantic_predicate": "alpha1_empty_frontier_did_not_complete",
        "reason": "Pinned Alpha1 blocked rather than completing unsafely with an empty frontier.",
        "source_package": {
            "path": "src/research_tree",
            "sha256": _tree_digest(checkout / "src" / "research_tree"),
        },
        "inputs": {"fixture": _input_receipt(fixture)},
        "commands": commands,
        "observed": {**observed, "predicate_satisfied": predicate_satisfied},
        "limitations": [
            "Alpha1 blocked rather than completed with an empty frontier, so the unsafe completion claim is not reproduced.",
            "baseline observation is not fix confirmation",
        ],
    }


def _fixture_contradiction_count(value: Mapping[str, Any]) -> int:
    finding = value.get("contradictory_finding")
    if not isinstance(finding, Mapping):
        return 0
    effects = finding.get("option_effects", ())
    if isinstance(effects, (str, bytes)) or not isinstance(effects, Sequence):
        return 0
    return sum(
        1
        for effect in effects
        if isinstance(effect, Mapping) and effect.get("effect") == "contradicts"
    )


def _replay_active_contradiction(
    *, fixture: Path, checkout: Path, workspace: Path
) -> dict[str, Any]:
    fixture_value = _read_json(fixture, "active-contradiction fixture")
    observed, commands = _run_state_probe(
        case_id="active-contradiction",
        fixture=fixture,
        checkout=checkout,
        workspace=workspace,
    )
    contradiction_count = _fixture_contradiction_count(fixture_value)
    predicate_satisfied = (
        contradiction_count > 0
        and observed.get("contradiction_count") == contradiction_count
        and observed.get("slot_status") == "closed"
        and observed.get("frontier_node_ids") == []
    )
    return {
        **_base_receipt("active-contradiction"),
        "status": "vulnerability_reproduced" if predicate_satisfied else "pending",
        "semantic_predicate": (
            "alpha1_closed_slot_while_active_contradiction_remained"
        ),
        "source_package": {
            "path": "src/research_tree",
            "sha256": _tree_digest(checkout / "src" / "research_tree"),
        },
        "inputs": {
            "fixture": _input_receipt(fixture),
            "contradiction_count": contradiction_count,
        },
        "commands": commands,
        "observed": {**observed, "predicate_satisfied": predicate_satisfied},
        "limitations": ["baseline reproduction is not fix confirmation"],
    }


def _alpha1_environment(checkout: Path) -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": str(checkout / "src")}


def _replay_repeated_reconnaissance(
    *, fixture: Path, checkout: Path, workspace: Path
) -> dict[str, Any]:
    spec = _read_json(fixture, "repeated-reconnaissance fixture")
    run_id = spec.get("run_id")
    fingerprint = spec.get("fingerprint")
    graph = spec.get("graph")
    if not isinstance(run_id, str) or not run_id:
        raise Alpha1StateTraceError("repeated-reconnaissance run_id is invalid")
    if not isinstance(fingerprint, str) or not fingerprint:
        raise Alpha1StateTraceError(
            "repeated-reconnaissance fingerprint is invalid"
        )
    if not isinstance(graph, Mapping):
        raise Alpha1StateTraceError("repeated-reconnaissance graph is invalid")

    workspace.mkdir(parents=True, exist_ok=True)
    graph_path = workspace / "graph.json"
    graph_path.write_text(
        json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    controller = checkout / "scripts" / "alignment_controller.py"
    env = _alpha1_environment(checkout)
    commands: list[dict[str, Any]] = []

    def invoke(name: str, *arguments: str) -> dict[str, Any]:
        completed, raw_receipt = _command(
            [sys.executable, str(controller), "--workspace", str(workspace), *arguments],
            cwd=workspace,
            env=env,
        )
        commands.append(
            _redact_command(
                raw_receipt,
                checkout=checkout,
                workspace=workspace,
                name=name,
            )
        )
        if completed.returncode:
            raise Alpha1StateTraceError(
                f"historical alignment {name} failed: "
                f"{completed.stdout}{completed.stderr}"
            )
        return _parse_json_output(completed, f"historical alignment {name}")

    invoke("init", "init", "--run-id", run_id)
    first_plan = invoke(
        "plan", "plan", "--run-id", run_id, "--graph-file", str(graph_path)
    )
    node_id = first_plan.get("node_id")
    if first_plan.get("action") != "ask_one" or not isinstance(node_id, str):
        raise Alpha1StateTraceError("Alpha1 did not expose the expected human gap")
    records = [
        invoke(
            "record",
            "record",
            "--run-id",
            run_id,
            "--node-id",
            node_id,
            "--outcome",
            "unchanged",
            "--fingerprint",
            fingerprint,
        )
        for _ in range(3)
    ]
    reconnaissance = [
        invoke(
            "plan",
            "plan",
            "--run-id",
            run_id,
            "--graph-file",
            str(graph_path),
        )
        for _ in range(2)
    ]
    status = invoke("status", "status", "--run-id", run_id)

    database = workspace / ".research-tree-alignment" / run_id / "alignment.db"
    with sqlite3.connect(database) as connection:
        response_events = int(
            connection.execute(
                "SELECT COUNT(*) FROM events WHERE event_type='response_recorded'"
            ).fetchone()[0]
        )
    nodes = status.get("graph", {}).get("nodes", [])
    node = next(
        (
            candidate
            for candidate in nodes
            if isinstance(candidate, Mapping) and candidate.get("id") == node_id
        ),
        {},
    )
    controller_state = status.get("controller", {})
    actions = [item.get("action") for item in reconnaissance]
    observed = {
        "initial_action": first_plan["action"],
        "next_action": records[-1].get("next_action"),
        "stagnant_turns": controller_state.get("stagnant_turns"),
        "response_events": response_events,
        "reconnaissance_actions": actions,
        "ask_count": node.get("ask_count"),
        "plan_count": controller_state.get("plan_count"),
    }
    predicate_satisfied = (
        observed["next_action"] == "reconnaissance"
        and observed["stagnant_turns"] == 2
        and response_events == 3
        and actions == ["reconnaissance", "reconnaissance"]
        and observed["ask_count"] == 1
    )
    return {
        **_base_receipt("repeated-reconnaissance"),
        "status": "vulnerability_reproduced" if predicate_satisfied else "pending",
        "semantic_predicate": (
            "alpha1_repeated_reconnaissance_without_attempt_consumption"
        ),
        "source_package": {
            "path": "src/research_tree/alignment_graph.py",
            "sha256": _sha256_file(
                checkout / "src" / "research_tree" / "alignment_graph.py"
            ),
        },
        "inputs": {"fixture": _input_receipt(fixture)},
        "commands": commands,
        "observed": {**observed, "predicate_satisfied": predicate_satisfied},
        "limitations": ["baseline reproduction is not fix confirmation"],
    }


def _copy_adapter_fixture(fixture: Path, workspace: Path) -> dict[str, Path]:
    names = ("handoff.json", "finding.txt", "technical.md", "human.md")
    if not fixture.is_dir() or any(not (fixture / name).is_file() for name in names):
        raise Alpha1StateTraceError("adapter-only-completion fixture is incomplete")
    workspace.mkdir(parents=True, exist_ok=True)
    return {
        name: _copy_fixture(fixture / name, workspace / name) for name in names
    }


def _is_json_document(path: Path) -> bool:
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return True


def _replay_adapter_only_completion(
    *, fixture: Path, checkout: Path, workspace: Path
) -> dict[str, Any]:
    files = _copy_adapter_fixture(fixture, workspace)
    adapter = checkout / HERMES_PACKAGE / "scripts" / "hermes_execution_adapter.py"
    run_id = "alpha1-adapter-only-completion"
    commands: list[dict[str, Any]] = []

    def invoke(name: str, *arguments: str) -> dict[str, Any]:
        completed, raw_receipt = _command(
            [sys.executable, str(adapter), "--workspace", str(workspace), *arguments],
            cwd=workspace,
        )
        commands.append(
            _redact_command(
                raw_receipt,
                checkout=checkout,
                workspace=workspace,
                name=name,
            )
        )
        if completed.returncode:
            raise Alpha1StateTraceError(
                f"historical Hermes {name} failed: "
                f"{completed.stdout}{completed.stderr}"
            )
        return _parse_json_output(completed, f"historical Hermes {name}")

    invoke(
        "init",
        "init",
        "--run-id",
        run_id,
        "--handoff",
        str(files["handoff.json"]),
    )
    invoke(
        "record-batch",
        "record-batch",
        "--run-id",
        run_id,
        "--batch-id",
        "batch-1",
        "--status",
        "verified",
        "--finding",
        str(files["finding.txt"]),
    )
    completed = invoke(
        "complete",
        "complete",
        "--run-id",
        run_id,
        "--technical-report",
        str(files["technical.md"]),
        "--human-report",
        str(files["human.md"]),
    )
    batch = completed.get("batches", {}).get("batch-1", {})
    delegation_ids = batch.get("delegation_ids")
    finding_is_json = _is_json_document(files["finding.txt"])
    observed = {
        "status": completed.get("status"),
        "batch_status": batch.get("status"),
        "delegation_ids": delegation_ids,
        "finding_is_json": finding_is_json,
        "finding_path_count": len(batch.get("finding_paths", [])),
    }
    predicate_satisfied = (
        observed["status"] == "complete"
        and observed["batch_status"] == "verified"
        and delegation_ids == []
        and finding_is_json is False
        and observed["finding_path_count"] == 1
    )
    return {
        **_base_receipt("adapter-only-completion"),
        "status": "vulnerability_reproduced" if predicate_satisfied else "pending",
        "semantic_predicate": (
            "alpha1_adapter_completed_without_delegation_or_semantic_finding"
        ),
        "host": "hermes",
        "host_package": {
            "path": HERMES_PACKAGE.as_posix(),
            "sha256": _tree_digest(checkout / HERMES_PACKAGE),
        },
        "inputs": {
            name: _input_receipt(fixture / name)
            for name in ("handoff.json", "finding.txt", "technical.md", "human.md")
        },
        "commands": commands,
        "observed": {**observed, "predicate_satisfied": predicate_satisfied},
        "limitations": ["baseline reproduction is not fix confirmation"],
    }


def replay_state_trace_cases(
    *,
    repository_root: str | Path,
    work_root: str | Path,
    keep_workspace: bool = False,
) -> dict[str, dict[str, Any]]:
    """Replay all four state/trace cases from one clean pinned checkout."""

    repository = Path(repository_root).resolve()
    root = Path(work_root).resolve()
    checkout = root / "alpha1-checkout"
    fixture_root = repository / FIXTURE_RELATIVE
    if root.exists() and any(root.iterdir()):
        raise Alpha1StateTraceError("work_root must be empty")
    required = {
        "empty-frontier": fixture_root / "empty-frontier.json",
        "active-contradiction": fixture_root / "active-contradiction.json",
        "repeated-reconnaissance": fixture_root / "repeated-reconnaissance.json",
        "adapter-only-completion": fixture_root / "adapter-only-completion",
    }
    if any(not path.exists() for path in required.values()):
        raise Alpha1StateTraceError("state-trace fixture set is incomplete")

    root.mkdir(parents=True, exist_ok=True)
    try:
        _materialize_clean_alpha1(repository, checkout)
        receipts = {
            "empty-frontier": _replay_empty_frontier(
                fixture=required["empty-frontier"],
                checkout=checkout,
                workspace=root / "empty-frontier-workspace",
            ),
            "active-contradiction": _replay_active_contradiction(
                fixture=required["active-contradiction"],
                checkout=checkout,
                workspace=root / "active-contradiction-workspace",
            ),
            "repeated-reconnaissance": _replay_repeated_reconnaissance(
                fixture=required["repeated-reconnaissance"],
                checkout=checkout,
                workspace=root / "repeated-reconnaissance-workspace",
            ),
            "adapter-only-completion": _replay_adapter_only_completion(
                fixture=required["adapter-only-completion"],
                checkout=checkout,
                workspace=root / "adapter-only-completion-workspace",
            ),
        }
        return receipts
    finally:
        try:
            _remove_worktree(repository, checkout)
        finally:
            if not keep_workspace:
                for child in tuple(root.iterdir()) if root.exists() else ():
                    if child.is_dir():
                        shutil.rmtree(child)
                    else:
                        child.unlink()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay pinned Alpha1 state/trace adversarial cases."
    )
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--keep-workspace", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    repository_root = arguments.repository_root.expanduser().resolve()
    work_root = arguments.work_root.expanduser().resolve()
    results_dir = arguments.results_dir.expanduser().resolve()
    if not arguments.keep_workspace and _inside(work_root, results_dir):
        print(
            json.dumps(
                {
                    "error": (
                        "--results-dir must be outside --work-root unless "
                        "--keep-workspace is used"
                    )
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    try:
        receipts = replay_state_trace_cases(
            repository_root=repository_root,
            work_root=work_root,
            keep_workspace=arguments.keep_workspace,
        )
        results_dir.mkdir(parents=True, exist_ok=True)
        for case_id in CASE_IDS:
            (results_dir / f"{case_id}.json").write_text(
                json.dumps(
                    receipts[case_id], ensure_ascii=False, indent=2, sort_keys=True
                )
                + "\n",
                encoding="utf-8",
            )
    except (Alpha1StateTraceError, OSError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(receipts, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
