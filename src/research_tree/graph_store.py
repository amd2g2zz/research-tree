"""Kùzu object-graph projection — replayable from the graph event log (issue #546).

Write authority stays in SQLite (``RunLedger.graph_events``, hash-chained,
append-only). This store is a **projection**: ``rebuild(records)`` must reproduce
an identical state from the log alone (T0 acceptance, replay test in CI), and
every ``apply_event`` is idempotent (upserts + existence-checked edges).

Node identity uses a single-column primary key — Kùzu requires single-column
PKs (W0 smoke, kuzu 0.11.3). Version ids are ``"<task_id>:<v>"`` shaped by
convention upstream; the projection never assumes the shape.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable, Mapping

from .graph_events import GraphEventError, validate_graph_event

if TYPE_CHECKING:  # pragma: no cover
    import kuzu

# kuzu is a declared runtime dependency but imported lazily (inside
# _ensure_connection): the portable CLI (deployment form ①, any-host skill)
# must boot without the graph engine — graph use without kuzu raises at
# connection time. Encoded by tests/test_cli.py wheel --no-deps contract.

NODE_TABLES: tuple[str, ...] = ("Claim", "Stage", "Evidence", "Artifact", "VersionNode")
REL_TABLES: tuple[str, ...] = (
    "KILL_EDGE",
    "STAGE_DEPENDS_ON",
    "CONTAINS",
    "EVIDENCE_FOR",
    "ARTIFACT_FOR",
    "FORKED_FROM",
)

_NODE_COLUMNS: dict[str, tuple[str, ...]] = {
    "Claim": ("id", "text", "source", "weight", "posterior", "verify_tier", "stale", "updated_at"),
    "Stage": ("id", "title", "status", "updated_at"),
    "Evidence": ("id", "digest", "origin", "updated_at"),
    "Artifact": ("id", "kind", "digest", "deleted", "updated_at"),
    "VersionNode": ("id", "task_id", "v", "commit_hash", "verdict", "summary", "created_at"),
}

_REL_ENDPOINTS: dict[str, tuple[str, str]] = {
    "KILL_EDGE": ("Claim", "Claim"),
    "STAGE_DEPENDS_ON": ("Stage", "Stage"),
    "CONTAINS": ("Stage", "Claim"),
    "EVIDENCE_FOR": ("Evidence", "Claim"),
    "ARTIFACT_FOR": ("Artifact", "Claim"),
    "FORKED_FROM": ("VersionNode", "VersionNode"),
}

_DDL: tuple[str, ...] = (
    "CREATE NODE TABLE IF NOT EXISTS Claim(id STRING, text STRING, source STRING, "
    "weight STRING, posterior DOUBLE, verify_tier STRING, stale BOOLEAN, updated_at STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE IF NOT EXISTS Stage(id STRING, title STRING, status STRING, updated_at STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE IF NOT EXISTS Evidence(id STRING, digest STRING, origin STRING, "
    "updated_at STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE IF NOT EXISTS Artifact(id STRING, kind STRING, digest STRING, "
    "deleted BOOLEAN, updated_at STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE IF NOT EXISTS VersionNode(id STRING, task_id STRING, v INT64, "
    "commit_hash STRING, verdict STRING, summary STRING, created_at STRING, PRIMARY KEY(id))",
    "CREATE REL TABLE IF NOT EXISTS KILL_EDGE(FROM Claim TO Claim)",
    "CREATE REL TABLE IF NOT EXISTS STAGE_DEPENDS_ON(FROM Stage TO Stage)",
    "CREATE REL TABLE IF NOT EXISTS CONTAINS(FROM Stage TO Claim)",
    "CREATE REL TABLE IF NOT EXISTS EVIDENCE_FOR(FROM Evidence TO Claim)",
    "CREATE REL TABLE IF NOT EXISTS ARTIFACT_FOR(FROM Artifact TO Claim)",
    "CREATE REL TABLE IF NOT EXISTS FORKED_FROM(FROM VersionNode TO VersionNode)",
)


class GraphStore:
    """Replayable Kùzu projection of the graph event log."""

    def __init__(self, database: str) -> None:
        self.database = str(database)
        self._connection: kuzu.Connection | None = None

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    # ------------------------------------------------------------------ write

    def apply_event(self, record: Mapping[str, Any]) -> None:
        """Fold one event-log record into the projection (idempotent).

        Payloads are re-validated at the projection boundary: a record that
        reached the store without ledger-side validation cannot poison the graph.
        """
        event_type = record.get("event_type")
        payload = validate_graph_event(event_type, record.get("payload"))
        created_at = str(record.get("created_at", ""))
        getattr(self, f"_apply_{event_type.replace('.', '_')}")(payload, created_at)

    def rebuild(self, records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        """Wipe the projection and fold the full event log; returns the snapshot."""
        connection = self._ensure_connection()
        for table in NODE_TABLES:
            connection.execute(f"MATCH (n:{table}) DETACH DELETE n")
        for record in records:
            self.apply_event(record)
        return self.snapshot_state()

    # ------------------------------------------------------------------ read

    def snapshot_state(self) -> dict[str, Any]:
        """Deterministic full-state dump (equality anchor for replay tests)."""
        state: dict[str, Any] = {}
        for table, columns in _NODE_COLUMNS.items():
            projection = ", ".join(f"n.{column}" for column in columns)
            rows = self._rows(f"MATCH (n:{table}) RETURN {projection} ORDER BY n.id")
            state[table] = {row[0]: dict(zip(columns, row)) for row in rows}
        for rel, (source_table, target_table) in _REL_ENDPOINTS.items():
            rows = self._rows(
                f"MATCH (a:{source_table})-[:{rel}]->(b:{target_table}) RETURN a.id, b.id ORDER BY a.id, b.id"
            )
            state[rel] = [[row[0], row[1]] for row in rows]
        return state

    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for table in NODE_TABLES:
            counts[table] = self._rows(f"MATCH (n:{table}) RETURN count(*)")[0][0]
        for rel, (source_table, target_table) in _REL_ENDPOINTS.items():
            counts[rel] = self._rows(f"MATCH (:{source_table})-[:{rel}]->(:{target_table}) RETURN count(*)")[0][0]
        return counts

    def fork_parent(self, version_id: str) -> str | None:
        rows = self._rows(
            "MATCH (c:VersionNode {id: $id})-[:FORKED_FROM]->(p:VersionNode) RETURN p.id",
            {"id": version_id},
        )
        return rows[0][0] if rows else None

    def fork_children(self, version_id: str) -> list[str]:
        rows = self._rows(
            "MATCH (c:VersionNode)-[:FORKED_FROM]->(p:VersionNode {id: $id}) RETURN c.id ORDER BY c.id",
            {"id": version_id},
        )
        return [row[0] for row in rows]

    # ------------------------------------------------------------------ internal

    def _ensure_connection(self) -> "kuzu.Connection":
        if self._connection is None:
            import kuzu  # lazy: keep the wheel bootable without the graph engine

            database = kuzu.Database(self.database)
            self._connection = kuzu.Connection(database)
            for ddl in _DDL:
                self._connection.execute(ddl)
        return self._connection

    def _rows(self, query: str, parameters: dict[str, Any] | None = None) -> list[list[Any]]:
        result = self._ensure_connection().execute(query, parameters or {})
        rows: list[list[Any]] = []
        while result.has_next():
            rows.append(result.get_next())
        return rows

    def _upsert(self, table: str, columns: tuple[str, ...], values: dict[str, Any]) -> None:
        connection = self._ensure_connection()
        exists = connection.execute(f"MATCH (n:{table} {{id: $id}}) RETURN count(*)", {"id": values["id"]}).get_next()[
            0
        ]
        if exists:
            assignments = ", ".join(f"n.{column} = ${column}" for column in columns if column != "id")
            connection.execute(f"MATCH (n:{table} {{id: $id}}) SET {assignments}", values)
        else:
            props = ", ".join(f"{column}: ${column}" for column in columns)
            connection.execute(f"CREATE (:{table} {{{props}}})", values)

    def _ensure_edge(self, rel: str, source_id: str, target_id: str) -> None:
        source_table, target_table = _REL_ENDPOINTS[rel]
        connection = self._ensure_connection()
        exists = connection.execute(
            f"MATCH (a:{source_table} {{id: $src}})-[:{rel}]->(b:{target_table} {{id: $dst}}) RETURN count(*)",
            {"src": source_id, "dst": target_id},
        ).get_next()[0]
        if not exists:
            connection.execute(
                f"MATCH (a:{source_table} {{id: $src}}), (b:{target_table} {{id: $dst}}) CREATE (a)-[:{rel}]->(b)",
                {"src": source_id, "dst": target_id},
            )

    # node appliers (payload is validated; created_at stamps provenance)

    def _apply_claim_upsert(self, payload: dict[str, Any], created_at: str) -> None:
        claim = payload["claim"]
        self._upsert(
            "Claim",
            ("id", "text", "source", "weight", "posterior", "verify_tier", "stale", "updated_at"),
            {
                "id": claim["id"],
                "text": claim["text"],
                "source": claim["source"],
                "weight": claim["weight"],
                "posterior": claim["posterior"],
                "verify_tier": claim["verify_tier"],
                "stale": claim["stale"],
                "updated_at": created_at,
            },
        )

    def _apply_claim_kill_edge(self, payload: dict[str, Any], created_at: str) -> None:
        self._ensure_edge("KILL_EDGE", payload["claim_id"], payload["kill_target_id"])

    def _apply_stage_upsert(self, payload: dict[str, Any], created_at: str) -> None:
        stage = payload["stage"]
        self._upsert(
            "Stage",
            ("id", "title", "status", "updated_at"),
            {"id": stage["id"], "title": stage["title"], "status": stage["status"], "updated_at": created_at},
        )

    def _apply_stage_depends_on(self, payload: dict[str, Any], created_at: str) -> None:
        self._ensure_edge("STAGE_DEPENDS_ON", payload["stage_id"], payload["depends_on_id"])

    def _apply_stage_contains(self, payload: dict[str, Any], created_at: str) -> None:
        self._ensure_edge("CONTAINS", payload["stage_id"], payload["claim_id"])

    def _apply_evidence_upsert(self, payload: dict[str, Any], created_at: str) -> None:
        evidence = payload["evidence"]
        self._upsert(
            "Evidence",
            ("id", "digest", "origin", "updated_at"),
            {
                "id": evidence["id"],
                "digest": evidence["digest"],
                "origin": evidence["origin"],
                "updated_at": created_at,
            },
        )

    def _apply_evidence_attach(self, payload: dict[str, Any], created_at: str) -> None:
        self._ensure_edge("EVIDENCE_FOR", payload["evidence_id"], payload["claim_id"])

    def _apply_artifact_upsert(self, payload: dict[str, Any], created_at: str) -> None:
        artifact = payload["artifact"]
        self._upsert(
            "Artifact",
            ("id", "kind", "digest", "deleted", "updated_at"),
            {
                "id": artifact["id"],
                "kind": artifact["kind"],
                "digest": artifact["digest"],
                "deleted": artifact["deleted"],
                "updated_at": created_at,
            },
        )

    def _apply_artifact_link(self, payload: dict[str, Any], created_at: str) -> None:
        self._ensure_edge("ARTIFACT_FOR", payload["artifact_id"], payload["claim_id"])

    def _apply_version_commit(self, payload: dict[str, Any], created_at: str) -> None:
        version = payload["version"]
        self._upsert(
            "VersionNode",
            ("id", "task_id", "v", "commit_hash", "verdict", "summary", "created_at"),
            {
                "id": version["id"],
                "task_id": version["task_id"],
                "v": version["v"],
                "commit_hash": version["commit_hash"],
                "verdict": version["verdict"],
                "summary": version["summary"],
                "created_at": created_at,
            },
        )

    def _apply_fork_edge(self, payload: dict[str, Any], created_at: str) -> None:
        self._ensure_edge("FORKED_FROM", payload["child_version_id"], payload["parent_version_id"])


__all__ = ["GraphStore", "GraphEventError", "NODE_TABLES", "REL_TABLES"]
