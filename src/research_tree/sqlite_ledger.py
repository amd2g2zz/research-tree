"""SQLite artifact ledger sharing the coordinator's canonical workspace DB."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable, Mapping, Sequence

from .contracts import canonical_json_bytes
from .coordinator import ResearchRunCoordinator
from .closure import oracle_successor_actions
from .cas import ContentAddressedStore
from .worker_contracts import CanonicalWorkItem


class SQLiteLedgerError(ValueError):
    def __init__(self, message: str, *, code: str = "ledger_error") -> None:
        super().__init__(message)
        self.code = code


class SQLiteRunLedger:
    """Append-only artifact revisions with exact parent lineage."""

    def __init__(
        self,
        workspace: str | Path,
        *,
        fault_injector: Callable[[str], None] | None = None,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.cas = ContentAddressedStore(self.workspace)
        coordinator = ResearchRunCoordinator(workspace)
        self.coordinator = coordinator
        self._fault_injector = fault_injector
        self.database = coordinator.database
        with self._connect() as connection:
            connection.executescript("""
            CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY,applied_at TEXT NOT NULL,migration_digest TEXT NOT NULL UNIQUE);
            CREATE TABLE IF NOT EXISTS artifacts(
              run_id TEXT NOT NULL REFERENCES runs(run_id),artifact_id TEXT NOT NULL,revision INTEGER NOT NULL,
              kind TEXT NOT NULL,schema_version INTEGER NOT NULL,created_at TEXT NOT NULL,actor_kind TEXT NOT NULL,
              actor_id TEXT NOT NULL,status TEXT NOT NULL,payload_json TEXT NOT NULL,content_hash TEXT NOT NULL,
              PRIMARY KEY(run_id,artifact_id,revision),UNIQUE(run_id,content_hash));
            CREATE TABLE IF NOT EXISTS artifact_parents(
              run_id TEXT NOT NULL,artifact_id TEXT NOT NULL,revision INTEGER NOT NULL,parent_run_id TEXT NOT NULL,
              parent_artifact_id TEXT NOT NULL,parent_revision INTEGER NOT NULL,
              PRIMARY KEY(run_id,artifact_id,revision,parent_run_id,parent_artifact_id,parent_revision),
              FOREIGN KEY(run_id,artifact_id,revision) REFERENCES artifacts(run_id,artifact_id,revision),
              FOREIGN KEY(parent_run_id,parent_artifact_id,parent_revision) REFERENCES artifacts(run_id,artifact_id,revision));
            CREATE TABLE IF NOT EXISTS content_objects(
              run_id TEXT NOT NULL REFERENCES runs(run_id),digest TEXT NOT NULL,
              media_type TEXT NOT NULL,size_bytes INTEGER NOT NULL,locator TEXT NOT NULL,
              status TEXT NOT NULL,metadata_json TEXT NOT NULL,record_json TEXT NOT NULL,
              created_at TEXT NOT NULL,PRIMARY KEY(run_id,digest));
            CREATE TABLE IF NOT EXISTS evidence(
              run_id TEXT NOT NULL,evidence_id TEXT NOT NULL,revision INTEGER NOT NULL,
              artifact_digest TEXT NOT NULL,provenance_group TEXT NOT NULL,
              media_type TEXT NOT NULL,selector_json TEXT NOT NULL,
              acquisition_json TEXT NOT NULL,status TEXT NOT NULL,
              PRIMARY KEY(run_id,evidence_id,revision),
              FOREIGN KEY(run_id,evidence_id,revision)
                REFERENCES artifacts(run_id,artifact_id,revision));
            """)
            schema = canonical_json_bytes({"version": 1, "tables": ["runs", "events", "artifacts", "artifact_parents"]})
            connection.execute("INSERT OR IGNORE INTO schema_migrations VALUES(1,?,?)", (datetime.now(timezone.utc).isoformat(), hashlib.sha256(schema).hexdigest()))
            schema_v2 = canonical_json_bytes({"version": 2, "tables": ["runs", "events", "artifacts", "artifact_parents", "action_attempts", "run_obligations", "run_revisions", "host_events"]})
            connection.execute("INSERT OR IGNORE INTO schema_migrations VALUES(2,?,?)", (datetime.now(timezone.utc).isoformat(), hashlib.sha256(schema_v2).hexdigest()))
            schema_v3 = canonical_json_bytes({"version": 3, "tables": ["oracle_runs", "slot_closure_assessments"]})
            connection.execute("INSERT OR IGNORE INTO schema_migrations VALUES(3,?,?)", (datetime.now(timezone.utc).isoformat(), hashlib.sha256(schema_v3).hexdigest()))
            schema_v4 = canonical_json_bytes({"version": 4, "tables": ["oracle_specs", "oracle_attempts", "oracle_runs"]})
            connection.execute("INSERT OR IGNORE INTO schema_migrations VALUES(4,?,?)", (datetime.now(timezone.utc).isoformat(), hashlib.sha256(schema_v4).hexdigest()))
            schema_v5 = canonical_json_bytes({"version": 5, "tables": ["decision_slot_sets", "p0_closure_aggregates", "slot_closure_assessments.blueprint_binding_revision"]})
            connection.execute("INSERT OR IGNORE INTO schema_migrations VALUES(5,?,?)", (datetime.now(timezone.utc).isoformat(), hashlib.sha256(schema_v5).hexdigest()))
            schema_v6 = canonical_json_bytes({"version": 6, "tables": ["content_objects", "evidence"]})
            connection.execute("INSERT OR IGNORE INTO schema_migrations VALUES(6,?,?)", (datetime.now(timezone.utc).isoformat(), hashlib.sha256(schema_v6).hexdigest()))

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _fault(self, boundary: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(boundary)

    def create_run(
        self,
        run_id: str,
        *,
        task_identity: Mapping[str, Any] | None = None,
        authority: Mapping[str, Any] | None = None,
        parent_run_id: str | None = None,
    ) -> dict[str, Any]:
        return self.coordinator.create(
            run_id,
            task_identity=task_identity,
            authority=authority,
            parent_run_id=parent_run_id,
        )

    def events(self, run_id: str) -> list[dict[str, Any]]:
        return self.coordinator.events(run_id)

    def append_artifact(self, *, run_id: str, artifact_id: str, kind: str, payload: Mapping[str, Any], actor_kind: str, actor_id: str, status: str, parent_refs: Sequence[Mapping[str, Any]] = (), expected_revision: int | None = None, expected_run_revision: int | None = None, created_at: str | None = None) -> dict[str, Any]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run_row = connection.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if run_row is None:
                raise SQLiteLedgerError("run does not exist", code="run_not_found")
            if expected_run_revision is not None and int(run_row["revision"]) != expected_run_revision:
                raise SQLiteLedgerError("run expected revision is stale", code="stale_run_revision")
            current = int(connection.execute("SELECT COALESCE(MAX(revision),0) FROM artifacts WHERE run_id=? AND artifact_id=?", (run_id, artifact_id)).fetchone()[0])
            if expected_revision is not None and current != expected_revision:
                raise SQLiteLedgerError("artifact expected revision is stale", code="stale_revision")
            revision = current + 1
            parents = [dict(item) for item in parent_refs]
            for parent in parents:
                if connection.execute("SELECT 1 FROM artifacts WHERE run_id=? AND artifact_id=? AND revision=?", (parent.get("run_id"), parent.get("artifact_id"), parent.get("revision"))).fetchone() is None:
                    raise SQLiteLedgerError("parent artifact does not resolve", code="dangling_parent")
            stamp = created_at or datetime.now(timezone.utc).isoformat()
            body = {"schema_version": 1, "kind": kind, "id": artifact_id, "run_id": run_id, "revision": revision, "created_at": stamp, "actor": {"kind": actor_kind, "id": actor_id}, "status": status, "payload": dict(payload), "parent_refs": parents}
            content_hash = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
            try:
                connection.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?)", (run_id, artifact_id, revision, kind, 1, stamp, actor_kind, actor_id, status, canonical_json_bytes(payload).decode("utf-8"), content_hash))
            except sqlite3.IntegrityError as exc:
                raise SQLiteLedgerError("artifact conflicts with immutable ledger", code="artifact_conflict") from exc
            self._fault("after_artifact")
            for parent in parents:
                connection.execute("INSERT INTO artifact_parents VALUES(?,?,?,?,?,?)", (run_id, artifact_id, revision, parent["run_id"], parent["artifact_id"], parent["revision"]))
            self._fault("after_parents")
            run_revision = int(run_row["revision"]) + 1
            state = {
                "run_id": run_id,
                "revision": run_revision,
                "lifecycle_state": run_row["lifecycle_state"],
                "task_identity": json.loads(run_row["task_identity_json"]),
                "feedback_id": None,
            }
            state_digest = hashlib.sha256(canonical_json_bytes(state)).hexdigest()
            connection.execute(
                "UPDATE runs SET revision=?,state_digest=?,updated_at=? WHERE run_id=?",
                (run_revision, state_digest, datetime.now(timezone.utc).isoformat(), run_id),
            )
            self._fault("after_run_update")
            event_id = f"artifact-appended-{artifact_id}-{revision}"
            event_payload = {
                "artifact_id": artifact_id,
                "artifact_revision": revision,
                "kind": kind,
                "content_hash": content_hash,
            }
            raw_event = canonical_json_bytes(event_payload)
            sequence = int(
                connection.execute(
                    "SELECT COALESCE(MAX(sequence),0)+1 FROM events WHERE run_id=?",
                    (run_id,),
                ).fetchone()[0]
            )
            connection.execute(
                """INSERT INTO events(
                     run_id,event_id,sequence,event_type,expected_revision,payload_json,
                     payload_digest,accepted,error_code,causation_id,correlation_id,emitted_at
                   ) VALUES(?,?,?,?,?,?,?,1,NULL,NULL,NULL,?)""",
                (
                    run_id,
                    event_id,
                    sequence,
                    "artifact_appended",
                    int(run_row["revision"]),
                    raw_event.decode("utf-8"),
                    hashlib.sha256(raw_event).hexdigest(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            revoked_closure_tokens: list[str] = []
            aggregate: dict[str, Any] | None = None
            if kind == "decision-ledger-entry":
                revoked_closure_tokens = self.coordinator._revoke_latest_closures(
                    connection,
                    run_id,
                    decision_artifact_id=artifact_id,
                    decision_revision=revision,
                    reason="decision ledger revision superseded the closure parent",
                    event_expected_revision=run_revision,
                )
                current_binding = self.coordinator._current_blueprint_target_ref(
                    connection, run_id
                )
                if current_binding is not None:
                    binding_revision, blueprint_ref = current_binding
                    aggregate = self.coordinator._persist_p0_closure_aggregate(
                        connection,
                        run_id,
                        binding_revision=binding_revision,
                        blueprint_target_ref=blueprint_ref,
                    )
            self._fault("after_event")
            self.coordinator._snapshot_current_revision(
                connection, run_id, source_event_id=event_id
            )
        return {
            **body,
            "content_hash": content_hash,
            **(
                {"revoked_closure_tokens": revoked_closure_tokens, "p0_closure_aggregate": aggregate}
                if kind == "decision-ledger-entry"
                else {}
            ),
        }

    def schedule_oracle_successors(
        self,
        *,
        run_id: str,
        slot_id: str,
        oracle_run_ids: Sequence[str],
        expected_revision: int,
    ) -> dict[str, Any]:
        """Persist bounded successor Work Items for non-passing OracleRuns.

        The deterministic artifact id makes this operation replay-safe: a retry
        observes the existing Work Item and does not advance the run revision.
        """

        if not isinstance(slot_id, str) or not slot_id.strip():
            raise SQLiteLedgerError("slot_id is required", code="invalid_slot")
        if isinstance(oracle_run_ids, (str, bytes)):
            raise SQLiteLedgerError("oracle_run_ids must be a sequence", code="invalid_oracle_runs")
        requested = [str(item) for item in oracle_run_ids]
        if not requested or any(not item.strip() for item in requested):
            raise SQLiteLedgerError("oracle_run_ids must be nonempty", code="invalid_oracle_runs")
        current = self.coordinator.status(run_id)
        if int(current["revision"]) != expected_revision:
            raise SQLiteLedgerError("run expected revision is stale", code="stale_run_revision")
        runs = self.coordinator.oracle_runs(run_id)
        missing = sorted(set(requested) - set(runs))
        if missing:
            raise SQLiteLedgerError(
                f"OracleRun does not resolve: {missing[0]}", code="oracle_run_not_found"
            )
        actions = oracle_successor_actions([runs[item] for item in requested])
        work_items: list[dict[str, Any]] = []
        for action in actions:
            oracle_id = action["oracle_run_id"]
            safe_oracle = "".join(char if char.isalnum() or char == "-" else "-" for char in oracle_id).strip("-")
            work_item_id = f"oracle-{safe_oracle}-{action['action']}"
            if len(work_item_id) > 63:
                work_item_id = f"oracle-{hashlib.sha256(oracle_id.encode('utf-8')).hexdigest()[:16]}-{action['action']}"
            existing = self._latest_artifact(run_id, work_item_id)
            if existing is not None:
                if existing["kind"] != "work-item":
                    raise SQLiteLedgerError(
                        f"successor id conflicts with {existing['kind']}", code="artifact_conflict"
                    )
                continue
            oracle = runs[oracle_id]
            work = CanonicalWorkItem.create(
                work_item_id=work_item_id,
                slot_id=slot_id,
                action_kind=action["action"],
                objective=(
                    f"{action['reason']}; execute an independent successor for {oracle_id}."
                ),
                inputs=(
                    f"oracle-run:{oracle_id}",
                    f"oracle-attempt:{oracle['oracle_attempt_id']}",
                    f"oracle-spec:{oracle['oracle_spec_id']}@{oracle['oracle_spec_version']}",
                ),
                method=(
                    "independent-method-switch"
                    if action["action"] == "method_switch"
                    else "independent-validation"
                ),
                expected_output="A new OracleRun with reproducible evidence or an explicit bounded fallback.",
                success_oracle="The successor OracleRun is independently reproducible or the residual risk is recorded.",
                permission_profile="research-read-only",
                completion_evidence=(
                    f"oracle-run:{oracle_id}",
                    "successor-oracle-run",
                ),
            )
            artifact = self.append_artifact(
                run_id=run_id,
                artifact_id=work_item_id,
                kind="work-item",
                payload=work.to_dict(),
                actor_kind="coordinator",
                actor_id="oracle-successor-scheduler",
                status="pending",
                expected_run_revision=current["revision"],
            )
            current = self.coordinator.status(run_id)
            work_items.append(artifact)
        return {"run_id": run_id, "revision": current["revision"], "work_items": work_items, "actions": actions}

    def put_content(
        self,
        *,
        run_id: str,
        data: bytes,
        media_type: str,
        metadata: Mapping[str, Any] | None = None,
        expected_revision: int,
    ) -> dict[str, Any]:
        """Commit a CAS object and its SQLite metadata as canonical run state."""

        digest = self.cas.digest(data)
        with self._connect() as connection:
            run_row = connection.execute(
                "SELECT revision FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if run_row is None:
                raise SQLiteLedgerError("run does not exist", code="run_not_found")
            if int(run_row["revision"]) != expected_revision:
                raise SQLiteLedgerError(
                    "run expected revision is stale", code="stale_run_revision"
                )
            existing = connection.execute(
                "SELECT record_json FROM content_objects WHERE run_id=? AND digest=?",
                (run_id, digest),
            ).fetchone()
        if existing is not None:
            record = json.loads(existing["record_json"])
            requested_metadata = {} if metadata is None else dict(metadata)
            if record.get("media_type") != media_type or record.get("metadata") != requested_metadata:
                raise SQLiteLedgerError(
                    "content digest is already registered with different metadata",
                    code="content_metadata_conflict",
                )
            self.cas.verify(digest)
            return record
        staged = self.cas.stage_bytes(
            data,
            media_type=media_type,
            metadata=None if metadata is None else dict(metadata),
        )
        preexisting = self.cas.path_for(digest).is_file()
        promoted = self.cas.promote(digest)
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                run_row = connection.execute(
                    "SELECT * FROM runs WHERE run_id=?", (run_id,)
                ).fetchone()
                if run_row is None:
                    raise SQLiteLedgerError("run does not exist", code="run_not_found")
                if int(run_row["revision"]) != expected_revision:
                    raise SQLiteLedgerError(
                        "run expected revision is stale", code="stale_run_revision"
                    )
                encoded = canonical_json_bytes(promoted).decode("utf-8")
                connection.execute(
                    """INSERT INTO content_objects(
                         run_id,digest,media_type,size_bytes,locator,status,
                         metadata_json,record_json,created_at
                       ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        run_id,
                        digest,
                        promoted["media_type"],
                        promoted["size"],
                        promoted["locator"],
                        "committed",
                        canonical_json_bytes(promoted.get("metadata", {})).decode("utf-8"),
                        encoded,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                revision = expected_revision + 1
                state = {
                    "run_id": run_id,
                    "revision": revision,
                    "lifecycle_state": run_row["lifecycle_state"],
                    "task_identity": json.loads(run_row["task_identity_json"]),
                    "feedback_id": None,
                }
                state_digest = hashlib.sha256(canonical_json_bytes(state)).hexdigest()
                connection.execute(
                    "UPDATE runs SET revision=?,state_digest=?,updated_at=? WHERE run_id=?",
                    (revision, state_digest, datetime.now(timezone.utc).isoformat(), run_id),
                )
                event_id = f"content-committed-{digest}"
                self.coordinator._event(
                    connection,
                    run_id,
                    event_id,
                    expected_revision,
                    {
                        "digest": digest,
                        "media_type": promoted["media_type"],
                        "size_bytes": promoted["size"],
                    },
                    event_type="content_committed",
                )
                self.coordinator._snapshot_current_revision(
                    connection, run_id, source_event_id=event_id
                )
        except Exception:
            if not preexisting:
                self.cas.quarantine(digest, reason="SQLite content metadata commit failed")
            raise
        return dict(promoted)

    def _latest_artifact(self, run_id: str, artifact_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT kind,revision FROM artifacts WHERE run_id=? AND artifact_id=? ORDER BY revision DESC LIMIT 1",
                (run_id, artifact_id),
            ).fetchone()
        if row is None:
            return None
        return {"kind": row["kind"], "revision": int(row["revision"])}

    def resolve(self, run_id: str, artifact_id: str, revision: int) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM artifacts WHERE run_id=? AND artifact_id=? AND revision=?", (run_id, artifact_id, revision)).fetchone()
            if row is None:
                raise SQLiteLedgerError("artifact revision does not exist", code="artifact_not_found")
            parents = connection.execute("SELECT parent_run_id,parent_artifact_id,parent_revision FROM artifact_parents WHERE run_id=? AND artifact_id=? AND revision=? ORDER BY parent_run_id,parent_artifact_id,parent_revision", (run_id, artifact_id, revision)).fetchall()
        body = {"schema_version": row["schema_version"], "kind": row["kind"], "id": row["artifact_id"], "run_id": row["run_id"], "revision": row["revision"], "created_at": row["created_at"], "actor": {"kind": row["actor_kind"], "id": row["actor_id"]}, "status": row["status"], "payload": json.loads(row["payload_json"]), "parent_refs": [{"run_id": item["parent_run_id"], "artifact_id": item["parent_artifact_id"], "revision": item["parent_revision"]} for item in parents]}
        if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != row["content_hash"]:
            raise SQLiteLedgerError("artifact content hash mismatch", code="digest_mismatch")
        return {**body, "content_hash": row["content_hash"]}

    def reconstruct(self, run_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            if connection.execute("SELECT 1 FROM runs WHERE run_id=?", (run_id,)).fetchone() is None:
                raise SQLiteLedgerError("run does not exist", code="run_not_found")
            refs = connection.execute("SELECT artifact_id,revision FROM artifacts WHERE run_id=? ORDER BY artifact_id,revision", (run_id,)).fetchall()
            content_rows = connection.execute(
                "SELECT record_json FROM content_objects WHERE run_id=? ORDER BY digest",
                (run_id,),
            ).fetchall()
        artifacts = [self.resolve(run_id, row["artifact_id"], row["revision"]) for row in refs]
        content_objects = [json.loads(row["record_json"]) for row in content_rows]
        digest = hashlib.sha256(
            canonical_json_bytes({"artifacts": artifacts, "content_objects": content_objects})
        ).hexdigest()
        return {
            "run_id": run_id,
            "artifacts": artifacts,
            "content_objects": content_objects,
            "semantic_digest": digest,
        }
