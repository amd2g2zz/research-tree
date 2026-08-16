#!/usr/bin/env python3
"""Validate Claude Code Agent, Workflow, and hybrid runtime receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

STATES = frozenset({"available", "unavailable", "partial", "denied", "failed", "unknown"})
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")


class ClaudeOrchestrationError(ValueError):
    """Raised when Claude orchestration evidence is insufficient."""


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _map(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ClaudeOrchestrationError(f"{label} must be an object")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ClaudeOrchestrationError(f"{label} must be a non-empty string")
    return value


def _id(value: Any, label: str) -> str:
    text = _text(value, label)
    if not IDENTIFIER.fullmatch(text) or text.startswith(("synthetic-", "projected-")):
        raise ClaudeOrchestrationError(f"{label} must be a non-synthetic runtime identifier")
    return text


def _sha(value: Any, label: str) -> str:
    text = _text(value, label)
    if not DIGEST.fullmatch(text):
        raise ClaudeOrchestrationError(f"{label} must be a sha256 digest")
    return text


def _metadata(value: Mapping[str, Any]) -> dict[str, str]:
    return {
        "project_id": _id(value.get("project_id"), "project_id"),
        "run_id": _id(value.get("run_id"), "run_id"),
        "claude_code_version": _text(value.get("claude_code_version"), "claude_code_version"),
        "sdk_version": _text(value.get("sdk_version"), "sdk_version"),
        "model": _text(value.get("model"), "model"),
        "package_revision": _text(value.get("package_revision"), "package_revision"),
        "environment_digest": _sha(value.get("environment_digest"), "environment_digest"),
    }


def _capabilities(value: Any) -> dict[str, str]:
    raw = _map(value, "capabilities")
    if set(raw) != {"agent", "workflow", "hooks"}:
        raise ClaudeOrchestrationError("capabilities must contain exactly agent, workflow, and hooks")
    result = {key: str(raw[key]) for key in raw}
    if invalid := [key for key, state in result.items() if state not in STATES]:
        raise ClaudeOrchestrationError(f"invalid capability state for {invalid[0]}")
    return result


def select_mode(request: Mapping[str, Any]) -> dict[str, Any]:
    """Select distinct Agent, Workflow, hybrid, or infeasible execution."""
    request = _map(request, "selection request")
    requested = str(request.get("requested_mode", "auto"))
    if requested not in {"auto", "agent", "workflow", "hybrid"}:
        raise ClaudeOrchestrationError("requested_mode must be auto, agent, workflow, or hybrid")
    capabilities = _capabilities(request.get("capabilities"))
    agent = capabilities["agent"] == "available"
    workflow = capabilities["workflow"] == "available"
    availability = {"agent": agent, "workflow": workflow, "hybrid": agent and workflow}
    mode = (
        ("hybrid" if agent and workflow else "agent" if agent else "workflow" if workflow else "infeasible")
        if requested == "auto"
        else (requested if availability[requested] else "infeasible")
    )
    result = {
        "schema_version": 1,
        **_metadata(request),
        "requested_mode": requested,
        "mode": mode,
        "selection_evidence": {"capabilities": capabilities},
        "authoritative": False,
        "completion_authority": "coordinator_only",
    }
    return {**result, "semantic_digest": _digest(result)}


def _agents(receipt: Mapping[str, Any], hybrid: bool) -> list[dict[str, Any]]:
    raw_agents = receipt.get("agents")
    if not isinstance(raw_agents, list) or len(raw_agents) < 2:
        raise ClaudeOrchestrationError("Agent execution requires at least two independent child identities")
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in raw_agents:
        raw = _map(value, "agent receipt")
        item: dict[str, Any] = {
            key: _id(raw.get(key), f"agent {key}") for key in ("agent_id", "runtime_id", "action_id", "attempt_id")
        }
        item["status"] = _text(raw.get("status"), "agent status")
        if item["status"] not in {"completed", "failed", "cancelled", "unknown"}:
            raise ClaudeOrchestrationError("agent status is unsupported")
        if {item["agent_id"], item["runtime_id"]} & seen:
            raise ClaudeOrchestrationError("child identities must be distinct")
        seen.update((item["agent_id"], item["runtime_id"]))
        if hybrid:
            item["parent_phase_id"] = _id(raw.get("parent_phase_id"), "agent parent_phase_id")
            if raw.get("delegation_depth") != 1:
                raise ClaudeOrchestrationError("hybrid receipt delegation depth must be exactly one")
        output.append(item)
    return output


def _workflow(receipt: Mapping[str, Any]) -> tuple[dict[str, str], list[dict[str, str]], list[str]]:
    raw = _map(receipt.get("workflow"), "workflow receipt")
    binding = {
        "workflow_id": _id(raw.get("workflow_id"), "workflow_id"),
        "runtime_id": _id(raw.get("runtime_id"), "workflow runtime_id"),
        "script_digest": _sha(raw.get("script_digest"), "workflow script_digest"),
    }
    values = raw.get("phases")
    if not isinstance(values, list) or len(values) < 2:
        raise ClaudeOrchestrationError("Workflow execution requires at least two phase identities")
    phases: list[dict[str, str]] = []
    phase_ids: set[str] = set()
    for value in values:
        phase = _map(value, "workflow phase")
        phase_id = _id(phase.get("phase_id"), "phase_id")
        if phase_id in phase_ids:
            raise ClaudeOrchestrationError("workflow phase identities must be distinct")
        phase_ids.add(phase_id)
        phases.append(
            {
                "phase_id": phase_id,
                "runtime_id": _id(phase.get("runtime_id"), "phase runtime_id"),
                "status": _text(phase.get("status"), "phase status"),
            }
        )
    replan = raw.get("replan")
    quarantined: list[str] = []
    if replan is not None:
        plan = _map(replan, "workflow replan")
        _id(plan.get("reason_event_id"), "replan reason_event_id")
        values = plan.get("superseded_phase_ids")
        if not isinstance(values, list) or not values:
            raise ClaudeOrchestrationError("workflow replan requires superseded_phase_ids")
        quarantined = [_id(value, "superseded phase_id") for value in values]
        if not set(quarantined) <= phase_ids:
            raise ClaudeOrchestrationError("superseded phase must exist in the workflow receipt")
    return binding, phases, quarantined


def bind_receipt(selected: Mapping[str, Any], receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Bind observed native identities to attempts without completion authority."""
    selected, receipt = _map(selected, "selected mode"), _map(receipt, "runtime receipt")
    if selected.get("semantic_digest") != _digest(
        {key: value for key, value in selected.items() if key != "semantic_digest"}
    ):
        raise ClaudeOrchestrationError("selected mode semantic digest does not match")
    mode = selected.get("mode")
    if mode not in {"agent", "workflow", "hybrid"} or receipt.get("mode") != mode:
        raise ClaudeOrchestrationError("receipt mode does not match a feasible selected mode")
    if receipt.get("schema_version") != 1 or receipt.get("receipt_kind") != "claude_code_runtime_receipt_v1":
        raise ClaudeOrchestrationError("receipt must be a schema-1 Claude Code runtime receipt")
    metadata = _metadata(receipt)
    if any(selected.get(key) != value for key, value in metadata.items()):
        raise ClaudeOrchestrationError("receipt metadata does not match selected mode")
    caps = _capabilities(_map(selected.get("selection_evidence"), "selection evidence").get("capabilities"))
    hook_events = receipt.get("hook_events", [])
    if not isinstance(hook_events, list) or (caps["hooks"] == "available" and not hook_events):
        raise ClaudeOrchestrationError("available hooks require observed hook events")
    hooks = [
        {
            "event_id": _id(_map(event, "hook event").get("event_id"), "hook event_id"),
            "kind": _text(_map(event, "hook event").get("kind"), "hook kind"),
        }
        for event in hook_events
    ]
    workflow_binding: dict[str, str] | None = None
    phases: list[dict[str, str]] = []
    quarantined: list[str] = []
    children: list[dict[str, Any]] = []
    if mode in {"workflow", "hybrid"}:
        workflow_binding, phases, quarantined = _workflow(receipt)
    if mode == "agent":
        children = _agents(receipt, False)
    elif mode == "workflow":
        if receipt.get("agents", []) not in ([], None):
            raise ClaudeOrchestrationError("workflow-only receipt must not fabricate Agent children")
    else:
        children = _agents(receipt, True)
        if not {item["parent_phase_id"] for item in children} <= {item["phase_id"] for item in phases}:
            raise ClaudeOrchestrationError("hybrid child must bind to an observed workflow phase")
    result = {
        "schema_version": 1,
        **metadata,
        "session_id": _id(receipt.get("session_id"), "session_id"),
        "mode": mode,
        "workflow_binding": workflow_binding,
        "phase_bindings": phases,
        "child_attempt_bindings": children,
        "hook_bindings": hooks,
        "quarantined_phase_ids": quarantined,
        "authoritative": False,
        "completion_authority": "coordinator_only",
    }
    return {**result, "semantic_digest": _digest(result)}


def _read(path: Path) -> Mapping[str, Any]:
    try:
        return _map(json.loads(path.read_text(encoding="utf-8")), str(path))
    except (OSError, json.JSONDecodeError) as error:
        raise ClaudeOrchestrationError(f"invalid JSON: {path}") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    select = commands.add_parser("select-mode")
    select.add_argument("--request", type=Path, required=True)
    bind = commands.add_parser("bind-receipt")
    bind.add_argument("--selected", type=Path, required=True)
    bind.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = (
            select_mode(_read(args.request))
            if args.command == "select-mode"
            else bind_receipt(_read(args.selected), _read(args.receipt))
        )
    except ClaudeOrchestrationError as error:
        parser.error(str(error))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
