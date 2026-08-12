"""Write and summarize sanitized, opt-in research workflow traces."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import time
from typing import Any, Iterable, Mapping, Sequence

from .coordinator import (
    HOST_EVENT_KIND,
    LIFECYCLE_EVENT_KIND,
    RESEARCH_RUN_STATE_KIND,
    ResearchRunCoordinator,
)
from .domain import ArtifactRef, ArtifactRevision, canonical_json_bytes, thaw_json, validate_identifier
from .host_events import normalize_host_path
from .run_ledger import RunLedger


TRACE_DIRECTORY = Path(".research-tree-debug") / "events"
HOSTS = frozenset({"codex", "claude", "hermes"})
PHASES = frozenset(
    {
        "lifecycle_observed",
        "intake",
        "reconnaissance",
        "alignment_turn",
        "alignment_checkpoint",
        "alignment_blocked",
        "research_started",
        "implementation_started",
        "worker_blocked",
        "completed",
        "aborted",
    }
)
STATUSES = frozenset({"started", "completed", "blocked", "skipped", "failed"})
IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
CODE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}\Z")
CAUSAL_TRACE_SCHEMA_VERSION = 1
_SENSITIVE_KEY_PARTS = (
    "chain_of_thought",
    "credential",
    "password",
    "prompt",
    "raw_error",
    "response",
    "secret",
    "token",
    "tool_input",
)
_HOST_OBSERVATION_FIELDS = frozenset({"event_id", "attempt_id", "status", "sequence", "category", "code", "log_ref"})
_HOST_STATUSES = frozenset({"active", "running", "complete", "completed", "failed", "unknown"})
_SAFE_HOST_DIAGNOSTIC_FIELDS = frozenset(
    {"category", "code", "retry_count", "log_ref", "reason", "retry_of", "verdict", "outcome", "evidence_refs"}
)
_OBLIGATION_KINDS = {
    "p0_closure_tokens": frozenset({"slot-closure-assessment"}),
    "insights_non_blocking": frozenset({"insight-digest"}),
    "readiness_ref": frozenset({"readiness-record"}),
    "evaluation_ref": frozenset({"blueprint-evaluation"}),
    "technical_delivery_ref": frozenset({"technical-research-package"}),
    "human_delivery_ref": frozenset({"human-research-report"}),
    "acceptance_ref": frozenset({"delivery-acceptance"}),
}


class DebugTraceError(ValueError):
    """Raised when a debug trace would be ambiguous or unsafe to persist."""


class CausalTraceError(DebugTraceError):
    """Raised when canonical lineage cannot be safely explained or replayed."""


class CausalTraceService:
    """Project deterministic, sanitized explanations from the canonical ledger."""

    def __init__(self, ledger: RunLedger) -> None:
        if not isinstance(ledger, RunLedger):
            raise CausalTraceError("causal tracing requires a RunLedger")
        self.ledger = ledger

    def replay(self, run_id: str) -> dict[str, Any]:
        validate_identifier(run_id, "run_id")
        snapshot = self.ledger.load_run(run_id)
        states = [item for item in snapshot.artifacts if item.kind == RESEARCH_RUN_STATE_KIND]
        if not states:
            raise CausalTraceError("run is not initialized")
        by_sequence: dict[int, list[ArtifactRevision]] = {}
        for state in states:
            sequence = state.payload.get("lifecycle_revision")
            if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
                raise CausalTraceError("invalid lifecycle revision")
            by_sequence.setdefault(sequence, []).append(state)
        if any(len(items) != 1 for items in by_sequence.values()):
            raise CausalTraceError("forked lifecycle revision")
        ordered_sequences = sorted(by_sequence)
        if ordered_sequences != list(range(len(ordered_sequences))):
            raise CausalTraceError("missing lifecycle revision")
        ordered = [by_sequence[index][0] for index in ordered_sequences]
        artifacts = {ArtifactRef(item.round_id, item.id, item.revision): item for item in snapshot.artifacts}
        transitions: list[dict[str, Any]] = []
        for sequence, state in enumerate(ordered):
            self._verify_state_digest(state)
            if sequence == 0:
                continue
            previous = ordered[sequence - 1]
            previous_ref = ArtifactRef(previous.round_id, previous.id, previous.revision)
            declared_previous = state.payload.get("previous_state_ref")
            if declared_previous != previous_ref.to_dict() or previous_ref not in state.parent_refs:
                raise CausalTraceError("missing_cause: previous state lineage")
            causes = [
                artifacts[reference]
                for reference in state.parent_refs
                if reference in artifacts and artifacts[reference].kind == LIFECYCLE_EVENT_KIND
            ]
            if len(causes) != 1:
                raise CausalTraceError("missing_cause: lifecycle event")
            transitions.append(self._trace_record(run_id, sequence, previous, state, causes[0]))
        terminal = ordered[-1]
        return {
            "schema_version": CAUSAL_TRACE_SCHEMA_VERSION,
            "run_id": run_id,
            "verified": True,
            "terminal_state": terminal.payload["state"],
            "state_digest": terminal.payload["state_digest"],
            "state_count": len(ordered),
            "transitions": transitions,
            "unresolved_references": [],
        }

    def explain_run(self, run_id: str) -> dict[str, Any]:
        replay = self.replay(run_id)
        why = self.why_not_complete(run_id)
        return {
            **replay,
            "state": why["state"],
            "unmet_obligations": why["unmet_obligations"],
            "next_actions": why["next_actions"],
            "evidence_gaps": why["evidence_gaps"],
            "host_events": self._host_traces(run_id),
            "completion_authority": "coordinator_only",
        }

    def why_not_complete(self, run_id: str) -> dict[str, Any]:
        result = ResearchRunCoordinator(self.ledger).why_not_complete(run_id)
        artifacts = self.ledger.load_run(run_id).artifacts
        gaps = []
        for obligation in result["unmet_obligations"]:
            kinds = _OBLIGATION_KINDS.get(obligation, frozenset())
            refs = sorted(
                (
                    ArtifactRef(item.round_id, item.id, item.revision).to_dict()
                    for item in artifacts
                    if item.kind in kinds
                ),
                key=lambda item: (item["artifact_id"], item["revision"]),
            )
            gaps.append({"obligation": obligation, "evidence_refs": refs})
        return {**result, "evidence_gaps": gaps, "completion_authority": "coordinator_only"}

    def why_action(self, run_id: str, action_id: str) -> dict[str, Any]:
        validate_identifier(run_id, "run_id")
        validate_identifier(action_id, "action_id")
        candidates = [
            item
            for item in self.ledger.load_run(run_id).artifacts
            if item.id == action_id or item.payload.get("action_id") == action_id
        ]
        if not candidates:
            raise CausalTraceError("unresolved action")
        action = max(candidates, key=lambda item: (item.revision, item.id))
        payload = thaw_json(action.payload)
        return {
            "schema_version": CAUSAL_TRACE_SCHEMA_VERSION,
            "run_id": run_id,
            "action_id": action_id,
            "artifact_ref": ArtifactRef(action.round_id, action.id, action.revision).to_dict(),
            "kind": action.kind,
            "inputs": _safe_value(payload.get("inputs", {}), "action inputs"),
            "score_components": dict(sorted(_score_components(payload.get("score_components", {})).items())),
            "outcome": _safe_value(payload.get("outcome", payload.get("disposition", "unknown")), "outcome"),
            "reason": _safe_value(payload.get("reason", "unspecified"), "reason"),
            "causal_refs": [reference.to_dict() for reference in action.parent_refs],
            "redaction_class": "allowlisted",
        }

    def reconcile_host(self, run_id: str, observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        validate_identifier(run_id, "run_id")
        if isinstance(observations, (str, bytes)) or len(observations) > 500:
            raise CausalTraceError("host observations must be a bounded sequence")
        normalized = [_host_observation(value) for value in observations]
        counts = Counter(item["event_id"] for item in normalized)
        duplicates = sorted(event_id for event_id, count in counts.items() if count > 1)
        snapshot = self.ledger.load_run(run_id)
        canonical = {
            str(item.payload.get("event_id", item.id)): item
            for item in snapshot.artifacts
            if item.kind == HOST_EVENT_KIND
        }
        latest_sequence: dict[str, int] = {}
        for item in canonical.values():
            attempt_id = str(item.payload.get("attempt_id", ""))
            latest_sequence[attempt_id] = max(latest_sequence.get(attempt_id, 0), int(item.payload.get("sequence", 0)))
        results = []
        seen: set[str] = set()
        for item in normalized:
            event_id = item["event_id"]
            if event_id in seen:
                continue
            seen.add(event_id)
            recorded = canonical.get(event_id)
            if item["status"] == "unknown":
                classification = "uncertain"
            elif recorded is None:
                classification = "missing"
            elif recorded.payload.get("attempt_id") != item["attempt_id"]:
                classification = "divergent"
            elif item.get("sequence", 0) < latest_sequence.get(item["attempt_id"], 0):
                classification = "stale"
            else:
                classification = "matched"
            results.append({**item, "classification": classification, "authoritative": False})
        current = ResearchRunCoordinator(self.ledger).state(run_id)
        return {
            "schema_version": CAUSAL_TRACE_SCHEMA_VERSION,
            "run_id": run_id,
            "completion_authority": "coordinator_only",
            "canonical_state": current.payload["state"],
            "state_digest": current.payload["state_digest"],
            "duplicate_event_ids": duplicates,
            "observations": results,
        }

    @staticmethod
    def _verify_state_digest(state: ArtifactRevision) -> None:
        payload = thaw_json(state.payload)
        recorded = payload.pop("state_digest", None)
        if payload.get("lifecycle_revision") == 0:
            payload.pop("idempotency_key", None)
            payload.pop("reason", None)
        calculated = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        if recorded != calculated:
            raise CausalTraceError("digest_mismatch: research-run-state")

    @staticmethod
    def _trace_record(
        run_id: str,
        sequence: int,
        previous: ArtifactRevision,
        state: ArtifactRevision,
        event: ArtifactRevision,
    ) -> dict[str, Any]:
        body = thaw_json(event.payload)
        if body.get("event_id") != event.id:
            raise CausalTraceError("missing_cause: event identity")
        if body.get("from") != previous.payload.get("state") or body.get("to") != state.payload.get("state"):
            raise CausalTraceError("missing_cause: state edge")
        raw_inputs = body.get("payload", {})
        if isinstance(raw_inputs, Mapping) and "confirmation" in raw_inputs:
            raw_inputs = {key: value for key, value in raw_inputs.items() if key != "confirmation"}
            raw_inputs["confirmation_digest"] = hashlib.sha256(
                str(body.get("payload", {}).get("confirmation", "")).encode("utf-8")
            ).hexdigest()
        inputs = _safe_value(raw_inputs, "transition inputs")
        actor = _safe_code(body.get("actor", "coordinator"), "actor")
        action = _safe_code(body.get("event", "unknown"), "action")
        host = _safe_code(inputs.get("host", "coordinator"), "host") if isinstance(inputs, Mapping) else "coordinator"
        trace_id = (
            "trace-"
            + hashlib.sha256(
                canonical_json_bytes({"event_hash": event.content_hash, "state_hash": state.content_hash})
            ).hexdigest()[:24]
        )
        return {
            "schema_version": CAUSAL_TRACE_SCHEMA_VERSION,
            "trace_id": trace_id,
            "run_id": run_id,
            "event_id": event.id,
            "causation_id": event.id,
            "correlation_id": run_id,
            "sequence": sequence,
            "emitted_at": event.created_at,
            "actor": actor,
            "host": host,
            "round_id": run_id,
            "decision_slot_id": inputs.get("decision_slot_id") if isinstance(inputs, Mapping) else None,
            "attempt_id": inputs.get("attempt_id") if isinstance(inputs, Mapping) else None,
            "prior_digest": previous.payload["state_digest"],
            "next_digest": state.payload["state_digest"],
            "action": action,
            "inputs": inputs,
            "score_components": _score_components(
                inputs.get("score_components", {}) if isinstance(inputs, Mapping) else {}
            ),
            "outcome": body.get("to"),
            "reason": inputs.get("reason", "transition_accepted")
            if isinstance(inputs, Mapping)
            else "transition_accepted",
            "redaction_class": "allowlisted",
            "retention_class": "canonical-lineage",
            "artifact_refs": [
                ArtifactRef(previous.round_id, previous.id, previous.revision).to_dict(),
                ArtifactRef(event.round_id, event.id, event.revision).to_dict(),
                ArtifactRef(state.round_id, state.id, state.revision).to_dict(),
            ],
        }

    def _host_traces(self, run_id: str) -> list[dict[str, Any]]:
        records = []
        for item in self.ledger.load_run(run_id).artifacts:
            if item.kind != HOST_EVENT_KIND:
                continue
            body = thaw_json(item.payload)
            payload = body.get("payload", {})
            if not isinstance(payload, Mapping):
                raise CausalTraceError("host event diagnostic payload is invalid")
            diagnostic = {}
            for key in sorted(set(payload) & _SAFE_HOST_DIAGNOSTIC_FIELDS):
                value = payload[key]
                diagnostic[key] = normalize_host_path(str(value)) if key == "log_ref" else _safe_value(value, key)
            records.append(
                {
                    "event_id": _safe_code(body.get("event_id", item.id), "event_id"),
                    "kind": _safe_code(body.get("kind", "observation"), "kind"),
                    "action_id": _optional_safe_code(body.get("action_id"), "action_id"),
                    "attempt_id": _safe_code(body.get("attempt_id", "unknown-attempt"), "attempt_id"),
                    "sequence": body.get("sequence", 0),
                    "actor": _safe_code(body.get("actor", "host"), "actor"),
                    "diagnostic": diagnostic,
                    "authoritative": False,
                }
            )
        return sorted(records, key=lambda value: (value["attempt_id"], value["sequence"], value["event_id"]))


def _safe_value(value: Any, label: str, *, depth: int = 0) -> Any:
    if depth > 5:
        raise CausalTraceError(f"{label} is too deeply nested")
    if isinstance(value, Mapping):
        if len(value) > 32:
            raise CausalTraceError(f"{label} has too many fields")
        result = {}
        for key, child in sorted(value.items(), key=lambda item: str(item[0])):
            name = str(key)
            if any(part in name.lower() for part in _SENSITIVE_KEY_PARTS):
                raise CausalTraceError(f"sensitive diagnostic field: {name}")
            if not CODE_RE.fullmatch(name):
                raise CausalTraceError(f"{label} contains an invalid field")
            result[name] = _safe_value(child, label, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        if len(value) > 64:
            raise CausalTraceError(f"{label} has too many values")
        return [_safe_value(item, label, depth=depth + 1) for item in value]
    if isinstance(value, str):
        return _safe_code(value, label)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    raise CausalTraceError(f"{label} contains an unsupported value")


def _safe_code(value: Any, label: str) -> str:
    text = str(value)
    if not CODE_RE.fullmatch(text):
        raise CausalTraceError(f"{label} must be a bounded diagnostic identifier")
    return text


def _optional_safe_code(value: Any, label: str) -> str | None:
    return None if value is None else _safe_code(value, label)


def _score_components(value: Any) -> dict[str, float]:
    if value is None:
        return {}
    if not isinstance(value, Mapping) or len(value) > 32:
        raise CausalTraceError("score components must be a bounded object")
    result: dict[str, float] = {}
    for key, component in value.items():
        name = str(key)
        if not CODE_RE.fullmatch(name) or isinstance(component, bool) or not isinstance(component, (int, float)):
            raise CausalTraceError("score components must contain named numeric values")
        result[name] = float(component)
    return result


def _host_observation(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CausalTraceError("host observation must be an object")
    sensitive = sorted(str(key) for key in value if any(part in str(key).lower() for part in _SENSITIVE_KEY_PARTS))
    if sensitive:
        raise CausalTraceError(f"sensitive diagnostic field: {sensitive[0]}")
    unknown = set(value) - _HOST_OBSERVATION_FIELDS
    if unknown:
        raise CausalTraceError(f"unsupported host observation field: {sorted(unknown)[0]}")
    event_id = str(value.get("event_id", ""))
    attempt_id = str(value.get("attempt_id", ""))
    status = str(value.get("status", ""))
    try:
        validate_identifier(event_id, "event_id")
        validate_identifier(attempt_id, "attempt_id")
    except (TypeError, ValueError) as error:
        raise CausalTraceError("host observation identifiers are invalid") from error
    if status not in _HOST_STATUSES:
        raise CausalTraceError("host observation status is invalid")
    result: dict[str, Any] = {"event_id": event_id, "attempt_id": attempt_id, "status": status}
    if "sequence" in value:
        sequence = value["sequence"]
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise CausalTraceError("host observation sequence is invalid")
        result["sequence"] = sequence
    for field in ("category", "code"):
        if field in value:
            item = str(value[field])
            if not CODE_RE.fullmatch(item):
                raise CausalTraceError(f"host observation {field} is invalid")
            result[field] = item
    if "log_ref" in value:
        result["log_ref"] = normalize_host_path(str(value["log_ref"]))
    return result


def find_project_root(start: Path) -> Path:
    """Find the checkout that owns an opt-in debug trace."""
    current = start.resolve(strict=False)
    for candidate in (current, *current.parents):
        if (
            (candidate / "pyproject.toml").is_file()
            and (candidate / "packages").is_dir()
            and (candidate / "skill-src").is_dir()
        ):
            return candidate
    raise DebugTraceError("debug tracing must run inside a Research Tree checkout")


def _inside(root: Path, candidate: Path) -> Path:
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise DebugTraceError("debug trace path must remain inside the project") from exc
    return resolved


def _project_root(project_root: Path | None) -> Path:
    root = project_root.resolve(strict=False) if project_root is not None else find_project_root(Path.cwd())
    if not ((root / "pyproject.toml").is_file() and (root / "packages").is_dir() and (root / "skill-src").is_dir()):
        raise DebugTraceError("project root is not a Research Tree checkout")
    return root


def _identifier(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    if not IDENTIFIER_RE.fullmatch(value):
        raise DebugTraceError(f"{label} must be a bounded identifier")
    return value


def _codes(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if not CODE_RE.fullmatch(value):
            raise DebugTraceError("debug code must be a bounded identifier")
        result.append(value)
    if len(result) > 16:
        raise DebugTraceError("a debug trace accepts at most 16 codes")
    return result


def _write_record(root: Path, record: dict[str, Any]) -> Path:
    destination = _inside(
        root,
        root / TRACE_DIRECTORY,
    )
    destination.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(record, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    for _ in range(3):
        prefix = f"{time.time_ns():020d}"
        path = _inside(
            root,
            destination / f"{prefix}-{secrets.token_hex(8)}.json",
        )
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
        return path
    raise DebugTraceError("could not allocate a debug trace file")


def emit_trace(
    *,
    host: str,
    phase: str,
    status: str,
    codes: Iterable[str] = (),
    run_id: str | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Persist one sanitized workflow transition and return its relative path."""
    if host not in HOSTS:
        raise DebugTraceError(f"unsupported debug host: {host}")
    if phase not in PHASES:
        raise DebugTraceError(f"unsupported debug phase: {phase}")
    if status not in STATUSES:
        raise DebugTraceError(f"unsupported debug status: {status}")

    root = _project_root(project_root)
    record: dict[str, Any] = {
        "schema": 1,
        "source": "research-tree-debug",
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "host": host,
        "phase": phase,
        "status": status,
        "codes": _codes(codes),
    }
    normalized_run_id = _identifier(run_id, "run id")
    if normalized_run_id is not None:
        record["run_id"] = normalized_run_id
    path = _write_record(root, record)
    return {"status": "recorded", "path": path.relative_to(root).as_posix()}


def summarize_traces(*, project_root: Path | None = None, limit: int = 25) -> dict[str, Any]:
    """Return a bounded, chronological summary of sanitized trace files."""
    if limit < 1 or limit > 200:
        raise DebugTraceError("limit must be between 1 and 200")
    root = _project_root(project_root)
    trace_dir = _inside(root, root / TRACE_DIRECTORY)
    records: list[dict[str, Any]] = []
    if trace_dir.is_dir():
        for path in sorted(trace_dir.glob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                records.append(value)
    phases = Counter(item["phase"] for item in records if isinstance(item.get("phase"), str))
    statuses = Counter(item["status"] for item in records if isinstance(item.get("status"), str))
    return {
        "schema": 1,
        "trace_directory": trace_dir.relative_to(root).as_posix(),
        "event_count": len(records),
        "by_phase": dict(sorted(phases.items())),
        "by_status": dict(sorted(statuses.items())),
        "recent": records[-limit:],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-tree-debug",
        description="Emit or summarize sanitized Research Tree workflow traces.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    emit = commands.add_parser("emit", help="write one sanitized phase event")
    emit.add_argument("--host", choices=tuple(sorted(HOSTS)), required=True)
    emit.add_argument("--phase", choices=tuple(sorted(PHASES)), required=True)
    emit.add_argument("--status", choices=tuple(sorted(STATUSES)), required=True)
    emit.add_argument("--code", action="append", default=[])
    emit.add_argument("--run-id")
    emit.add_argument("--project-root", type=Path)

    summary = commands.add_parser("summary", help="summarize sanitized phase events")
    summary.add_argument("--project-root", type=Path)
    summary.add_argument("--limit", type=int, default=25)

    for name, help_text in (
        ("explain-run", "explain canonical run state and blockers"),
        ("why-not-complete", "list every canonical completion blocker"),
        ("replay", "verify and replay canonical lifecycle state"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--run-id", required=True)
        command.add_argument("--project-root", type=Path)
    why_action = commands.add_parser("why-action", help="explain one canonical research action")
    why_action.add_argument("--run-id", required=True)
    why_action.add_argument("--action-id", required=True)
    why_action.add_argument("--project-root", type=Path)
    reconcile = commands.add_parser("reconcile-host", help="compare host observations with canonical events")
    reconcile.add_argument("--run-id", required=True)
    reconcile.add_argument("--observations", type=Path, required=True)
    reconcile.add_argument("--project-root", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "emit":
            result = emit_trace(
                host=arguments.host,
                phase=arguments.phase,
                status=arguments.status,
                codes=arguments.code,
                run_id=arguments.run_id,
                project_root=arguments.project_root,
            )
        elif arguments.command == "summary":
            result = summarize_traces(project_root=arguments.project_root, limit=arguments.limit)
        else:
            service = CausalTraceService(RunLedger(arguments.project_root or Path.cwd()))
            if arguments.command == "explain-run":
                result = service.explain_run(arguments.run_id)
            elif arguments.command == "why-action":
                result = service.why_action(arguments.run_id, arguments.action_id)
            elif arguments.command == "why-not-complete":
                result = service.why_not_complete(arguments.run_id)
            elif arguments.command == "replay":
                result = service.replay(arguments.run_id)
            else:
                observations = json.loads(arguments.observations.read_text(encoding="utf-8"))
                if not isinstance(observations, list):
                    raise CausalTraceError("host observations JSON must be an array")
                result = service.reconcile_host(arguments.run_id, observations)
    except DebugTraceError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
