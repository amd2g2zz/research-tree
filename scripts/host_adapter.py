"""Safe file-protocol adapter for host-managed research subagents.

The host (Codex, Claude Code, or another agent runtime) owns subagent creation.
This adapter only writes a task batch and accepts validated structured commands;
it never executes a command supplied by a worker.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from research_orchestrator import ResearchOrchestrator
from research_repository import atomic_write_json, workspace
from research_service import ResearchService


_HOSTS = {"codex", "claude-code"}
_HOST_NAME = re.compile(r"[a-z][a-z-]{0,31}")


def _host(value: str) -> str:
    if value not in _HOSTS or not _HOST_NAME.fullmatch(value):
        raise ValueError(f"unsupported host: {value}")
    return value


def _read_json(value: str, expected: type | tuple[type, ...]):
    if value.startswith("@"):
        candidate = (workspace() / value[1:]).resolve()
        try:
            candidate.relative_to(workspace().resolve())
        except ValueError as exc:
            raise ValueError("command file must be inside the research workspace") from exc
        value = candidate.read_text(encoding="utf-8")
    parsed = json.loads(value)
    if not isinstance(parsed, expected):
        names = (expected,) if isinstance(expected, type) else expected
        raise ValueError(f"expected JSON {' or '.join(item.__name__ for item in names)}")
    return parsed


def _read_commands(value: str) -> list[dict]:
    """Read one worker command or a bounded batch without changing its shape."""

    parsed = _read_json(value, (dict, list))
    if isinstance(parsed, dict):
        return [parsed]
    if not all(isinstance(item, dict) for item in parsed):
        raise ValueError("commands must be a JSON object or a list of objects")
    return parsed


def _read_text(value: str) -> str:
    if value.startswith("@@"):
        return value[1:]
    if not value.startswith("@"):
        return value
    candidate = (workspace() / value[1:]).resolve()
    try:
        candidate.relative_to(workspace().resolve())
    except ValueError as exc:
        raise ValueError("content file must be inside the research workspace") from exc
    if not candidate.is_file():
        raise FileNotFoundError(f"content file not found: {candidate}")
    return candidate.read_text(encoding="utf-8")


def dispatch(host: str, snapshot: str | None = None, question: str | None = None,
             discover: bool = False, refresh_discovery: bool = False) -> dict:
    host = _host(host)
    if refresh_discovery and not discover:
        raise ValueError("refresh_discovery requires discover")
    if snapshot and discover:
        raise ValueError("frozen snapshot dispatch cannot run live discovery")
    if question and not snapshot:
        raise ValueError("Q&A dispatch requires a frozen snapshot")
    orchestrator = ResearchOrchestrator()
    discovery = orchestrator.discover(refresh=refresh_discovery) if discover else None
    batch = orchestrator.plan(snapshot=snapshot, question=question)
    root = workspace() / "research" / "orchestrator" / host
    root.mkdir(parents=True, exist_ok=True)
    output = root / "worker_batch.json"
    payload = {"schema": 1, "host": host, "batch": batch,
               "submission": {"command": "submit", "requires": "structured command list only"}}
    if discovery is not None:
        payload["discovery"] = discovery
    atomic_write_json(output, payload)
    result = {"host": host, "task_count": len(batch["tasks"]),
              "path": str(output.relative_to(workspace())).replace("\\", "/")}
    if discovery is not None:
        result["discovery"] = discovery
    return result


def submit(host: str, commands: list[dict]) -> dict:
    _host(host)
    if len(commands) > 64:
        raise ValueError("worker submission exceeds 64 commands")
    result = ResearchService().execute_batch(commands)
    return {"host": host, "accepted": len(result), "results": result}


def acquire_source(host: str, url: str, title: str | None = None) -> dict:
    """Save one AnySearch-extracted page without granting a graph mutation."""

    _host(host)
    import source_acquirer

    return {"host": host, "result": source_acquirer.acquire_anysearch(url, title)}


def submit_chapter(host: str, snapshot: str, chapter: str, content: str) -> dict:
    """Accept one writer artifact through the frozen-delivery boundary."""
    _host(host)
    import project

    result = project.submit_chapter(snapshot, chapter, content)
    return {"host": host, "result": result}


def compile_report(host: str, snapshot: str, content: str) -> dict:
    """Accept the editor artifact through the frozen-delivery boundary."""
    _host(host)
    import project

    result = project.compile_report(snapshot, content)
    return {"host": host, "result": result}


def stage_report(host: str, snapshot: str, content: str) -> dict:
    """Accept an editor-owned report draft at a fixed review boundary."""

    _host(host)
    import project

    result = project.stage_report(snapshot, content)
    return {"host": host, "result": result}


def submit_report_review(host: str, snapshot: str, content: str, assessment: dict) -> dict:
    """Accept a reviewer-owned, hash-bound decision report assessment."""

    _host(host)
    import project

    result = project.submit_report_review(snapshot, content, assessment)
    return {"host": host, "result": result}


def answer(host: str, snapshot: str, question: str, top: int = 8) -> dict:
    """Expose frozen retrieval for a dedicated host-managed Q&A worker."""
    _host(host)
    import qa

    result = qa.ask(snapshot, question, top)
    return {"host": host, "result": result}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="host-adapter", description="bridge host subagents to research-tree safely")
    sub = parser.add_subparsers(dest="command", required=True)
    dispatch_cmd = sub.add_parser("dispatch"); dispatch_cmd.add_argument("--host", required=True, choices=sorted(_HOSTS)); dispatch_cmd.add_argument("--snapshot"); dispatch_cmd.add_argument("--question"); dispatch_cmd.add_argument("--discover", action="store_true"); dispatch_cmd.add_argument("--refresh-discovery", action="store_true")
    submit_cmd = sub.add_parser("submit"); submit_cmd.add_argument("--host", required=True, choices=sorted(_HOSTS)); submit_cmd.add_argument("--commands", required=True)
    acquire_cmd = sub.add_parser("acquire-source"); acquire_cmd.add_argument("--host", required=True, choices=sorted(_HOSTS)); acquire_cmd.add_argument("--url", required=True); acquire_cmd.add_argument("--title")
    chapter_cmd = sub.add_parser("submit-chapter"); chapter_cmd.add_argument("--host", required=True, choices=sorted(_HOSTS)); chapter_cmd.add_argument("--snapshot", required=True); chapter_cmd.add_argument("--chapter", required=True); chapter_cmd.add_argument("--content", required=True)
    draft_cmd = sub.add_parser("stage-report"); draft_cmd.add_argument("--host", required=True, choices=sorted(_HOSTS)); draft_cmd.add_argument("--snapshot", required=True); draft_cmd.add_argument("--content", required=True)
    review_cmd = sub.add_parser("submit-report-review"); review_cmd.add_argument("--host", required=True, choices=sorted(_HOSTS)); review_cmd.add_argument("--snapshot", required=True); review_cmd.add_argument("--content", required=True); review_cmd.add_argument("--assessment", required=True)
    report_cmd = sub.add_parser("compile-report"); report_cmd.add_argument("--host", required=True, choices=sorted(_HOSTS)); report_cmd.add_argument("--snapshot", required=True); report_cmd.add_argument("--content", required=True)
    answer_cmd = sub.add_parser("answer"); answer_cmd.add_argument("--host", required=True, choices=sorted(_HOSTS)); answer_cmd.add_argument("--snapshot", required=True); answer_cmd.add_argument("--question", required=True); answer_cmd.add_argument("--top", type=int, default=8)
    args = parser.parse_args(argv)
    if args.command == "dispatch":
        result = dispatch(args.host, args.snapshot, args.question, args.discover, args.refresh_discovery)
    elif args.command == "submit":
        result = submit(args.host, _read_commands(args.commands))
    elif args.command == "acquire-source":
        result = acquire_source(args.host, args.url, args.title)
    elif args.command == "submit-chapter":
        result = submit_chapter(args.host, args.snapshot, args.chapter, _read_text(args.content))
    elif args.command == "stage-report":
        result = stage_report(args.host, args.snapshot, _read_text(args.content))
    elif args.command == "submit-report-review":
        result = submit_report_review(args.host, args.snapshot, _read_text(args.content), _read_json(args.assessment, dict))
    elif args.command == "compile-report":
        result = compile_report(args.host, args.snapshot, _read_text(args.content))
    else:
        result = answer(args.host, args.snapshot, args.question, args.top)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
