"""The alpha2 single-writer lifecycle coordinator.

This is intentionally small and explicit.  Existing product compilers remain
usable, but lifecycle, correction invalidation, and host-event idempotency have
one durable authority here.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from .contracts import HostEvent, canonical_json_bytes, validate_feedback_event
from .replay import explain_run, why_not_complete
from .leases import AttemptLease
from .host_events import reconcile_host_events


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

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(f"{message} [{code}]")
        self.code = code


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

    def record_obligation(self, run_id: str, obligation: str, *, evidence_ref: str, expected_revision: int) -> dict[str, Any]:
        if obligation not in COMPLETION_OBLIGATIONS or obligation in {"technical_delivery", "human_delivery", "acceptance"}:
            raise CoordinatorError("obligation must be recorded by its canonical boundary", code="invalid_obligation")
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
            self._event(connection, run_id, f"obligation-{obligation}-{revision}", expected_revision, {"obligation": obligation, "evidence_ref": evidence_ref}, event_type="obligation_satisfied")
        return self.status(run_id)

    def next_actions(self, run_id: str) -> dict[str, Any]:
        state = self.status(run_id)
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
        return {"run_id": run_id, "lifecycle_state": state["lifecycle_state"], "next_action": mapping.get(state["lifecycle_state"], "export_audit"), "revision": state["revision"]}

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
            if connection.execute("SELECT 1 FROM action_attempts WHERE run_id=? AND attempt_id=?", (lease.run_id, lease.attempt_id)).fetchone():
                raise CoordinatorError("attempt already exists", code="duplicate_attempt")
            revision = expected_revision + 1
            state = self._state_payload(row, lifecycle_state=row["lifecycle_state"], revision=revision, body={})
            connection.execute("INSERT INTO action_attempts VALUES(?,?,?,?)", (lease.run_id, lease.attempt_id, json.dumps(lease.to_dict(), sort_keys=True), self._now()))
            connection.execute("UPDATE runs SET revision=?,state_digest=?,updated_at=? WHERE run_id=?", (revision, self._digest(state), self._now(), lease.run_id))
            self._event(connection, lease.run_id, "attempt-started-" + lease.attempt_id, expected_revision, lease.to_dict(), event_type="attempt_lease_issued")
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
        with self._connect() as connection:
            row = self._require_run(connection, run_id)
            if row["revision"] != expected_revision:
                raise CoordinatorError("expected revision is stale", code="stale_revision")
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
            self._event(connection, run_id, f"{event}-{revision}", expected_revision, body, event_type=event)
        return self.status(run_id)

    def record_feedback(self, value: Mapping[str, Any], *, expected_revision: int) -> dict[str, Any]:
        feedback = validate_feedback_event(value)
        run_id = feedback["run_id"]
        with self._connect() as connection:
            row = self._require_run(connection, run_id)
            if row["revision"] != expected_revision:
                raise CoordinatorError("expected revision is stale", code="stale_revision")
            revision = int(row["revision"]) + 1
            invalidated = [str(ref).split(":", 1)[1] for ref in feedback["target_refs"] if str(ref).startswith("strategy:")]
            if feedback["materiality"] in {"material", "terminal"}:
                for digest in invalidated:
                    connection.execute("INSERT OR IGNORE INTO invalidations VALUES(?,?,?,?)", (run_id, digest, feedback["message"], revision))
                self._ensure_obligations(connection, run_id)
                connection.execute("UPDATE run_obligations SET satisfied=0,updated_at=? WHERE run_id=?", (self._now(), run_id))
            identity = feedback.get("successor_task_identity") or json.loads(row["task_identity_json"])
            next_state = "alignment" if feedback["materiality"] == "material" else row["lifecycle_state"]
            state = self._state_payload(row, lifecycle_state=next_state, revision=revision, body={"task_identity": identity, "feedback_id": feedback["feedback_id"]})
            digest = self._digest(state)
            connection.execute("UPDATE runs SET lifecycle_state=?,revision=?,state_digest=?,task_identity_json=?,updated_at=? WHERE run_id=?", (next_state, revision, digest, json.dumps(identity, ensure_ascii=False, sort_keys=True), self._now(), run_id))
            self._event(connection, run_id, "feedback-" + feedback["feedback_id"], expected_revision, feedback, event_type="feedback_recorded")
        result = self.status(run_id)
        result["invalidated_digests"] = sorted(invalidated)
        return result

    def assert_current(self, run_id: str, digest: str, *, action: str) -> None:
        with self._connect() as connection:
            self._require_run(connection, run_id)
            if connection.execute("SELECT 1 FROM invalidations WHERE run_id=? AND digest=?", (run_id, digest)).fetchone():
                raise CoordinatorError(f"{action} references an invalidated digest", code="stale_digest")

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
        return payload

    def _authority_digest(self, row: sqlite3.Row) -> str:
        return str(row["authority_digest"])

    def _state_payload(self, row: sqlite3.Row, *, lifecycle_state: str, revision: int, body: Mapping[str, Any]) -> dict[str, Any]:
        return {"run_id": row["run_id"], "revision": revision, "lifecycle_state": lifecycle_state, "task_identity": body.get("task_identity", json.loads(row["task_identity_json"])), "feedback_id": body.get("feedback_id")}

    def _event(self, connection: sqlite3.Connection, run_id: str, event_id: str, expected_revision: int, payload: Mapping[str, Any], *, event_type: str | None = None) -> None:
        sequence = int(connection.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM events WHERE run_id=?", (run_id,)).fetchone()[0])
        raw = canonical_json_bytes(payload)
        connection.execute("INSERT INTO events(run_id,event_id,sequence,event_type,expected_revision,payload_json,payload_digest,accepted,error_code,causation_id,correlation_id,emitted_at) VALUES(?,?,?,?,?,?,?,1,NULL,NULL,NULL,?)", (run_id, event_id, sequence, event_type or event_id, expected_revision, raw.decode("utf-8"), hashlib.sha256(raw).hexdigest(), self._now()))

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
