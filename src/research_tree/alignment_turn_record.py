"""File-persisted alignment turn records with a fail-closed continuity gate.

Issue #497: alignment state must live in a research-tree file, not only in
conversation context (user ruling: 对齐表现要在 research-tree 文件里面体现；
不写文件就无法更新). Every pre-handoff alignment turn appends exactly one
record — mirror (current understanding), gap (the named consequential gap),
delta (what changed on the graph), user_move (the classified user response
class), plus the contract terms and traces of the ``turn_contract`` seam
(ADR-008 canonical loop step 4) — BEFORE the agent's response is considered
valid.

The continuity gate fails closed like checkpoint discipline: a missing,
invalid, or stale record blocks the next alignment turn with a named reason,
and a turn that introduces no persisted delta is a protocol violation (the
self-ask/self-answer guard). Validation is presence-and-schema only, never
content quality (ADR-008).

Artifacts live under the run's existing ``alignment/`` workspace directory
(see ``project_workspace.RUN_DIRECTORIES``):

- ``turn-records.jsonl`` — append-only, one strict-whitelist JSON object per
  line; the file grows by exactly one line per turn.
- ``turn-records.state.json`` — the hook's validation receipt (see
  :func:`refresh_validation`); evidence of refresh, never an authority.

Stdlib-only per ADR-001. Schema errors reuse ``turn_contract``'s exception
types; record/gate errors are this module's own.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .turn_contract import (
    DEFAULT_TRACE_REGISTRY,
    RESPONSE_CLASSES,
    ContractTerms,
    TurnContractError,
    verify_traces,
)

__all__ = [
    "ContinuityGateError",
    "RECORDS_FILENAME",
    "RECEIPT_FILENAME",
    "SCHEMA_VERSION",
    "AlignmentTurnRecord",
    "AlignmentTurnRecordStore",
    "TurnRecordError",
    "refresh_validation",
]

SCHEMA_VERSION = 1
RECORDS_FILENAME = "turn-records.jsonl"
RECEIPT_FILENAME = "turn-records.state.json"
RECORD_KEYS = frozenset(
    {
        "schema",
        "turn_index",
        "recorded_at",
        "mirror",
        "gap",
        "delta",
        "user_move",
        "contract_terms",
        "traces",
    }
)
DELTA_KEYS = frozenset({"summary", "nodes"})

# Mirrors alignment_graph.IDENTIFIER_RE / turn_contract.NODE_ID_RE. Kept local
# so this module stays independent of the sqlite-backed graph module.
NODE_ID_RE_SOURCE = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"


class TurnRecordError(ValueError):
    """A turn record violates the record schema or the turn protocol."""


class ContinuityGateError(TurnRecordError):
    """The next alignment turn is blocked: the persisted record is missing, invalid, or stale."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(f"{reason}: {message}")
        self.reason = reason


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _node_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or re.fullmatch(NODE_ID_RE_SOURCE, value) is None:
        raise TurnRecordError(f"{label} must be an alignment-graph node id: {value!r}")
    return value


@dataclass(frozen=True, slots=True)
class AlignmentTurnRecord:
    """One persisted alignment exchange (canonical loop step 4, issue #497)."""

    turn_index: int
    mirror: str
    gap: str
    delta_summary: str
    delta_nodes: tuple[str, ...]
    user_move: str
    contract_terms: ContractTerms | None
    traces: tuple[dict[str, Any], ...]
    recorded_at: str

    @property
    def delta(self) -> dict[str, Any]:
        return {"summary": self.delta_summary, "nodes": list(self.delta_nodes)}

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": SCHEMA_VERSION,
            "turn_index": self.turn_index,
            "recorded_at": self.recorded_at,
            "mirror": self.mirror,
            "gap": self.gap,
            "delta": self.delta,
            "user_move": self.user_move,
        }
        payload["contract_terms"] = self.contract_terms.to_dict() if self.contract_terms is not None else None
        payload["traces"] = [dict(trace) for trace in self.traces]
        return payload

    @classmethod
    def from_dict(cls, value: Any) -> "AlignmentTurnRecord":
        if not isinstance(value, Mapping):
            raise TurnRecordError("turn record must be a JSON object")
        unknown = set(value) - RECORD_KEYS
        missing = RECORD_KEYS - set(value)
        if unknown or missing:
            raise TurnRecordError(f"turn record field mismatch; missing: {sorted(missing)}, unknown: {sorted(unknown)}")
        if value["schema"] != SCHEMA_VERSION:
            raise TurnRecordError(f"turn record schema must be {SCHEMA_VERSION}")
        turn_index = value["turn_index"]
        if isinstance(turn_index, bool) or not isinstance(turn_index, int) or turn_index < 1:
            raise TurnRecordError(f"turn record turn_index must be a positive integer: {turn_index!r}")
        mirror = _nonempty(value["mirror"], "mirror")
        gap = _nonempty(value["gap"], "gap")
        user_move = _nonempty(value["user_move"], "user_move")
        if user_move not in RESPONSE_CLASSES:
            raise TurnRecordError(
                f"user_move must be one of the turn_contract response classes {RESPONSE_CLASSES}: {user_move!r}"
            )
        recorded_at = _nonempty(value["recorded_at"], "recorded_at")
        delta = _delta(value["delta"])
        terms_value = value["contract_terms"]
        contract_terms = None if terms_value is None else ContractTerms.from_dict(terms_value)
        traces_value = value["traces"]
        if not isinstance(traces_value, list):
            raise TurnRecordError("turn record traces must be a list")
        traces = tuple(_trace_copy(trace, index) for index, trace in enumerate(traces_value))
        # Fail-closed reading: a persisted record must still satisfy the seam
        # registry and, when terms were carried, its own required traces.
        _validate_traces(traces, contract_terms)
        return cls(
            turn_index=turn_index,
            mirror=mirror,
            gap=gap,
            delta_summary=delta["summary"],
            delta_nodes=delta["nodes"],
            user_move=user_move,
            contract_terms=contract_terms,
            traces=traces,
            recorded_at=recorded_at,
        )


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TurnRecordError(f"turn record {label} must be a non-empty string")
    return value


def _delta(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != DELTA_KEYS:
        raise TurnRecordError("turn record delta must contain exactly summary and nodes")
    summary = value["summary"]
    if not isinstance(summary, str) or not summary.strip():
        raise TurnRecordError("turn record delta.summary must be a non-empty string")
    nodes_value = value["nodes"]
    if not isinstance(nodes_value, list):
        raise TurnRecordError("turn record delta.nodes must be a list")
    nodes = tuple(_node_id(node, "delta.nodes entry") for node in nodes_value)
    if len(set(nodes)) != len(nodes):
        raise TurnRecordError("turn record delta.nodes must be unique")
    return {"summary": summary, "nodes": nodes}


def _trace_copy(trace: Any, index: int) -> dict[str, Any]:
    if not isinstance(trace, Mapping) or set(trace) != {"type", "payload"}:
        raise TurnRecordError(f"turn record trace {index} must contain exactly type and payload")
    return {"type": trace["type"], "payload": dict(trace["payload"])}


def _validate_traces(traces: Sequence[Mapping[str, Any]], contract_terms: ContractTerms | None) -> None:
    """Validate traces against the seam registry; enforce required traces when terms exist."""
    for index, trace in enumerate(traces):
        if not isinstance(trace, Mapping) or set(trace) != {"type", "payload"}:
            raise TurnRecordError(f"trace record {index} must contain exactly type and payload")
        name = trace["type"]
        if not isinstance(name, str) or name not in DEFAULT_TRACE_REGISTRY:
            raise TurnRecordError(f"trace record {index} has an unregistered trace type: {name!r}")
        payload = trace["payload"]
        if not isinstance(payload, Mapping):
            raise TurnRecordError(f"trace record {index} payload must be a mapping")
        for required_field in DEFAULT_TRACE_REGISTRY.get(name).required_fields:
            if required_field not in payload:
                raise TurnRecordError(
                    f"trace record {index} ({name}) is missing required payload field: {required_field}"
                )
    if contract_terms is not None:
        # The seam's own primitive: fails naming the exact missing required term.
        verify_traces(contract_terms, traces)


class AlignmentTurnRecordStore:
    """Append-only JSONL store of alignment turn records for one run."""

    def __init__(self, run_root: Path) -> None:
        self.run_root = Path(run_root)
        self.alignment_directory = self.run_root / "alignment"
        self.records_path = self.alignment_directory / RECORDS_FILENAME
        self.receipt_path = self.alignment_directory / RECEIPT_FILENAME

    # -- reads ---------------------------------------------------------------

    def records(self) -> tuple[AlignmentTurnRecord, ...]:
        """Parse the whole file; any malformed line fails closed."""
        if not self.records_path.is_file():
            return ()
        records: list[AlignmentTurnRecord] = []
        for number, line in enumerate(self.records_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                record = AlignmentTurnRecord.from_dict(payload)
            except (json.JSONDecodeError, TurnContractError, TurnRecordError) as exc:
                raise TurnRecordError(f"invalid turn record at line {number}: {exc}") from exc
            records.append(record)
        return tuple(records)

    def latest(self) -> AlignmentTurnRecord | None:
        records = self.records()
        return records[-1] if records else None

    def next_turn_index(self) -> int:
        latest = self.latest()
        return 1 if latest is None else latest.turn_index + 1

    # -- continuity gate (fail-closed) ----------------------------------------

    def check_continuity(self, next_turn: int) -> dict[str, Any]:
        """Read before allowing the move: ground the next alignment turn in the file.

        Allowed returns ``{"status": "allowed", "grounding": <latest record
        fields or None>, "record_count": N}``; anything else raises
        ``ContinuityGateError`` with a named reason.
        """
        if isinstance(next_turn, bool) or not isinstance(next_turn, int) or next_turn < 1:
            raise TurnRecordError(f"next_turn must be a positive integer: {next_turn!r}")
        try:
            records = self.records()
        except TurnRecordError:
            raise ContinuityGateError(
                "invalid_turn_record",
                f"alignment turn record file is unreadable or violates the schema: {self.records_path}",
            ) from None
        if not records:
            if next_turn == 1:
                return {"status": "allowed", "grounding": None, "record_count": 0}
            raise ContinuityGateError(
                "missing_turn_record",
                f"alignment turn record file is missing; exchange {next_turn} is blocked "
                f"(fail-closed): {self.records_path}",
            )
        latest = records[-1]
        if latest.turn_index < next_turn - 1:
            raise ContinuityGateError(
                "stale_turn_record",
                f"alignment turn record is stale: latest persisted exchange is {latest.turn_index}, "
                f"next exchange is {next_turn}; at least one exchange left no record",
            )
        grounding = {
            "turn_index": latest.turn_index,
            "mirror": latest.mirror,
            "gap": latest.gap,
            "delta": latest.delta,
            "user_move": latest.user_move,
        }
        return {"status": "allowed", "grounding": grounding, "record_count": len(records)}

    # -- append ---------------------------------------------------------------

    def append(
        self,
        *,
        turn_index: int,
        mirror: str,
        gap: str,
        delta_summary: str,
        user_move: str,
        delta_nodes: Sequence[str] = (),
        contract_terms: ContractTerms | None = None,
        traces: Sequence[Mapping[str, Any]] = (),
        recorded_at: str | None = None,
    ) -> AlignmentTurnRecord:
        """Append one turn record; refuses gaps, replays, and delta-less turns."""
        records = self.records()
        expected = records[-1].turn_index + 1 if records else 1
        if isinstance(turn_index, bool) or not isinstance(turn_index, int) or turn_index < 1:
            raise TurnRecordError(f"turn_index must be a positive integer: {turn_index!r}")
        if turn_index < expected:
            raise ContinuityGateError(
                "duplicate_turn_index",
                f"turn record {turn_index} is already persisted; next expected turn index is {expected}",
            )
        if turn_index > expected:
            raise ContinuityGateError(
                "missing_turn_record",
                f"alignment turn record for exchange {expected} is missing; cannot append exchange "
                f"{turn_index} out of order (fail-closed)",
            )
        if not isinstance(delta_summary, str) or not delta_summary.strip():
            raise TurnRecordError(
                "turn introduces no persisted delta: a turn with an empty delta is a protocol "
                "violation (self-ask/self-answer guard)"
            )
        mirror_text = _nonempty(mirror, "mirror")
        gap_text = _nonempty(gap, "gap")
        if user_move not in RESPONSE_CLASSES:
            raise TurnRecordError(
                f"user_move must be one of the turn_contract response classes {RESPONSE_CLASSES}: {user_move!r}"
            )
        nodes = tuple(_node_id(node, "delta_nodes entry") for node in delta_nodes)
        if len(set(nodes)) != len(nodes):
            raise TurnRecordError("delta_nodes must be unique")
        validated_traces = tuple(_trace_copy(trace, index) for index, trace in enumerate(traces))
        _validate_traces(validated_traces, contract_terms)
        record = AlignmentTurnRecord(
            turn_index=turn_index,
            mirror=mirror_text,
            gap=gap_text,
            delta_summary=delta_summary,
            delta_nodes=nodes,
            user_move=user_move,
            contract_terms=contract_terms,
            traces=validated_traces,
            recorded_at=recorded_at or _now(),
        )
        self.alignment_directory.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record.to_dict(), ensure_ascii=True, separators=(",", ":")) + "\n"
        descriptor = os.open(self.records_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
            handle.write(line)
        return record


def refresh_validation(run_root: Path) -> dict[str, Any]:
    """Validate the record file and write the receipt (hook refresh, issue #497).

    Returns ``{"status": "validated"|"missing"|"invalid", "record_count": N,
    "last_turn_index": K}`` (plus ``reason`` when invalid). The receipt is
    written only when the alignment directory already exists: the refresh
    never creates workspace directories. Raises nothing for a missing or
    broken file — a broken file is a reported verdict, not an exception.
    """
    store = AlignmentTurnRecordStore(Path(run_root))
    verdict: dict[str, Any]
    if not store.records_path.is_file():
        verdict = {"status": "missing", "record_count": 0, "last_turn_index": None}
    else:
        try:
            records = store.records()
        except TurnRecordError as exc:
            verdict = {"status": "invalid", "reason": str(exc)}
        else:
            verdict = {
                "status": "validated",
                "record_count": len(records),
                "last_turn_index": records[-1].turn_index if records else None,
            }
    if store.alignment_directory.is_dir():
        _write_receipt(store.receipt_path, verdict)
    return verdict


def _write_receipt(receipt_path: Path, verdict: Mapping[str, Any]) -> None:
    receipt = {
        "schema": SCHEMA_VERSION,
        "state": verdict["status"],
        "record_count": verdict.get("record_count"),
        "last_turn_index": verdict.get("last_turn_index"),
        "validated_at": _now(),
    }
    temporary = receipt_path.with_name(f".{receipt_path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, receipt_path)
    finally:
        temporary.unlink(missing_ok=True)
