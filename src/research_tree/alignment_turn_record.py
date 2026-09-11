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

Issue #529 adds one recovery attempt before the block: on a missing or stale
record the gate rebuilds a baseline record from the alignment graph's
append-only event log (read-only; the graph is ground truth and is never
written from here). The recovery record is marked ``reconstructed: true`` —
a schema-enforced marker so a repaired record never masquerades as an
authored one — and the healed run continues in visibly degraded mode
(receipts and gate verdicts name the repair). An empty, unreadable, or
contradictory event log blocks exactly as before.

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
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .turn_contract import (
    DEFAULT_TRACE_REGISTRY,
    RESPONSE_CLASS_GENERATION,
    RESPONSE_CLASSES,
    ContractTerms,
    TurnContractError,
    verify_traces,
)

__all__ = [
    "ContinuityGateError",
    "EVENT_LOG_SOURCE",
    "RECORDS_FILENAME",
    "RECEIPT_FILENAME",
    "MAX_DECISION_POINTS",
    "MAX_QUESTIONS",
    "MAX_TURN_LENGTH",
    "SCHEMA_VERSION",
    "REGISTRY_DELTA_ACTIONS",
    "AlignmentTurnRecord",
    "AlignmentTurnRecordStore",
    "TurnRecordError",
    "measure_turn_shape",
    "refresh_validation",
    "registry_delta",
]

# Round discipline (issue #493): the SKILL prose rules become measured
# dimensions on the turn record — one record, three measured dimensions,
# checked mechanically; what a compliant turn *says* stays prompt-layer craft
# (#501). ``transformation_ratio`` is the #499 placeholder slot.
SCHEMA_VERSION = 2
MAX_TURN_LENGTH = 1000
MAX_DECISION_POINTS = 1
MAX_QUESTIONS = 1
TURN_SHAPE_KEYS = frozenset(
    {"length", "decision_count", "question_count", "transformation_ratio", "verdict", "violations"}
)
TURN_SHAPE_VERDICTS = frozenset({"compliant", "violated"})
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
        # Issue #529: the reconstruction marker — optional, schema-enforced
        # (present implies the record IS reconstructed), written only by the
        # reconstruction path.
        "reconstructed",
    }
)
DELTA_KEYS = frozenset({"summary", "nodes"})

# Issue #529 self-heal: the alignment graph database lives in the same
# alignment/ directory as the record file (the graph's ``_run_dir`` layout),
# and its append-only ``response_recorded`` events are the ground truth a
# lost record file is rebuilt from. ``EVENT_LOG_SOURCE`` names that source in
# the healed gate verdict.
GRAPH_DATABASE_FILENAME = "alignment.db"
EVENT_LOG_SOURCE = "alignment_event_log"
# Mirrors alignment_graph._OPEN_GAP_STATUSES (kept local — this module reads
# the graph's sqlite store without importing the graph's runtime).
OPEN_GAP_STATUSES = frozenset({"candidate", "disputed"})

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


def measure_turn_shape(
    response_text: str,
    *,
    decision_count: int,
    question_count: int,
    transformation_ratio: float | None = None,
) -> dict[str, Any]:
    """Measure one composed turn against the round discipline (issue #493).

    Pure and mechanical: the verdict flags named dimensions only — length over
    the round cap, more than one decision point, more than one question. The
    composer decides what a compliant turn says; the record only proves the
    shape was measured. ``transformation_ratio`` is carried for #499.
    """

    if not isinstance(response_text, str):
        raise TurnRecordError("turn shape response_text must be a string")
    for name, count in (("decision_count", decision_count), ("question_count", question_count)):
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise TurnRecordError(f"turn shape {name} must be a nonnegative integer")
    if transformation_ratio is not None and (
        isinstance(transformation_ratio, bool) or not isinstance(transformation_ratio, (int, float))
    ):
        raise TurnRecordError("turn shape transformation_ratio must be numeric or None")
    length = len(response_text)
    violations: list[str] = []
    if length > MAX_TURN_LENGTH:
        violations.append(f"length>{MAX_TURN_LENGTH}: {length}")
    if decision_count > MAX_DECISION_POINTS:
        violations.append(f"decision_count>{MAX_DECISION_POINTS}: {decision_count}")
    if question_count > MAX_QUESTIONS:
        violations.append(f"question_count>{MAX_QUESTIONS}: {question_count}")
    return {
        "length": length,
        "decision_count": decision_count,
        "question_count": question_count,
        "transformation_ratio": transformation_ratio,
        "verdict": "violated" if violations else "compliant",
        "violations": violations,
    }


def _validate_turn_shape(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != TURN_SHAPE_KEYS:
        raise TurnRecordError("turn record turn_shape fields do not match schema")
    verdict = value["verdict"]
    if verdict not in TURN_SHAPE_VERDICTS:
        raise TurnRecordError(f"turn shape verdict must be one of {sorted(TURN_SHAPE_VERDICTS)}")
    for name in ("length", "decision_count", "question_count"):
        count = value[name]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise TurnRecordError(f"turn shape {name} must be a nonnegative integer")
    ratio = value["transformation_ratio"]
    if ratio is not None and (isinstance(ratio, bool) or not isinstance(ratio, (int, float))):
        raise TurnRecordError("turn shape transformation_ratio must be numeric or None")
    violations = value["violations"]
    if isinstance(violations, (str, bytes)) or not isinstance(violations, list):
        raise TurnRecordError("turn shape violations must be a list")
    if any(not isinstance(item, str) or not item.strip() for item in violations):
        raise TurnRecordError("turn shape violations entries must be non-empty strings")
    expected = "violated" if violations else "compliant"
    if verdict != expected:
        raise TurnRecordError(f"turn shape verdict must be {expected!r} for the recorded violations: {violations}")
    return dict(value)


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
    turn_shape: dict[str, Any] | None = None
    # Issue #529: True only for records reconstructed from the alignment
    # event log; authored records leave the field unset and their persisted
    # payload unchanged.
    reconstructed: bool = False

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
        if self.turn_shape is not None:
            payload["turn_shape"] = dict(self.turn_shape)
        if self.reconstructed:
            payload["reconstructed"] = True
        return payload

    @classmethod
    def from_dict(cls, value: Any) -> "AlignmentTurnRecord":
        if not isinstance(value, Mapping):
            raise TurnRecordError("turn record must be a JSON object")
        schema = value.get("schema")
        legacy = schema == 1
        allowed_keys = RECORD_KEYS | (frozenset() if legacy else {"turn_shape"})
        unknown = set(value) - allowed_keys
        # ``reconstructed`` is optional (issue #529): authored records omit it.
        missing = (RECORD_KEYS - {"reconstructed"}) - set(value)
        if unknown or missing:
            raise TurnRecordError(f"turn record field mismatch; missing: {sorted(missing)}, unknown: {sorted(unknown)}")
        # Issue #529 marker presence rules: the field's presence means the
        # record IS reconstructed, so anything but boolean true is a schema
        # error (a forged ``reconstructed: false`` never masquerades as an
        # authored record's absence). Key presence, not truthiness — a null
        # marker is a forge attempt, not an omission.
        if "reconstructed" in value and value["reconstructed"] is not True:
            raise TurnRecordError(
                "turn record reconstructed marker must be boolean true when present; authored records omit it"
            )
        if legacy:
            # Schema 1 records (issue #497) predate the turn-shape dimensions;
            # they stay readable — fail-closed continuity must survive.
            turn_shape = None
        elif "turn_shape" in value:
            turn_shape = _validate_turn_shape(value["turn_shape"])
        else:
            turn_shape = None
        if not legacy and schema != SCHEMA_VERSION:
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
            turn_shape=turn_shape,
            reconstructed=value.get("reconstructed") is True,
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


def _graph_database_path_helper() -> Any:
    """Lazily resolve the graph's canonical ``database_path`` helper (issue #529).

    Function-level because ``alignment_graph`` imports ``lifecycle_hook``
    which imports this module — a module-level import would close a cycle;
    the bare-name fallback covers the packaged single-file layout (#470).
    Returns None when the graph module is unreachable, in which case the
    canonical adjacency (see ``AlignmentTurnRecordStore._graph_database``)
    resolves the database.
    """

    try:
        from .alignment_graph import database_path
    except ImportError:
        pass
    else:
        return database_path
    try:
        from alignment_graph import database_path  # type: ignore[no-redef]
    except ImportError:
        return None
    return database_path


def _read_response_events(database: Path) -> list[dict[str, Any]] | None:
    """Read the graph's ``response_recorded`` event log, read-only (issue #529).

    Opens the alignment SQLite store in read-only URI mode — the hook's
    ``_budget_violations_from_events`` pattern; the graph is ground truth
    and is never written from here. Returns the parsed events oldest-first,
    or None when the log is missing, unreadable, empty, or corrupt: any of
    those makes reconstruction impossible and the gate stays fail-closed.
    """

    if not database.is_file():
        return None
    try:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=0.5)
    except sqlite3.Error:
        return None
    try:
        rows = connection.execute(
            "SELECT details_json, state_json, created_at FROM events "
            "WHERE event_type='response_recorded' ORDER BY sequence"
        ).fetchall()
    except sqlite3.Error:
        return None
    finally:
        connection.close()
    if not rows:
        return None
    events: list[dict[str, Any]] = []
    for details_json, state_json, created_at in rows:
        try:
            details = json.loads(details_json)
            state = json.loads(state_json)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(details, dict) or not isinstance(state, dict):
            return None
        events.append({"details": details, "state": state, "recorded_at": created_at})
    return events


def _synthesized_baseline(event: Mapping[str, Any]) -> dict[str, Any] | None:
    """Synthesize the recovery record's fields from the latest event (issue #529).

    The mirror is grounded in the event's materialized graph state, the delta
    in the recorded response, ``recorded_at`` in the event's log timestamp.
    Event traces survive only when they validate against the seam registry —
    nothing is fabricated. Returns None when the event cannot ground a
    schema-valid baseline (the gate then stays fail-closed).
    """

    details = event["details"]
    node_id = details.get("node_id")
    outcome = details.get("outcome")
    if not isinstance(node_id, str) or not node_id.strip():
        return None
    if not isinstance(outcome, str) or not outcome.strip():
        return None
    state = event["state"]
    controller = state.get("controller")
    turn = controller.get("turn") if isinstance(controller, Mapping) else None
    if isinstance(turn, bool) or not isinstance(turn, int) or turn < 1:
        return None
    graph = state.get("graph")
    nodes_value = graph.get("nodes") if isinstance(graph, Mapping) else None
    nodes = [node for node in nodes_value if isinstance(node, Mapping)] if isinstance(nodes_value, list) else []
    edges_value = graph.get("edges") if isinstance(graph, Mapping) else None
    edge_count = len(edges_value) if isinstance(edges_value, list) else 0
    open_gaps = sum(1 for node in nodes if node.get("status") in OPEN_GAP_STATUSES)
    mirror = (
        f"Reconstructed baseline from the alignment event log: the graph holds {len(nodes)} nodes "
        f"and {edge_count} edges with {open_gaps} open gap(s); the latest recorded turn {turn} "
        f"logged outcome '{outcome}' on node '{node_id}'."
    )
    # The recorded node is the consequential gap under discussion; its
    # statement (when still materialized) grounds the gap field.
    statement = next(
        (
            node["statement"]
            for node in nodes
            if node.get("id") == node_id and isinstance(node.get("statement"), str) and node["statement"].strip()
        ),
        None,
    )
    gap = f"{node_id} — {statement}" if statement else node_id
    user_move = details.get("user_move")
    if user_move not in RESPONSE_CLASSES:
        # The permissive default for logs that predate typed moves; the
        # reconstructed marker carries the epistemic caveat.
        user_move = RESPONSE_CLASS_GENERATION
    traces: list[dict[str, Any]] = []
    for trace in details.get("traces") or []:
        try:
            candidate = _trace_copy(trace, len(traces))
            _validate_traces((candidate,), None)
        except TurnRecordError:
            continue
        traces.append(candidate)
    recorded_at = event.get("recorded_at")
    if not isinstance(recorded_at, str) or not recorded_at.strip():
        recorded_at = _now()
    return {
        "turn_index": turn,
        "mirror": mirror,
        "gap": gap,
        "delta_summary": f"reconstructed: outcome '{outcome}' recorded on node '{node_id}'",
        "delta_nodes": (node_id,) if re.fullmatch(NODE_ID_RE_SOURCE, node_id) else (),
        "user_move": user_move,
        "traces": tuple(traces),
        "recorded_at": recorded_at,
    }


class AlignmentTurnRecordStore:
    """Append-only JSONL store of alignment turn records for one run."""

    def __init__(self, run_root: Path) -> None:
        self.run_root = Path(run_root)
        self.alignment_directory = self.run_root / "alignment"
        self.records_path = self.alignment_directory / RECORDS_FILENAME
        self.receipt_path = self.alignment_directory / RECEIPT_FILENAME

    def _graph_database(self) -> Path:
        """Resolve the alignment graph database for this run (issue #529).

        The graph's canonical helper (``alignment_graph.database_path``) is
        the authority on the location; resolving it needs the
        workspace/run-id/project-id decomposition that only the canonical
        workspace layout provides, so the canonical adjacency — the database
        lives in the same ``alignment/`` directory as the record file, which
        is the helper's own layout — is the fallback (and the same file in
        every layout the helper serves).
        """

        run_root = self.run_root
        if (
            run_root.parent.name == "runs"
            and len(run_root.parents) > 4
            and run_root.parents[2].name == "projects"
            and run_root.parents[3].name == ".research-tree"
        ):
            helper = _graph_database_path_helper()
            if helper is not None:
                try:
                    return helper(run_root.parents[4], run_root.name, run_root.parents[1].name)
                except (OSError, ValueError):
                    pass  # non-resolvable workspace: fall through to the adjacency
        return self.alignment_directory / GRAPH_DATABASE_FILENAME

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

        Issue #529 self-heal: on a missing or stale record the gate first
        attempts a baseline reconstruction from the alignment graph's
        append-only event log. Success appends one reconstructed baseline
        record and returns an allowed verdict marked degraded (``degraded``,
        a named ``recovery`` section, ``grounding["reconstructed"]``);
        failure raises the original fail-closed error unchanged. A verdict
        grounded on a reconstructed latest record always reports degraded —
        continuity repaired is never silently pristine.
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
            healed = self._reconstruct(next_turn, records)
            if healed is not None:
                return healed
            raise ContinuityGateError(
                "missing_turn_record",
                f"alignment turn record file is missing; exchange {next_turn} is blocked "
                f"(fail-closed): {self.records_path}",
            )
        latest = records[-1]
        if latest.turn_index < next_turn - 1:
            healed = self._reconstruct(next_turn, records)
            if healed is not None:
                return healed
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
        verdict = {"status": "allowed", "grounding": grounding, "record_count": len(records)}
        if latest.reconstructed:
            grounding["reconstructed"] = True
            verdict["degraded"] = True
        return verdict

    # -- self-heal reconstruction (issue #529) --------------------------------

    def _reconstruct(self, next_turn: int, records: tuple[AlignmentTurnRecord, ...]) -> dict[str, Any] | None:
        """Attempt the baseline reconstruction from the alignment event log.

        Returns the healed (degraded) verdict, or None when reconstruction
        is impossible or contradictory — the caller then raises today's
        fail-closed error unchanged. Contradiction rules: the log's response
        turn axis must be exactly ``1..N`` in sequence order; its latest
        turn must reach the exchange the run expects and must extend (not
        contradict) the persisted record file. The graph database is opened
        read-only and never written.
        """
        events = _read_response_events(self._graph_database())
        if events is None:
            return None
        turns: list[int] = []
        for event in events:
            controller = event["state"].get("controller")
            turn = controller.get("turn") if isinstance(controller, Mapping) else None
            if isinstance(turn, bool) or not isinstance(turn, int):
                return None
            turns.append(turn)
        if turns != list(range(1, len(turns) + 1)):
            return None
        latest_turn = turns[-1]
        if latest_turn < next_turn - 1:
            return None
        if records and latest_turn <= records[-1].turn_index:
            return None
        baseline = _synthesized_baseline(events[-1])
        if baseline is None:
            return None
        try:
            record = self.reconstruct(**baseline)
        except (OSError, TurnRecordError):
            return None
        return {
            "status": "allowed",
            "grounding": {
                "turn_index": record.turn_index,
                "mirror": record.mirror,
                "gap": record.gap,
                "delta": record.delta,
                "user_move": record.user_move,
                "reconstructed": True,
            },
            "record_count": len(records) + 1,
            "degraded": True,
            "recovery": {"turn_index": record.turn_index, "source": EVENT_LOG_SOURCE},
        }

    def reconstruct(
        self,
        *,
        turn_index: int,
        mirror: str,
        gap: str,
        delta_summary: str,
        user_move: str,
        delta_nodes: Sequence[str] = (),
        traces: Sequence[Mapping[str, Any]] = (),
        recorded_at: str | None = None,
    ) -> AlignmentTurnRecord:
        """Append the reconstructed baseline record (issue #529 self-heal).

        The only writer of the ``reconstructed`` marker: a record rebuilt
        from the alignment event log must never masquerade as an authored
        turn. Refuses to rewind or overwrite the persisted history (the
        index must advance the file) and, like ``append``, refuses a
        delta-less baseline — the recovery delta names the recorded outcome.
        """
        records = self.records()
        if isinstance(turn_index, bool) or not isinstance(turn_index, int) or turn_index < 1:
            raise TurnRecordError(f"turn_index must be a positive integer: {turn_index!r}")
        if records and turn_index <= records[-1].turn_index:
            raise ContinuityGateError(
                "duplicate_turn_index",
                f"turn record {turn_index} is already persisted; reconstruction must advance the file",
            )
        if not isinstance(delta_summary, str) or not delta_summary.strip():
            raise TurnRecordError(
                "reconstructed baseline introduces no persisted delta: a turn with an empty delta is a "
                "protocol violation (self-ask/self-answer guard)"
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
        _validate_traces(validated_traces, None)
        record = AlignmentTurnRecord(
            turn_index=turn_index,
            mirror=mirror_text,
            gap=gap_text,
            delta_summary=delta_summary,
            delta_nodes=nodes,
            user_move=user_move,
            contract_terms=None,
            traces=validated_traces,
            recorded_at=recorded_at or _now(),
            turn_shape=None,
            reconstructed=True,
        )
        self._append_line(record)
        return record

    def _append_line(self, record: AlignmentTurnRecord) -> None:
        """Append one record as a single strict-whitelist JSON line."""
        self.alignment_directory.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record.to_dict(), ensure_ascii=True, separators=(",", ":")) + "\n"
        descriptor = os.open(self.records_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
            handle.write(line)

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
        turn_shape: Mapping[str, Any] | None = None,
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
        shape = _validate_turn_shape(turn_shape) if turn_shape is not None else None
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
            turn_shape=shape,
        )
        self._append_line(record)
        return record


def refresh_validation(run_root: Path) -> dict[str, Any]:
    """Validate the record file and write the receipt (hook refresh, issue #497).

    Returns ``{"status": "validated"|"missing"|"invalid", "record_count": N,
    "last_turn_index": K}`` (plus ``reason`` when invalid). When the file
    holds reconstructed records (issue #529) the verdict also carries
    ``reconstructed_count`` and ``degraded: true`` — the receipt shows the
    run was repaired from the event log, never silently pristine. The receipt
    is written only when the alignment directory already exists: the refresh
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
                "last_turn_shape": (records[-1].turn_shape or {}).get("verdict"),
            }
            reconstructed_count = sum(1 for record in records if record.reconstructed)
            if reconstructed_count:
                verdict["reconstructed_count"] = reconstructed_count
                verdict["degraded"] = True
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
    if verdict.get("degraded") is True:
        # Issue #529: reconstructed records in the file degrade the run's
        # continuity receipt — visible, never silently pristine.
        receipt["degraded"] = True
        receipt["reconstructed_count"] = verdict.get("reconstructed_count")
    temporary = receipt_path.with_name(f".{receipt_path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, receipt_path)
    finally:
        temporary.unlink(missing_ok=True)


# Brief-registry delta seam (issue #524, additive): a user input's delta can
# now be precisely its brief-registry changes, so the no-delta protocol
# violation check above becomes accurate for registry-only turns. The
# refinery's change records convert into the exact delta payload this
# module's ``append`` consumes; nothing existing changes.
REGISTRY_DELTA_ACTIONS = frozenset({"registered", "confirmed", "transitioned"})
REGISTRY_CHANGE_KEYS = frozenset({"action", "object_id"})


def registry_delta(changes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Convert a brief-registry change set into a turn-record delta payload.

    Each change is ``{"action", "object_id"}`` with an action from
    ``REGISTRY_DELTA_ACTIONS`` and an object id satisfying the delta-node
    identifier rules. Returns ``{"summary", "nodes"}``: the summary names
    the actions and object ids, the nodes are the unique object ids in
    first-seen order. An empty change set is refused — an empty change set
    is no delta, and appending a delta-less turn is a protocol violation.
    """

    if isinstance(changes, (str, bytes)) or not isinstance(changes, Sequence):
        raise TurnRecordError("brief-registry change set must be a sequence of change records")
    if not changes:
        raise TurnRecordError(
            "brief-registry change set is empty; an empty change set is no delta "
            "(a turn without registry changes carries no registry delta)"
        )
    summary_parts: list[str] = []
    nodes: list[str] = []
    for index, change in enumerate(changes):
        if not isinstance(change, Mapping) or set(change) != REGISTRY_CHANGE_KEYS:
            raise TurnRecordError(f"registry change {index} must contain exactly action and object_id")
        action = change["action"]
        if action not in REGISTRY_DELTA_ACTIONS:
            raise TurnRecordError(
                f"registry change {index} action must be one of {sorted(REGISTRY_DELTA_ACTIONS)}: {action!r}"
            )
        object_id = _node_id(change["object_id"], f"registry change {index} object_id")
        summary_parts.append(f"{action} {object_id}")
        if object_id not in nodes:
            nodes.append(object_id)
    return {"summary": "brief-registry: " + ", ".join(summary_parts), "nodes": nodes}
