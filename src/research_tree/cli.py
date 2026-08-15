"""Current-only command boundary for the canonical research runtime."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .coordinator import (
    CompletionBlockedError,
    CoordinatorConflictError,
    CoordinatorError,
    IllegalTransitionError,
    ResearchRunCoordinator,
    StaleStateError,
)
from .domain import RuntimeStoreError
from .run_ledger import RunLedger


class CliInputError(ValueError):
    """Raised when a current CLI input cannot be parsed safely."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-tree",
        description="Current-only canonical coordinator commands.",
        epilog="Available verbs: ingest, recover, why-not-complete, complete.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="invoke one canonical SQLite coordinator operation")
    run.add_argument("--workspace", required=True, type=Path, help="workspace containing the canonical SQLite ledger")
    verbs = run.add_subparsers(dest="verb", required=True)

    ingest = verbs.add_parser("ingest", help="persist one validated HostEvent envelope")
    ingest.add_argument("--event", required=True, type=Path, help="path to one HostEvent JSON object")

    recover = verbs.add_parser("recover", help="mark interrupted canonical attempts as unknown")
    recover.add_argument("--run-id", required=True)

    why_not_complete = verbs.add_parser("why-not-complete", help="report completion obligations from the coordinator")
    why_not_complete.add_argument("--run-id", required=True)

    complete = verbs.add_parser("complete", help="request terminal completion from the coordinator")
    complete.add_argument("--run-id", required=True)
    complete.add_argument("--actor", required=True)
    complete.add_argument("--expected-revision", required=True, type=int)
    return parser


def _read_json_object(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CliInputError("event_json_invalid") from error
    if not isinstance(value, Mapping):
        raise CliInputError("event_json_object_required")
    return value


def _success(run_id: str | None, result: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "code": "ok",
        "category": "success",
        "retryability": False,
        "run_id": run_id,
        "safe_message": "ok",
        "unmet_obligations": [],
        "evidence_refs": [],
        "next_action": None,
        "result": result,
    }
    if isinstance(result, Mapping):
        obligations = result.get("unmet_obligations")
        if isinstance(obligations, (list, tuple)):
            payload["unmet_obligations"] = list(obligations)
        actions = result.get("next_actions")
        if isinstance(actions, (list, tuple)) and actions:
            payload["next_action"] = actions[0]
    return payload


def _failure(error: Exception, run_id: str | None) -> tuple[int, dict[str, Any]]:
    code = str(error) or type(error).__name__
    category = "invalid_input"
    retryability = False
    exit_code = 2
    unmet_obligations: list[str] = []
    next_action: str | None = None

    if isinstance(error, CompletionBlockedError):
        code = "completion_blocked"
        category = "blocked"
        exit_code = 4
        unmet_obligations = list(error.unmet_obligations)
        next_action = "resolve:" + unmet_obligations[0] if unmet_obligations else None
    elif isinstance(error, StaleStateError):
        category = "conflict"
        retryability = True
        exit_code = 3
        next_action = error.next_action
    elif isinstance(error, CoordinatorConflictError) and code == "stale_revision":
        category = "conflict"
        retryability = True
        exit_code = 3
    elif isinstance(error, IllegalTransitionError):
        category = "terminal"
        exit_code = 10
    elif isinstance(error, (RuntimeStoreError, OSError)) and not isinstance(error, CoordinatorError):
        category = "store_unavailable"
        retryability = True
        exit_code = 9

    return exit_code, {
        "code": code,
        "category": category,
        "retryability": retryability,
        "run_id": run_id,
        "safe_message": code,
        "unmet_obligations": unmet_obligations,
        "evidence_refs": [],
        "next_action": next_action,
    }


def _emit(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True))


def _run(arguments: argparse.Namespace) -> tuple[str | None, Any]:
    if arguments.verb == "ingest":
        event = _read_json_object(arguments.event)
        run_id = event.get("run_id") if isinstance(event.get("run_id"), str) else None
        arguments.run_id = run_id
        result = ResearchRunCoordinator(RunLedger(arguments.workspace)).ingest_host_event(event)
        return run_id, result.to_dict()

    coordinator = ResearchRunCoordinator(RunLedger(arguments.workspace))
    if arguments.verb == "recover":
        return arguments.run_id, coordinator.recover(arguments.run_id)
    if arguments.verb == "why-not-complete":
        return arguments.run_id, coordinator.why_not_complete(arguments.run_id)
    if arguments.verb == "complete":
        result = coordinator.complete(
            arguments.run_id,
            actor=arguments.actor,
            expected_revision=arguments.expected_revision,
        )
        return arguments.run_id, result.to_dict()
    raise CliInputError("unsupported_current_verb")


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        resolved_run_id, result = _run(arguments)
    except (CliInputError, CoordinatorError, RuntimeStoreError, OSError) as error:
        exit_code, payload = _failure(error, getattr(arguments, "run_id", None))
        _emit(payload)
        return exit_code
    _emit(_success(resolved_run_id, result))
    return 0
