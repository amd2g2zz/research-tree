"""Durable, bounded accounting for source reads and process output costs."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable


CONTEXT_LEDGER_KIND = "context-read-ledger"
CONTEXT_RECEIPT_KIND = "context-read-receipt"
CONTEXT_LEDGER_SCHEMA_VERSION = 1
READ_DISPOSITIONS = ("fresh", "cached", "replayed")
ACTIVE_OUTPUT_ROOTS = (
    ".research-tree",
    ".research-tree-native",
    ".research-tree-hermes",
    ".research-tree-hooks",
    ".research-tree-debug",
)
DISCOVERY_EXCLUDED_DIRECTORIES = (
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "packages",
    "venv",
)
TOKEN_FIELDS = (
    "fresh_input_tokens",
    "cached_input_tokens",
    "replayed_input_tokens",
    "tool_output_tokens",
    "process_output_tokens",
)
BUDGET_FIELDS = tuple(f"max_{field}" for field in TOKEN_FIELDS)


class ContextLedgerError(ValueError):
    """Raised when a context ledger operation is not safely representable."""


@dataclass(frozen=True)
class ContextBudget:
    """Per-wave token and duplicate-read limits for one run."""

    max_fresh_input_tokens: int | None = None
    max_cached_input_tokens: int | None = None
    max_replayed_input_tokens: int | None = None
    max_tool_output_tokens: int | None = None
    max_process_output_tokens: int | None = None
    max_duplicate_read_ratio: float | None = None

    def __post_init__(self) -> None:
        for field_name in BUDGET_FIELDS:
            value = getattr(self, field_name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise ContextLedgerError(f"{field_name} must be a nonnegative integer or null")
        ratio = self.max_duplicate_read_ratio
        if ratio is not None and (
            isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or ratio < 0 or ratio > 1
        ):
            raise ContextLedgerError("max_duplicate_read_ratio must be a number between zero and one or null")

    @property
    def is_unbounded(self) -> bool:
        return all(getattr(self, field_name) is None for field_name in BUDGET_FIELDS) and (
            self.max_duplicate_read_ratio is None
        )

    def as_dict(self) -> dict[str, int | float | None]:
        return {
            field_name: getattr(self, field_name)
            for field_name in (*BUDGET_FIELDS, "max_duplicate_read_ratio")
        }

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> ContextBudget:
        return cls(**{field_name: value.get(field_name) for field_name in (*BUDGET_FIELDS, "max_duplicate_read_ratio")})


def _token_totals(records: Iterable[dict[str, Any]]) -> dict[str, int]:
    totals = {field_name: 0 for field_name in TOKEN_FIELDS}
    for record in records:
        token_usage = record.get("token_usage", {})
        if not isinstance(token_usage, dict):
            raise ContextLedgerError("context ledger record token_usage must be an object")
        for field_name in TOKEN_FIELDS:
            value = token_usage.get(field_name, 0)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ContextLedgerError(f"context ledger record {field_name} must be a nonnegative integer")
            totals[field_name] += value
    return totals


def _read_counts(records: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = {disposition: 0 for disposition in READ_DISPOSITIONS}
    for record in records:
        disposition = record.get("disposition")
        if disposition not in counts:
            raise ContextLedgerError("context ledger record has an invalid disposition")
        counts[disposition] += 1
    return counts


def _duplicate_ratio(read_counts: dict[str, int]) -> float:
    total = sum(read_counts.values())
    if total == 0:
        return 0.0
    return (read_counts["cached"] + read_counts["replayed"]) / total


def _require_nonnegative_int(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContextLedgerError(f"{label} must be a nonnegative integer")
    return value


class ContextReadLedger:
    """Record bounded source reads without turning cost telemetry into completion."""

    def __init__(
        self,
        workspace: Path,
        run_root: Path,
        run_id: str,
        *,
        budget: ContextBudget | None = None,
    ) -> None:
        self.workspace = workspace.resolve()
        self.run_root = run_root.resolve()
        try:
            self.run_root.relative_to(self.workspace)
        except ValueError as error:
            raise ContextLedgerError("run root must remain inside the workspace") from error
        if not isinstance(run_id, str) or not run_id:
            raise ContextLedgerError("run_id must be a non-empty string")
        self.run_id = run_id
        self.initial_budget = budget or ContextBudget()
        self.path = self.run_root / "context" / "read-ledger.json"

    def _initial_document(self) -> dict[str, Any]:
        return {
            "schema": CONTEXT_LEDGER_SCHEMA_VERSION,
            "kind": CONTEXT_LEDGER_KIND,
            "run_id": self.run_id,
            "status": "active",
            "execution_state": "unknown",
            "wave": 1,
            "budget": self.initial_budget.as_dict(),
            "reads": [],
            "sealed_sources": {},
            "checkpoint": None,
        }

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._initial_document()
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ContextLedgerError(f"context ledger is unreadable: {error}") from error
        if not isinstance(value, dict):
            raise ContextLedgerError("context ledger must be an object")
        if (
            value.get("schema") != CONTEXT_LEDGER_SCHEMA_VERSION
            or value.get("kind") != CONTEXT_LEDGER_KIND
            or value.get("run_id") != self.run_id
        ):
            raise ContextLedgerError("context ledger identity does not match this run")
        if value.get("status") not in ("active", "budget_exceeded"):
            raise ContextLedgerError("context ledger status is invalid")
        if value.get("execution_state") != "unknown":
            raise ContextLedgerError("context ledger execution state must remain unknown")
        if isinstance(value.get("wave"), bool) or not isinstance(value.get("wave"), int) or value["wave"] < 1:
            raise ContextLedgerError("context ledger wave is invalid")
        if not isinstance(value.get("budget"), dict):
            raise ContextLedgerError("context ledger budget must be an object")
        ContextBudget.from_mapping(value["budget"])
        if not isinstance(value.get("reads"), list):
            raise ContextLedgerError("context ledger reads must be a list")
        if not isinstance(value.get("sealed_sources"), dict):
            raise ContextLedgerError("context ledger sealed_sources must be an object")
        return value

    def _save(self, document: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix="read-ledger-", suffix=".json", dir=self.path.parent)
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(document, stream, ensure_ascii=False, indent=2, sort_keys=True)
                stream.write("\n")
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    def _resolve_source(self, source: Path) -> tuple[Path, str]:
        candidate = source if source.is_absolute() else self.workspace / source
        resolved = candidate.resolve()
        try:
            relative = resolved.relative_to(self.workspace)
        except ValueError as error:
            raise ContextLedgerError("context source must remain inside the workspace") from error
        if not resolved.is_file():
            raise ContextLedgerError("context source must identify a readable file")
        return resolved, relative.as_posix()

    @staticmethod
    def _is_active_output(relative: str) -> bool:
        return relative.split("/", 1)[0] in ACTIVE_OUTPUT_ROOTS

    def _assert_readable_source(self, document: dict[str, Any], source: Path, relative: str, digest: str) -> None:
        if not self._is_active_output(relative):
            return
        sealed_sources = document["sealed_sources"]
        sealed_digest = sealed_sources.get(relative)
        if sealed_digest is None:
            raise ContextLedgerError("active_output_unsealed: seal the source before recording a read")
        if sealed_digest != digest:
            raise ContextLedgerError("sealed_source_changed: sealed source digest no longer matches")

    @staticmethod
    def _line_range(contents: bytes, byte_start: int, byte_end: int) -> tuple[int, int]:
        line_start = contents[:byte_start].count(b"\n") + 1
        if byte_end == byte_start:
            return line_start, line_start
        line_end = contents[: byte_end - 1].count(b"\n") + 1
        return line_start, line_end

    @staticmethod
    def _matching_disposition(
        reads: list[dict[str, Any]],
        digest: str,
        byte_start: int,
        byte_end: int,
        consumer: str,
    ) -> str:
        matches = [
            record
            for record in reads
            if record.get("source_sha256") == digest
            and record.get("byte_start") == byte_start
            and record.get("byte_end") == byte_end
        ]
        if not matches:
            return "fresh"
        if any(record.get("consumer") == consumer for record in matches):
            return "cached"
        return "replayed"

    @staticmethod
    def _budget_reasons(records: list[dict[str, Any]], budget: ContextBudget) -> list[str]:
        totals = _token_totals(records)
        reasons = [
            f"{field_name}_exceeded"
            for field_name in TOKEN_FIELDS
            if (limit := getattr(budget, f"max_{field_name}")) is not None and totals[field_name] > limit
        ]
        read_counts = _read_counts(records)
        if (
            budget.max_duplicate_read_ratio is not None
            and _duplicate_ratio(read_counts) > budget.max_duplicate_read_ratio
        ):
            reasons.append("duplicate_read_ratio_exceeded")
        return reasons

    @staticmethod
    def _records_for_wave(document: dict[str, Any]) -> list[dict[str, Any]]:
        return [record for record in document["reads"] if record.get("wave") == document["wave"]]

    def seal_source(self, source: Path) -> dict[str, Any]:
        document = self._load()
        resolved, relative = self._resolve_source(source)
        digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
        document["sealed_sources"][relative] = digest
        self._save(document)
        return self.receipt()

    def record_read(
        self,
        source: Path,
        *,
        consumer: str,
        phase: str,
        byte_start: int = 0,
        byte_end: int | None = None,
        input_tokens: int = 0,
        tool_output_tokens: int = 0,
        process_output_tokens: int = 0,
    ) -> dict[str, Any]:
        if not isinstance(consumer, str) or not consumer:
            raise ContextLedgerError("consumer must be a non-empty string")
        if not isinstance(phase, str) or not phase:
            raise ContextLedgerError("phase must be a non-empty string")
        document = self._load()
        if document["status"] == "budget_exceeded":
            raise ContextLedgerError("budget_exceeded: resume this context ledger before reading again")
        resolved, relative = self._resolve_source(source)
        contents = resolved.read_bytes()
        digest = hashlib.sha256(contents).hexdigest()
        self._assert_readable_source(document, resolved, relative, digest)
        byte_start = _require_nonnegative_int(byte_start, "byte_start")
        actual_end = len(contents) if byte_end is None else _require_nonnegative_int(byte_end, "byte_end")
        if byte_start > actual_end or actual_end > len(contents):
            raise ContextLedgerError("byte range must be within the source length")
        input_tokens = _require_nonnegative_int(input_tokens, "input_tokens")
        tool_output_tokens = _require_nonnegative_int(tool_output_tokens, "tool_output_tokens")
        process_output_tokens = _require_nonnegative_int(process_output_tokens, "process_output_tokens")
        disposition = self._matching_disposition(document["reads"], digest, byte_start, actual_end, consumer)
        token_usage = {field_name: 0 for field_name in TOKEN_FIELDS}
        token_usage[f"{disposition}_input_tokens"] = input_tokens
        token_usage["tool_output_tokens"] = tool_output_tokens
        token_usage["process_output_tokens"] = process_output_tokens
        line_start, line_end = self._line_range(contents, byte_start, actual_end)
        document["reads"].append(
            {
                "source": relative,
                "source_sha256": digest,
                "byte_start": byte_start,
                "byte_end": actual_end,
                "line_start": line_start,
                "line_end": line_end,
                "consumer": consumer,
                "phase": phase,
                "disposition": disposition,
                "wave": document["wave"],
                "token_usage": token_usage,
            }
        )
        budget = ContextBudget.from_mapping(document["budget"])
        reasons = self._budget_reasons(self._records_for_wave(document), budget)
        if reasons:
            document["status"] = "budget_exceeded"
            document["checkpoint"] = {
                "reason": "budget_exceeded",
                "reasons": reasons,
                "resumable": True,
                "wave": document["wave"],
            }
        self._save(document)
        return self.receipt()

    def resume(self, budget: ContextBudget | None = None) -> dict[str, Any]:
        document = self._load()
        if document["status"] != "budget_exceeded":
            raise ContextLedgerError("context ledger is not paused for budget_exceeded")
        document["wave"] += 1
        document["status"] = "active"
        document["checkpoint"] = None
        if budget is not None:
            document["budget"] = budget.as_dict()
        self._save(document)
        return self.receipt()

    def discover_sources(self, root: Path | None = None) -> tuple[Path, ...]:
        document = self._load()
        base = self.workspace if root is None else (root if root.is_absolute() else self.workspace / root).resolve()
        try:
            base.relative_to(self.workspace)
        except ValueError as error:
            raise ContextLedgerError("discovery root must remain inside the workspace") from error
        if not base.is_dir():
            raise ContextLedgerError("discovery root must identify a directory")
        sealed_sources = document["sealed_sources"]
        discovered: list[Path] = []
        for candidate in sorted(base.rglob("*")):
            if not candidate.is_file():
                continue
            relative = candidate.resolve().relative_to(self.workspace).as_posix()
            if any(directory in DISCOVERY_EXCLUDED_DIRECTORIES for directory in Path(relative).parts):
                continue
            if self._is_active_output(relative) and relative not in sealed_sources:
                continue
            discovered.append(candidate.resolve())
        return tuple(discovered)

    def receipt(self) -> dict[str, Any]:
        document = self._load()
        reads = document["reads"]
        read_counts = _read_counts(reads)
        token_totals = _token_totals(reads)
        ranges = {
            (record["source_sha256"], record["byte_start"], record["byte_end"])
            for record in reads
        }
        return {
            "schema": CONTEXT_LEDGER_SCHEMA_VERSION,
            "kind": CONTEXT_RECEIPT_KIND,
            "run_id": self.run_id,
            "status": document["status"],
            "execution_state": "unknown",
            "completion_authority": "none",
            "authoritative": False,
            "wave": document["wave"],
            "budget": document["budget"],
            "checkpoint": document["checkpoint"],
            "read_counts": read_counts,
            "token_totals": token_totals,
            "duplicate_read_ratio": _duplicate_ratio(read_counts),
            "evidence_coverage": {
                "unique_source_digests": len({record["source_sha256"] for record in reads}),
                "unique_digest_ranges": len(ranges),
            },
            "records": list(reads),
        }
