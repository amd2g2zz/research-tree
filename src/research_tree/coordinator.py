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
import re
import sqlite3
from typing import Any, Callable, Mapping, Sequence

from .contracts import (
    ContractError,
    HostEvent,
    canonical_json_bytes,
    validate_alignment_handoff,
    validate_blueprint_target,
    validate_exact_artifact_ref,
    validate_feedback_event,
)
from .replay import explain_run, why_not_complete
from .leases import AttemptLease
from .host_events import reconcile_host_events
from .oracles import OracleAttempt, OracleRun, OracleSpec
from .closure import P0ClosureAggregate, SlotClosureAssessment
from .evidence import EvidenceArtifact, EvidenceError, EvidenceResolver
from .finding_packs import FindingPackContractError, validate_finding_pack_payload
from .decision_entries import (
    DecisionEntryContractError,
    validate_decision_entry_payload,
)
from .convergence_records import (
    ConvergenceRecordContractError,
    validate_convergence_record_payload,
)
from .readiness_records import (
    ReadinessRecordContractError,
    evaluate_canonical_readiness,
)
from .insights import (
    InsightDigestError,
    build_insight_digest,
    validate_canonical_insight_digest,
)
from .worker_contracts import CanonicalWorkItem, WorkerContractError


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
IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


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

    def __init__(
        self,
        workspace: str | Path,
        *,
        fault_injector: Callable[[str], None] | None = None,
    ) -> None:
        root = Path(workspace).resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.database = root / ".research-tree" / "run-ledger.sqlite3"
        self._fault_injector = fault_injector
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            self._schema(connection)

    def _fault(self, boundary: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(boundary)

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
        CREATE TABLE IF NOT EXISTS stage_operations(
          run_id TEXT NOT NULL, stage_id TEXT NOT NULL, stage TEXT NOT NULL,
          input_digest TEXT NOT NULL, committed_revision INTEGER NOT NULL,
          result_json TEXT NOT NULL, created_at TEXT NOT NULL,
          PRIMARY KEY(run_id,stage_id), FOREIGN KEY(run_id) REFERENCES runs(run_id)
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

    @staticmethod
    def delivery_pair_digest(
        run_id: str, technical_revision: str, human_revision: str
    ) -> str:
        """Return the presentation digest for one exact delivery pair."""

        values = (run_id, technical_revision, human_revision)
        if not all(isinstance(value, str) and value.strip() for value in values):
            raise CoordinatorError(
                "delivery pair fields are required", code="missing_delivery"
            )
        return hashlib.sha256(
            canonical_json_bytes(
                {
                    "run_id": run_id,
                    "technical_revision": technical_revision,
                    "human_revision": human_revision,
                }
            )
        ).hexdigest()

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

    def initialize_from_alignment(
        self,
        run_id: str,
        *,
        handoff_ref: Mapping[str, Any],
        blueprint_target_ref: Mapping[str, Any],
        expected_revision: int,
    ) -> dict[str, Any]:
        """Enter autonomous research from one confirmed, exact lineage pair.

        Validation happens before the first transition. The three existing
        coordinator operations are then resumed from whichever committed
        prefix is current, which makes a retry idempotent without introducing
        a second transition implementation.
        """

        try:
            exact_handoff_ref = validate_exact_artifact_ref(
                handoff_ref, label="alignment handoff reference", run_id=run_id
            )
        except ContractError as error:
            raise CoordinatorError(
                "alignment handoff reference is invalid",
                code="handoff_ref_invalid",
            ) from error
        try:
            exact_blueprint_ref = validate_exact_artifact_ref(
                blueprint_target_ref,
                label="blueprint target reference",
                run_id=run_id,
            )
        except ContractError as error:
            raise CoordinatorError(
                "blueprint target reference is invalid",
                code="blueprint_ref_invalid",
            ) from error

        with self._connect() as connection:
            row = self._require_run(connection, run_id)
            if int(row["revision"]) != expected_revision:
                raise CoordinatorError("expected revision is stale", code="stale_revision")
            handoff_artifact = self._resolve_initialization_artifact(
                connection,
                exact_handoff_ref,
                expected_kind="alignment-handoff",
                stale_code="stale_handoff",
            )
            if handoff_artifact["status"] != "confirmed":
                raise CoordinatorError(
                    "alignment handoff is not explicitly confirmed",
                    code="handoff_confirmation_invalid",
                )
            try:
                handoff = validate_alignment_handoff(
                    handoff_artifact["payload"], run_id=run_id
                )
            except ContractError as error:
                raise CoordinatorError(
                    "alignment handoff confirmation is invalid",
                    code="handoff_confirmation_invalid",
                ) from error

            blueprint_artifact = self._resolve_initialization_artifact(
                connection,
                exact_blueprint_ref,
                expected_kind="blueprint-target",
                stale_code="stale_blueprint",
            )
            if blueprint_artifact["status"] != "active":
                raise CoordinatorError(
                    "blueprint target is not active", code="blueprint_lineage_invalid"
                )
            try:
                blueprint = validate_blueprint_target(
                    blueprint_artifact["payload"], run_id=run_id
                )
            except ContractError as error:
                raise CoordinatorError(
                    "blueprint target contract is invalid",
                    code="blueprint_lineage_invalid",
                ) from error
            if blueprint["target_id"] != exact_blueprint_ref["artifact_id"]:
                raise CoordinatorError(
                    "blueprint target id does not match its artifact",
                    code="blueprint_lineage_invalid",
                )

            lineage_refs = {
                "alignment-graph": handoff["alignment_graph_ref"],
                "working-brief": handoff["working_brief_ref"],
                "intent-model": handoff["intent_model_ref"],
            }
            for expected_kind, reference in lineage_refs.items():
                self._resolve_initialization_artifact(
                    connection,
                    reference,
                    expected_kind=expected_kind,
                    stale_code="blueprint_lineage_invalid",
                )
            expected_handoff_parents = {
                self._lineage_key(reference) for reference in lineage_refs.values()
            }
            if handoff_artifact["parent_keys"] != expected_handoff_parents:
                raise CoordinatorError(
                    "alignment handoff parent lineage is not exact",
                    code="blueprint_lineage_invalid",
                )
            if (
                blueprint["working_brief_ref"] != handoff["working_brief_ref"]
                or blueprint["intent_model_ref"] != handoff["intent_model_ref"]
                or blueprint["alignment_handoff_ref"] != exact_handoff_ref
            ):
                raise CoordinatorError(
                    "blueprint target does not bind the confirmed handoff lineage",
                    code="blueprint_lineage_invalid",
                )
            expected_blueprint_parents = {
                self._lineage_key(exact_handoff_ref),
                self._lineage_key(handoff["working_brief_ref"]),
                self._lineage_key(handoff["intent_model_ref"]),
            }
            if blueprint_artifact["parent_keys"] != expected_blueprint_parents:
                raise CoordinatorError(
                    "blueprint target parent lineage is not exact",
                    code="blueprint_lineage_invalid",
                )

            state_name = row["lifecycle_state"]
            strategy_digest = handoff["strategy_digest"]
            current_binding = self._current_blueprint_target_ref(connection, run_id)
            already_bound = (
                current_binding is not None and current_binding[1] == exact_blueprint_ref
            )
            if current_binding is not None and not already_bound:
                raise CoordinatorError(
                    "another Blueprint Target is already bound",
                    code="blueprint_binding_conflict",
                )
            if state_name not in {"alignment", "handoff_pending", "autonomous_research"}:
                raise CoordinatorError(
                    "run cannot initialize from its current lifecycle state",
                    code="initialization_state_invalid",
                )
            if state_name in {"handoff_pending", "autonomous_research"} and row[
                "authority_digest"
            ] != strategy_digest:
                raise CoordinatorError(
                    "committed initialization prefix belongs to another strategy",
                    code="stale_digest",
                    next_action="return_to_alignment_and_rederive_strategy",
                )
            if state_name == "autonomous_research" and not already_bound:
                # This is a valid interrupted prefix: handoff committed, binding did not.
                pass

        state = self.status(run_id)
        if state["lifecycle_state"] == "alignment":
            state = self.transition(
                run_id,
                event="alignment_projection_ready",
                actor="coordinator",
                expected_revision=state["revision"],
                payload={
                    "strategy_digest": strategy_digest,
                    "handoff_ref": exact_handoff_ref,
                },
            )
        if state["lifecycle_state"] == "handoff_pending":
            state = self.transition(
                run_id,
                event="handoff_confirmed",
                actor="human",
                expected_revision=state["revision"],
                payload={
                    "displayed_digest": strategy_digest,
                    "handoff_ref": exact_handoff_ref,
                    "confirmation_actor_id": handoff["confirmation"]["actor_id"],
                    "confirmation_response_digest": handoff["confirmation"][
                        "response_digest"
                    ],
                },
            )
        with self._connect() as connection:
            current_binding = self._current_blueprint_target_ref(connection, run_id)
        if current_binding is None:
            state = self.bind_blueprint_target(
                run_id,
                exact_blueprint_ref,
                expected_revision=state["revision"],
            )
        elif current_binding[1] != exact_blueprint_ref:
            raise CoordinatorError(
                "another Blueprint Target is already bound",
                code="blueprint_binding_conflict",
            )
        return state

    def dispatch_action(
        self,
        run_id: str,
        *,
        stage_id: str,
        work_item_ref: Mapping[str, Any],
        blueprint_target_ref: Mapping[str, Any],
        attempt_id: str,
        owner: str,
        started_at: str,
        lease_expires_at: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        """Atomically bind one exact Work Item to a new attempt lease."""

        if not isinstance(stage_id, str) or not IDENTIFIER_RE.fullmatch(stage_id):
            raise CoordinatorError("stage id is invalid", code="invalid_stage_id")
        try:
            exact_work_ref = validate_exact_artifact_ref(
                work_item_ref, label="dispatch work item reference", run_id=run_id
            )
            exact_target_ref = validate_exact_artifact_ref(
                blueprint_target_ref,
                label="dispatch Blueprint Target reference",
                run_id=run_id,
            )
        except ContractError as error:
            raise CoordinatorError(
                "dispatch artifact reference is invalid", code="dispatch_ref_invalid"
            ) from error
        request = {
            "stage": "dispatch",
            "stage_id": stage_id,
            "run_id": run_id,
            "work_item_ref": exact_work_ref,
            "blueprint_target_ref": exact_target_ref,
            "attempt_id": attempt_id,
            "owner": owner,
            "started_at": started_at,
            "lease_expires_at": lease_expires_at,
            "expected_revision": expected_revision,
        }
        input_digest = self._digest(request)

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            prior = connection.execute(
                "SELECT input_digest,result_json FROM stage_operations WHERE run_id=? AND stage_id=?",
                (run_id, stage_id),
            ).fetchone()
            if prior is not None:
                if prior["input_digest"] != input_digest:
                    raise CoordinatorError(
                        "stage id was reused with different inputs",
                        code="idempotency_conflict",
                    )
                return json.loads(prior["result_json"])

            row = self._require_run(connection, run_id)
            if int(row["revision"]) != expected_revision:
                raise CoordinatorError("expected revision is stale", code="stale_revision")
            if row["lifecycle_state"] != "autonomous_research":
                raise CoordinatorError(
                    "actions can only dispatch during autonomous research",
                    code="dispatch_state_invalid",
                )
            self._assert_current_in_connection(
                connection, run_id, self._authority_digest(row), action="dispatch"
            )

            binding = self._current_blueprint_target_ref(connection, run_id)
            if binding is None or binding[1] != exact_target_ref:
                raise CoordinatorError(
                    "dispatch does not bind the current Blueprint Target",
                    code="blueprint_binding_invalid",
                )
            target = self._resolve_initialization_artifact(
                connection,
                exact_target_ref,
                expected_kind="blueprint-target",
                stale_code="stale_blueprint",
            )
            if target["status"] != "active":
                raise CoordinatorError(
                    "dispatch Blueprint Target is not active",
                    code="blueprint_binding_invalid",
                )
            work_artifact = self._resolve_initialization_artifact(
                connection,
                exact_work_ref,
                expected_kind="work-item",
                stale_code="stale_work_item",
            )
            if work_artifact["status"] != "pending":
                raise CoordinatorError(
                    "Work Item is not pending dispatch", code="work_item_not_dispatchable"
                )
            if self._lineage_key(exact_target_ref) not in work_artifact["parent_keys"]:
                raise CoordinatorError(
                    "Work Item does not descend from the current Blueprint Target",
                    code="work_item_lineage_invalid",
                )
            try:
                work = CanonicalWorkItem.create(**work_artifact["payload"])
            except (TypeError, WorkerContractError, ValueError) as error:
                raise CoordinatorError(
                    "Work Item execution contract is invalid",
                    code="unverifiable_work_item",
                ) from error
            if work.work_item_id != exact_work_ref["artifact_id"]:
                raise CoordinatorError(
                    "Work Item id does not match its artifact",
                    code="work_item_lineage_invalid",
                )

            attempts = [
                AttemptLease.from_dict(json.loads(item["lease_json"]))
                for item in connection.execute(
                    "SELECT lease_json FROM action_attempts WHERE run_id=?",
                    (run_id,),
                ).fetchall()
            ]
            for dependency in work.dependencies:
                if not any(
                    attempt.work_item_id == dependency
                    and attempt.status in {"verified", "completed"}
                    for attempt in attempts
                ):
                    raise CoordinatorError(
                        f"Work Item dependency is not complete: {dependency}",
                        code="work_dependency_open",
                    )
            if any(
                attempt.work_item_id == work.work_item_id
                and attempt.status in {"leased", "running", "submitted"}
                for attempt in attempts
            ):
                raise CoordinatorError(
                    "Work Item already has an active attempt",
                    code="work_item_already_active",
                )

            dispatch_digest = self._digest(
                {
                    "authority_digest": self._authority_digest(row),
                    "work_item_ref": exact_work_ref,
                    "blueprint_target_ref": exact_target_ref,
                    "attempt_id": attempt_id,
                    "owner": owner,
                    "retry_ordinal": 0,
                }
            )
            try:
                lease = AttemptLease.create(
                    attempt_id=attempt_id,
                    work_item_id=work.work_item_id,
                    run_id=run_id,
                    owner=owner,
                    dispatch_digest=dispatch_digest,
                    started_at=started_at,
                    lease_expires_at=lease_expires_at,
                )
            except ValueError as error:
                raise CoordinatorError(str(error), code="invalid_lease") from error
            if connection.execute(
                "SELECT 1 FROM action_attempts WHERE run_id=? AND attempt_id=?",
                (run_id, lease.attempt_id),
            ).fetchone():
                raise CoordinatorError("attempt already exists", code="duplicate_attempt")

            now = self._now()
            revision = expected_revision + 1
            connection.execute(
                "INSERT INTO action_attempts VALUES(?,?,?,?)",
                (run_id, lease.attempt_id, json.dumps(lease.to_dict(), sort_keys=True), now),
            )
            self._fault("dispatch_after_attempt")
            state_payload = self._state_payload(
                row,
                lifecycle_state=row["lifecycle_state"],
                revision=revision,
                body={"stage_id": stage_id, "work_item_ref": exact_work_ref},
            )
            connection.execute(
                "UPDATE runs SET revision=?,state_digest=?,updated_at=? WHERE run_id=?",
                (revision, self._digest(state_payload), now, run_id),
            )
            self._fault("dispatch_after_run_update")
            event_id = f"action-dispatched-{stage_id}"
            self._snapshot_current_revision(connection, run_id, source_event_id=event_id)
            self._fault("dispatch_after_snapshot")
            event_payload = {
                "stage_id": stage_id,
                "input_digest": input_digest,
                "work_item_ref": exact_work_ref,
                "blueprint_target_ref": exact_target_ref,
                "attempt": lease.to_dict(),
            }
            self._event(
                connection,
                run_id,
                event_id,
                expected_revision,
                event_payload,
                event_type="action_dispatched",
            )
            self._fault("dispatch_after_event")
            committed_row = self._require_run(connection, run_id)
            result = {
                "run": self._row(committed_row),
                "stage_id": stage_id,
                "input_digest": input_digest,
                "work_item_ref": exact_work_ref,
                "blueprint_target_ref": exact_target_ref,
                "attempt": lease.to_dict(),
            }
            connection.execute(
                "INSERT INTO stage_operations VALUES(?,?,?,?,?,?,?)",
                (
                    run_id,
                    stage_id,
                    "dispatch",
                    input_digest,
                    revision,
                    canonical_json_bytes(result).decode("utf-8"),
                    now,
                ),
            )
            self._fault("dispatch_after_stage_record")
        return result

    def ingest_finding_pack(
        self,
        run_id: str,
        *,
        stage_id: str,
        finding_pack: Mapping[str, Any],
        expected_revision: int,
    ) -> dict[str, Any]:
        """Validate and atomically ingest one attempt-bound Finding Pack."""

        if not isinstance(stage_id, str) or not IDENTIFIER_RE.fullmatch(stage_id):
            raise CoordinatorError("stage id is invalid", code="invalid_stage_id")
        try:
            finding = validate_finding_pack_payload(finding_pack, run_id=run_id)
        except FindingPackContractError as error:
            raise CoordinatorError(
                "Finding Pack contract is invalid", code="finding_pack_invalid"
            ) from error
        if not IDENTIFIER_RE.fullmatch(finding["finding_id"]):
            raise CoordinatorError(
                "Finding Pack id is invalid", code="finding_pack_invalid"
            )
        request = {
            "stage": "ingest",
            "stage_id": stage_id,
            "run_id": run_id,
            "finding_pack": finding,
            "expected_revision": expected_revision,
        }
        input_digest = self._digest(request)

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            prior = connection.execute(
                "SELECT input_digest,result_json FROM stage_operations WHERE run_id=? AND stage_id=?",
                (run_id, stage_id),
            ).fetchone()
            if prior is not None:
                if prior["input_digest"] != input_digest:
                    raise CoordinatorError(
                        "stage id was reused with different inputs",
                        code="idempotency_conflict",
                    )
                return json.loads(prior["result_json"])

            row = self._require_run(connection, run_id)
            if int(row["revision"]) != expected_revision:
                raise CoordinatorError("expected revision is stale", code="stale_revision")
            if row["lifecycle_state"] != "autonomous_research":
                raise CoordinatorError(
                    "findings can only ingest during autonomous research",
                    code="ingest_state_invalid",
                )
            if connection.execute(
                "SELECT 1 FROM attempt_invalidations WHERE run_id=? AND attempt_id=?",
                (run_id, finding["attempt_id"]),
            ).fetchone():
                raise CoordinatorError(
                    "attempt was invalidated by material feedback",
                    code="attempt_invalidated",
                    next_action="replan_and_create_new_attempt",
                )

            binding = self._current_blueprint_target_ref(connection, run_id)
            if binding is None or binding[1] != finding["blueprint_target_ref"]:
                raise CoordinatorError(
                    "Finding Pack does not bind the current Blueprint Target",
                    code="blueprint_binding_invalid",
                )
            target_artifact = self._resolve_initialization_artifact(
                connection,
                finding["blueprint_target_ref"],
                expected_kind="blueprint-target",
                stale_code="stale_blueprint",
            )
            work_artifact = self._resolve_initialization_artifact(
                connection,
                finding["work_item_ref"],
                expected_kind="work-item",
                stale_code="stale_work_item",
            )
            try:
                work = CanonicalWorkItem.create(**work_artifact["payload"])
            except (TypeError, WorkerContractError, ValueError) as error:
                raise CoordinatorError(
                    "Work Item execution contract is invalid",
                    code="unverifiable_work_item",
                ) from error
            if (
                work.work_item_id != finding["work_item_ref"]["artifact_id"]
                or work.slot_id != finding["decision_slot_id"]
            ):
                raise CoordinatorError(
                    "Finding Pack does not match its Work Item",
                    code="finding_work_binding_invalid",
                )
            slots = {
                slot.get("slot_id"): slot
                for slot in target_artifact["payload"].get("slots", [])
                if isinstance(slot, Mapping) and isinstance(slot.get("slot_id"), str)
            }
            slot = slots.get(finding["decision_slot_id"])
            if slot is None or slot.get("status") in {"closed", "superseded"}:
                raise CoordinatorError(
                    "Finding Pack Decision Slot is not active",
                    code="finding_slot_invalid",
                )
            options = set(slot.get("options", []))
            if any(effect["option"] not in options for effect in finding["option_effects"]):
                raise CoordinatorError(
                    "Finding Pack option effect is outside the Decision Slot",
                    code="finding_option_invalid",
                )

            attempt_row = connection.execute(
                "SELECT lease_json FROM action_attempts WHERE run_id=? AND attempt_id=?",
                (run_id, finding["attempt_id"]),
            ).fetchone()
            if attempt_row is None:
                raise CoordinatorError("attempt does not exist", code="attempt_not_found")
            lease = AttemptLease.from_dict(json.loads(attempt_row["lease_json"]))
            if lease.work_item_id != work.work_item_id:
                raise CoordinatorError(
                    "Finding Pack attempt belongs to another Work Item",
                    code="attempt_binding_invalid",
                )
            if lease.status not in {"leased", "running", "submitted"}:
                raise CoordinatorError(
                    "attempt cannot submit a Finding Pack",
                    code="attempt_not_submittable",
                )

            evidence_parents: dict[tuple[str, str, int], dict[str, Any]] = {}
            resolver = EvidenceResolver(workspace=self.database.parents[1])
            for observation in finding["observations"]:
                for anchor in observation["anchors"]:
                    evidence = self._resolve_evidence_anchor_in_connection(
                        connection, run_id, anchor
                    )
                    try:
                        resolver.resolve(anchor, evidence["payload"])
                    except EvidenceError as error:
                        raise CoordinatorError(
                            "Evidence Anchor does not resolve",
                            code="evidence_anchor_unresolved",
                        ) from error
                    key = (run_id, evidence["artifact_id"], evidence["revision"])
                    evidence_parents[key] = {
                        "run_id": run_id,
                        "artifact_id": evidence["artifact_id"],
                        "revision": evidence["revision"],
                    }
            for oracle_ref in finding["oracle_run_refs"]:
                oracle = connection.execute(
                    "SELECT attempt_id,payload_digest FROM oracle_runs WHERE run_id=? AND oracle_run_id=?",
                    (run_id, oracle_ref["oracle_run_id"]),
                ).fetchone()
                if (
                    oracle is None
                    or oracle["payload_digest"] != oracle_ref["payload_digest"]
                    or oracle["attempt_id"] != finding["attempt_id"]
                ):
                    raise CoordinatorError(
                        "Finding Pack OracleRun reference does not resolve",
                        code="oracle_run_ref_invalid",
                    )

            parent_refs = [
                {
                    "run_id": run_id,
                    "artifact_id": finding["work_item_ref"]["artifact_id"],
                    "revision": finding["work_item_ref"]["revision"],
                },
                {
                    "run_id": run_id,
                    "artifact_id": finding["blueprint_target_ref"]["artifact_id"],
                    "revision": finding["blueprint_target_ref"]["revision"],
                },
                *evidence_parents.values(),
            ]
            now = self._now()
            artifact = self._append_stage_artifact(
                connection,
                run_id=run_id,
                artifact_id=finding["finding_id"],
                kind="finding-pack",
                payload=finding,
                actor_kind="coordinator",
                actor_id="finding-ingestion",
                status="accepted",
                parent_refs=parent_refs,
                created_at=now,
            )
            self._fault("ingest_after_artifact")
            submitted = replace(lease, status="submitted", last_seen_at=now)
            connection.execute(
                "UPDATE action_attempts SET lease_json=?,updated_at=? WHERE run_id=? AND attempt_id=?",
                (
                    json.dumps(submitted.to_dict(), sort_keys=True),
                    now,
                    run_id,
                    submitted.attempt_id,
                ),
            )
            self._fault("ingest_after_attempt")
            revision = expected_revision + 1
            state_payload = self._state_payload(
                row,
                lifecycle_state=row["lifecycle_state"],
                revision=revision,
                body={"stage_id": stage_id, "finding_id": finding["finding_id"]},
            )
            connection.execute(
                "UPDATE runs SET revision=?,state_digest=?,updated_at=? WHERE run_id=?",
                (revision, self._digest(state_payload), now, run_id),
            )
            self._fault("ingest_after_run_update")
            event_id = f"finding-ingested-{stage_id}"
            self._snapshot_current_revision(connection, run_id, source_event_id=event_id)
            self._fault("ingest_after_snapshot")
            finding_ref = {
                "run_id": run_id,
                "artifact_id": artifact["id"],
                "revision": artifact["revision"],
                "content_hash": artifact["content_hash"],
            }
            self._event(
                connection,
                run_id,
                event_id,
                expected_revision,
                {
                    "stage_id": stage_id,
                    "input_digest": input_digest,
                    "attempt_id": submitted.attempt_id,
                    "finding_pack_ref": finding_ref,
                },
                event_type="finding_ingested",
            )
            self._fault("ingest_after_event")
            result = {
                "run": self._row(self._require_run(connection, run_id)),
                "stage_id": stage_id,
                "input_digest": input_digest,
                "finding_pack_ref": finding_ref,
                "attempt": submitted.to_dict(),
            }
            connection.execute(
                "INSERT INTO stage_operations VALUES(?,?,?,?,?,?,?)",
                (
                    run_id,
                    stage_id,
                    "ingest",
                    input_digest,
                    revision,
                    canonical_json_bytes(result).decode("utf-8"),
                    now,
                ),
            )
            self._fault("ingest_after_stage_record")
        return result

    def synthesize_findings(
        self,
        run_id: str,
        *,
        stage_id: str,
        finding_pack_refs: Sequence[Mapping[str, Any]],
        digest_id: str,
        producer_version: str,
        expected_revision: int,
        previous_digest_ref: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Reduce exact Finding Pack revisions into one atomic InsightDigest."""

        if not isinstance(stage_id, str) or not IDENTIFIER_RE.fullmatch(stage_id):
            raise CoordinatorError("stage id is invalid", code="invalid_stage_id")
        if not isinstance(digest_id, str) or not IDENTIFIER_RE.fullmatch(digest_id):
            raise CoordinatorError("InsightDigest id is invalid", code="invalid_digest_id")
        if not isinstance(producer_version, str) or not producer_version.strip():
            raise CoordinatorError(
                "InsightDigest producer version is required",
                code="invalid_producer_version",
            )
        if isinstance(finding_pack_refs, (str, bytes)):
            raise CoordinatorError(
                "Finding Pack references must be an array",
                code="finding_refs_invalid",
            )
        try:
            exact_finding_refs = sorted(
                (
                    validate_exact_artifact_ref(
                        reference,
                        label="Finding Pack reference",
                        run_id=run_id,
                    )
                    for reference in finding_pack_refs
                ),
                key=self._lineage_key,
            )
            exact_previous_ref = (
                validate_exact_artifact_ref(
                    previous_digest_ref,
                    label="previous InsightDigest reference",
                    run_id=run_id,
                )
                if previous_digest_ref is not None
                else None
            )
        except (ContractError, TypeError) as error:
            raise CoordinatorError(
                "synthesis artifact reference is invalid",
                code="synthesis_ref_invalid",
            ) from error
        if len({self._lineage_key(ref) for ref in exact_finding_refs}) != len(
            exact_finding_refs
        ):
            raise CoordinatorError(
                "Finding Pack references must be unique",
                code="finding_refs_invalid",
            )
        request = {
            "stage": "synthesize",
            "stage_id": stage_id,
            "run_id": run_id,
            "finding_pack_refs": exact_finding_refs,
            "digest_id": digest_id,
            "producer_version": producer_version,
            "previous_digest_ref": exact_previous_ref,
            "expected_revision": expected_revision,
        }
        input_digest = self._digest(request)

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            prior = connection.execute(
                "SELECT input_digest,result_json FROM stage_operations WHERE run_id=? AND stage_id=?",
                (run_id, stage_id),
            ).fetchone()
            if prior is not None:
                if prior["input_digest"] != input_digest:
                    raise CoordinatorError(
                        "stage id was reused with different inputs",
                        code="idempotency_conflict",
                    )
                return json.loads(prior["result_json"])

            row = self._require_run(connection, run_id)
            if int(row["revision"]) != expected_revision:
                raise CoordinatorError("expected revision is stale", code="stale_revision")
            if row["lifecycle_state"] != "autonomous_research":
                raise CoordinatorError(
                    "synthesis requires an autonomous research checkpoint",
                    code="synthesis_state_invalid",
                )
            self._assert_current_in_connection(
                connection, run_id, self._authority_digest(row), action="synthesize"
            )
            in_flight_attempts = [
                lease.attempt_id
                for lease in (
                    AttemptLease.from_dict(json.loads(item["lease_json"]))
                    for item in connection.execute(
                        "SELECT lease_json FROM action_attempts WHERE run_id=?",
                        (run_id,),
                    ).fetchall()
                )
                if lease.status in {"leased", "running"}
            ]
            if in_flight_attempts:
                raise CoordinatorError(
                    "synthesis checkpoint has in-flight attempts: "
                    + ", ".join(sorted(in_flight_attempts)),
                    code="batch_incomplete",
                    next_action="reconcile_or_await_attempt",
                )

            binding = self._current_blueprint_target_ref(connection, run_id)
            if binding is None:
                raise CoordinatorError(
                    "synthesis requires a bound Blueprint Target",
                    code="blueprint_not_bound",
                )
            target = self._resolve_initialization_artifact(
                connection,
                binding[1],
                expected_kind="blueprint-target",
                stale_code="stale_blueprint",
            )
            active_slot_ids = sorted(
                {
                    str(slot["slot_id"])
                    for slot in target["payload"].get("slots", [])
                    if isinstance(slot, Mapping)
                    and isinstance(slot.get("slot_id"), str)
                    and slot.get("status") not in {"closed", "superseded"}
                }
            )
            findings: list[dict[str, Any]] = []
            for reference in exact_finding_refs:
                artifact = self._resolve_initialization_artifact(
                    connection,
                    reference,
                    expected_kind="finding-pack",
                    stale_code="stale_finding_pack",
                )
                if artifact["status"] != "accepted":
                    raise CoordinatorError(
                        "synthesis requires accepted Finding Packs",
                        code="finding_pack_not_accepted",
                    )
                try:
                    finding = validate_finding_pack_payload(
                        artifact["payload"], run_id=run_id
                    )
                except FindingPackContractError as error:
                    raise CoordinatorError(
                        "persisted Finding Pack contract is invalid",
                        code="finding_pack_invalid",
                    ) from error
                if finding["blueprint_target_ref"] != binding[1]:
                    raise CoordinatorError(
                        "Finding Pack does not bind the current Blueprint Target",
                        code="blueprint_binding_invalid",
                    )
                if finding["decision_slot_id"] not in active_slot_ids:
                    raise CoordinatorError(
                        "Finding Pack does not cover an active Decision Slot",
                        code="finding_slot_invalid",
                    )
                findings.append(finding)

            latest_digest = connection.execute(
                """SELECT artifact_id,revision,content_hash FROM artifacts
                   WHERE run_id=? AND kind='insight-digest'
                   ORDER BY created_at DESC,artifact_id DESC,revision DESC LIMIT 1""",
                (run_id,),
            ).fetchone()
            if latest_digest is None and exact_previous_ref is not None:
                raise CoordinatorError(
                    "previous InsightDigest does not resolve",
                    code="previous_digest_invalid",
                )
            if latest_digest is not None:
                latest_ref = {
                    "run_id": run_id,
                    "artifact_id": latest_digest["artifact_id"],
                    "revision": int(latest_digest["revision"]),
                    "content_hash": latest_digest["content_hash"],
                }
                if exact_previous_ref != latest_ref:
                    raise CoordinatorError(
                        "synthesis must supersede the latest InsightDigest",
                        code="previous_digest_required",
                    )
            previous_ref_text = (
                "insight-digest:"
                f"{exact_previous_ref['artifact_id']}@{exact_previous_ref['revision']}"
                f"#{exact_previous_ref['content_hash']}"
                if exact_previous_ref is not None
                else None
            )
            try:
                insight = build_insight_digest(
                    findings,
                    digest_id=digest_id,
                    producer_version=producer_version,
                    active_slot_ids=active_slot_ids,
                    previous_digest_ref=previous_ref_text,
                )
                validate_canonical_insight_digest(insight)
            except InsightDigestError as error:
                raise CoordinatorError(
                    "InsightDigest synthesis failed",
                    code="insight_digest_invalid",
                ) from error

            parent_refs: list[Mapping[str, Any]] = list(exact_finding_refs)
            if exact_previous_ref is not None:
                parent_refs.append(exact_previous_ref)
            now = self._now()
            artifact = self._append_stage_artifact(
                connection,
                run_id=run_id,
                artifact_id=digest_id,
                kind="insight-digest",
                payload=insight,
                actor_kind="coordinator",
                actor_id="insight-synthesis",
                status="active",
                parent_refs=parent_refs,
                created_at=now,
            )
            self._fault("synthesize_after_artifact")
            insight_ref = {
                "run_id": run_id,
                "artifact_id": artifact["id"],
                "revision": artifact["revision"],
                "content_hash": artifact["content_hash"],
            }
            insight_clear = not (
                insight["gaps"]
                or insight["contradictions"]
                or insight["recommended_actions"]
            )
            self._ensure_obligations(connection, run_id)
            connection.execute(
                """UPDATE run_obligations SET satisfied=?,evidence_ref=?,updated_at=?
                   WHERE run_id=? AND obligation='insight_clear'""",
                (int(insight_clear), insight_ref["content_hash"], now, run_id),
            )
            self._fault("synthesize_after_obligation")
            revision = expected_revision + 1
            state_payload = self._state_payload(
                row,
                lifecycle_state="synthesis",
                revision=revision,
                body={
                    "stage_id": stage_id,
                    "insight_digest_ref": insight_ref,
                    "insight_clear": insight_clear,
                },
            )
            connection.execute(
                """UPDATE runs SET lifecycle_state=?,revision=?,state_digest=?,updated_at=?
                   WHERE run_id=?""",
                ("synthesis", revision, self._digest(state_payload), now, run_id),
            )
            self._fault("synthesize_after_run_update")
            event_id = f"batch-checkpoint-{stage_id}"
            self._snapshot_current_revision(connection, run_id, source_event_id=event_id)
            self._fault("synthesize_after_snapshot")
            self._event(
                connection,
                run_id,
                event_id,
                expected_revision,
                {
                    "stage_id": stage_id,
                    "input_digest": input_digest,
                    "finding_pack_refs": exact_finding_refs,
                    "insight_digest_ref": insight_ref,
                    "insight_clear": insight_clear,
                },
                event_type="batch_checkpoint",
            )
            self._fault("synthesize_after_event")
            result = {
                "run": self._row(self._require_run(connection, run_id)),
                "stage_id": stage_id,
                "input_digest": input_digest,
                "finding_pack_refs": exact_finding_refs,
                "insight_digest_ref": insight_ref,
                "insight_digest": insight,
                "insight_clear": insight_clear,
            }
            connection.execute(
                "INSERT INTO stage_operations VALUES(?,?,?,?,?,?,?)",
                (
                    run_id,
                    stage_id,
                    "synthesize",
                    input_digest,
                    revision,
                    canonical_json_bytes(result).decode("utf-8"),
                    now,
                ),
            )
            self._fault("synthesize_after_stage_record")
        return result

    def converge_decisions(
        self,
        run_id: str,
        *,
        stage_id: str,
        convergence_id: str,
        insight_digest_ref: Mapping[str, Any],
        decision_entries: Sequence[Mapping[str, Any]],
        producer_version: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        """Commit validated decisions and one revision-bound convergence result."""

        for value, label in (
            (stage_id, "stage id"),
            (convergence_id, "convergence id"),
        ):
            if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
                raise CoordinatorError(f"{label} is invalid", code="invalid_stage_id")
        if not isinstance(producer_version, str) or not producer_version.strip():
            raise CoordinatorError(
                "convergence producer version is required",
                code="invalid_producer_version",
            )
        if isinstance(decision_entries, (str, bytes)) or not isinstance(
            decision_entries, Sequence
        ):
            raise CoordinatorError(
                "decision entries must be an array", code="decision_entries_invalid"
            )
        if not all(isinstance(item, Mapping) for item in decision_entries):
            raise CoordinatorError(
                "decision entries must be objects", code="decision_entries_invalid"
            )
        try:
            exact_insight_ref = validate_exact_artifact_ref(
                insight_digest_ref,
                label="InsightDigest reference",
                run_id=run_id,
            )
        except (ContractError, TypeError) as error:
            raise CoordinatorError(
                "InsightDigest reference is invalid", code="synthesis_ref_invalid"
            ) from error
        entries = [dict(item) for item in decision_entries]
        decision_ids = [item.get("decision_id") for item in entries]
        if len(set(decision_ids)) != len(decision_ids):
            raise CoordinatorError(
                "decision ids must be unique within convergence",
                code="decision_entries_invalid",
            )
        request = {
            "stage": "converge",
            "stage_id": stage_id,
            "convergence_id": convergence_id,
            "run_id": run_id,
            "insight_digest_ref": exact_insight_ref,
            "decision_entries": entries,
            "producer_version": producer_version,
            "expected_revision": expected_revision,
        }
        input_digest = self._digest(request)

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            prior = connection.execute(
                "SELECT input_digest,result_json FROM stage_operations WHERE run_id=? AND stage_id=?",
                (run_id, stage_id),
            ).fetchone()
            if prior is not None:
                if prior["input_digest"] != input_digest:
                    raise CoordinatorError(
                        "stage id was reused with different inputs",
                        code="idempotency_conflict",
                    )
                return json.loads(prior["result_json"])

            row = self._require_run(connection, run_id)
            if int(row["revision"]) != expected_revision:
                raise CoordinatorError("expected revision is stale", code="stale_revision")
            if row["lifecycle_state"] != "synthesis":
                raise CoordinatorError(
                    "decision convergence requires synthesis state",
                    code="convergence_state_invalid",
                )
            self._assert_current_in_connection(
                connection, run_id, self._authority_digest(row), action="converge"
            )

            binding = self._current_blueprint_target_ref(connection, run_id)
            if binding is None:
                raise CoordinatorError(
                    "convergence requires a bound Blueprint Target",
                    code="blueprint_not_bound",
                )
            target_ref = binding[1]
            target_artifact = self._resolve_initialization_artifact(
                connection,
                target_ref,
                expected_kind="blueprint-target",
                stale_code="stale_blueprint",
            )
            insight_artifact = self._resolve_initialization_artifact(
                connection,
                exact_insight_ref,
                expected_kind="insight-digest",
                stale_code="stale_insight_digest",
            )
            if insight_artifact["status"] != "active":
                raise CoordinatorError(
                    "InsightDigest is not active", code="stale_insight_digest"
                )
            latest_insight = connection.execute(
                """SELECT artifact_id,revision,content_hash FROM artifacts
                   WHERE run_id=? AND kind='insight-digest'
                   ORDER BY created_at DESC,artifact_id DESC,revision DESC LIMIT 1""",
                (run_id,),
            ).fetchone()
            if latest_insight is None or exact_insight_ref != {
                "run_id": run_id,
                "artifact_id": latest_insight["artifact_id"],
                "revision": int(latest_insight["revision"]),
                "content_hash": latest_insight["content_hash"],
            }:
                raise CoordinatorError(
                    "convergence requires the latest InsightDigest",
                    code="stale_insight_digest",
                )
            try:
                validate_canonical_insight_digest(insight_artifact["payload"])
            except InsightDigestError as error:
                raise CoordinatorError(
                    "persisted InsightDigest is invalid",
                    code="insight_digest_invalid",
                ) from error

            normalized_entries: list[dict[str, Any]] = []
            entry_contexts: list[
                tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any] | None]
            ] = []
            for entry in entries:
                if entry.get("blueprint_target_ref") != target_ref:
                    raise CoordinatorError(
                        "decision does not bind the current Blueprint Target",
                        code="blueprint_binding_invalid",
                    )
                if entry.get("insight_digest_ref") != exact_insight_ref:
                    raise CoordinatorError(
                        "decision does not bind the current InsightDigest",
                        code="stale_insight_digest",
                    )
                finding_payloads: dict[str, Mapping[str, Any]] = {}
                finding_refs: list[dict[str, Any]] = []
                for reference_value in entry.get("finding_pack_refs", []):
                    try:
                        reference = validate_exact_artifact_ref(
                            reference_value,
                            label="decision Finding Pack reference",
                            run_id=run_id,
                        )
                    except (ContractError, TypeError) as error:
                        raise CoordinatorError(
                            "decision Finding Pack reference is invalid",
                            code="decision_entry_invalid",
                        ) from error
                    artifact = self._resolve_initialization_artifact(
                        connection,
                        reference,
                        expected_kind="finding-pack",
                        stale_code="stale_finding_pack",
                    )
                    if artifact["status"] != "accepted":
                        raise CoordinatorError(
                            "decision requires accepted Finding Packs",
                            code="finding_pack_not_accepted",
                        )
                    finding_payloads[reference["artifact_id"]] = artifact["payload"]
                    finding_refs.append(reference)

                decision_id = entry.get("decision_id")
                latest_decision = (
                    connection.execute(
                        """SELECT revision,content_hash,payload_json FROM artifacts
                           WHERE run_id=? AND artifact_id=? AND kind='decision-ledger-entry'
                           ORDER BY revision DESC LIMIT 1""",
                        (run_id, decision_id),
                    ).fetchone()
                    if isinstance(decision_id, str)
                    else None
                )
                previous_ref = None
                if latest_decision is not None:
                    previous_ref = {
                        "run_id": run_id,
                        "artifact_id": decision_id,
                        "revision": int(latest_decision["revision"]),
                        "content_hash": latest_decision["content_hash"],
                    }
                if entry.get("previous_decision_ref") != previous_ref:
                    raise CoordinatorError(
                        "decision must bind its exact latest predecessor",
                        code="previous_decision_required",
                    )
                try:
                    normalized = validate_decision_entry_payload(
                        entry,
                        run_id=run_id,
                        blueprint_target=target_artifact["payload"],
                        finding_packs=finding_payloads,
                        insight_digest=insight_artifact["payload"],
                    )
                except DecisionEntryContractError as error:
                    raise CoordinatorError(
                        "DecisionLedgerEntry contract is invalid",
                        code="decision_entry_invalid",
                    ) from error
                for oracle_ref in normalized["validation"]["oracle_run_refs"]:
                    oracle = connection.execute(
                        "SELECT payload_digest FROM oracle_runs WHERE run_id=? AND oracle_run_id=?",
                        (run_id, oracle_ref["oracle_run_id"]),
                    ).fetchone()
                    if oracle is None or oracle["payload_digest"] != oracle_ref["payload_digest"]:
                        raise CoordinatorError(
                            "decision OracleRun reference does not resolve",
                            code="oracle_run_ref_invalid",
                        )
                normalized_entries.append(normalized)
                entry_contexts.append((normalized, finding_refs, previous_ref))

            now = self._now()
            decision_refs: list[dict[str, Any]] = []
            for entry, finding_refs, previous_ref in entry_contexts:
                parents: list[Mapping[str, Any]] = [
                    target_ref,
                    exact_insight_ref,
                    *finding_refs,
                ]
                if previous_ref is not None:
                    parents.append(previous_ref)
                decision_artifact = self._append_stage_artifact(
                    connection,
                    run_id=run_id,
                    artifact_id=entry["decision_id"],
                    kind="decision-ledger-entry",
                    payload=entry,
                    actor_kind="coordinator",
                    actor_id="decision-convergence",
                    status="active",
                    parent_refs=parents,
                    created_at=now,
                )
                decision_ref = {
                    "run_id": run_id,
                    "artifact_id": decision_artifact["id"],
                    "revision": decision_artifact["revision"],
                    "content_hash": decision_artifact["content_hash"],
                }
                decision_refs.append(decision_ref)
                if previous_ref is not None:
                    self._revoke_latest_closures(
                        connection,
                        run_id,
                        reason="Decision Ledger revision was superseded by convergence",
                        event_expected_revision=expected_revision,
                        binding_revision=binding[0],
                        decision_artifact_id=entry["decision_id"],
                        decision_revision=decision_artifact["revision"],
                    )
            self._fault("converge_after_decisions")

            aggregate = self._persist_p0_closure_aggregate(
                connection,
                run_id,
                binding_revision=binding[0],
                blueprint_target_ref=target_ref,
            )
            aggregate_ref = {
                "run_id": run_id,
                "aggregate_revision": aggregate["aggregate_revision"],
                "aggregate_digest": aggregate["aggregate_digest"],
            }
            current_decisions = {
                self._lineage_key(reference): reference for reference in decision_refs
            }
            for slot in aggregate.get("slots", []):
                reference = slot.get("decision_ref") if isinstance(slot, Mapping) else None
                if not isinstance(reference, Mapping):
                    continue
                try:
                    exact_reference = validate_exact_artifact_ref(
                        reference,
                        label="P0 closure decision reference",
                        run_id=run_id,
                    )
                except (ContractError, TypeError) as error:
                    raise CoordinatorError(
                        "P0 closure aggregate has an invalid decision reference",
                        code="closure_aggregate_invalid",
                    ) from error
                current_decisions[self._lineage_key(exact_reference)] = exact_reference
            decision_refs = [
                current_decisions[key] for key in sorted(current_decisions)
            ]
            self._fault("converge_after_aggregate")

            deficits = self._convergence_deficits(
                run_id=run_id,
                insight_ref=exact_insight_ref,
                insight=insight_artifact["payload"],
                aggregate=aggregate,
            )
            self._ensure_obligations(connection, run_id)
            obligations = {
                item["obligation"]: bool(item["satisfied"])
                for item in connection.execute(
                    "SELECT obligation,satisfied FROM run_obligations WHERE run_id=?",
                    (run_id,),
                ).fetchall()
            }
            all_closed = bool(
                obligations.get("insight_clear")
                and obligations.get("p0_closure")
                and aggregate["status"] == "passed"
            )
            outcome = "all_slots_closed" if all_closed else "closure_deficit"
            if all_closed:
                deficits = []
            elif not deficits:
                raise CoordinatorError(
                    "closure deficit has no actionable diagnostic",
                    code="convergence_deficit_invalid",
                )
            convergence = {
                "convergence_id": convergence_id,
                "run_id": run_id,
                "blueprint_target_ref": target_ref,
                "insight_digest_ref": exact_insight_ref,
                "decision_refs": decision_refs,
                "p0_closure_aggregate_ref": aggregate_ref,
                "outcome": outcome,
                "deficits": deficits,
                "producer_version": producer_version,
            }
            try:
                convergence = validate_convergence_record_payload(
                    convergence, run_id=run_id
                )
            except ConvergenceRecordContractError as error:
                raise CoordinatorError(
                    "ConvergenceRecord contract is invalid",
                    code="convergence_record_invalid",
                ) from error
            convergence_artifact = self._append_stage_artifact(
                connection,
                run_id=run_id,
                artifact_id=convergence_id,
                kind="convergence-record",
                payload=convergence,
                actor_kind="coordinator",
                actor_id="decision-convergence",
                status="active",
                parent_refs=[target_ref, exact_insight_ref, *decision_refs],
                created_at=now,
            )
            convergence_ref = {
                "run_id": run_id,
                "artifact_id": convergence_artifact["id"],
                "revision": convergence_artifact["revision"],
                "content_hash": convergence_artifact["content_hash"],
            }
            self._fault("converge_after_record")

            event_type = outcome
            next_state = "readiness" if all_closed else "autonomous_research"
            self._guard_transition(
                connection,
                row,
                event_type,
                {"convergence_record_ref": convergence_ref},
            )
            revision = expected_revision + 1
            state_payload = self._state_payload(
                row,
                lifecycle_state=next_state,
                revision=revision,
                body={
                    "stage_id": stage_id,
                    "convergence_record_ref": convergence_ref,
                    "outcome": outcome,
                },
            )
            connection.execute(
                """UPDATE runs SET lifecycle_state=?,revision=?,state_digest=?,updated_at=?
                   WHERE run_id=?""",
                (next_state, revision, self._digest(state_payload), now, run_id),
            )
            self._fault("converge_after_run_update")
            event_id = f"{event_type}-{stage_id}"
            self._snapshot_current_revision(connection, run_id, source_event_id=event_id)
            self._fault("converge_after_snapshot")
            self._event(
                connection,
                run_id,
                event_id,
                expected_revision,
                {
                    "stage_id": stage_id,
                    "input_digest": input_digest,
                    "decision_refs": decision_refs,
                    "convergence_record_ref": convergence_ref,
                    "p0_closure_aggregate_ref": aggregate_ref,
                    "deficits": deficits,
                },
                event_type=event_type,
            )
            self._fault("converge_after_event")
            result = {
                "run": self._row(self._require_run(connection, run_id)),
                "stage_id": stage_id,
                "input_digest": input_digest,
                "decision_refs": decision_refs,
                "convergence_record_ref": convergence_ref,
                "convergence_record": convergence,
                "p0_closure_aggregate": aggregate,
            }
            connection.execute(
                "INSERT INTO stage_operations VALUES(?,?,?,?,?,?,?)",
                (
                    run_id,
                    stage_id,
                    "converge",
                    input_digest,
                    revision,
                    canonical_json_bytes(result).decode("utf-8"),
                    now,
                ),
            )
            self._fault("converge_after_stage_record")
        return result

    def evaluate_readiness(
        self,
        run_id: str,
        *,
        stage_id: str,
        readiness_id: str,
        convergence_record_ref: Mapping[str, Any],
        risk_tier: str,
        producer_version: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        """Atomically evaluate exact canonical lineage for delivery readiness."""

        for value, label in (
            (stage_id, "stage id"),
            (readiness_id, "readiness id"),
        ):
            if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
                raise CoordinatorError(f"{label} is invalid", code="invalid_stage_id")
        if not isinstance(producer_version, str) or not producer_version.strip():
            raise CoordinatorError(
                "readiness producer version is required",
                code="invalid_producer_version",
            )
        try:
            exact_convergence_ref = validate_exact_artifact_ref(
                convergence_record_ref,
                label="ConvergenceRecord reference",
                run_id=run_id,
            )
        except (ContractError, TypeError, ValueError) as error:
            raise CoordinatorError(
                "ConvergenceRecord reference is invalid",
                code="convergence_ref_invalid",
            ) from error
        request = {
            "stage": "readiness",
            "stage_id": stage_id,
            "readiness_id": readiness_id,
            "run_id": run_id,
            "convergence_record_ref": exact_convergence_ref,
            "risk_tier": risk_tier,
            "producer_version": producer_version,
            "expected_revision": expected_revision,
        }
        input_digest = self._digest(request)

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            prior = connection.execute(
                "SELECT input_digest,result_json FROM stage_operations WHERE run_id=? AND stage_id=?",
                (run_id, stage_id),
            ).fetchone()
            if prior is not None:
                if prior["input_digest"] != input_digest:
                    raise CoordinatorError(
                        "stage id was reused with different inputs",
                        code="idempotency_conflict",
                    )
                return json.loads(prior["result_json"])

            row = self._require_run(connection, run_id)
            if int(row["revision"]) != expected_revision:
                raise CoordinatorError(
                    "expected revision is stale", code="stale_revision"
                )
            if row["lifecycle_state"] != "readiness":
                raise CoordinatorError(
                    "readiness evaluation requires readiness state",
                    code="readiness_state_invalid",
                )
            self._assert_current_in_connection(
                connection,
                run_id,
                self._authority_digest(row),
                action="evaluate readiness",
            )

            convergence_artifact = self._resolve_initialization_artifact(
                connection,
                exact_convergence_ref,
                expected_kind="convergence-record",
                stale_code="stale_convergence_record",
            )
            if convergence_artifact["status"] != "active":
                raise CoordinatorError(
                    "ConvergenceRecord is not active",
                    code="stale_convergence_record",
                )
            latest_convergence = connection.execute(
                """SELECT artifact_id,revision,content_hash FROM artifacts
                   WHERE run_id=? AND kind='convergence-record'
                   ORDER BY created_at DESC,artifact_id DESC,revision DESC LIMIT 1""",
                (run_id,),
            ).fetchone()
            if latest_convergence is None or exact_convergence_ref != {
                "run_id": run_id,
                "artifact_id": latest_convergence["artifact_id"],
                "revision": int(latest_convergence["revision"]),
                "content_hash": latest_convergence["content_hash"],
            }:
                raise CoordinatorError(
                    "readiness requires the latest ConvergenceRecord",
                    code="stale_convergence_record",
                )
            try:
                convergence = validate_convergence_record_payload(
                    convergence_artifact["payload"], run_id=run_id
                )
            except ConvergenceRecordContractError as error:
                raise CoordinatorError(
                    "persisted ConvergenceRecord is invalid",
                    code="convergence_record_invalid",
                ) from error

            binding = self._current_blueprint_target_ref(connection, run_id)
            if binding is None or binding[1] != convergence["blueprint_target_ref"]:
                raise CoordinatorError(
                    "ConvergenceRecord does not bind the current Blueprint Target",
                    code="stale_blueprint",
                )
            target_ref = binding[1]
            target_artifact = self._resolve_initialization_artifact(
                connection,
                target_ref,
                expected_kind="blueprint-target",
                stale_code="stale_blueprint",
            )
            if target_artifact["status"] not in {"active", "accepted"}:
                raise CoordinatorError(
                    "Blueprint Target is not active", code="stale_blueprint"
                )

            insight_ref = convergence["insight_digest_ref"]
            insight_artifact = self._resolve_initialization_artifact(
                connection,
                insight_ref,
                expected_kind="insight-digest",
                stale_code="stale_insight_digest",
            )
            latest_insight = connection.execute(
                """SELECT artifact_id,revision,content_hash FROM artifacts
                   WHERE run_id=? AND kind='insight-digest'
                   ORDER BY created_at DESC,artifact_id DESC,revision DESC LIMIT 1""",
                (run_id,),
            ).fetchone()
            if latest_insight is None or insight_ref != {
                "run_id": run_id,
                "artifact_id": latest_insight["artifact_id"],
                "revision": int(latest_insight["revision"]),
                "content_hash": latest_insight["content_hash"],
            }:
                raise CoordinatorError(
                    "readiness requires the latest InsightDigest",
                    code="stale_insight_digest",
                )
            try:
                validate_canonical_insight_digest(insight_artifact["payload"])
            except InsightDigestError as error:
                raise CoordinatorError(
                    "persisted InsightDigest is invalid",
                    code="insight_digest_invalid",
                ) from error

            decision_payloads: list[dict[str, Any]] = []
            decision_refs = convergence["decision_refs"]
            for decision_ref in decision_refs:
                decision_artifact = self._resolve_initialization_artifact(
                    connection,
                    decision_ref,
                    expected_kind="decision-ledger-entry",
                    stale_code="stale_decision",
                )
                latest_decision = connection.execute(
                    """SELECT revision,content_hash FROM artifacts
                       WHERE run_id=? AND artifact_id=? AND kind='decision-ledger-entry'
                       ORDER BY revision DESC LIMIT 1""",
                    (run_id, decision_ref["artifact_id"]),
                ).fetchone()
                if latest_decision is None or (
                    int(latest_decision["revision"]) != decision_ref["revision"]
                    or latest_decision["content_hash"] != decision_ref["content_hash"]
                ):
                    raise CoordinatorError(
                        "readiness requires current Decision Ledger entries",
                        code="stale_decision",
                    )
                decision_payloads.append(decision_artifact["payload"])

            aggregate_ref = convergence["p0_closure_aggregate_ref"]
            aggregate_row = connection.execute(
                """SELECT payload_json,aggregate_digest FROM p0_closure_aggregates
                   WHERE run_id=? AND aggregate_revision=?""",
                (run_id, aggregate_ref["aggregate_revision"]),
            ).fetchone()
            latest_aggregate = connection.execute(
                """SELECT aggregate_revision,aggregate_digest FROM p0_closure_aggregates
                   WHERE run_id=? ORDER BY aggregate_revision DESC LIMIT 1""",
                (run_id,),
            ).fetchone()
            if (
                aggregate_row is None
                or latest_aggregate is None
                or aggregate_row["aggregate_digest"] != aggregate_ref["aggregate_digest"]
                or int(latest_aggregate["aggregate_revision"])
                != aggregate_ref["aggregate_revision"]
                or latest_aggregate["aggregate_digest"]
                != aggregate_ref["aggregate_digest"]
            ):
                raise CoordinatorError(
                    "readiness requires the latest P0 closure aggregate",
                    code="stale_closure_aggregate",
                )
            aggregate = json.loads(aggregate_row["payload_json"])

            self._ensure_obligations(connection, run_id)
            evaluation_row = connection.execute(
                """SELECT satisfied,evidence_ref FROM run_obligations
                   WHERE run_id=? AND obligation='evaluation'""",
                (run_id,),
            ).fetchone()
            evaluation_obligation = {
                "obligation": "evaluation",
                "satisfied": bool(evaluation_row["satisfied"]),
                "evidence_ref": evaluation_row["evidence_ref"],
            }
            try:
                readiness = evaluate_canonical_readiness(
                    readiness_id=readiness_id,
                    run_id=run_id,
                    blueprint_target_ref=target_ref,
                    convergence_record_ref=exact_convergence_ref,
                    convergence_record=convergence,
                    insight_digest_ref=insight_ref,
                    insight_digest=insight_artifact["payload"],
                    decision_refs=decision_refs,
                    decisions=decision_payloads,
                    p0_closure_aggregate_ref=aggregate_ref,
                    p0_closure_aggregate=aggregate,
                    evaluation_obligation=evaluation_obligation,
                    risk_tier=risk_tier,
                    producer_version=producer_version,
                )
            except ReadinessRecordContractError as error:
                raise CoordinatorError(
                    "canonical readiness evaluation failed",
                    code="readiness_record_invalid",
                ) from error

            now = self._now()
            readiness_artifact = self._append_stage_artifact(
                connection,
                run_id=run_id,
                artifact_id=readiness_id,
                kind="readiness-record",
                payload=readiness,
                actor_kind="coordinator",
                actor_id="readiness-evaluator",
                status="active",
                parent_refs=[
                    target_ref,
                    exact_convergence_ref,
                    insight_ref,
                    *decision_refs,
                ],
                created_at=now,
            )
            readiness_ref = {
                "run_id": run_id,
                "artifact_id": readiness_artifact["id"],
                "revision": readiness_artifact["revision"],
                "content_hash": readiness_artifact["content_hash"],
            }
            self._fault("readiness_after_record")

            ready = readiness["status"] == "ready"
            connection.execute(
                """UPDATE run_obligations SET satisfied=?,evidence_ref=?,updated_at=?
                   WHERE run_id=? AND obligation='readiness'""",
                (int(ready), readiness_ref["content_hash"], now, run_id),
            )
            self._fault("readiness_after_obligation")
            event_type = "readiness_passed" if ready else "readiness_deficit"
            next_state = "delivery_pending" if ready else "autonomous_research"
            self._guard_transition(
                connection,
                row,
                event_type,
                {"readiness_record_ref": readiness_ref},
            )
            revision = expected_revision + 1
            state_payload = self._state_payload(
                row,
                lifecycle_state=next_state,
                revision=revision,
                body={
                    "stage_id": stage_id,
                    "readiness_record_ref": readiness_ref,
                    "status": readiness["status"],
                },
            )
            connection.execute(
                """UPDATE runs SET lifecycle_state=?,revision=?,state_digest=?,updated_at=?
                   WHERE run_id=?""",
                (next_state, revision, self._digest(state_payload), now, run_id),
            )
            self._fault("readiness_after_run_update")
            event_id = f"{event_type}-{stage_id}"
            self._snapshot_current_revision(
                connection, run_id, source_event_id=event_id
            )
            self._fault("readiness_after_snapshot")
            self._event(
                connection,
                run_id,
                event_id,
                expected_revision,
                {
                    "stage_id": stage_id,
                    "input_digest": input_digest,
                    "readiness_record_ref": readiness_ref,
                    "status": readiness["status"],
                    "deficits": readiness["deficits"],
                },
                event_type=event_type,
            )
            self._fault("readiness_after_event")
            result = {
                "run": self._row(self._require_run(connection, run_id)),
                "stage_id": stage_id,
                "input_digest": input_digest,
                "readiness_record_ref": readiness_ref,
                "readiness_record": readiness,
            }
            connection.execute(
                "INSERT INTO stage_operations VALUES(?,?,?,?,?,?,?)",
                (
                    run_id,
                    stage_id,
                    "readiness",
                    input_digest,
                    revision,
                    canonical_json_bytes(result).decode("utf-8"),
                    now,
                ),
            )
            self._fault("readiness_after_stage_record")
        return result

    def _convergence_deficits(
        self,
        *,
        run_id: str,
        insight_ref: Mapping[str, Any],
        insight: Mapping[str, Any],
        aggregate: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        """Project canonical insight and closure gaps into stable successor inputs."""

        insight_source = (
            f"insight-digest:{insight_ref['artifact_id']}@{insight_ref['revision']}"
            f"#{insight_ref['content_hash']}"
        )
        aggregate_source = (
            f"p0-closure:{aggregate['aggregate_revision']}"
            f"#{aggregate['aggregate_digest']}"
        )
        candidates: list[dict[str, Any]] = []
        for gap in insight.get("gaps", []):
            if not isinstance(gap, Mapping) or not isinstance(gap.get("slot_id"), str):
                continue
            method = str(gap.get("next_acquisition_method", "validation"))
            action = method if method in {
                "landscape",
                "deep_dive",
                "adversarial",
                "validation",
                "method_switch",
            } else "validation"
            reason = str(gap.get("reason", "Insight gap remains open"))
            kind = "uncovered" if action == "landscape" else "insight_gap"
            candidates.append(
                {
                    "slot_id": gap["slot_id"],
                    "kind": kind,
                    "trigger": reason,
                    "action": action,
                    "source_refs": [insight_source],
                }
            )
        for contradiction in insight.get("contradictions", []):
            if not isinstance(contradiction, Mapping) or not isinstance(
                contradiction.get("slot_id"), str
            ):
                continue
            candidates.append(
                {
                    "slot_id": contradiction["slot_id"],
                    "kind": "contradiction",
                    "trigger": f"Contradictory evidence remains for {contradiction.get('subject', 'the Slot')}.",
                    "action": "adversarial",
                    "source_refs": [
                        insight_source,
                        *sorted(
                            str(item)
                            for item in contradiction.get("evidence_refs", [])
                            if str(item).strip()
                        ),
                    ],
                }
            )
        for slot in aggregate.get("slots", []):
            if not isinstance(slot, Mapping) or slot.get("status") == "passed":
                continue
            status = str(slot.get("status", "missing"))
            kind = "closure_stale" if status in {
                "stale",
                "revoked",
                "failed",
            } else "closure_missing"
            source_refs = [aggregate_source]
            decision_ref = slot.get("decision_ref")
            if isinstance(decision_ref, Mapping):
                source_refs.append(
                    f"decision:{decision_ref.get('artifact_id')}@{decision_ref.get('revision')}"
                    f"#{decision_ref.get('content_hash')}"
                )
            candidates.append(
                {
                    "slot_id": str(slot.get("slot_id")),
                    "kind": kind,
                    "trigger": f"P0 closure status is {status}.",
                    "action": "validation",
                    "source_refs": source_refs,
                }
            )

        unique: dict[tuple[str, str, str], dict[str, Any]] = {}
        for candidate in candidates:
            key = (
                candidate["slot_id"],
                candidate["kind"],
                candidate["action"],
            )
            unique.setdefault(key, candidate)
        result: list[dict[str, Any]] = []
        for key, candidate in sorted(unique.items()):
            semantic = {
                "run_id": run_id,
                "slot_id": key[0],
                "kind": key[1],
                "action": key[2],
                "trigger": candidate["trigger"],
                "source_refs": sorted(set(candidate["source_refs"])),
            }
            result.append(
                {
                    "deficit_id": "deficit-" + self._digest(semantic)[:16],
                    "slot_id": semantic["slot_id"],
                    "kind": semantic["kind"],
                    "trigger": semantic["trigger"],
                    "action": semantic["action"],
                    "source_refs": semantic["source_refs"],
                }
            )
        return result

    @staticmethod
    def _lineage_key(reference: Mapping[str, Any]) -> tuple[str, str, int]:
        return (
            str(reference["run_id"]),
            str(reference["artifact_id"]),
            int(reference["revision"]),
        )

    def _append_stage_artifact(
        self,
        connection: sqlite3.Connection,
        *,
        run_id: str,
        artifact_id: str,
        kind: str,
        payload: Mapping[str, Any],
        actor_kind: str,
        actor_id: str,
        status: str,
        parent_refs: list[Mapping[str, Any]],
        created_at: str,
    ) -> dict[str, Any]:
        """Append an artifact inside an already-open coordinator transaction."""

        if not IDENTIFIER_RE.fullmatch(artifact_id):
            raise CoordinatorError("artifact id is invalid", code="artifact_id_invalid")
        current = int(
            connection.execute(
                "SELECT COALESCE(MAX(revision),0) FROM artifacts WHERE run_id=? AND artifact_id=?",
                (run_id, artifact_id),
            ).fetchone()[0]
        )
        revision = current + 1
        parents = sorted(
            (
                {
                    "run_id": str(parent["run_id"]),
                    "artifact_id": str(parent["artifact_id"]),
                    "revision": int(parent["revision"]),
                }
                for parent in parent_refs
            ),
            key=lambda parent: (
                parent["run_id"], parent["artifact_id"], parent["revision"]
            ),
        )
        if len({self._lineage_key(parent) for parent in parents}) != len(parents):
            raise CoordinatorError(
                "artifact parent lineage contains duplicates",
                code="artifact_lineage_invalid",
            )
        for parent in parents:
            if connection.execute(
                "SELECT 1 FROM artifacts WHERE run_id=? AND artifact_id=? AND revision=?",
                self._lineage_key(parent),
            ).fetchone() is None:
                raise CoordinatorError(
                    "artifact parent does not resolve", code="artifact_lineage_invalid"
                )
        body = {
            "schema_version": 1,
            "kind": kind,
            "id": artifact_id,
            "run_id": run_id,
            "revision": revision,
            "created_at": created_at,
            "actor": {"kind": actor_kind, "id": actor_id},
            "status": status,
            "payload": dict(payload),
            "parent_refs": parents,
        }
        content_hash = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
        try:
            connection.execute(
                """INSERT INTO artifacts(
                     run_id,artifact_id,revision,kind,schema_version,created_at,
                     actor_kind,actor_id,status,payload_json,content_hash
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id,
                    artifact_id,
                    revision,
                    kind,
                    1,
                    created_at,
                    actor_kind,
                    actor_id,
                    status,
                    canonical_json_bytes(payload).decode("utf-8"),
                    content_hash,
                ),
            )
        except sqlite3.IntegrityError as error:
            raise CoordinatorError(
                "artifact conflicts with immutable ledger", code="artifact_conflict"
            ) from error
        for parent in parents:
            connection.execute(
                "INSERT INTO artifact_parents VALUES(?,?,?,?,?,?)",
                (
                    run_id,
                    artifact_id,
                    revision,
                    parent["run_id"],
                    parent["artifact_id"],
                    parent["revision"],
                ),
            )
        return {**body, "content_hash": content_hash}

    def _resolve_evidence_anchor_in_connection(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        anchor: Mapping[str, Any],
    ) -> dict[str, Any]:
        rows = connection.execute(
            """SELECT artifact_id,revision,status,payload_json
               FROM artifacts
               WHERE run_id=? AND kind='evidence-artifact' AND revision=?""",
            (run_id, int(anchor["artifact_revision"])),
        ).fetchall()
        matches: list[dict[str, Any]] = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            if payload.get("content_digest") != anchor["artifact_digest"]:
                continue
            try:
                parsed = EvidenceArtifact.from_mapping(payload)
            except EvidenceError as error:
                raise CoordinatorError(
                    "Evidence Artifact contract is invalid",
                    code="evidence_anchor_unresolved",
                ) from error
            if row["status"] != "active" or parsed.status != "active":
                continue
            matches.append(
                {
                    "artifact_id": row["artifact_id"],
                    "revision": int(row["revision"]),
                    "payload": payload,
                }
            )
        if len(matches) != 1:
            raise CoordinatorError(
                "Evidence Anchor must resolve to exactly one active artifact",
                code="evidence_anchor_unresolved",
            )
        return matches[0]

    def _resolve_initialization_artifact(
        self,
        connection: sqlite3.Connection,
        reference: Mapping[str, Any],
        *,
        expected_kind: str,
        stale_code: str,
    ) -> dict[str, Any]:
        try:
            row = connection.execute(
                """SELECT kind,status,payload_json,content_hash FROM artifacts
                   WHERE run_id=? AND artifact_id=? AND revision=?""",
                self._lineage_key(reference),
            ).fetchone()
        except sqlite3.OperationalError as error:
            raise CoordinatorError(
                "canonical artifact ledger is unavailable",
                code="canonical_store_unavailable",
            ) from error
        if row is None:
            raise CoordinatorError(
                f"{expected_kind} artifact does not resolve", code=stale_code
            )
        if row["kind"] != expected_kind or row["content_hash"] != reference["content_hash"]:
            raise CoordinatorError(
                f"{expected_kind} artifact reference is stale", code=stale_code
            )
        parents = connection.execute(
            """SELECT parent_run_id,parent_artifact_id,parent_revision
               FROM artifact_parents
               WHERE run_id=? AND artifact_id=? AND revision=?""",
            self._lineage_key(reference),
        ).fetchall()
        return {
            "status": row["status"],
            "payload": json.loads(row["payload_json"]),
            "parent_keys": {
                (
                    parent["parent_run_id"],
                    parent["parent_artifact_id"],
                    int(parent["parent_revision"]),
                )
                for parent in parents
            },
        }

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
        displayed_digest = self.delivery_pair_digest(
            run_id, technical_digest, human_digest
        )
        state = self.transition(
            run_id,
            event="deliveries_compiled",
            actor="coordinator",
            expected_revision=expected_revision,
            payload={
                "technical_digest": technical_digest,
                "human_digest": human_digest,
                "displayed_digest": displayed_digest,
            },
        )
        return {**state, "displayed_digest": displayed_digest}

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
                allowed_actors = (
                    {"human", "operator"}
                    if required_actor == "human_or_operator"
                    else {required_actor}
                )
                if actor not in allowed_actors:
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
                self._fault("transition_after_run_update")
                if event == "deliveries_compiled":
                    connection.execute("UPDATE run_obligations SET satisfied=1,evidence_ref=?,updated_at=? WHERE run_id=? AND obligation='technical_delivery'", (body["technical_digest"], now, run_id))
                    connection.execute("UPDATE run_obligations SET satisfied=1,evidence_ref=?,updated_at=? WHERE run_id=? AND obligation='human_delivery'", (body["human_digest"], now, run_id))
                elif event == "delivery_accepted":
                    connection.execute("UPDATE run_obligations SET satisfied=1,evidence_ref=?,updated_at=? WHERE run_id=? AND obligation='acceptance'", (body["displayed_digest"], now, run_id))
                elif event == "needs_deeper_research":
                    connection.execute("UPDATE run_obligations SET satisfied=0,updated_at=? WHERE run_id=? AND obligation IN ('readiness','evaluation','technical_delivery','human_delivery','acceptance')", (now, run_id))
                self._fault("transition_after_side_effects")
                event_id = f"{event}-{revision}"
                self._snapshot_current_revision(connection, run_id, source_event_id=event_id)
                self._fault("transition_after_snapshot")
                self._event(connection, run_id, event_id, expected_revision, body, event_type=event)
                self._fault("transition_after_event")
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
            expected_display = self.delivery_pair_digest(
                row["run_id"], body["technical_digest"], body["human_digest"]
            )
            if body.get("displayed_digest") != expected_display:
                raise CoordinatorError(
                    "delivery display digest does not bind the exact pair",
                    code="stale_delivery_digest",
                )
        elif event == "delivery_accepted":
            require(("p0_closure", "insight_clear", "readiness", "evaluation", "technical_delivery", "human_delivery"))
            technical = body.get("technical_revision")
            human = body.get("human_revision")
            if technical != records["technical_delivery"]["evidence_ref"] or human != records["human_delivery"]["evidence_ref"]:
                raise CoordinatorError("acceptance does not bind exact delivery revisions", code="stale_acceptance")
            expected_display = self.delivery_pair_digest(
                row["run_id"], technical, human
            )
            if body.get("displayed_digest") != expected_display:
                raise CoordinatorError(
                    "acceptance display digest does not bind the exact delivery pair",
                    code="stale_acceptance",
                )
            if not isinstance(body.get("feedback"), str) or body["feedback"].strip().casefold() in {"", "ok", "okay", "yes", "continue", "go ahead"}:
                raise CoordinatorError("generic acknowledgement cannot accept delivery", code="invalid_acceptance")
        elif event == "cancel_requested":
            reason = body.get("termination_reason")
            if not isinstance(reason, str) or not reason.strip():
                raise CoordinatorError(
                    "cancellation reason is required", code="missing_termination_reason"
                )

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        return {"run_id": row["run_id"], "lifecycle_state": row["lifecycle_state"], "revision": row["revision"], "authority_digest": row["authority_digest"], "state_digest": row["state_digest"], "task_identity": json.loads(row["task_identity_json"]), "parent_run_id": row["parent_run_id"], "termination_reason": row["termination_reason"], "created_at": row["created_at"], "updated_at": row["updated_at"]}
