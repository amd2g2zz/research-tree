"""The alpha2 single-writer lifecycle coordinator.

This is intentionally small and explicit.  Existing product compilers remain
usable, but lifecycle, correction invalidation, and host-event idempotency have
one durable authority here.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from .contracts import HostEvent, canonical_json_bytes, validate_feedback_event
from .replay import explain_run, why_not_complete
from .leases import AttemptLease
from .host_events import reconcile_host_events
from .oracles import OracleAttempt, OracleRun, OracleSpec
from .closure import P0ClosureAggregate, SlotClosureAssessment


LIFECYCLE_STATES = frozenset({
    "alignment", "handoff_pending", "autonomous_research", "synthesis", "readiness",
    "delivery_pending", "awaiting_acceptance", "completed", "paused", "blocked",
    "superseded", "authority_blocked", "failed",
})
TERMINAL_STATES = frozenset({"completed", "superseded", "authority_blocked", "failed"})
TRANSITIONS = {
    ("alignment", "alignment_projection_ready"): ("handoff_pending", "coordinator"),
    ("alignment", "authority_impossible"): ("authority_blocked", "coordinator"),
    ("handoff_pending", "handoff_confirmed"): ("autonomous_research", "human"),
    ("handoff_pending", "alignment_feedback"): ("alignment", "human"),
    ("autonomous_research", "batch_checkpoint"): ("synthesis", "coordinator"),
    ("autonomous_research", "operational_limit"): ("paused", "coordinator"),
    ("synthesis", "closure_deficit"): ("autonomous_research", "coordinator"),
    ("synthesis", "all_slots_closed"): ("readiness", "coordinator"),
    ("readiness", "readiness_passed"): ("delivery_pending", "coordinator"),
    ("readiness", "readiness_deficit"): ("autonomous_research", "coordinator"),
    ("delivery_pending", "deliveries_compiled"): ("awaiting_acceptance", "coordinator"),
    ("awaiting_acceptance", "delivery_accepted"): ("completed", "human"),
    ("awaiting_acceptance", "needs_deeper_research"): ("autonomous_research", "human"),
    ("awaiting_acceptance", "intent_correction"): ("superseded", "coordinator"),
    ("paused", "resume"): ("autonomous_research", "coordinator"),
    ("blocked", "blocker_resolved"): ("autonomous_research", "coordinator"),
    ("alignment", "supersede"): ("superseded", "coordinator"),
    ("autonomous_research", "cancel_requested"): ("superseded", "human_or_operator"),
    ("autonomous_research", "fatal_failure"): ("failed", "coordinator"),
}
COMPLETION_OBLIGATIONS = (
    "p0_closure", "insight_clear", "readiness", "evaluation",
    "technical_delivery", "human_delivery", "acceptance",
)
ATTEMPT_BOUND_EVENT_TYPES = frozenset({
    "attempt_started", "finding_submitted", "review_completed",
    "provider_failed", "attempt_unknown", "retry_requested", "worker_finished",
})


class CoordinatorError(RuntimeError):
    """Stable error with a machine-readable code."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        next_action: str | None = None,
    ) -> None:
        super().__init__(f"{message} [{code}]")
        self.code = code
        self.next_action = next_action


class ResearchRunCoordinator:
    """SQLite-backed single authority for lifecycle and external host events."""

    error_type = CoordinatorError

    def __init__(self, workspace: str | Path) -> None:
        root = Path(workspace).resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.database = root / ".research-tree" / "run-ledger.sqlite3"
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            self._schema(connection)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    @staticmethod
    def _schema(connection: sqlite3.Connection) -> None:
        connection.executescript("""
        CREATE TABLE IF NOT EXISTS runs(
          run_id TEXT PRIMARY KEY, lifecycle_state TEXT NOT NULL, revision INTEGER NOT NULL,
          authority_digest TEXT NOT NULL, state_digest TEXT NOT NULL, task_identity_json TEXT NOT NULL,
          parent_run_id TEXT, termination_reason TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events(
          run_id TEXT NOT NULL, event_id TEXT NOT NULL, sequence INTEGER NOT NULL,
          event_type TEXT NOT NULL, expected_revision INTEGER NOT NULL, payload_json TEXT NOT NULL,
          payload_digest TEXT NOT NULL, accepted INTEGER NOT NULL, error_code TEXT,
          PRIMARY KEY(run_id,event_id), UNIQUE(run_id,sequence)
        );
        CREATE TABLE IF NOT EXISTS host_events(
          run_id TEXT NOT NULL, event_id TEXT NOT NULL, event_json TEXT NOT NULL,
          payload_digest TEXT NOT NULL, PRIMARY KEY(run_id,event_id)
        );
        CREATE TABLE IF NOT EXISTS invalidations(
          run_id TEXT NOT NULL, digest TEXT NOT NULL, reason TEXT NOT NULL,
          revision INTEGER NOT NULL, PRIMARY KEY(run_id,digest)
        );
        CREATE TABLE IF NOT EXISTS action_attempts(
          run_id TEXT NOT NULL, attempt_id TEXT NOT NULL, lease_json TEXT NOT NULL,
          updated_at TEXT NOT NULL, PRIMARY KEY(run_id,attempt_id),
          FOREIGN KEY(run_id) REFERENCES runs(run_id)
        );
        CREATE TABLE IF NOT EXISTS run_obligations(
          run_id TEXT NOT NULL, obligation TEXT NOT NULL, satisfied INTEGER NOT NULL DEFAULT 0,
          evidence_ref TEXT, updated_at TEXT NOT NULL,
          PRIMARY KEY(run_id,obligation), FOREIGN KEY(run_id) REFERENCES runs(run_id)
        );
        CREATE TABLE IF NOT EXISTS run_revisions(
          run_id TEXT NOT NULL, revision INTEGER NOT NULL,
          lifecycle_state TEXT NOT NULL, authority_digest TEXT NOT NULL,
          state_digest TEXT NOT NULL, task_identity_json TEXT NOT NULL,
          source_event_id TEXT NOT NULL, created_at TEXT NOT NULL,
          PRIMARY KEY(run_id,revision), FOREIGN KEY(run_id) REFERENCES runs(run_id)
        );
        CREATE TABLE IF NOT EXISTS attempt_invalidations(
          run_id TEXT NOT NULL, attempt_id TEXT NOT NULL, feedback_id TEXT NOT NULL,
          prior_status TEXT NOT NULL, revision INTEGER NOT NULL, reason TEXT NOT NULL,
          created_at TEXT NOT NULL, PRIMARY KEY(run_id,attempt_id,feedback_id),
          FOREIGN KEY(run_id,attempt_id) REFERENCES action_attempts(run_id,attempt_id)
        );
        CREATE TABLE IF NOT EXISTS oracle_specs(
          run_id TEXT NOT NULL, oracle_spec_id TEXT NOT NULL, oracle_spec_version INTEGER NOT NULL,
          payload_json TEXT NOT NULL, payload_digest TEXT NOT NULL, created_at TEXT NOT NULL,
          PRIMARY KEY(run_id,oracle_spec_id,oracle_spec_version),
          FOREIGN KEY(run_id) REFERENCES runs(run_id)
        );
        CREATE TABLE IF NOT EXISTS oracle_attempts(
          run_id TEXT NOT NULL, oracle_attempt_id TEXT NOT NULL, action_attempt_id TEXT NOT NULL,
          oracle_spec_id TEXT NOT NULL, oracle_spec_version INTEGER NOT NULL,
          oracle_spec_digest TEXT NOT NULL, payload_json TEXT NOT NULL,
          payload_digest TEXT NOT NULL, created_at TEXT NOT NULL,
          PRIMARY KEY(run_id,oracle_attempt_id),
          FOREIGN KEY(run_id,action_attempt_id) REFERENCES action_attempts(run_id,attempt_id),
          FOREIGN KEY(run_id,oracle_spec_id,oracle_spec_version)
            REFERENCES oracle_specs(run_id,oracle_spec_id,oracle_spec_version)
        );
        CREATE TABLE IF NOT EXISTS oracle_runs(
          run_id TEXT NOT NULL, oracle_run_id TEXT NOT NULL, oracle_attempt_id TEXT NOT NULL,
          oracle_spec_id TEXT NOT NULL,
          attempt_id TEXT NOT NULL, payload_json TEXT NOT NULL, payload_digest TEXT NOT NULL,
          created_at TEXT NOT NULL, PRIMARY KEY(run_id,oracle_run_id),
          FOREIGN KEY(run_id,oracle_attempt_id) REFERENCES oracle_attempts(run_id,oracle_attempt_id),
          FOREIGN KEY(run_id,attempt_id) REFERENCES action_attempts(run_id,attempt_id)
        );
        CREATE TABLE IF NOT EXISTS slot_closure_assessments(
          run_id TEXT NOT NULL, slot_id TEXT NOT NULL, assessment_revision INTEGER NOT NULL,
          blueprint_binding_revision INTEGER NOT NULL, payload_json TEXT NOT NULL,
          token_digest TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL,
          PRIMARY KEY(run_id,slot_id,assessment_revision), FOREIGN KEY(run_id) REFERENCES runs(run_id)
        );
        CREATE TABLE IF NOT EXISTS decision_slot_sets(
          run_id TEXT NOT NULL, binding_revision INTEGER NOT NULL,
          blueprint_artifact_id TEXT NOT NULL, blueprint_revision INTEGER NOT NULL,
          blueprint_content_hash TEXT NOT NULL, slots_json TEXT NOT NULL,
          created_at TEXT NOT NULL, PRIMARY KEY(run_id,binding_revision),
          FOREIGN KEY(run_id) REFERENCES runs(run_id)
        );
        CREATE TABLE IF NOT EXISTS p0_closure_aggregates(
          run_id TEXT NOT NULL, aggregate_revision INTEGER NOT NULL,
          blueprint_binding_revision INTEGER NOT NULL, payload_json TEXT NOT NULL,
          aggregate_digest TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
          PRIMARY KEY(run_id,aggregate_revision),
          FOREIGN KEY(run_id,blueprint_binding_revision)
            REFERENCES decision_slot_sets(run_id,binding_revision)
        );
        """)
        run_columns = {row[1] for row in connection.execute("PRAGMA table_info(runs)")}
        if "schema_version" not in run_columns:
            connection.execute("ALTER TABLE runs ADD COLUMN schema_version INTEGER NOT NULL DEFAULT 1")
        event_columns = {row[1] for row in connection.execute("PRAGMA table_info(events)")}
        for name, declaration in (
            ("causation_id", "TEXT"), ("correlation_id", "TEXT"),
            ("emitted_at", "TEXT NOT NULL DEFAULT ''"),
        ):
            if name not in event_columns:
                connection.execute(f"ALTER TABLE events ADD COLUMN {name} {declaration}")
        oracle_run_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(oracle_runs)")
        }
        if "oracle_attempt_id" not in oracle_run_columns:
            connection.execute("ALTER TABLE oracle_runs ADD COLUMN oracle_attempt_id TEXT")
        closure_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(slot_closure_assessments)")
        }
        if "blueprint_binding_revision" not in closure_columns:
            connection.execute(
                "ALTER TABLE slot_closure_assessments ADD COLUMN blueprint_binding_revision INTEGER"
            )
        connection.execute(
            """INSERT OR IGNORE INTO run_revisions(
                 run_id,revision,lifecycle_state,authority_digest,state_digest,
                 task_identity_json,source_event_id,created_at
               )
               SELECT run_id,revision,lifecycle_state,authority_digest,state_digest,
                      task_identity_json,'schema-backfill',updated_at
               FROM runs"""
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _digest(value: Any) -> str:
        return hashlib.sha256(canonical_json_bytes(value)).hexdigest()

    def create(self, run_id: str, *, task_identity: Mapping[str, Any] | None = None,
               authority: Mapping[str, Any] | None = None, parent_run_id: str | None = None) -> dict[str, Any]:
        now = self._now()
        identity = dict(task_identity or {})
        authority_digest = self._digest(authority or {})
        state_digest = self._digest({"run_id": run_id, "lifecycle_state": "alignment", "task_identity": identity})
        with self._connect() as connection:
            try:
                connection.execute("INSERT INTO runs(run_id,lifecycle_state,revision,authority_digest,state_digest,task_identity_json,parent_run_id,termination_reason,created_at,updated_at,schema_version) VALUES(?,?,?,?,?,?,?,?,?,?,1)", (run_id, "alignment", 0, authority_digest, state_digest, json.dumps(identity, ensure_ascii=False, sort_keys=True), parent_run_id, None, now, now))
            except sqlite3.IntegrityError as exc:
                raise CoordinatorError("run already exists", code="duplicate_run") from exc
            self._event(connection, run_id, "run-initialized", 0, {"task_identity": identity}, event_type="run_initialized")
            self._ensure_obligations(connection, run_id)
            self._snapshot_current_revision(
                connection, run_id, source_event_id="run-initialized"
            )
        return self.status(run_id)

    def status(self, run_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise CoordinatorError("run does not exist", code="run_not_found")
        return self._row(row)

    def events(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            self._require_run(connection, run_id)
            rows = connection.execute(
                "SELECT event_id,sequence,event_type,expected_revision,payload_json,payload_digest,accepted,error_code FROM events WHERE run_id=? ORDER BY sequence",
                (run_id,),
            ).fetchall()
        return [
            {"event_id": row["event_id"], "sequence": row["sequence"], "event_type": row["event_type"], "expected_revision": row["expected_revision"], "payload": json.loads(row["payload_json"]), "payload_digest": row["payload_digest"], "accepted": bool(row["accepted"]), "error_code": row["error_code"]}
            for row in rows
        ]

    def audit(self, run_id: str) -> dict[str, Any]:
        state = self.status(run_id)
        events = self.events(run_id)
        manifest = {"schema_version": 1, "run": state, "event_count": len(events), "events": events}
        manifest["manifest_digest"] = self._digest(manifest)
        return manifest

    def replay(self, run_id: str) -> dict[str, Any]:
        state = self.status(run_id)
        return explain_run(state, self.events(run_id))

    def why_not_complete(self, run_id: str) -> dict[str, Any]:
        state = self.status(run_id)
        records = self.obligations(run_id)
        unmet = [name for name, value in records.items() if not value["satisfied"]]
        return why_not_complete(state, unmet)

    def obligations(self, run_id: str) -> dict[str, dict[str, Any]]:
        with self._connect() as connection:
            self._require_run(connection, run_id)
            self._ensure_obligations(connection, run_id)
            rows = connection.execute("SELECT obligation,satisfied,evidence_ref,updated_at FROM run_obligations WHERE run_id=? ORDER BY obligation", (run_id,)).fetchall()
        return {row["obligation"]: {"satisfied": bool(row["satisfied"]), "evidence_ref": row["evidence_ref"], "updated_at": row["updated_at"]} for row in rows}

    def attempts(self, run_id: str) -> dict[str, dict[str, Any]]:
        """Return canonical attempt leases for diagnostics and reconciliation."""

        with self._connect() as connection:
            self._require_run(connection, run_id)
            rows = connection.execute(
                "SELECT attempt_id,lease_json FROM action_attempts WHERE run_id=? ORDER BY attempt_id",
                (run_id,),
            ).fetchall()
        return {row["attempt_id"]: json.loads(row["lease_json"]) for row in rows}

    def revisions(self, run_id: str) -> dict[int, dict[str, Any]]:
        """Return immutable canonical run snapshots indexed by revision."""

        with self._connect() as connection:
            self._require_run(connection, run_id)
            rows = connection.execute(
                """SELECT revision,lifecycle_state,authority_digest,state_digest,
                          task_identity_json,source_event_id,created_at
                   FROM run_revisions WHERE run_id=? ORDER BY revision""",
                (run_id,),
            ).fetchall()
        return {
            int(row["revision"]): {
                "run_id": run_id,
                "revision": int(row["revision"]),
                "lifecycle_state": row["lifecycle_state"],
                "authority_digest": row["authority_digest"],
                "state_digest": row["state_digest"],
                "task_identity": json.loads(row["task_identity_json"]),
                "source_event_id": row["source_event_id"],
                "created_at": row["created_at"],
            }
            for row in rows
        }

    def attempt_invalidations(self, run_id: str) -> dict[str, dict[str, Any]]:
        """Return attempt results quarantined by material feedback."""

        with self._connect() as connection:
            self._require_run(connection, run_id)
            rows = connection.execute(
                """SELECT attempt_id,feedback_id,prior_status,revision,reason,created_at
                   FROM attempt_invalidations WHERE run_id=? ORDER BY attempt_id,revision""",
                (run_id,),
            ).fetchall()
        return {
            row["attempt_id"]: {
                "feedback_id": row["feedback_id"],
                "prior_status": row["prior_status"],
                "revision": int(row["revision"]),
                "reason": row["reason"],
                "created_at": row["created_at"],
            }
            for row in rows
        }

    def record_obligation(self, run_id: str, obligation: str, *, evidence_ref: str, expected_revision: int) -> dict[str, Any]:
        if obligation not in COMPLETION_OBLIGATIONS or obligation in {"technical_delivery", "human_delivery", "acceptance"}:
            raise CoordinatorError("obligation must be recorded by its canonical boundary", code="invalid_obligation")
        if obligation == "p0_closure":
            raise CoordinatorError(
                "P0 closure is issued only by the core aggregate evaluator",
                code="closure_aggregate_required",
            )
        if not isinstance(evidence_ref, str) or not evidence_ref.strip():
            raise CoordinatorError("obligation evidence is required", code="missing_evidence")
        with self._connect() as connection:
            row = self._require_run(connection, run_id)
            if int(row["revision"]) != expected_revision:
                raise CoordinatorError("expected revision is stale", code="stale_revision")
            self._ensure_obligations(connection, run_id)
            revision = expected_revision + 1
            connection.execute("UPDATE run_obligations SET satisfied=1,evidence_ref=?,updated_at=? WHERE run_id=? AND obligation=?", (evidence_ref, self._now(), run_id, obligation))
            state = self._state_payload(row, lifecycle_state=row["lifecycle_state"], revision=revision, body={})
            connection.execute("UPDATE runs SET revision=?,state_digest=?,updated_at=? WHERE run_id=?", (revision, self._digest(state), self._now(), run_id))
            event_id = f"obligation-{obligation}-{revision}"
            self._snapshot_current_revision(connection, run_id, source_event_id=event_id)
            self._event(connection, run_id, event_id, expected_revision, {"obligation": obligation, "evidence_ref": evidence_ref}, event_type="obligation_satisfied")
        return self.status(run_id)

    def record_oracle_run(
        self,
        run_id: str,
        oracle_run: OracleRun | Mapping[str, Any],
        *,
        expected_revision: int,
    ) -> dict[str, Any]:
        parsed = oracle_run if isinstance(oracle_run, OracleRun) else OracleRun.from_mapping(oracle_run)
        payload = parsed.to_contract_dict()
        if payload["attempt_id"] != parsed.attempt_id:
            raise CoordinatorError("oracle attempt binding is inconsistent", code="attempt_binding_required")
        with self._connect() as connection:
            row = self._require_run(connection, run_id)
            if int(row["revision"]) != expected_revision:
                raise CoordinatorError("expected revision is stale", code="stale_revision")
            if connection.execute(
                "SELECT 1 FROM action_attempts WHERE run_id=? AND attempt_id=?",
                (run_id, parsed.attempt_id),
            ).fetchone() is None:
                raise CoordinatorError("oracle references an unknown attempt", code="attempt_not_found")
            attempt_row = connection.execute(
                """SELECT payload_json FROM oracle_attempts
                   WHERE run_id=? AND oracle_attempt_id=?""",
                (run_id, parsed.oracle_attempt_id),
            ).fetchone()
            if attempt_row is None:
                raise CoordinatorError(
                    "oracle references an unknown OracleAttempt",
                    code="oracle_attempt_not_found",
                )
            oracle_attempt = json.loads(attempt_row["payload_json"])
            expected_binding = {
                "action_attempt_id": payload["attempt_id"],
                "oracle_spec_id": payload["oracle_spec_id"],
                "oracle_spec_version": payload["oracle_spec_version"],
                "method": payload["method"],
                "input_digests": payload["input_digests"],
                "environment_digest": payload["environment_digest"],
                "toolchain_digest": payload["toolchain_digest"],
            }
            for field, expected in expected_binding.items():
                if oracle_attempt[field] != expected:
                    raise CoordinatorError(
                        f"oracle run does not match OracleAttempt field {field}",
                        code="oracle_attempt_binding_mismatch",
                    )
            for tool_event_ref in payload["tool_event_refs"]:
                if connection.execute(
                    "SELECT 1 FROM events WHERE run_id=? AND event_id=?",
                    (run_id, tool_event_ref),
                ).fetchone() is None:
                    raise CoordinatorError(
                        "oracle references an unresolved tool event",
                        code="tool_event_not_found",
                    )
            artifacts_available = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='artifacts'"
            ).fetchone()
            for artifact_ref in payload["result_artifact_refs"]:
                if artifact_ref["run_id"] != run_id:
                    raise CoordinatorError(
                        "oracle result artifact must belong to the current run",
                        code="result_artifact_scope_mismatch",
                    )
                artifact = None
                if artifacts_available is not None:
                    artifact = connection.execute(
                        """SELECT content_hash FROM artifacts
                           WHERE run_id=? AND artifact_id=? AND revision=?""",
                        (
                            artifact_ref["run_id"],
                            artifact_ref["artifact_id"],
                            artifact_ref["revision"],
                        ),
                    ).fetchone()
                if artifact is None:
                    raise CoordinatorError(
                        "oracle references an unresolved result artifact",
                        code="result_artifact_not_found",
                    )
                if artifact["content_hash"] != artifact_ref["content_hash"]:
                    raise CoordinatorError(
                        "oracle result artifact digest is stale",
                        code="stale_result_artifact",
                    )
            raw = canonical_json_bytes(payload)
            try:
                connection.execute(
                    """INSERT INTO oracle_runs(
                         run_id,oracle_run_id,oracle_attempt_id,oracle_spec_id,
                         attempt_id,payload_json,payload_digest,created_at
                       ) VALUES(?,?,?,?,?,?,?,?)""",
                    (run_id, parsed.oracle_run_id, parsed.oracle_attempt_id, parsed.oracle_spec_id, parsed.attempt_id, raw.decode("utf-8"), hashlib.sha256(raw).hexdigest(), self._now()),
                )
            except sqlite3.IntegrityError as error:
                raise CoordinatorError("oracle run is not immutable and unique", code="oracle_conflict") from error
            revision = expected_revision + 1
            state = self._state_payload(row, lifecycle_state=row["lifecycle_state"], revision=revision, body={})
            connection.execute(
                "UPDATE runs SET revision=?,state_digest=?,updated_at=? WHERE run_id=?",
                (revision, self._digest(state), self._now(), run_id),
            )
            event_id = f"oracle-run-{parsed.oracle_run_id}"
            self._event(connection, run_id, event_id, expected_revision, payload, event_type="oracle_run_recorded")
            self._snapshot_current_revision(connection, run_id, source_event_id=event_id)
        return self.status(run_id)

    def record_oracle_spec(
        self,
        run_id: str,
        oracle_spec: OracleSpec | Mapping[str, Any],
        *,
        expected_revision: int,
    ) -> dict[str, Any]:
        parsed = (
            oracle_spec
            if isinstance(oracle_spec, OracleSpec)
            else OracleSpec.from_mapping(oracle_spec)
        )
        payload = parsed.to_contract_dict()
        raw = canonical_json_bytes(payload)
        digest = hashlib.sha256(raw).hexdigest()
        with self._connect() as connection:
            row = self._require_run(connection, run_id)
            if int(row["revision"]) != expected_revision:
                raise CoordinatorError("expected revision is stale", code="stale_revision")
            try:
                connection.execute(
                    """INSERT INTO oracle_specs(
                         run_id,oracle_spec_id,oracle_spec_version,payload_json,
                         payload_digest,created_at
                       ) VALUES(?,?,?,?,?,?)""",
                    (
                        run_id,
                        parsed.oracle_id,
                        parsed.version,
                        raw.decode("utf-8"),
                        digest,
                        self._now(),
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise CoordinatorError(
                    "oracle specification is not immutable and unique",
                    code="oracle_spec_conflict",
                ) from error
            revision = expected_revision + 1
            state = self._state_payload(
                row, lifecycle_state=row["lifecycle_state"], revision=revision, body={}
            )
            connection.execute(
                "UPDATE runs SET revision=?,state_digest=?,updated_at=? WHERE run_id=?",
                (revision, self._digest(state), self._now(), run_id),
            )
            event_id = f"oracle-spec-{parsed.oracle_id}-{parsed.version}"
            self._event(
                connection,
                run_id,
                event_id,
                expected_revision,
                {"oracle_spec": payload, "contract_digest": digest},
                event_type="oracle_spec_recorded",
            )
            self._snapshot_current_revision(connection, run_id, source_event_id=event_id)
        return self.status(run_id)

    def oracle_specs(self, run_id: str) -> dict[str, dict[str, Any]]:
        with self._connect() as connection:
            self._require_run(connection, run_id)
            rows = connection.execute(
                """SELECT oracle_spec_id,oracle_spec_version,payload_json,payload_digest
                   FROM oracle_specs WHERE run_id=?
                   ORDER BY oracle_spec_id,oracle_spec_version""",
                (run_id,),
            ).fetchall()
        return {
            f"{row['oracle_spec_id']}@{row['oracle_spec_version']}": {
                **json.loads(row["payload_json"]),
                "contract_digest": row["payload_digest"],
            }
            for row in rows
        }

    def record_oracle_attempt(
        self,
        run_id: str,
        oracle_attempt: OracleAttempt | Mapping[str, Any],
        *,
        expected_revision: int,
    ) -> dict[str, Any]:
        parsed = (
            oracle_attempt
            if isinstance(oracle_attempt, OracleAttempt)
            else OracleAttempt.from_mapping(oracle_attempt)
        )
        payload = parsed.to_contract_dict()
        if parsed.run_id != run_id:
            raise CoordinatorError(
                "OracleAttempt must belong to the current run",
                code="oracle_attempt_scope_mismatch",
            )
        raw = canonical_json_bytes(payload)
        with self._connect() as connection:
            row = self._require_run(connection, run_id)
            if int(row["revision"]) != expected_revision:
                raise CoordinatorError("expected revision is stale", code="stale_revision")
            if connection.execute(
                "SELECT 1 FROM action_attempts WHERE run_id=? AND attempt_id=?",
                (run_id, parsed.action_attempt_id),
            ).fetchone() is None:
                raise CoordinatorError(
                    "OracleAttempt references an unknown action attempt",
                    code="attempt_not_found",
                )
            spec = connection.execute(
                """SELECT payload_json,payload_digest FROM oracle_specs
                   WHERE run_id=? AND oracle_spec_id=? AND oracle_spec_version=?""",
                (run_id, parsed.oracle_spec_id, parsed.oracle_spec_version),
            ).fetchone()
            if spec is None:
                raise CoordinatorError(
                    "OracleAttempt references an unknown OracleSpec revision",
                    code="oracle_spec_not_found",
                )
            if spec["payload_digest"] != parsed.oracle_spec_digest:
                raise CoordinatorError(
                    "OracleAttempt OracleSpec digest is stale",
                    code="stale_oracle_spec",
                )
            spec_payload = json.loads(spec["payload_json"])
            if spec_payload["invocation_adapter"] != parsed.method:
                raise CoordinatorError(
                    "OracleAttempt method does not match OracleSpec",
                    code="oracle_spec_method_mismatch",
                )
            try:
                connection.execute(
                    """INSERT INTO oracle_attempts(
                         run_id,oracle_attempt_id,action_attempt_id,oracle_spec_id,
                         oracle_spec_version,oracle_spec_digest,payload_json,
                         payload_digest,created_at
                       ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        run_id,
                        parsed.oracle_attempt_id,
                        parsed.action_attempt_id,
                        parsed.oracle_spec_id,
                        parsed.oracle_spec_version,
                        parsed.oracle_spec_digest,
                        raw.decode("utf-8"),
                        hashlib.sha256(raw).hexdigest(),
                        self._now(),
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise CoordinatorError(
                    "OracleAttempt is not immutable and unique",
                    code="oracle_attempt_conflict",
                ) from error
            revision = expected_revision + 1
            state = self._state_payload(
                row, lifecycle_state=row["lifecycle_state"], revision=revision, body={}
            )
            connection.execute(
                "UPDATE runs SET revision=?,state_digest=?,updated_at=? WHERE run_id=?",
                (revision, self._digest(state), self._now(), run_id),
            )
            event_id = f"oracle-attempt-{parsed.oracle_attempt_id}"
            self._event(
                connection,
                run_id,
                event_id,
                expected_revision,
                payload,
                event_type="oracle_attempt_recorded",
            )
            self._snapshot_current_revision(connection, run_id, source_event_id=event_id)
        return self.status(run_id)

    def oracle_attempts(self, run_id: str) -> dict[str, dict[str, Any]]:
        with self._connect() as connection:
            self._require_run(connection, run_id)
            rows = connection.execute(
                """SELECT oracle_attempt_id,payload_json FROM oracle_attempts
                   WHERE run_id=? ORDER BY oracle_attempt_id""",
                (run_id,),
            ).fetchall()
        return {
            row["oracle_attempt_id"]: json.loads(row["payload_json"]) for row in rows
        }

    def oracle_runs(self, run_id: str) -> dict[str, dict[str, Any]]:
        with self._connect() as connection:
            self._require_run(connection, run_id)
            rows = connection.execute(
                "SELECT oracle_run_id,payload_json FROM oracle_runs WHERE run_id=? ORDER BY oracle_run_id",
                (run_id,),
            ).fetchall()
        return {row["oracle_run_id"]: json.loads(row["payload_json"]) for row in rows}

    def closure_assessments(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            self._require_run(connection, run_id)
            rows = connection.execute(
                """SELECT payload_json FROM slot_closure_assessments
                   WHERE run_id=? ORDER BY slot_id,assessment_revision""",
                (run_id,),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def bind_blueprint_target(
        self,
        run_id: str,
        blueprint_target_ref: Mapping[str, Any],
        *,
        expected_revision: int,
    ) -> dict[str, Any]:
        """Bind one exact Blueprint Target as the source of active P0 Slots."""

        required = {"run_id", "artifact_id", "revision", "content_hash"}
        if not isinstance(blueprint_target_ref, Mapping) or set(blueprint_target_ref) != required:
            raise CoordinatorError(
                "blueprint target reference fields mismatch",
                code="blueprint_ref_invalid",
            )
        if blueprint_target_ref["run_id"] != run_id:
            raise CoordinatorError(
                "blueprint target belongs to another run",
                code="blueprint_scope_mismatch",
            )
        if (
            not isinstance(blueprint_target_ref["revision"], int)
            or isinstance(blueprint_target_ref["revision"], bool)
            or blueprint_target_ref["revision"] < 1
            or not isinstance(blueprint_target_ref["content_hash"], str)
            or len(blueprint_target_ref["content_hash"]) != 64
        ):
            raise CoordinatorError("blueprint target reference is invalid", code="blueprint_ref_invalid")
        with self._connect() as connection:
            row = self._require_run(connection, run_id)
            if int(row["revision"]) != expected_revision:
                raise CoordinatorError("expected revision is stale", code="stale_revision")
            artifact = connection.execute(
                """SELECT kind,content_hash,payload_json FROM artifacts
                   WHERE run_id=? AND artifact_id=? AND revision=?""",
                (run_id, blueprint_target_ref["artifact_id"], blueprint_target_ref["revision"]),
            ).fetchone()
            if artifact is None:
                raise CoordinatorError("blueprint target does not resolve", code="blueprint_not_found")
            if artifact["kind"] != "blueprint-target" or artifact["content_hash"] != blueprint_target_ref["content_hash"]:
                raise CoordinatorError("blueprint target reference is stale", code="stale_blueprint")
            try:
                slots = json.loads(artifact["payload_json"])["slots"]
            except (KeyError, TypeError, json.JSONDecodeError) as error:
                raise CoordinatorError("blueprint target slots are malformed", code="blueprint_slots_invalid") from error
            if not isinstance(slots, list) or not slots:
                raise CoordinatorError("blueprint target must contain slots", code="blueprint_slots_invalid")
            seen: set[str] = set()
            for slot in slots:
                if not isinstance(slot, Mapping):
                    raise CoordinatorError("blueprint target slot is malformed", code="blueprint_slots_invalid")
                slot_id = slot.get("id", slot.get("slot_id"))
                if not isinstance(slot_id, str) or not slot_id.strip() or slot_id in seen:
                    raise CoordinatorError("blueprint target Slot ids must be unique", code="blueprint_slots_invalid")
                seen.add(slot_id)
                if slot.get("priority") not in {"P0", "P1", "P2"}:
                    raise CoordinatorError("blueprint target Slot priority is invalid", code="blueprint_slots_invalid")
            prior = connection.execute(
                """SELECT binding_revision,blueprint_artifact_id,blueprint_revision
                   FROM decision_slot_sets WHERE run_id=? ORDER BY binding_revision DESC LIMIT 1""",
                (run_id,),
            ).fetchone()
            if prior is not None and (
                prior["blueprint_artifact_id"] == blueprint_target_ref["artifact_id"]
                and int(prior["blueprint_revision"]) == blueprint_target_ref["revision"]
            ):
                raise CoordinatorError("blueprint target is already bound", code="blueprint_binding_conflict")
            binding_revision = int(prior["binding_revision"]) + 1 if prior else 1
            connection.execute(
                """INSERT INTO decision_slot_sets(
                     run_id,binding_revision,blueprint_artifact_id,blueprint_revision,
                     blueprint_content_hash,slots_json,created_at
                   ) VALUES(?,?,?,?,?,?,?)""",
                (
                    run_id,
                    binding_revision,
                    blueprint_target_ref["artifact_id"],
                    blueprint_target_ref["revision"],
                    blueprint_target_ref["content_hash"],
                    canonical_json_bytes(slots).decode("utf-8"),
                    self._now(),
                ),
            )
            if prior is not None:
                self._revoke_latest_closures(
                    connection,
                    run_id,
                    binding_revision=int(prior["binding_revision"]),
                    reason="Blueprint Target revision superseded the closure parent",
                    event_expected_revision=expected_revision,
                )
            aggregate = self._persist_p0_closure_aggregate(
                connection,
                run_id,
                binding_revision=binding_revision,
                blueprint_target_ref=blueprint_target_ref,
            )
            self._ensure_obligations(connection, run_id)
            revision = expected_revision + 1
            state = self._state_payload(row, lifecycle_state=row["lifecycle_state"], revision=revision, body={})
            connection.execute(
                "UPDATE runs SET revision=?,state_digest=?,updated_at=? WHERE run_id=?",
                (revision, self._digest(state), self._now(), run_id),
            )
            event_id = f"blueprint-bound-{binding_revision}"
            self._event(
                connection,
                run_id,
                event_id,
                expected_revision,
                {"blueprint_target_ref": dict(blueprint_target_ref), "aggregate": aggregate},
                event_type="blueprint_target_bound",
            )
            self._snapshot_current_revision(connection, run_id, source_event_id=event_id)
        return self.status(run_id)

    def p0_closure_aggregates(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            self._require_run(connection, run_id)
            rows = connection.execute(
                """SELECT payload_json FROM p0_closure_aggregates
                   WHERE run_id=? ORDER BY aggregate_revision""",
                (run_id,),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def _current_blueprint_target_ref(
        self, connection: sqlite3.Connection, run_id: str
    ) -> tuple[int, dict[str, Any]] | None:
        binding = connection.execute(
            """SELECT binding_revision,blueprint_artifact_id,blueprint_revision,
                      blueprint_content_hash
               FROM decision_slot_sets WHERE run_id=?
               ORDER BY binding_revision DESC LIMIT 1""",
            (run_id,),
        ).fetchone()
        if binding is None:
            return None
        return int(binding["binding_revision"]), {
            "run_id": run_id,
            "artifact_id": binding["blueprint_artifact_id"],
            "revision": int(binding["blueprint_revision"]),
            "content_hash": binding["blueprint_content_hash"],
        }

    def _revoke_latest_closures(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        *,
        reason: str,
        event_expected_revision: int,
        binding_revision: int | None = None,
        decision_artifact_id: str | None = None,
        decision_revision: int | None = None,
    ) -> list[str]:
        rows = connection.execute(
            """SELECT slot_id,assessment_revision,blueprint_binding_revision,
                      payload_json,token_digest,status
               FROM slot_closure_assessments WHERE run_id=?""",
            (run_id,),
        ).fetchall()
        latest: dict[tuple[str, int], sqlite3.Row] = {}
        for row in rows:
            key = (row["slot_id"], int(row["blueprint_binding_revision"] or 0))
            if key not in latest or int(row["assessment_revision"]) > int(latest[key]["assessment_revision"]):
                latest[key] = row
        revoked: list[str] = []
        for row in latest.values():
            if row["status"] != "passed" or not row["token_digest"]:
                continue
            if binding_revision is not None and int(row["blueprint_binding_revision"] or 0) != binding_revision:
                continue
            prior = json.loads(row["payload_json"])
            parent = prior.get("decision_ref") or {}
            if decision_artifact_id is not None:
                if parent.get("artifact_id") != decision_artifact_id:
                    continue
                if decision_revision is not None and int(parent.get("revision", 0)) >= decision_revision:
                    continue
            revoked_payload = {
                **prior,
                "assessment_revision": int(row["assessment_revision"]) + 1,
                "status": "revoked",
                "token_digest": None,
                "revocation_reason": reason,
                "checks": {**dict(prior.get("checks", {})), "revoked": reason},
            }
            connection.execute(
                """INSERT INTO slot_closure_assessments(
                     run_id,slot_id,assessment_revision,blueprint_binding_revision,
                     payload_json,token_digest,status,created_at
                   ) VALUES(?,?,?,?,?,?,?,?)""",
                (
                    run_id,
                    row["slot_id"],
                    revoked_payload["assessment_revision"],
                    row["blueprint_binding_revision"],
                    canonical_json_bytes(revoked_payload).decode("utf-8"),
                    None,
                    "revoked",
                    self._now(),
                ),
            )
            token = str(row["token_digest"])
            revoked.append(token)
            self._event(
                connection,
                run_id,
                f"closure-revoked-{row['slot_id']}-{revoked_payload['assessment_revision']}",
                event_expected_revision,
                {
                    "slot_id": row["slot_id"],
                    "assessment_revision": revoked_payload["assessment_revision"],
                    "revoked_token": token,
                    "reason": reason,
                },
                event_type="slot_closure_revoked",
            )
        return revoked

    def _persist_p0_closure_aggregate(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        *,
        binding_revision: int,
        blueprint_target_ref: Mapping[str, Any],
    ) -> dict[str, Any]:
        binding = connection.execute(
            "SELECT slots_json FROM decision_slot_sets WHERE run_id=? AND binding_revision=?",
            (run_id, binding_revision),
        ).fetchone()
        if binding is None:
            raise CoordinatorError("blueprint binding does not resolve", code="blueprint_not_found")
        slots = json.loads(binding["slots_json"])
        active_p0 = [
            slot
            for slot in slots
            if slot.get("priority") == "P0"
            and slot.get("status") not in {"superseded", "removed"}
        ]
        latest_rows = connection.execute(
            """SELECT closure.payload_json
               FROM slot_closure_assessments AS closure
               JOIN (
                 SELECT slot_id,MAX(assessment_revision) AS assessment_revision
                 FROM slot_closure_assessments
                 WHERE run_id=? AND blueprint_binding_revision=?
                 GROUP BY slot_id
               ) AS latest
               ON latest.slot_id=closure.slot_id
              AND latest.assessment_revision=closure.assessment_revision
               WHERE closure.run_id=? AND closure.blueprint_binding_revision=?""",
            (run_id, binding_revision, run_id, binding_revision),
        ).fetchall()
        latest = {
            str(json.loads(row["payload_json"])["slot_id"]): json.loads(row["payload_json"])
            for row in latest_rows
        }
        prior = connection.execute(
            "SELECT COALESCE(MAX(aggregate_revision),0) FROM p0_closure_aggregates WHERE run_id=?",
            (run_id,),
        ).fetchone()[0]
        aggregate = P0ClosureAggregate.build(
            run_id=run_id,
            aggregate_revision=int(prior) + 1,
            blueprint_target_ref=blueprint_target_ref,
            active_slots=active_p0,
            latest_assessments=latest,
            assessor_version="core-closure-aggregate-v1",
            issued_at=self._now(),
        )
        payload = aggregate.to_contract_dict()
        connection.execute(
            """INSERT INTO p0_closure_aggregates(
                 run_id,aggregate_revision,blueprint_binding_revision,payload_json,
                 aggregate_digest,status,created_at
               ) VALUES(?,?,?,?,?,?,?)""",
            (
                run_id,
                aggregate.aggregate_revision,
                binding_revision,
                canonical_json_bytes(payload).decode("utf-8"),
                aggregate.aggregate_digest,
                aggregate.status,
                aggregate.issued_at,
            ),
        )
        self._ensure_obligations(connection, run_id)
        connection.execute(
            """UPDATE run_obligations SET satisfied=?,evidence_ref=?,updated_at=?
               WHERE run_id=? AND obligation='p0_closure'""",
            (1 if aggregate.status == "passed" else 0, aggregate.aggregate_digest, self._now(), run_id),
        )
        return payload

    def record_closure_assessment(
        self,
        run_id: str,
        assessment: SlotClosureAssessment,
        *,
        expected_revision: int,
    ) -> dict[str, Any]:
        payload = assessment.to_contract_dict()
        if payload["status"] != "passed" or not payload["token_digest"]:
            raise CoordinatorError("only a passed core assessment can close a slot", code="closure_not_passed")
        with self._connect() as connection:
            row = self._require_run(connection, run_id)
            if int(row["revision"]) != expected_revision:
                raise CoordinatorError("expected revision is stale", code="stale_revision")
            binding = connection.execute(
                """SELECT binding_revision,blueprint_artifact_id,blueprint_revision,
                          blueprint_content_hash,slots_json
                   FROM decision_slot_sets WHERE run_id=?
                   ORDER BY binding_revision DESC LIMIT 1""",
                (run_id,),
            ).fetchone()
            if binding is None:
                raise CoordinatorError(
                    "closure requires a bound Blueprint Target",
                    code="blueprint_not_bound",
                )
            bound_slots = json.loads(binding["slots_json"])
            slot = next(
                (
                    item
                    for item in bound_slots
                    if item.get("id", item.get("slot_id")) == assessment.slot_id
                ),
                None,
            )
            if slot is None:
                raise CoordinatorError(
                    "closure references a Slot outside the bound Blueprint Target",
                    code="closure_slot_not_found",
                )
            decision_ref = payload["decision_ref"]
            decision = connection.execute(
                """SELECT kind,content_hash,payload_json FROM artifacts
                   WHERE run_id=? AND artifact_id=? AND revision=?""",
                (decision_ref["run_id"], decision_ref["artifact_id"], decision_ref["revision"]),
            ).fetchone() if connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='artifacts'"
            ).fetchone() else None
            if decision is None:
                raise CoordinatorError("closure references an unresolved Decision Ledger revision", code="decision_not_found")
            if decision["kind"] != "decision-ledger-entry" or decision["content_hash"] != decision_ref["content_hash"]:
                raise CoordinatorError("closure decision reference is stale or has the wrong kind", code="stale_decision")
            decision_payload = json.loads(decision["payload_json"])
            if decision_payload.get("decision_slot_id") != assessment.slot_id:
                raise CoordinatorError(
                    "closure Slot differs from the Decision Ledger Slot",
                    code="closure_slot_mismatch",
                )
            if decision_payload.get("status") != payload["decision_status"]:
                raise CoordinatorError(
                    "closure decision status differs from the Decision Ledger",
                    code="closure_decision_status_mismatch",
                )
            if decision_payload.get("fallback") and decision_payload["fallback"] != payload["fallback"]:
                raise CoordinatorError(
                    "closure fallback differs from the Decision Ledger",
                    code="closure_fallback_mismatch",
                )
            if decision_payload.get("reversal_condition") and decision_payload["reversal_condition"] != payload["reversal_condition"]:
                raise CoordinatorError(
                    "closure reversal condition differs from the Decision Ledger",
                    code="closure_reversal_mismatch",
                )
            target_bound = decision_payload.get("blueprint_target_id") == binding["blueprint_artifact_id"]
            if not target_bound:
                target_bound = connection.execute(
                    """SELECT 1 FROM artifact_parents
                       WHERE run_id=? AND artifact_id=? AND revision=?
                         AND parent_artifact_id=? AND parent_revision=?""",
                    (
                        run_id,
                        decision_ref["artifact_id"],
                        decision_ref["revision"],
                        binding["blueprint_artifact_id"],
                        binding["blueprint_revision"],
                    ),
                ).fetchone() is not None
            if not target_bound:
                raise CoordinatorError(
                    "Decision Ledger revision is not bound to the current Blueprint Target",
                    code="decision_not_bound",
                )
            for oracle_ref in payload["oracle_refs"]:
                oracle = connection.execute(
                    "SELECT payload_json FROM oracle_runs WHERE run_id=? AND oracle_run_id=?",
                    (run_id, oracle_ref),
                ).fetchone()
                if oracle is None:
                    raise CoordinatorError("closure references an unresolved OracleRun", code="oracle_not_found")
                oracle_payload = json.loads(oracle["payload_json"])
                if oracle_payload.get("verdict") != "passed" or oracle_payload.get("reproducibility_status") != "reproducible":
                    raise CoordinatorError("closure references a nonpassing OracleRun", code="oracle_not_passing")
            try:
                connection.execute(
                    """INSERT INTO slot_closure_assessments(
                         run_id,slot_id,assessment_revision,blueprint_binding_revision,
                         payload_json,token_digest,status,created_at
                       ) VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        run_id,
                        assessment.slot_id,
                        assessment.assessment_revision,
                        binding["binding_revision"],
                        canonical_json_bytes(payload).decode("utf-8"),
                        assessment.token_digest,
                        "passed",
                        self._now(),
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise CoordinatorError("closure assessment revision already exists", code="closure_conflict") from error
            aggregate = self._persist_p0_closure_aggregate(
                connection,
                run_id,
                binding_revision=binding["binding_revision"],
                blueprint_target_ref={
                    "run_id": run_id,
                    "artifact_id": binding["blueprint_artifact_id"],
                    "revision": binding["blueprint_revision"],
                    "content_hash": binding["blueprint_content_hash"],
                },
            )
            revision = expected_revision + 1
            state = self._state_payload(row, lifecycle_state=row["lifecycle_state"], revision=revision, body={})
            connection.execute(
                "UPDATE runs SET revision=?,state_digest=?,updated_at=? WHERE run_id=?",
                (revision, self._digest(state), self._now(), run_id),
            )
            event_id = f"slot-closure-{assessment.slot_id}-{assessment.assessment_revision}"
            self._event(
                connection,
                run_id,
                event_id,
                expected_revision,
                {**payload, "p0_closure_aggregate": aggregate},
                event_type="slot_closure_recorded",
            )
            self._snapshot_current_revision(connection, run_id, source_event_id=event_id)
        return self.status(run_id)

    def next_actions(self, run_id: str) -> dict[str, Any]:
        state = self.status(run_id)
        return {
            "run_id": run_id,
            "lifecycle_state": state["lifecycle_state"],
            "next_action": self._next_action_for_state(state["lifecycle_state"]),
            "revision": state["revision"],
        }

    @staticmethod
    def _next_action_for_state(lifecycle_state: str) -> str:
        mapping = {
            "alignment": "plan_alignment",
            "handoff_pending": "confirm_handoff",
            "autonomous_research": "dispatch_or_recover",
            "synthesis": "synthesize_and_replan",
            "readiness": "evaluate_readiness",
            "delivery_pending": "compile_deliveries",
            "awaiting_acceptance": "accept_or_request_depth",
            "paused": "resume_or_change_method",
            "blocked": "resolve_blocker_or_request_authority",
        }
        return mapping.get(lifecycle_state, "export_audit")

    def recover(self, run_id: str) -> dict[str, Any]:
        """Return a deterministic recovery projection; unknown host events remain visible."""

        state = self.status(run_id)
        return {"run_id": run_id, "state": state, "reconciled_events": [], "next_action": self.next_actions(run_id)["next_action"]}

    def reconcile_host(self, run_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            self._require_run(connection, run_id)
            attempts = {
                row["attempt_id"]: json.loads(row["lease_json"])
                for row in connection.execute("SELECT attempt_id,lease_json FROM action_attempts WHERE run_id=?", (run_id,)).fetchall()
            }
            events = [json.loads(row["event_json"]) for row in connection.execute("SELECT event_json FROM host_events WHERE run_id=? ORDER BY event_id", (run_id,)).fetchall()]
        result = reconcile_host_events(canonical_attempts=attempts, host_events=events)
        result["run_id"] = run_id
        return result

    def issue_lease(self, lease: AttemptLease, *, expected_revision: int) -> dict[str, Any]:
        """Persist a new attempt lease and advance the run revision atomically."""
        with self._connect() as connection:
            row = self._require_run(connection, lease.run_id)
            if int(row["revision"]) != expected_revision:
                raise CoordinatorError("expected revision is stale", code="stale_revision")
            self._assert_current_in_connection(
                connection, lease.run_id, lease.dispatch_digest, action="dispatch"
            )
            if connection.execute("SELECT 1 FROM action_attempts WHERE run_id=? AND attempt_id=?", (lease.run_id, lease.attempt_id)).fetchone():
                raise CoordinatorError("attempt already exists", code="duplicate_attempt")
            revision = expected_revision + 1
            state = self._state_payload(row, lifecycle_state=row["lifecycle_state"], revision=revision, body={})
            connection.execute("INSERT INTO action_attempts VALUES(?,?,?,?)", (lease.run_id, lease.attempt_id, json.dumps(lease.to_dict(), sort_keys=True), self._now()))
            connection.execute("UPDATE runs SET revision=?,state_digest=?,updated_at=? WHERE run_id=?", (revision, self._digest(state), self._now(), lease.run_id))
            event_id = "attempt-started-" + lease.attempt_id
            self._snapshot_current_revision(connection, lease.run_id, source_event_id=event_id)
            self._event(connection, lease.run_id, event_id, expected_revision, lease.to_dict(), event_type="attempt_lease_issued")
        return self.status(lease.run_id)

    def heartbeat_lease(self, run_id: str, attempt_id: str, *, now: str, lease_seconds: int | None = None) -> dict[str, Any]:
        with self._connect() as connection:
            self._require_run(connection, run_id)
            row = connection.execute("SELECT lease_json FROM action_attempts WHERE run_id=? AND attempt_id=?", (run_id, attempt_id)).fetchone()
            if row is None:
                raise CoordinatorError("attempt does not exist", code="attempt_not_found")
            lease = AttemptLease.from_dict(json.loads(row["lease_json"])).heartbeat(now=now, lease_seconds=lease_seconds)
            connection.execute("UPDATE action_attempts SET lease_json=?,updated_at=? WHERE run_id=? AND attempt_id=?", (json.dumps(lease.to_dict(), sort_keys=True), self._now(), run_id, attempt_id))
        return lease.to_dict()

    def expire_leases(self, run_id: str, *, now: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            self._require_run(connection, run_id)
            rows = connection.execute("SELECT attempt_id,lease_json FROM action_attempts WHERE run_id=?", (run_id,)).fetchall()
            expired: list[dict[str, Any]] = []
            for row in rows:
                lease = AttemptLease.from_dict(json.loads(row["lease_json"])).expire(now=now)
                if lease.status == "unknown":
                    connection.execute("UPDATE action_attempts SET lease_json=?,updated_at=? WHERE run_id=? AND attempt_id=?", (json.dumps(lease.to_dict(), sort_keys=True), self._now(), run_id, row["attempt_id"]))
                    expired.append(lease.to_dict())
        return expired

    def retry_attempt(
        self,
        run_id: str,
        attempt_id: str,
        *,
        dispatch_digest: str,
        expected_revision: int,
        lease_seconds: int = 900,
    ) -> dict[str, Any]:
        """Create a distinct retry attempt after a retryable/unknown outcome."""

        if lease_seconds <= 0:
            raise CoordinatorError("lease_seconds must be positive", code="invalid_lease")
        now = datetime.now(timezone.utc)
        with self._connect() as connection:
            row = self._require_run(connection, run_id)
            if int(row["revision"]) != expected_revision:
                raise CoordinatorError("expected revision is stale", code="stale_revision")
            self._assert_current_in_connection(
                connection, run_id, dispatch_digest, action="retry"
            )
            prior_row = connection.execute(
                "SELECT lease_json FROM action_attempts WHERE run_id=? AND attempt_id=?",
                (run_id, attempt_id),
            ).fetchone()
            if prior_row is None:
                raise CoordinatorError("attempt does not exist", code="attempt_not_found")
            prior = AttemptLease.from_dict(json.loads(prior_row["lease_json"]))
            if prior.status not in {"retryable", "unknown"}:
                raise CoordinatorError(
                    "only retryable or unknown attempts can retry",
                    code="attempt_not_retryable",
                )
            try:
                retry = prior.retry(dispatch_digest=dispatch_digest)
            except ValueError as exc:
                raise CoordinatorError(str(exc), code="invalid_retry") from exc
            retry = replace(
                retry,
                started_at=now.isoformat(),
                lease_expires_at=(now + timedelta(seconds=lease_seconds)).isoformat(),
                last_seen_at=None,
            )
            if connection.execute(
                "SELECT 1 FROM action_attempts WHERE run_id=? AND attempt_id=?",
                (run_id, retry.attempt_id),
            ).fetchone():
                raise CoordinatorError("retry attempt already exists", code="duplicate_attempt")
            revision = expected_revision + 1
            state = self._state_payload(row, lifecycle_state=row["lifecycle_state"], revision=revision, body={})
            connection.execute(
                "INSERT INTO action_attempts VALUES(?,?,?,?)",
                (run_id, retry.attempt_id, json.dumps(retry.to_dict(), sort_keys=True), self._now()),
            )
            connection.execute(
                "UPDATE runs SET revision=?,state_digest=?,updated_at=? WHERE run_id=?",
                (revision, self._digest(state), self._now(), run_id),
            )
            self._snapshot_current_revision(
                connection,
                run_id,
                source_event_id=f"retry-requested-{retry.attempt_id}",
            )
            self._event(
                connection,
                run_id,
                f"retry-requested-{retry.attempt_id}",
                expected_revision,
                {"predecessor_attempt": attempt_id, "retry": retry.to_dict()},
                event_type="retry_requested",
            )
        return {"run": self.status(run_id), "predecessor": prior.to_dict(), "retry": retry.to_dict()}

    def why_action(self, run_id: str) -> dict[str, Any]:
        state = self.status(run_id)
        return {"run_id": run_id, "selected_action": self.next_actions(run_id)["next_action"], "inputs": {"lifecycle_state": state["lifecycle_state"], "revision": state["revision"], "state_digest": state["state_digest"]}, "rejected_alternatives": [], "evidence_refs": []}

    def deliver(self, run_id: str, *, expected_revision: int, technical_digest: str, human_digest: str) -> dict[str, Any]:
        return self.transition(run_id, event="deliveries_compiled", actor="coordinator", expected_revision=expected_revision, payload={"technical_digest": technical_digest, "human_digest": human_digest})

    def accept(self, run_id: str, *, expected_revision: int, displayed_digest: str, technical_revision: str | None = None, human_revision: str | None = None, feedback: str | None = None) -> dict[str, Any]:
        return self.transition(run_id, event="delivery_accepted", actor="human", expected_revision=expected_revision, payload={"displayed_digest": displayed_digest, "technical_revision": technical_revision, "human_revision": human_revision, "feedback": feedback})

    def transition(self, run_id: str, *, event: str, actor: str,
                   expected_revision: int, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        body = dict(payload or {})
        rejection: CoordinatorError | None = None
        with self._connect() as connection:
            row = self._require_run(connection, run_id)
            try:
                if row["revision"] != expected_revision:
                    raise CoordinatorError("expected revision is stale", code="stale_revision")
                for field, value in body.items():
                    if field.endswith("_digest") and isinstance(value, str):
                        self._assert_current_in_connection(
                            connection, run_id, value, action=event
                        )
                if row["lifecycle_state"] in TERMINAL_STATES:
                    if event == "delivery_accepted" and row["lifecycle_state"] == "completed":
                        return self._row(row)
                    raise CoordinatorError("terminal state cannot transition", code="terminal_state")
                target = TRANSITIONS.get((row["lifecycle_state"], event))
                if target is None:
                    raise CoordinatorError("illegal transition", code="illegal_transition")
                next_state, required_actor = target
                if required_actor != actor and required_actor != "human_or_operator":
                    raise CoordinatorError("actor is not authorized for transition", code="authority_denied")
                if event == "handoff_confirmed":
                    displayed = body.get("displayed_digest")
                    if not displayed or displayed != self._authority_digest(row):
                        raise CoordinatorError("confirmation digest is stale", code="stale_digest")
                self._guard_transition(connection, row, event, body)
            except CoordinatorError as error:
                self._record_rejected_transition(
                    connection,
                    row,
                    event=event,
                    actor=actor,
                    attempted_revision=expected_revision,
                    payload=body,
                    error=error,
                )
                rejection = error
            else:
                revision = int(row["revision"]) + 1
                now = self._now()
                state = self._state_payload(row, lifecycle_state=next_state, revision=revision, body=body)
                digest = self._digest(state)
                authority_digest = body.get("strategy_digest") if event == "alignment_projection_ready" else row["authority_digest"]
                connection.execute("UPDATE runs SET lifecycle_state=?,revision=?,state_digest=?,authority_digest=?,updated_at=?,termination_reason=? WHERE run_id=?", (next_state, revision, digest, authority_digest or row["authority_digest"], now, body.get("termination_reason"), run_id))
                if event == "deliveries_compiled":
                    connection.execute("UPDATE run_obligations SET satisfied=1,evidence_ref=?,updated_at=? WHERE run_id=? AND obligation='technical_delivery'", (body["technical_digest"], now, run_id))
                    connection.execute("UPDATE run_obligations SET satisfied=1,evidence_ref=?,updated_at=? WHERE run_id=? AND obligation='human_delivery'", (body["human_digest"], now, run_id))
                elif event == "delivery_accepted":
                    connection.execute("UPDATE run_obligations SET satisfied=1,evidence_ref=?,updated_at=? WHERE run_id=? AND obligation='acceptance'", (body["displayed_digest"], now, run_id))
                elif event == "needs_deeper_research":
                    connection.execute("UPDATE run_obligations SET satisfied=0,updated_at=? WHERE run_id=? AND obligation IN ('readiness','evaluation','technical_delivery','human_delivery','acceptance')", (now, run_id))
                event_id = f"{event}-{revision}"
                self._snapshot_current_revision(connection, run_id, source_event_id=event_id)
                self._event(connection, run_id, event_id, expected_revision, body, event_type=event)
        if rejection is not None:
            raise rejection
        return self.status(run_id)

    def record_feedback(self, value: Mapping[str, Any], *, expected_revision: int) -> dict[str, Any]:
        feedback = validate_feedback_event(value)
        run_id = feedback["run_id"]
        with self._connect() as connection:
            row = self._require_run(connection, run_id)
            if row["revision"] != expected_revision:
                raise CoordinatorError("expected revision is stale", code="stale_revision")
            self._snapshot_current_revision(
                connection,
                run_id,
                source_event_id="feedback-predecessor-" + feedback["feedback_id"],
            )
            revision = int(row["revision"]) + 1
            invalidation_refs = list(feedback["target_refs"]) + list(
                feedback.get("invalidated_refs", [])
            )
            invalidated = sorted(
                {
                    str(ref).split(":", 1)[1]
                    for ref in invalidation_refs
                    if str(ref).startswith("strategy:")
                }
            )
            invalidated_attempt_ids: list[str] = []
            invalidated_obligations: list[str] = []
            revoked_closure_tokens: list[str] = []
            if feedback["materiality"] in {"material", "terminal"}:
                for digest in invalidated:
                    connection.execute("INSERT OR IGNORE INTO invalidations VALUES(?,?,?,?)", (run_id, digest, feedback["message"], revision))
                self._ensure_obligations(connection, run_id)
                invalidated_obligations = [
                    item["obligation"]
                    for item in connection.execute(
                        "SELECT obligation FROM run_obligations WHERE run_id=? AND satisfied=1 ORDER BY obligation",
                        (run_id,),
                    ).fetchall()
                ]
                connection.execute("UPDATE run_obligations SET satisfied=0,updated_at=? WHERE run_id=?", (self._now(), run_id))
                revoked_closure_tokens = self._revoke_latest_closures(
                    connection,
                    run_id,
                    reason=f"human feedback invalidated prior closure: {feedback['message']}",
                    event_expected_revision=expected_revision,
                )
                binding = connection.execute(
                    """SELECT binding_revision,blueprint_artifact_id,blueprint_revision,
                              blueprint_content_hash
                       FROM decision_slot_sets WHERE run_id=?
                       ORDER BY binding_revision DESC LIMIT 1""",
                    (run_id,),
                ).fetchone()
                if binding is not None:
                    self._persist_p0_closure_aggregate(
                        connection,
                        run_id,
                        binding_revision=binding["binding_revision"],
                        blueprint_target_ref={
                            "run_id": run_id,
                            "artifact_id": binding["blueprint_artifact_id"],
                            "revision": binding["blueprint_revision"],
                            "content_hash": binding["blueprint_content_hash"],
                        },
                    )
                for attempt in connection.execute(
                    "SELECT attempt_id,lease_json FROM action_attempts WHERE run_id=? ORDER BY attempt_id",
                    (run_id,),
                ).fetchall():
                    lease = AttemptLease.from_dict(json.loads(attempt["lease_json"]))
                    if lease.dispatch_digest not in invalidated:
                        continue
                    invalidated_attempt_ids.append(lease.attempt_id)
                    connection.execute(
                        """INSERT OR IGNORE INTO attempt_invalidations(
                             run_id,attempt_id,feedback_id,prior_status,revision,reason,created_at
                           ) VALUES(?,?,?,?,?,?,?)""",
                        (
                            run_id,
                            lease.attempt_id,
                            feedback["feedback_id"],
                            lease.status,
                            revision,
                            feedback["message"],
                            self._now(),
                        ),
                    )
            identity = feedback.get("successor_task_identity") or json.loads(row["task_identity_json"])
            next_state = "alignment" if feedback["materiality"] == "material" else row["lifecycle_state"]
            state = self._state_payload(row, lifecycle_state=next_state, revision=revision, body={"task_identity": identity, "feedback_id": feedback["feedback_id"]})
            digest = self._digest(state)
            connection.execute("UPDATE runs SET lifecycle_state=?,revision=?,state_digest=?,task_identity_json=?,updated_at=? WHERE run_id=?", (next_state, revision, digest, json.dumps(identity, ensure_ascii=False, sort_keys=True), self._now(), run_id))
            event_id = "feedback-" + feedback["feedback_id"]
            self._snapshot_current_revision(
                connection, run_id, source_event_id=event_id
            )
            event_payload = dict(feedback)
            event_payload.update(
                {
                    "predecessor_revision": expected_revision,
                    "predecessor_state_digest": row["state_digest"],
                    "successor_revision": revision,
                    "successor_state_digest": digest,
                    "invalidated_digests": invalidated,
                    "invalidated_attempt_ids": invalidated_attempt_ids,
                    "invalidated_obligations": invalidated_obligations,
                    "revoked_closure_tokens": revoked_closure_tokens,
                }
            )
            self._event(connection, run_id, event_id, expected_revision, event_payload, event_type="feedback_recorded")
        result = self.status(run_id)
        result["invalidated_digests"] = sorted(invalidated)
        return result

    def assert_current(self, run_id: str, digest: str, *, action: str) -> None:
        with self._connect() as connection:
            self._require_run(connection, run_id)
            self._assert_current_in_connection(connection, run_id, digest, action=action)

    @staticmethod
    def _assert_current_in_connection(
        connection: sqlite3.Connection,
        run_id: str,
        digest: str,
        *,
        action: str,
    ) -> None:
        if connection.execute(
            "SELECT 1 FROM invalidations WHERE run_id=? AND digest=?",
            (run_id, digest),
        ).fetchone():
            raise CoordinatorError(
                f"{action} references an invalidated digest",
                code="stale_digest",
                next_action="return_to_alignment_and_rederive_strategy",
            )

    def ingest_host_event(self, event: HostEvent | Mapping[str, Any]) -> dict[str, Any]:
        host_event = event if isinstance(event, HostEvent) else HostEvent.from_dict(event)
        payload = host_event.to_dict()
        with self._connect() as connection:
            row = self._require_run(connection, host_event.run_id)
            raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            prior = connection.execute("SELECT event_json,payload_digest FROM host_events WHERE run_id=? AND event_id=?", (host_event.run_id, host_event.event_id)).fetchone()
            if prior:
                if prior["payload_digest"] != host_event.payload_digest:
                    raise CoordinatorError("event id reused with different payload", code="event_id_conflict")
                return json.loads(prior["event_json"])
            if row["revision"] != host_event.expected_revision:
                raise CoordinatorError("host event expected revision is stale", code="stale_revision")
            if host_event.event_type in ATTEMPT_BOUND_EVENT_TYPES:
                if not host_event.attempt_id:
                    raise CoordinatorError(
                        "attempt-bound host event requires attempt_id",
                        code="attempt_binding_required",
                    )
                attempt = connection.execute(
                    "SELECT lease_json FROM action_attempts WHERE run_id=? AND attempt_id=?",
                    (host_event.run_id, host_event.attempt_id),
                ).fetchone()
                if attempt is None:
                    raise CoordinatorError(
                        "host event references an unknown attempt",
                        code="attempt_not_found",
                    )
                if connection.execute(
                    "SELECT 1 FROM attempt_invalidations WHERE run_id=? AND attempt_id=?",
                    (host_event.run_id, host_event.attempt_id),
                ).fetchone():
                    raise CoordinatorError(
                        "attempt was invalidated by material feedback",
                        code="attempt_invalidated",
                        next_action="replan_and_create_new_attempt",
                    )
                lease_status = json.loads(attempt["lease_json"]).get("status")
                if lease_status == "unknown" and host_event.event_type != "attempt_unknown":
                    raise CoordinatorError(
                        "expired attempt cannot report success",
                        code="attempt_expired",
                    )
            self._event(connection, host_event.run_id, host_event.event_id, host_event.expected_revision, payload, event_type=host_event.event_type)
            revision = int(row["revision"]) + 1
            state = self._state_payload(row, lifecycle_state=row["lifecycle_state"], revision=revision, body={})
            connection.execute(
                "UPDATE runs SET revision=?,state_digest=?,updated_at=? WHERE run_id=?",
                (revision, self._digest(state), self._now(), host_event.run_id),
            )
            connection.execute("INSERT INTO host_events VALUES(?,?,?,?)", (host_event.run_id, host_event.event_id, raw, host_event.payload_digest))
            self._apply_host_event_effect(connection, host_event)
            self._snapshot_current_revision(
                connection,
                host_event.run_id,
                source_event_id=host_event.event_id,
            )
        return payload

    def _apply_host_event_effect(self, connection: sqlite3.Connection, event: HostEvent) -> None:
        """Project an accepted host observation onto its canonical attempt lease.

        This is intentionally narrower than lifecycle completion: host events
        may advance an attempt to a reviewable or recoverable state, but only
        coordinator obligations and human acceptance can close a run.
        """

        if not event.attempt_id:
            return
        row = connection.execute(
            "SELECT lease_json FROM action_attempts WHERE run_id=? AND attempt_id=?",
            (event.run_id, event.attempt_id),
        ).fetchone()
        if row is None:
            return
        lease = AttemptLease.from_dict(json.loads(row["lease_json"]))
        status: str | None = None
        if event.event_type == "attempt_started":
            status = "running"
        elif event.event_type == "finding_submitted":
            status = "submitted"
        elif event.event_type == "review_completed":
            status = "verified" if event.payload.get("accepted_refs") else "rejected"
        elif event.event_type == "provider_failed":
            category = str(event.payload.get("retry_category", "unknown")).casefold()
            status = "retryable" if category in {"retryable", "transient", "context_limit"} else "unknown"
        elif event.event_type == "attempt_unknown":
            status = "unknown"
        elif event.event_type == "retry_requested":
            status = "retryable"
        elif event.event_type == "worker_finished":
            terminal = str(event.payload.get("terminal_status", "")).casefold()
            status = "submitted" if terminal in {"completed", "verified", "success", "submitted"} else "rejected"
        if status is None or lease.status == status:
            return
        updated = replace(lease, status=status, last_seen_at=self._now())
        connection.execute(
            "UPDATE action_attempts SET lease_json=?,updated_at=? WHERE run_id=? AND attempt_id=?",
            (json.dumps(updated.to_dict(), sort_keys=True), self._now(), event.run_id, event.attempt_id),
        )

    def _authority_digest(self, row: sqlite3.Row) -> str:
        return str(row["authority_digest"])

    def _state_payload(self, row: sqlite3.Row, *, lifecycle_state: str, revision: int, body: Mapping[str, Any]) -> dict[str, Any]:
        return {"run_id": row["run_id"], "revision": revision, "lifecycle_state": lifecycle_state, "task_identity": body.get("task_identity", json.loads(row["task_identity_json"])), "feedback_id": body.get("feedback_id")}

    def _event(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        event_id: str,
        expected_revision: int,
        payload: Mapping[str, Any],
        *,
        event_type: str | None = None,
        accepted: bool = True,
        error_code: str | None = None,
        idempotent: bool = False,
    ) -> None:
        sequence = int(connection.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM events WHERE run_id=?", (run_id,)).fetchone()[0])
        raw = canonical_json_bytes(payload)
        insert = "INSERT OR IGNORE" if idempotent else "INSERT"
        connection.execute(
            f"{insert} INTO events(run_id,event_id,sequence,event_type,expected_revision,payload_json,payload_digest,accepted,error_code,causation_id,correlation_id,emitted_at) VALUES(?,?,?,?,?,?,?,?,?,NULL,NULL,?)",
            (
                run_id,
                event_id,
                sequence,
                event_type or event_id,
                expected_revision,
                raw.decode("utf-8"),
                hashlib.sha256(raw).hexdigest(),
                int(accepted),
                error_code,
                self._now(),
            ),
        )

    def _record_rejected_transition(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        *,
        event: str,
        actor: str,
        attempted_revision: int,
        payload: Mapping[str, Any],
        error: CoordinatorError,
    ) -> None:
        payload_digest = self._digest(payload)
        rejection = {
            "actor": actor,
            "actual_revision": int(row["revision"]),
            "attempted_event": event,
            "attempted_revision": attempted_revision,
            "current_state": row["lifecycle_state"],
            "next_action": error.next_action
            or self._next_action_for_state(row["lifecycle_state"]),
            "payload_digest": payload_digest,
            "reason_code": error.code,
        }
        fingerprint = self._digest({"run_id": row["run_id"], **rejection})
        self._event(
            connection,
            row["run_id"],
            f"transition-rejected-{fingerprint[:24]}",
            attempted_revision,
            rejection,
            event_type="transition_rejected",
            accepted=False,
            error_code=error.code,
            idempotent=True,
        )

    @staticmethod
    def _require_run(connection: sqlite3.Connection, run_id: str) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise CoordinatorError("run does not exist", code="run_not_found")
        return row

    def _ensure_obligations(self, connection: sqlite3.Connection, run_id: str) -> None:
        now = self._now()
        for obligation in COMPLETION_OBLIGATIONS:
            connection.execute("INSERT OR IGNORE INTO run_obligations(run_id,obligation,satisfied,evidence_ref,updated_at) VALUES(?,?,0,NULL,?)", (run_id, obligation, now))

    def _snapshot_current_revision(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        *,
        source_event_id: str,
    ) -> None:
        row = self._require_run(connection, run_id)
        connection.execute(
            """INSERT OR IGNORE INTO run_revisions(
                 run_id,revision,lifecycle_state,authority_digest,state_digest,
                 task_identity_json,source_event_id,created_at
               ) VALUES(?,?,?,?,?,?,?,?)""",
            (
                run_id,
                int(row["revision"]),
                row["lifecycle_state"],
                row["authority_digest"],
                row["state_digest"],
                row["task_identity_json"],
                source_event_id,
                self._now(),
            ),
        )

    def _guard_transition(self, connection: sqlite3.Connection, row: sqlite3.Row, event: str, body: Mapping[str, Any]) -> None:
        self._ensure_obligations(connection, row["run_id"])
        records = {item["obligation"]: item for item in connection.execute("SELECT obligation,satisfied,evidence_ref FROM run_obligations WHERE run_id=?", (row["run_id"],)).fetchall()}
        def require(names: tuple[str, ...]) -> None:
            missing = [name for name in names if not bool(records[name]["satisfied"])]
            if missing:
                raise CoordinatorError("canonical obligations are not satisfied: " + ", ".join(missing), code="completion_gate_failed")
        if event == "all_slots_closed":
            require(("p0_closure", "insight_clear"))
        elif event == "readiness_passed":
            require(("p0_closure", "insight_clear", "readiness", "evaluation"))
        elif event == "deliveries_compiled":
            require(("p0_closure", "insight_clear", "readiness", "evaluation"))
            if not body.get("technical_digest") or not body.get("human_digest"):
                raise CoordinatorError("both delivery revisions are required", code="missing_delivery")
        elif event == "delivery_accepted":
            require(("p0_closure", "insight_clear", "readiness", "evaluation", "technical_delivery", "human_delivery"))
            technical = body.get("technical_revision")
            human = body.get("human_revision")
            if technical != records["technical_delivery"]["evidence_ref"] or human != records["human_delivery"]["evidence_ref"]:
                raise CoordinatorError("acceptance does not bind exact delivery revisions", code="stale_acceptance")
            if not isinstance(body.get("feedback"), str) or body["feedback"].strip().casefold() in {"", "ok", "okay", "yes", "continue", "go ahead"}:
                raise CoordinatorError("generic acknowledgement cannot accept delivery", code="invalid_acceptance")

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        return {"run_id": row["run_id"], "lifecycle_state": row["lifecycle_state"], "revision": row["revision"], "authority_digest": row["authority_digest"], "state_digest": row["state_digest"], "task_identity": json.loads(row["task_identity_json"]), "parent_run_id": row["parent_run_id"], "termination_reason": row["termination_reason"], "created_at": row["created_at"], "updated_at": row["updated_at"]}
