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
        CREATE TABLE IF NOT EXISTS quarantined_host_events(
          run_id TEXT NOT NULL, event_id TEXT NOT NULL, reason_code TEXT NOT NULL,
          safe_event_json TEXT NOT NULL, payload_digest TEXT NOT NULL,
          created_at TEXT NOT NULL, PRIMARY KEY(run_id,event_id,reason_code)
        );
        CREATE TABLE IF NOT EXISTS invalidations(
          run_id TEXT NOT NULL, digest TEXT NOT NULL, reason TEXT NOT NULL,
          revision INTEGER NOT NULL, PRIMARY KEY(run_id,digest)
        );
        """)

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
                connection.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?,?)", (run_id, "alignment", 0, authority_digest, state_digest, json.dumps(identity, ensure_ascii=False, sort_keys=True), parent_run_id, None, now, now))
            except sqlite3.IntegrityError as exc:
                raise CoordinatorError("run already exists", code="duplicate_run") from exc
            self._event(connection, run_id, "run-initialized", 0, {"task_identity": identity}, event_type="run_initialized")
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

    def quarantined_host_events(self, run_id: str) -> list[dict[str, Any]]:
        """Return bounded protocol diagnostics without raw host payloads."""

        with self._connect() as connection:
            self._require_run(connection, run_id)
            rows = connection.execute(
                "SELECT event_id,reason_code,safe_event_json,payload_digest,created_at FROM quarantined_host_events WHERE run_id=? ORDER BY created_at,event_id",
                (run_id,),
            ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "reason_code": row["reason_code"],
                "safe_event": json.loads(row["safe_event_json"]),
                "payload_digest": row["payload_digest"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def audit(self, run_id: str) -> dict[str, Any]:
        state = self.status(run_id)
        events = self.events(run_id)
        manifest = {"schema_version": 1, "run": state, "event_count": len(events), "events": events}
        manifest["manifest_digest"] = self._digest(manifest)
        return manifest

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

    def why_action(self, run_id: str) -> dict[str, Any]:
        state = self.status(run_id)
        return {"run_id": run_id, "selected_action": self.next_actions(run_id)["next_action"], "inputs": {"lifecycle_state": state["lifecycle_state"], "revision": state["revision"], "state_digest": state["state_digest"]}, "rejected_alternatives": [], "evidence_refs": []}

    def deliver(self, run_id: str, *, expected_revision: int, technical_digest: str, human_digest: str) -> dict[str, Any]:
        return self.transition(run_id, event="deliveries_compiled", actor="coordinator", expected_revision=expected_revision, payload={"technical_digest": technical_digest, "human_digest": human_digest})

    def accept(self, run_id: str, *, expected_revision: int, displayed_digest: str) -> dict[str, Any]:
        return self.transition(run_id, event="delivery_accepted", actor="human", expected_revision=expected_revision, payload={"displayed_digest": displayed_digest})

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
            revision = int(row["revision"]) + 1
            now = self._now()
            state = self._state_payload(row, lifecycle_state=next_state, revision=revision, body=body)
            digest = self._digest(state)
            authority_digest = body.get("strategy_digest") if event == "alignment_projection_ready" else row["authority_digest"]
            connection.execute("UPDATE runs SET lifecycle_state=?,revision=?,state_digest=?,authority_digest=?,updated_at=?,termination_reason=? WHERE run_id=?", (next_state, revision, digest, authority_digest or row["authority_digest"], now, body.get("termination_reason"), run_id))
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
        if isinstance(event, HostEvent):
            host_event = event
        else:
            try:
                host_event = HostEvent.from_dict(event)
            except ContractError as error:
                if error.code != "unsupported_protocol_version":
                    raise
                raw_event = dict(event)
                run_id = raw_event.get("run_id")
                event_id = raw_event.get("event_id")
                if not isinstance(run_id, str) or not IDENTIFIER_RE.fullmatch(run_id):
                    raise CoordinatorError("unsupported event has invalid run identity", code=error.code) from error
                if not isinstance(event_id, str) or not IDENTIFIER_RE.fullmatch(event_id):
                    raise CoordinatorError("unsupported event has invalid event identity", code=error.code) from error
                with self._connect() as connection:
                    self._require_run(connection, run_id)
                    self._quarantine_host_event(
                        connection,
                        run_id=run_id,
                        event_id=event_id,
                        reason_code=error.code,
                        value=raw_event,
                    )
                raise CoordinatorError(
                    "host event protocol version is unsupported",
                    code=error.code,
                    next_action="upgrade_adapter_or_apply_registered_migration",
                ) from error
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
            elif self._host_sequence_is_out_of_order(connection, host_event):
                self._quarantine_host_event(
                    connection,
                    run_id=host_event.run_id,
                    event_id=host_event.event_id,
                    reason_code="out_of_order_event",
                    value=payload,
                )
                rejection = CoordinatorError(
                    "host event sequence is out of order",
                    code="out_of_order_event",
                    next_action="reconcile_host_sequence",
                )
            elif host_event.event_type == "completion_claimed":
                self._ensure_obligations(connection, host_event.run_id)
                unmet = [
                    item["obligation"]
                    for item in connection.execute(
                        """SELECT obligation FROM run_obligations
                           WHERE run_id=? AND satisfied=0 ORDER BY obligation""",
                        (host_event.run_id,),
                    ).fetchall()
                ]
                rejection_payload = {
                    "actor": f"adapter:{host_event.host}",
                    "actual_revision": int(row["revision"]),
                    "attempted_event": "completion_claimed",
                    "attempted_revision": host_event.expected_revision,
                    "current_state": row["lifecycle_state"],
                    "payload_digest": host_event.payload_digest,
                    "reason_code": "completion_claim_rejected",
                    "next_action": "continue_canonical_gates",
                    "claim_kind": host_event.payload["claim_kind"],
                    "claimed_state": host_event.payload["claimed_state"],
                    "source_ref": host_event.payload["source_ref"],
                    "local_status": host_event.payload["local_status"],
                    "unmet_obligations": unmet,
                }
                self._event(
                    connection,
                    host_event.run_id,
                    f"completion-claim-rejected-{host_event.event_id}",
                    host_event.expected_revision,
                    rejection_payload,
                    event_type="completion_claim_rejected",
                    accepted=False,
                    error_code="completion_claim_rejected",
                    idempotent=True,
                )
                connection.execute(
                    "INSERT INTO host_events VALUES(?,?,?,?)",
                    (
                        host_event.run_id,
                        host_event.event_id,
                        raw,
                        host_event.payload_digest,
                    ),
                )
                rejection = CoordinatorError(
                    "host completion claim is not authoritative",
                    code="completion_claim_rejected",
                    next_action="continue_canonical_gates",
                )
            elif host_event.event_type in ATTEMPT_BOUND_EVENT_TYPES:
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
                    self._quarantine_host_event(
                        connection,
                        run_id=host_event.run_id,
                        event_id=host_event.event_id,
                        reason_code="attempt_not_found",
                        value=payload,
                    )
                    rejection = CoordinatorError(
                        "host event references an unknown attempt",
                        code="attempt_not_found",
                        next_action="reconcile_orphan_event",
                    )
                elif connection.execute(
                    "SELECT 1 FROM attempt_invalidations WHERE run_id=? AND attempt_id=?",
                    (host_event.run_id, host_event.attempt_id),
                ).fetchone():
                    raise CoordinatorError(
                        "attempt was invalidated by material feedback",
                        code="attempt_invalidated",
                        next_action="replan_and_create_new_attempt",
                    )
                lease_status = json.loads(attempt["lease_json"]).get("status") if attempt is not None else None
                if rejection is None and lease_status == "unknown" and host_event.event_type != "attempt_unknown":
                    raise CoordinatorError(
                        "expired attempt cannot report success",
                        code="attempt_expired",
                    )
            if rejection is None:
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
        if rejection is not None:
            raise rejection
        return payload

    def _quarantine_host_event(
        self,
        connection: sqlite3.Connection,
        *,
        run_id: str,
        event_id: str,
        reason_code: str,
        value: Mapping[str, Any],
    ) -> None:
        safe_keys = {
            "protocol_version", "event_id", "event_type", "run_id", "round_id",
            "host", "causation_id", "correlation_id", "sequence",
            "expected_revision", "payload_digest", "emitted_at",
        }
        safe_event = {key: value.get(key) for key in sorted(safe_keys) if key in value}
        supplied_digest = value.get("payload_digest")
        if isinstance(supplied_digest, str) and re.fullmatch(r"[0-9a-f]{64}", supplied_digest):
            payload_digest = supplied_digest
        else:
            try:
                payload_digest = hashlib.sha256(
                    canonical_json_bytes(value.get("payload", {}))
                ).hexdigest()
            except ContractError:
                payload_digest = hashlib.sha256(b"invalid-host-payload").hexdigest()
        connection.execute(
            """
            INSERT OR IGNORE INTO quarantined_host_events(
                run_id,event_id,reason_code,safe_event_json,payload_digest,created_at
            ) VALUES(?,?,?,?,?,?)
            """,
            (
                run_id,
                event_id,
                reason_code,
                canonical_json_bytes(safe_event).decode("utf-8"),
                payload_digest,
                self._now(),
            ),
        )

    @staticmethod
    def _host_sequence_is_out_of_order(
        connection: sqlite3.Connection, event: HostEvent
    ) -> bool:
        maximum = 0
        for row in connection.execute(
            "SELECT event_json FROM host_events WHERE run_id=?", (event.run_id,)
        ).fetchall():
            try:
                prior = json.loads(row["event_json"])
            except json.JSONDecodeError:
                continue
            if prior.get("host") == event.host:
                sequence = prior.get("sequence", 0)
                if isinstance(sequence, int) and not isinstance(sequence, bool):
                    maximum = max(maximum, sequence)
        return maximum > 0 and event.sequence <= maximum

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

    def _event(self, connection: sqlite3.Connection, run_id: str, event_id: str, expected_revision: int, payload: Mapping[str, Any], *, event_type: str | None = None) -> None:
        sequence = int(connection.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM events WHERE run_id=?", (run_id,)).fetchone()[0])
        raw = canonical_json_bytes(payload)
        connection.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?,1,NULL)", (run_id, event_id, sequence, event_type or event_id, expected_revision, raw.decode("utf-8"), hashlib.sha256(raw).hexdigest()))

    @staticmethod
    def _require_run(connection: sqlite3.Connection, run_id: str) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise CoordinatorError("run does not exist", code="run_not_found")
        return row

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        return {"run_id": row["run_id"], "lifecycle_state": row["lifecycle_state"], "revision": row["revision"], "authority_digest": row["authority_digest"], "state_digest": row["state_digest"], "task_identity": json.loads(row["task_identity_json"]), "parent_run_id": row["parent_run_id"], "termination_reason": row["termination_reason"], "created_at": row["created_at"], "updated_at": row["updated_at"]}
