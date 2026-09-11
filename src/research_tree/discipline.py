"""Discipline telemetry: the external, never-forgetting compliance loop (issue #525).

The lifecycle hook consumes what the event stream already emits (#527 agent
turn budget violations, #514 turn-shape verdicts, #497 record compliance)
and appends each named violation to an append-only per-run JSONL stream.
A sliding-window violation rate over that stream drives a graduated
response ladder — receipt-only, reminder injection, forced SKILL discipline
reload, block — so "comply, relapse" becomes visible without duplicating
any measurement logic. A single violation is data, not a verdict; only the
top ladder step is fail-closed.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

DISCIPLINE_STREAM_SCHEMA = 1
VIOLATIONS_DIRECTORY = "discipline"
VIOLATIONS_FILENAME = "violations.jsonl"
# Canonical violation vocabulary: #527's max_questions/max_chars and #514's
# length/question_count normalize onto these; anything unrecognized is other.
DISCIPLINE_DIMENSIONS = frozenset({"questions", "chars", "record", "other"})
DISCIPLINE_SOURCES = frozenset({"agent_turn_budget", "turn_shape", "turn_record"})
MAX_SOURCE_LENGTH = 64

# Sliding window: the rate counts violation records inside the last N turn
# slots over the full N, so one violation reads 1/N — data, not a verdict —
# while sustained violations accumulate toward the ladder.
DISCIPLINE_WINDOW_TURNS = 10

# Graduated response ladder thresholds (issue #525; pinned by tests at both
# boundaries). With the default window: two violating turns in the window
# remind, four reload the discipline section, six block the next turn.
RECEIPT_ONLY = "receipt_only"
DISCIPLINE_REMINDER = "discipline_reminder"
DISCIPLINE_RELOAD = "discipline_reload"
DISCIPLINE_BLOCK = "discipline_block"
DISCIPLINE_RESPONSES = (RECEIPT_ONLY, DISCIPLINE_REMINDER, DISCIPLINE_RELOAD, DISCIPLINE_BLOCK)
DISCIPLINE_REMINDER_RATE = 0.2
DISCIPLINE_RELOAD_RATE = 0.4
DISCIPLINE_BLOCK_RATE = 0.6

# The reminder/reload payloads ride #530's tail-injection channel: single
# line, fixed slot, bounded. The channel design is #530's; this module only
# emits the structured payload it will carry.
DISCIPLINE_INJECTION_SLOT = "discipline"
DISCIPLINE_INJECTION_MAX_CHARS = 200

RECENT_VIOLATION_LIMIT = 5
# Bounded read: a runaway stream cannot make the hook scan without end.
MAX_RECORDS_SCAN = 1000


class DisciplineTelemetryError(ValueError):
    """Raised when a violation record or the violation stream is invalid."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_violation(value: Mapping[str, Any], *, recorded_at: str | None = None) -> dict[str, Any]:
    """Validate one violation record and return it in canonical shape.

    A record is ``{turn_index, dimension, measured, cap, source}`` plus the
    stream schema and an ISO timestamp. ``turn_index 0`` names an unnumbered
    observation (the run's turn axis was unknown); ``recorded_at`` given as
    an argument wins over the payload's own stamp.
    """
    if not isinstance(value, Mapping):
        raise DisciplineTelemetryError("violation record must be a JSON object")
    turn_index = value.get("turn_index")
    if isinstance(turn_index, bool) or not isinstance(turn_index, int) or turn_index < 0:
        raise DisciplineTelemetryError(f"violation turn_index must be a nonnegative integer: {turn_index!r}")
    dimension = value.get("dimension")
    if dimension not in DISCIPLINE_DIMENSIONS:
        raise DisciplineTelemetryError(
            f"violation dimension must be one of {sorted(DISCIPLINE_DIMENSIONS)}: {dimension!r}"
        )
    for name, number in (("measured", value.get("measured")), ("cap", value.get("cap"))):
        if isinstance(number, bool) or not isinstance(number, int) or number < 0:
            raise DisciplineTelemetryError(f"violation {name} must be a nonnegative integer: {number!r}")
    source = value.get("source")
    if not isinstance(source, str) or not source.strip() or len(source) > MAX_SOURCE_LENGTH:
        raise DisciplineTelemetryError(f"violation source must be a bounded non-empty string: {source!r}")
    stamp = recorded_at or value.get("recorded_at")
    if stamp is not None and (not isinstance(stamp, str) or not stamp.strip()):
        raise DisciplineTelemetryError("violation recorded_at must be a non-empty string")
    return {
        "schema": DISCIPLINE_STREAM_SCHEMA,
        "turn_index": turn_index,
        "dimension": dimension,
        "measured": value.get("measured"),
        "cap": value.get("cap"),
        "source": source,
        "recorded_at": stamp if isinstance(stamp, str) else _now(),
    }


def _violation_key(record: Mapping[str, Any]) -> tuple[str, int, str, int, int]:
    """Dedupe identity of one violation: the same emitted violation re-read
    from the event stream must never be counted twice."""
    return (record["source"], record["turn_index"], record["dimension"], record["measured"], record["cap"])


class DisciplineViolationStore:
    """Append-only JSONL violation stream for one run (issue #525).

    Persisted beside the turn record under the run's ``discipline/``
    directory. Appends are idempotent per the dedupe identity, so the hook
    can re-read the same event stream on every fire without double-counting;
    new turns append. Records are never rewritten or removed.
    """

    def __init__(self, run_root: Path) -> None:
        self.run_root = Path(run_root)
        self.violations_path = self.run_root / VIOLATIONS_DIRECTORY / VIOLATIONS_FILENAME

    def records(self) -> tuple[dict[str, Any], ...]:
        """Parse the stream (bounded tail); a malformed line fails closed."""
        if not self.violations_path.is_file():
            return ()
        records: list[dict[str, Any]] = []
        lines = self.violations_path.read_text(encoding="utf-8").splitlines()[-MAX_RECORDS_SCAN:]
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DisciplineTelemetryError(f"invalid violation record at line {number}: {exc}") from exc
            records.append(normalize_violation(payload))
        return tuple(records)

    def append(self, violations: Iterable[Mapping[str, Any]] = ()) -> list[dict[str, Any]]:
        """Append unseen violations; returns the records newly written."""
        existing = {_violation_key(record) for record in self.records()}
        fresh: list[dict[str, Any]] = []
        for raw in violations:
            record = normalize_violation(raw)
            key = _violation_key(record)
            if key in existing:
                continue
            existing.add(key)
            fresh.append(record)
        if not fresh:
            return []
        payload = "".join(json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n" for record in fresh)
        self.violations_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.violations_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
            handle.write(payload)
        return fresh


def sliding_window_rate(
    records: Iterable[Mapping[str, Any]],
    *,
    window: int = DISCIPLINE_WINDOW_TURNS,
    turns_observed: int | None = None,
) -> float:
    """Violation rate over the last ``window`` turn slots.

    The window ends at the most recent observed turn — the highest stream
    turn index, extended by the caller's turn axis (``turns_observed``, e.g.
    the alignment event count) when known so clean recent turns dilute the
    rate. The denominator is the full window: a single violation stays data,
    not a verdict, and an empty stream rates ``0.0``. Saturates at ``1.0``.
    """
    if isinstance(window, bool) or not isinstance(window, int) or window < 1:
        raise DisciplineTelemetryError(f"window must be a positive integer: {window!r}")
    indices = [record["turn_index"] for record in records]
    if not indices:
        return 0.0
    latest = max(indices)
    if turns_observed is not None:
        if isinstance(turns_observed, bool) or not isinstance(turns_observed, int) or turns_observed < 0:
            raise DisciplineTelemetryError(f"turns_observed must be a nonnegative integer: {turns_observed!r}")
        latest = max(latest, turns_observed)
    cutoff = latest - window
    counted = sum(1 for index in indices if index > cutoff)
    return min(counted / window, 1.0)


def resolve_discipline_response(rate: float) -> str:
    """Resolve the violation rate to exactly one ladder step (issue #525)."""
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or rate < 0:
        raise DisciplineTelemetryError(f"violation rate must be a nonnegative number: {rate!r}")
    if rate >= DISCIPLINE_BLOCK_RATE:
        return DISCIPLINE_BLOCK
    if rate >= DISCIPLINE_RELOAD_RATE:
        return DISCIPLINE_RELOAD
    if rate >= DISCIPLINE_REMINDER_RATE:
        return DISCIPLINE_REMINDER
    return RECEIPT_ONLY


def is_discipline_blocked(rate: float) -> bool:
    """True only at the top ladder step — the one fail-closed step."""
    return resolve_discipline_response(rate) == DISCIPLINE_BLOCK


def build_discipline_injection(
    response: str,
    *,
    rate: float,
    window: int = DISCIPLINE_WINDOW_TURNS,
) -> dict[str, Any] | None:
    """Build the tail-injection payload for the reminder and reload steps.

    Single line (whitespace collapsed), bounded to
    ``DISCIPLINE_INJECTION_MAX_CHARS``, fixed slot ``discipline`` — the
    structured payload #530's channel carries. The reload step requests the
    SKILL discipline section (contract-emission/round-discipline clauses).
    Other steps inject nothing.
    """
    if response == DISCIPLINE_REMINDER:
        text = (
            f"discipline: violation rate {rate:.2f} over the last {window} turns — "
            "one question and one decision per turn, keep turns short"
        )
    elif response == DISCIPLINE_RELOAD:
        text = (
            f"discipline: violation rate {rate:.2f} sustained over the last {window} turns — "
            "reload the SKILL discipline section before the next turn"
        )
    else:
        return None
    line = " ".join(text.split())[:DISCIPLINE_INJECTION_MAX_CHARS]
    return {"marker": response, "slot": DISCIPLINE_INJECTION_SLOT, "line": line}


def build_discipline_section(
    records: Iterable[Mapping[str, Any]],
    *,
    turns_observed: int | None = None,
    window: int = DISCIPLINE_WINDOW_TURNS,
) -> dict[str, Any]:
    """Build the receipt's ``discipline`` section: rate, recent violations,
    the resolved ladder step, and the injection or gate verdict it carries."""
    materialized = list(records)
    rate = sliding_window_rate(materialized, window=window, turns_observed=turns_observed)
    response = resolve_discipline_response(rate)
    indices = [record["turn_index"] for record in materialized]
    latest = max(indices) if indices else 0
    if turns_observed is not None:
        latest = max(latest, turns_observed)
    cutoff = latest - window
    section: dict[str, Any] = {
        "rate": rate,
        "window": window,
        "violations_in_window": sum(1 for index in indices if index > cutoff),
        "last_turn_index": latest,
        "recent": [dict(record) for record in materialized[-RECENT_VIOLATION_LIMIT:]],
        "response": response,
    }
    injection = build_discipline_injection(response, rate=rate, window=window)
    if injection is not None:
        section["injection"] = injection
    if response == DISCIPLINE_BLOCK:
        section["gate"] = {"status": "blocked", "reason": DISCIPLINE_BLOCK}
    return section


def check_discipline_gate(
    run_root: Path,
    *,
    window: int = DISCIPLINE_WINDOW_TURNS,
    turns_observed: int | None = None,
) -> dict[str, Any]:
    """Next-turn gate check over the persisted violation stream (issue #525).

    The seam a next-turn gate calls to honor the block verdict: ``blocked``
    with reason ``discipline_block`` when the stream's sliding-window rate
    reaches ``DISCIPLINE_BLOCK_RATE``, ``allowed`` otherwise. Fail-open
    everywhere except the top step — an absent or unreadable stream allows,
    because observation must never block.
    """
    try:
        records = DisciplineViolationStore(run_root).records()
    except (OSError, ValueError):
        records = ()
    rate = sliding_window_rate(records, window=window, turns_observed=turns_observed)
    response = resolve_discipline_response(rate)
    if response == DISCIPLINE_BLOCK:
        return {"status": "blocked", "reason": DISCIPLINE_BLOCK, "rate": rate}
    return {"status": "allowed", "rate": rate, "response": response}
