"""Evaluator-owned, append-only episode journal for recoverable benchmarks."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any, Iterator


_CONTRACT_FIELDS = frozenset(
    {
        "episode_id",
        "pair_group_id",
        "model_version",
        "runtime_digest",
        "intervention_digest",
        "host_binding_digest",
        "guest_rootfs_digest",
        "runner_input_digest",
        "synthetic_user_assignment_digest",
    }
)
_OBSERVED_FIELDS = _CONTRACT_FIELDS.difference({"episode_id", "pair_group_id", "model_version"})


class EpisodeJournalError(ValueError):
    """Raised when an evaluator journal is malformed or cannot safely resume."""


class EpisodeJournal:
    """Durably record only evaluator-side episode lifecycle metadata."""

    def __init__(self, root: Path, *, attestation_key: bytes) -> None:
        if not isinstance(attestation_key, bytes) or len(attestation_key) < 16:
            raise EpisodeJournalError("journal attestation key must be evaluator-owned bounded bytes")
        self.root = root
        self.attestation_key = attestation_key
        self.root.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.root / "episode-journal.sqlite3", isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.execute("PRAGMA synchronous = FULL")
        self.connection.execute("PRAGMA busy_timeout = 5000")
        self._create_schema()

    def close(self) -> None:
        self.connection.close()

    def initialize(self, manifest: Mapping[str, object], *, harness_revision: str) -> str:
        """Bind one sealed manifest to a durable journal run."""

        normalized = _benchmark().validate_sealed_manifest(manifest)
        manifest_digest = _digest_json(manifest)
        run_id = f"run-{manifest_digest[7:23]}"
        contracts = _contracts(normalized)
        contracts_digest = _digest_json(contracts)
        row = self.connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is not None:
            expected = {
                "manifest_digest": manifest_digest,
                "task_plan_digest": normalized["task_plan_digest"],
                "contracts_digest": contracts_digest,
                "harness_revision": harness_revision,
            }
            if any(row[key] != value for key, value in expected.items()):
                raise EpisodeJournalError("existing journal run does not match the sealed manifest")
            self.verify(run_id)
            return run_id
        with self._transaction():
            self.connection.execute(
                """
                INSERT INTO runs(run_id, manifest_digest, task_plan_digest, contracts_digest, harness_revision, contracts_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    manifest_digest,
                    normalized["task_plan_digest"],
                    contracts_digest,
                    harness_revision,
                    _canonical_json(contracts),
                ),
            )
            self._append_event(
                run_id,
                "run.opened",
                None,
                None,
                {
                    "manifest_digest": manifest_digest,
                    "task_plan_digest": normalized["task_plan_digest"],
                    "contracts_digest": contracts_digest,
                    "harness_revision": harness_revision,
                },
            )
        return run_id

    def reserve(self, run_id: str, episode_id: str) -> str:
        """Reserve one fresh attempt after checking its sealed contract."""

        contract = self._contract(run_id, episode_id)
        events = self._events(run_id, episode_id)
        if events and events[-1]["kind"] == "episode.checkpointed" and events[-1]["payload"]["status"] == "completed":
            raise EpisodeJournalError("completed episode cannot be reserved again")
        attempt_number = 1 + max((event["attempt_number"] or 0 for event in events), default=0)
        attempt_id = f"{episode_id}:attempt:{attempt_number}"
        with self._transaction():
            self._append_event(
                run_id,
                "episode.reserved",
                episode_id,
                attempt_number,
                {"attempt_id": attempt_id, "contract_digest": _digest_json(contract)},
            )
        return attempt_id

    def start(self, run_id: str, episode_id: str, attempt_id: str, observed: Mapping[str, object]) -> None:
        """Record a pre-launch attestation of the actual immutable environment."""

        contract = self._contract(run_id, episode_id)
        expected_attempt = self._require_reservation(run_id, episode_id, attempt_id)
        if expected_attempt != attempt_id:
            raise EpisodeJournalError("episode attempt does not match its reservation")
        values = _mapping(observed, "observed environment")
        if set(values) != _OBSERVED_FIELDS:
            raise EpisodeJournalError("observed environment must contain exactly the sealed immutable digests")
        if any(values[name] != contract[name] for name in _OBSERVED_FIELDS):
            raise EpisodeJournalError("observed environment does not match the sealed episode contract")
        with self._transaction():
            self._append_event(
                run_id,
                "episode.started",
                episode_id,
                _attempt_number(attempt_id),
                {
                    "attempt_id": attempt_id,
                    "contract_digest": _digest_json(contract),
                    "observed": {name: values[name] for name in sorted(values)},
                },
            )

    def checkpoint(
        self,
        run_id: str,
        episode_id: str,
        attempt_id: str,
        *,
        status: str,
        result_digest: str,
        source_capture_set_digest: str,
        transcript_digest: str,
        synthetic_session_receipt_digest: str,
        token_usage: Mapping[str, int],
        integrity: Mapping[str, bool],
    ) -> None:
        """Append a terminal metadata-only checkpoint after external bytes are durable."""

        if status not in {"completed", "failed"}:
            raise EpisodeJournalError("checkpoint status must be completed or failed")
        contract = self._contract(run_id, episode_id)
        self._require_started(run_id, episode_id, attempt_id)
        usage = _mapping(token_usage, "token usage")
        if set(usage) != {"cache_hit_input_tokens", "cache_miss_input_tokens", "output_tokens"}:
            raise EpisodeJournalError("checkpoint token usage has an unexpected shape")
        if not all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in usage.values()):
            raise EpisodeJournalError("checkpoint token usage must be non-negative integers")
        checks = _mapping(integrity, "integrity")
        if not checks or not all(isinstance(value, bool) for value in checks.values()):
            raise EpisodeJournalError("checkpoint integrity must be non-empty booleans")
        payload = {
            "attempt_id": attempt_id,
            "contract_digest": _digest_json(contract),
            "status": status,
            "result_digest": _sha256_digest(result_digest, "result_digest"),
            "source_capture_set_digest": _sha256_digest(source_capture_set_digest, "source_capture_set_digest"),
            "transcript_digest": _sha256_digest(transcript_digest, "transcript_digest"),
            "synthetic_session_receipt_digest": _sha256_digest(
                synthetic_session_receipt_digest, "synthetic_session_receipt_digest"
            ),
            "token_usage": {name: usage[name] for name in sorted(usage)},
            "integrity": {name: checks[name] for name in sorted(checks)},
        }
        with self._transaction():
            self._append_event(run_id, "episode.checkpointed", episode_id, _attempt_number(attempt_id), payload)

    def abandon_started(self, run_id: str) -> tuple[str, ...]:
        """Invalidate every arm in an interrupted paired group.

        Restarting only one cell would mix fresh and stale observations within
        a comparison. Recovery discards the entire task/repeat/role group.
        """

        latest = self._latest_events(run_id)
        contracts = self._contracts_for_run(run_id)
        interrupted_groups = {
            contracts[episode_id]["pair_group_id"]
            for episode_id, event in latest.items()
            if event["kind"] == "episode.started"
        }
        invalidated = [
            episode_id for episode_id, contract in contracts.items() if contract["pair_group_id"] in interrupted_groups
        ]
        for episode_id in sorted(invalidated):
            event = latest.get(episode_id)
            with self._transaction():
                self._append_event(
                    run_id,
                    "episode.invalidated",
                    episode_id,
                    event["attempt_number"] if event else None,
                    {
                        "pair_group_id": contracts[episode_id]["pair_group_id"],
                        "previous_kind": event["kind"] if event else "unstarted",
                        "reason_code": "paired_recovery_after_start",
                    },
                )
        return tuple(sorted(invalidated))

    def pending(self, run_id: str) -> tuple[str, ...]:
        """Return episodes eligible for a fresh VM attempt after verification."""

        self.verify(run_id)
        completed = {
            episode_id
            for episode_id, event in self._latest_events(run_id).items()
            if event["kind"] == "episode.checkpointed" and event["payload"]["status"] == "completed"
        }
        return tuple(sorted(set(self._contracts_for_run(run_id)).difference(completed)))

    def verify(self, run_id: str) -> None:
        """Verify the HMAC-linked append-only event chain before any resume."""

        previous = "sha256:" + "0" * 64
        events = self._events(run_id)
        for sequence, event in enumerate(events, start=1):
            if event["sequence"] != sequence or event["previous_event_digest"] != previous:
                raise EpisodeJournalError("journal event sequence is not append-only")
            unsigned = {
                "run_id": event["run_id"],
                "sequence": event["sequence"],
                "kind": event["kind"],
                "episode_id": event["episode_id"],
                "attempt_number": event["attempt_number"],
                "payload": event["payload"],
                "previous_event_digest": event["previous_event_digest"],
                "created_at": event["created_at"],
            }
            event_digest = _digest_json(unsigned)
            if event["event_digest"] != event_digest:
                raise EpisodeJournalError("journal event digest is invalid")
            expected = hmac.new(self.attestation_key, event_digest.encode("ascii"), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(event["event_attestation"], expected):
                raise EpisodeJournalError("journal event attestation is invalid")
            previous = event_digest

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
              run_id TEXT PRIMARY KEY,
              manifest_digest TEXT NOT NULL,
              task_plan_digest TEXT NOT NULL,
              contracts_digest TEXT NOT NULL,
              harness_revision TEXT NOT NULL,
              contracts_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
              run_id TEXT NOT NULL REFERENCES runs(run_id),
              sequence INTEGER NOT NULL,
              kind TEXT NOT NULL,
              episode_id TEXT,
              attempt_number INTEGER,
              payload_json TEXT NOT NULL,
              previous_event_digest TEXT NOT NULL,
              event_digest TEXT NOT NULL,
              event_attestation TEXT NOT NULL,
              created_at TEXT NOT NULL,
              PRIMARY KEY (run_id, sequence)
            );
            CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
            BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
            CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
            BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
            """
        )

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise
        else:
            self.connection.execute("COMMIT")

    def _append_event(
        self,
        run_id: str,
        kind: str,
        episode_id: str | None,
        attempt_number: int | None,
        payload: Mapping[str, object],
    ) -> None:
        row = self.connection.execute(
            "SELECT sequence, event_digest FROM events WHERE run_id = ? ORDER BY sequence DESC LIMIT 1", (run_id,)
        ).fetchone()
        sequence = int(row["sequence"]) + 1 if row else 1
        previous = str(row["event_digest"]) if row else "sha256:" + "0" * 64
        created_at = datetime.now(UTC).isoformat()
        unsigned = {
            "run_id": run_id,
            "sequence": sequence,
            "kind": kind,
            "episode_id": episode_id,
            "attempt_number": attempt_number,
            "payload": dict(payload),
            "previous_event_digest": previous,
            "created_at": created_at,
        }
        event_digest = _digest_json(unsigned)
        attestation = hmac.new(self.attestation_key, event_digest.encode("ascii"), hashlib.sha256).hexdigest()
        self.connection.execute(
            """
            INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                sequence,
                kind,
                episode_id,
                attempt_number,
                _canonical_json(payload),
                previous,
                event_digest,
                attestation,
                created_at,
            ),
        )

    def _events(self, run_id: str, episode_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM events WHERE run_id = ?"
        values: tuple[object, ...] = (run_id,)
        if episode_id is not None:
            query += " AND episode_id = ?"
            values += (episode_id,)
        query += " ORDER BY sequence"
        rows = self.connection.execute(query, values).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]

    def _latest_events(self, run_id: str) -> dict[str, dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for event in self._events(run_id):
            if event["episode_id"]:
                latest[str(event["episode_id"])] = event
        return latest

    def _contracts_for_run(self, run_id: str) -> dict[str, dict[str, str]]:
        row = self.connection.execute("SELECT contracts_json FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise EpisodeJournalError("journal run does not exist")
        return json.loads(row["contracts_json"])

    def _contract(self, run_id: str, episode_id: str) -> dict[str, str]:
        contracts = self._contracts_for_run(run_id)
        try:
            return contracts[episode_id]
        except KeyError as error:
            raise EpisodeJournalError("episode is not in the sealed journal plan") from error

    def _require_reservation(self, run_id: str, episode_id: str, attempt_id: str) -> str:
        events = self._events(run_id, episode_id)
        if not events or events[-1]["kind"] != "episode.reserved":
            raise EpisodeJournalError("episode must be reserved before it starts")
        value = events[-1]["payload"]["attempt_id"]
        if value != attempt_id:
            raise EpisodeJournalError("episode attempt does not match its reservation")
        return str(value)

    def _require_started(self, run_id: str, episode_id: str, attempt_id: str) -> None:
        events = self._events(run_id, episode_id)
        if not events or events[-1]["kind"] != "episode.started" or events[-1]["payload"]["attempt_id"] != attempt_id:
            raise EpisodeJournalError("episode must be started before it checkpoints")


def _contracts(manifest: Mapping[str, object]) -> dict[str, dict[str, str]]:
    cells = {(cell["host"], cell["condition"]): cell for cell in manifest["cells"]}
    contracts: dict[str, dict[str, str]] = {}
    for entry in manifest["episode_plan"]:
        cell = cells[(entry["host"], entry["condition"])]
        contract = {
            "episode_id": str(entry["episode_id"]),
            "pair_group_id": _pair_group_id(entry),
            "model_version": str(manifest["model"]["version"]),
            "runtime_digest": str(cell["runtime_digest"]),
            "intervention_digest": str(cell["intervention_digest"]),
            "host_binding_digest": str(cell["host_binding_digest"]),
            "guest_rootfs_digest": str(cell["guest_rootfs_digest"]),
            "runner_input_digest": str(entry["runner_input_digest"]),
            "synthetic_user_assignment_digest": str(entry["synthetic_user_assignment_digest"]),
        }
        if set(contract) != _CONTRACT_FIELDS:
            raise EpisodeJournalError("sealed episode contract is incomplete")
        contracts[contract["episode_id"]] = contract
    return contracts


def _pair_group_id(entry: Mapping[str, object]) -> str:
    return "|".join((str(entry["task_id"]), str(entry["role"]), str(entry["repeat"])))


def _attempt_number(attempt_id: str) -> int:
    try:
        return int(attempt_id.rsplit(":", 1)[1])
    except (IndexError, ValueError) as error:
        raise EpisodeJournalError("attempt id is malformed") from error


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _digest_json(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("ascii")).hexdigest()


def _sha256_digest(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 71 or not value.startswith("sha256:"):
        raise EpisodeJournalError(f"{label} must be a SHA-256 digest")
    try:
        int(value[7:], 16)
    except ValueError as error:
        raise EpisodeJournalError(f"{label} must be a SHA-256 digest") from error
    return value


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise EpisodeJournalError(f"{label} must be a mapping with string keys")
    return value


def _benchmark():
    name = "_research_tree_evaluation_paired_benchmark"
    if name in sys.modules:
        return sys.modules[name]
    path = Path(__file__).with_name("paired_benchmark.py")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise EpisodeJournalError("unable to load paired benchmark validator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
