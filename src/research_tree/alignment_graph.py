"""SQLite-backed temporal heterogeneous multigraph for pre-research alignment."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
from typing import Any, Iterable, Mapping, Sequence

from .contracts import validate_feedback_event
from .alignment_strategy import select_alignment_action


SCHEMA = 2
MAX_TURNS = 6
MAX_STAGNANT_TURNS = 2
MAX_ASKS_PER_NODE = 2
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
NODE_TYPES = frozenset(
    {
        "human_belief",
        "agent_belief",
        "intent_hypothesis",
        "outcome",
        "intended_use",
        "scope_boundary",
        "delivery",
        "authority",
        "success_oracle",
        "feasibility",
        "constraint",
        "unknown",
        "research_question",
        "evidence",
        "disagreement",
        "argument",
        "strategy",
        "decision",
    }
)
EDGE_RELATIONS = frozenset(
    {
        "asserts",
        "supports",
        "contradicts",
        "limits",
        "refines",
        "supersedes",
        "depends_on",
        "answers",
        "informs",
        "accepted_by",
        "derived_from",
    }
)
NODE_STATUSES = frozenset(
    {"candidate", "supported", "disputed", "resolved", "accepted", "deferred", "rejected"}
)
EDGE_STATUSES = frozenset({"active", "superseded", "rejected"})
CONFIDENCES = frozenset({"low", "medium", "high"})
SOURCES = frozenset({"human", "agent", "joint", "reconnaissance", "repository", "experiment"})
OUTCOMES = frozenset({"answered", "changed", "unchanged", "deferred", "reopened"})
REQUIRED_ALIGNMENT_TYPES = (
    "outcome",
    "intended_use",
    "scope_boundary",
    "delivery",
    "authority",
    "success_oracle",
    "feasibility",
    "strategy",
)
ACCEPTED_STATUSES = frozenset({"supported", "resolved", "accepted"})
RESEARCHABLE_TYPES = frozenset({"unknown", "research_question", "disagreement"})


class AlignmentGraphError(ValueError):
    """Raised when alignment state or a graph transition is invalid."""


ControllerError = AlignmentGraphError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _identifier(value: Any, label: str) -> str:
    text = str(value)
    if not IDENTIFIER_RE.fullmatch(text):
        raise AlignmentGraphError(f"invalid {label}: {text!r}")
    return text


def _enum(value: Any, allowed: Iterable[str], label: str) -> str:
    text = str(value)
    if text not in allowed:
        allowed_values = ", ".join(sorted(str(item) for item in allowed))
        raise AlignmentGraphError(f"unsupported {label}: {text!r}; allowed: {allowed_values}")
    return text


def _text(value: Any, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise AlignmentGraphError(f"{label} must be nonempty")
    return text


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    descriptor, raw_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw_path)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _run_dir(workspace: Path, run_id: str) -> Path:
    root = workspace.resolve()
    target = (root / ".research-tree-alignment" / _identifier(run_id, "run id")).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise AlignmentGraphError("alignment database must remain in the workspace") from exc
    return target


def database_path(workspace: Path, run_id: str) -> Path:
    return _run_dir(workspace, run_id) / "alignment.db"


class AlignmentGraphStore:
    """Persist graph events and a rebuildable materialized view in SQLite."""

    def __init__(self, database: Path) -> None:
        self.database = database.resolve()
        self.database.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self, run_id: str) -> dict[str, Any]:
        run_id = _identifier(run_id, "run id")
        if self.database.exists():
            raise AlignmentGraphError(f"alignment run already exists: {run_id}")
        with self._connect() as connection:
            self._create_schema(connection)
            now = _now()
            connection.execute(
                """
                INSERT INTO controller(
                    singleton, run_id, phase, status, turn, stagnant_turns,
                    plan_count, revision, created_at, updated_at
                ) VALUES(1, ?, 'exploring', 'alignment', 0, 0, 0, 0, ?, ?)
                """,
                (run_id, now, now),
            )
            self._commit_event(connection, "run_initialized", {"run_id": run_id})
        return self.status()

    def merge(self, update: Mapping[str, Any]) -> dict[str, Any]:
        nodes, edges = _normalize_update(update)
        with self._connect() as connection:
            self._require_schema(connection)
            for node in nodes:
                self._upsert_node(connection, node)
            for edge in edges:
                self._upsert_edge(connection, edge)
            self._commit_event(
                connection,
                "graph_merged",
                {"node_ids": [node["id"] for node in nodes], "edge_ids": [edge["id"] for edge in edges]},
            )
        return self.status()

    def plan(self, update: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if update is not None:
            self.merge(update)
        with self._connect() as connection:
            self._require_schema(connection)
            state = self._materialize(connection)
            nodes = state["graph"]["nodes"]
            readiness = _alignment_readiness(nodes, state["graph"]["edges"])
            controller = state["controller"]
            eligible = [
                node
                for node in nodes
                if node["human_only"]
                and node["status"] in {"candidate", "disputed"}
                and node["ask_count"] < MAX_ASKS_PER_NODE
                and node["last_asked_turn"] != controller["turn"]
            ]
            eligible.sort(key=lambda node: (-node["impact"], node["ask_count"], node["id"]))
            if readiness["ready"]:
                decision: dict[str, Any] = {
                    "action": "await_human_confirmation",
                    "reason": "the alignment graph supports a strategy handoff",
                    "question": None,
                }
            elif controller["stagnant_turns"] >= MAX_STAGNANT_TURNS:
                decision = {
                    "action": "reconnaissance",
                    "reason": "two consecutive turns produced no graph change",
                    "question": None,
                }
            elif controller["turn"] >= MAX_TURNS:
                decision = {
                    "action": "reconnaissance",
                    "reason": "alignment dialogue limit reached; resolve remaining nodes with evidence",
                    "question": None,
                }
            elif eligible:
                node = eligible[0]
                connection.execute(
                    "UPDATE nodes SET ask_count=ask_count+1, last_asked_turn=? WHERE node_id=?",
                    (controller["turn"], node["id"]),
                )
                connection.execute(
                    "UPDATE controller SET pending_node_id=? WHERE singleton=1", (node["id"],)
                )
                decision = {
                    "action": "ask_one",
                    "node_id": node["id"],
                    "gap_id": node["id"],
                    "question": f"Ask one open-ended question about: {node['statement']}",
                    "reason": "highest-impact unresolved point that only the requester can settle",
                }
            else:
                reason = "; ".join(readiness["reasons"][:3])
                decision = {
                    "action": "reconnaissance",
                    "reason": reason or "remaining uncertainty is agent-verifiable",
                    "question": None,
                }
            strategy_decision, _strategy_state = select_alignment_action(
                nodes=nodes, readiness=readiness, turn=int(controller["turn"]), graph_digest=_digest({"nodes": nodes, "edges": state["graph"]["edges"]})
            )
            # Keep the existing action contract, but persist the internal rationale
            # and only adopt the strategy projection's open prompt when it is safer.
            decision["strategy_state"] = strategy_decision["strategy_state"]
            connection.execute(
                """
                UPDATE controller
                SET plan_count=plan_count+1, last_decision_json=?
                WHERE singleton=1
                """,
                (_json(decision),),
            )
            state = self._commit_event(connection, "plan_selected", decision)
        return {
            **decision,
            "turn": state["controller"]["turn"],
            "stagnant_turns": state["controller"]["stagnant_turns"],
            "alignment_digest": state["graph_digest"],
            "readiness": readiness,
        }

    def record(
        self, node_id: str, outcome: str, fingerprint: str
    ) -> dict[str, Any]:
        node_id = _identifier(node_id, "node id")
        outcome = _enum(outcome, OUTCOMES, "outcome")
        with self._connect() as connection:
            self._require_schema(connection)
            node = connection.execute(
                "SELECT * FROM nodes WHERE node_id=?", (node_id,)
            ).fetchone()
            if node is None:
                raise AlignmentGraphError(f"unknown graph node: {node_id}")
            controller = connection.execute(
                "SELECT * FROM controller WHERE singleton=1"
            ).fetchone()
            pending_node_id = controller["pending_node_id"]
            last_decision = json.loads(controller["last_decision_json"] or "{}")
            if pending_node_id is None and last_decision.get("action") == "ask_one":
                pending_node_id = last_decision.get("node_id") or last_decision.get("gap_id")
            if pending_node_id is None:
                raise AlignmentGraphError("no pending alignment action; record a typed FeedbackEvent")
            if pending_node_id != node_id:
                raise AlignmentGraphError(
                    f"response targets {node_id}, but pending action is {pending_node_id}"
                )
            hashed = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
            changed = hashed != controller["last_fingerprint"]
            turn = int(controller["turn"]) + 1
            stagnant = int(controller["stagnant_turns"])
            status = node["status"]
            if outcome == "answered":
                status = "resolved"
                stagnant = 0
            elif outcome == "changed":
                stagnant = 0
            elif outcome == "reopened":
                status = "candidate"
                stagnant = 0
            elif not changed:
                stagnant += 1
            connection.execute(
                "UPDATE nodes SET status=?, updated_at=? WHERE node_id=?",
                (status, _now(), node_id),
            )
            connection.execute(
                """
                UPDATE controller
                SET turn=?, stagnant_turns=?, last_fingerprint=?, pending_node_id=NULL
                WHERE singleton=1
                """,
                (turn, stagnant, hashed),
            )
            state = self._commit_event(
                connection,
                "response_recorded",
                {"node_id": node_id, "outcome": outcome, "state_changed": changed},
            )
        return {
            "turn": state["controller"]["turn"],
            "stagnant_turns": state["controller"]["stagnant_turns"],
            "state_changed": changed,
            "next_action": "reconnaissance" if stagnant >= MAX_STAGNANT_TURNS else "plan",
        }

    def apply_correction(
        self, feedback: Mapping[str, Any], *, expected_revision: int,
        successor_update: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Atomically quarantine handoff state after a material correction.

        The previous graph remains available through the event snapshots.  Any
        optional successor graph must use new identifiers; callers express
        replacement explicitly with a ``supersedes`` edge.
        """

        normalized = validate_feedback_event(feedback)
        if normalized["materiality"] not in {"material", "terminal"}:
            raise AlignmentGraphError("only material feedback can invalidate alignment")
        with self._connect() as connection:
            self._require_schema(connection)
            controller = connection.execute(
                "SELECT * FROM controller WHERE singleton=1"
            ).fetchone()
            if controller is None:
                raise AlignmentGraphError("alignment controller state is missing")
            if int(controller["revision"]) != expected_revision:
                raise AlignmentGraphError("alignment revision is stale")
            prior_state = self._materialize(connection)
            existing_event = connection.execute(
                "SELECT 1 FROM events WHERE event_id=?", ("feedback-" + normalized["feedback_id"],)
            ).fetchone()
            if existing_event:
                raise AlignmentGraphError("feedback event has already been recorded")
            invalidated = list(prior_state["controller"].get("invalidated_digests", []))
            handoff = prior_state["controller"].get("handoff")
            if handoff and handoff.get("alignment_digest"):
                invalidated.append(str(handoff["alignment_digest"]))
            for ref in normalized["target_refs"]:
                if str(ref).startswith("strategy:"):
                    invalidated.append(str(ref).split(":", 1)[1])
            invalidated = sorted(set(invalidated))
            if successor_update is not None:
                nodes, edges = _normalize_update(successor_update)
                current_ids = {
                    row["node_id"] for row in connection.execute("SELECT node_id FROM nodes")
                }
                reused = sorted({node["id"] for node in nodes} & current_ids)
                if reused:
                    raise AlignmentGraphError(
                        "correction successor must use new node ids: " + ", ".join(reused)
                    )
                for node in nodes:
                    self._upsert_node(connection, node)
                for edge in edges:
                    self._upsert_edge(connection, edge)
            connection.execute(
                "UPDATE controller SET phase='alignment', status='alignment', pending_node_id=NULL, last_decision_json=NULL, handoff_json=NULL, invalidated_digests_json=? WHERE singleton=1",
                (_json(invalidated),),
            )
            state = self._commit_event(
                connection,
                "correction_received",
                {
                    "feedback": normalized,
                    "invalidated_digests": invalidated,
                    "prior_revision": expected_revision,
                    "successor_graph": successor_update is not None,
                },
            )
        return state

    def confirm(self, confirmation: str, expected_digest: str | None = None) -> dict[str, Any]:
        text = " ".join(confirmation.split())
        if not text:
            raise AlignmentGraphError("handoff confirmation must be nonempty")
        if text.casefold() in {"ok", "okay", "yes", "continue", "go ahead", "可以", "继续"}:
            raise AlignmentGraphError("generic acknowledgement is not handoff confirmation")
        with self._connect() as connection:
            self._require_schema(connection)
            state = self._materialize(connection)
            readiness = _alignment_readiness(
                state["graph"]["nodes"], state["graph"]["edges"]
            )
            if not readiness["ready"]:
                raise AlignmentGraphError(
                    "alignment graph is not ready: " + "; ".join(readiness["reasons"])
                )
            last_decision = state["controller"].get("last_decision") or {}
            if last_decision.get("action") != "await_human_confirmation":
                raise AlignmentGraphError("cannot confirm before the handoff draft is shown")
            if expected_digest is None:
                raise AlignmentGraphError(
                    "handoff confirmation must include the alignment digest shown in the draft"
                )
            if expected_digest != state["graph_digest"]:
                raise AlignmentGraphError("alignment graph changed after the displayed handoff draft")
            connection.execute(
                "UPDATE nodes SET status='accepted', updated_at=? WHERE node_type='strategy' AND status IN ('supported','resolved')",
                (_now(),),
            )
            handoff = {
                "confirmed_at": _now(),
                "confirmation_digest": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "alignment_digest": state["graph_digest"],
                "actor_id": "requester",
            }
            connection.execute(
                """
                UPDATE controller
                SET status='autonomous', phase='research', handoff_json=?
                WHERE singleton=1
                """,
                (_json(handoff),),
            )
            state = self._commit_event(connection, "handoff_confirmed", handoff)
        return {
            "status": state["controller"]["status"],
            "phase": state["controller"]["phase"],
            "handoff": state["controller"]["handoff"],
        }

    def compile_handoff(self) -> dict[str, Any]:
        state = self.status()
        if state["controller"]["status"] != "autonomous":
            raise AlignmentGraphError("alignment must be explicitly confirmed before compilation")
        nodes = {node["id"]: node for node in state["graph"]["nodes"]}
        active_edges = [
            edge for edge in state["graph"]["edges"] if edge["status"] == "active"
        ]
        superseded_by: dict[str, list[str]] = {}
        for edge in active_edges:
            if (
                edge["relation"] in {"supersedes", "refines"}
                and edge["source_id"] in nodes
                and edge["target_id"] in nodes
                and nodes[edge["source_id"]]["type"] in RESEARCHABLE_TYPES
                and nodes[edge["target_id"]]["type"] in RESEARCHABLE_TYPES
            ):
                superseded_by.setdefault(edge["target_id"], []).append(edge["source_id"])
        slots: dict[str, dict[str, Any]] = {}
        for node in nodes.values():
            if (
                node["type"] not in RESEARCHABLE_TYPES
                or node["human_only"]
                or node["id"] in superseded_by
                or node["status"] in {"resolved", "accepted", "rejected"}
            ):
                continue
            oracle = node.get("oracle")
            if not oracle:
                raise AlignmentGraphError(f"research node {node['id']} has no closure oracle")
            slots[node["id"]] = {
                "status": "open",
                "priority": "P0" if node["impact"] >= 5 else "P1" if node["impact"] >= 3 else "P2",
                "uncertainty": {"low": "high", "medium": "medium", "high": "low"}[node["confidence"]],
                "question": node["statement"],
                "validation": {"oracle": oracle},
            }
        if not slots:
            raise AlignmentGraphError("confirmed alignment graph has no executable research question")
        baseline_findings: list[dict[str, Any]] = []
        compiled_evidence_ids: set[str] = set()
        evidence_paths: dict[tuple[str, str], list[list[dict[str, Any]]]] = {}
        for source in nodes.values():
            if source["type"] != "evidence" or source["status"] not in ACCEPTED_STATUSES:
                continue
            anchor = source["attributes"].get("anchor")
            if not isinstance(anchor, Mapping) or not anchor.get("kind") or not anchor.get("ref"):
                raise AlignmentGraphError(
                    f"supported evidence node {source['id']} has no structured anchor"
                )
            for target_id, path in _evidence_paths_to_slots(
                source["id"], nodes, active_edges, set(slots)
            ):
                evidence_paths.setdefault((source["id"], target_id), []).append(path)
        for (evidence_id, target_id), paths in sorted(evidence_paths.items()):
            source = nodes[evidence_id]
            anchor = source["attributes"]["anchor"]
            compiled_evidence_ids.add(evidence_id)
            finding_id = "alignment-" + hashlib.sha256(
                f"{evidence_id}:{target_id}".encode("utf-8")
            ).hexdigest()[:20]
            baseline_findings.append(
                {
                    "id": finding_id,
                    "decision_slot_id": target_id,
                    "research_node_id": None,
                    "observations": [
                        {
                            "claim": source["statement"],
                            "anchor": {"kind": str(anchor["kind"]), "ref": str(anchor["ref"])},
                            "alignment_paths": paths,
                        }
                    ],
                    "option_effects": [],
                    "remaining_uncertainties": [],
                    "research_continuations": [],
                    "oracle_run_refs": [],
                }
            )
        dropped_evidence = []
        for node in nodes.values():
            if node["type"] != "evidence" or node["status"] not in ACCEPTED_STATUSES:
                continue
            if node["id"] in compiled_evidence_ids:
                continue
            disposition = node["attributes"].get("handoff_disposition")
            if disposition != "alignment_only":
                dropped_evidence.append(
                    {
                        "node_id": node["id"],
                        "reason": "no active edge connects this evidence to a current Decision Slot",
                    }
                )
        if dropped_evidence:
            raise AlignmentGraphError(
                "supported evidence would be dropped during handoff: "
                + ", ".join(item["node_id"] for item in dropped_evidence)
            )
        objective = next(
            node["statement"]
            for node in nodes.values()
            if node["type"] == "outcome" and node["status"] in ACCEPTED_STATUSES
        )
        strategy = next(
            node["statement"]
            for node in nodes.values()
            if node["type"] == "strategy" and node["status"] in ACCEPTED_STATUSES
        )
        execution_context = {
            "objective": objective,
            "intended_use": _accepted_statements(nodes, "intended_use"),
            "scope_boundaries": _accepted_statements(nodes, "scope_boundary"),
            "delivery": _accepted_statements(nodes, "delivery"),
            "authority": _accepted_statements(nodes, "authority"),
            "success_oracles": _accepted_statements(nodes, "success_oracle"),
            "feasibility": _accepted_statements(nodes, "feasibility"),
            "constraints": _accepted_statements(nodes, "constraint"),
            "strategy": strategy,
        }
        return {
            "schema": 1,
            "kind": "alignment-handoff",
            "run_id": state["controller"]["run_id"],
            "alignment_revision": state["controller"]["revision"],
            "alignment_digest": state["controller"]["handoff"]["alignment_digest"],
            "strategy_digest": state["controller"]["handoff"]["alignment_digest"],
            "compiled_graph_digest": state["graph_digest"],
            "objective": objective,
            "strategy": strategy,
            "execution_context": execution_context,
            "decision_slots": slots,
            "baseline_findings": baseline_findings,
            "diagnostics": {
                "excluded_superseded_nodes": [
                    {"node_id": node_id, "superseded_by": sorted(source_ids)}
                    for node_id, source_ids in sorted(superseded_by.items())
                ],
                "dropped_evidence": [],
            },
            "confirmation": {
                "actor_id": state["controller"]["handoff"].get("actor_id", "requester"),
                "response_digest": state["controller"]["handoff"]["confirmation_digest"],
                "displayed_strategy_digest": state["controller"]["handoff"]["alignment_digest"],
                "confirmed_at": state["controller"]["handoff"]["confirmed_at"],
            },
            "alignment_graph": state["graph"],
        }

    def status(self) -> dict[str, Any]:
        with self._connect() as connection:
            self._require_schema(connection)
            return self._materialize(connection)

    def rebuild_materialized(self) -> dict[str, Any]:
        with self._connect() as connection:
            self._require_schema(connection)
            event = connection.execute(
                "SELECT state_json FROM events ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            if event is None:
                raise AlignmentGraphError("alignment event log is empty")
            state = json.loads(event["state_json"])
            connection.execute("DELETE FROM edges")
            connection.execute("DELETE FROM nodes")
            self._restore_state(connection, state)
        return self.status()

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO metadata(key, value) VALUES('schema', '2');
            CREATE TABLE controller(
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                run_id TEXT NOT NULL,
                phase TEXT NOT NULL,
                status TEXT NOT NULL,
                turn INTEGER NOT NULL,
                stagnant_turns INTEGER NOT NULL,
                plan_count INTEGER NOT NULL,
                revision INTEGER NOT NULL,
                last_fingerprint TEXT,
                pending_node_id TEXT,
                last_decision_json TEXT,
                handoff_json TEXT,
                invalidated_digests_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE nodes(
                node_id TEXT PRIMARY KEY,
                node_type TEXT NOT NULL,
                statement TEXT NOT NULL,
                status TEXT NOT NULL,
                impact INTEGER NOT NULL CHECK(impact BETWEEN 1 AND 5),
                human_only INTEGER NOT NULL CHECK(human_only IN (0,1)),
                confidence TEXT NOT NULL,
                source TEXT NOT NULL,
                oracle TEXT,
                attributes_json TEXT NOT NULL,
                ask_count INTEGER NOT NULL DEFAULT 0,
                last_asked_turn INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE edges(
                edge_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES nodes(node_id),
                target_id TEXT NOT NULL REFERENCES nodes(node_id),
                relation TEXT NOT NULL,
                status TEXT NOT NULL,
                confidence TEXT NOT NULL,
                provenance TEXT NOT NULL,
                attributes_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX edges_source_idx ON edges(source_id, relation, status);
            CREATE INDEX edges_target_idx ON edges(target_id, relation, status);
            CREATE TABLE events(
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                details_json TEXT NOT NULL,
                state_json TEXT NOT NULL,
                state_digest TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )

    @staticmethod
    def _require_schema(connection: sqlite3.Connection) -> None:
        try:
            row = connection.execute("SELECT value FROM metadata WHERE key='schema'").fetchone()
        except sqlite3.OperationalError as exc:
            raise AlignmentGraphError("alignment database schema is missing") from exc
        if row is None or row["value"] != str(SCHEMA):
            raise AlignmentGraphError("unsupported alignment database schema")
        columns = {
            item["name"] for item in connection.execute("PRAGMA table_info(controller)")
        }
        if "invalidated_digests_json" not in columns:
            connection.execute(
                "ALTER TABLE controller ADD COLUMN invalidated_digests_json TEXT NOT NULL DEFAULT '[]'"
            )

    @staticmethod
    def _upsert_node(connection: sqlite3.Connection, node: Mapping[str, Any]) -> None:
        now = _now()
        prior = connection.execute(
            "SELECT ask_count, last_asked_turn, created_at FROM nodes WHERE node_id=?", (node["id"],)
        ).fetchone()
        connection.execute(
            """
            INSERT INTO nodes(
                node_id,node_type,statement,status,impact,human_only,confidence,
                source,oracle,attributes_json,ask_count,last_asked_turn,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(node_id) DO UPDATE SET
                node_type=excluded.node_type, statement=excluded.statement,
                status=excluded.status, impact=excluded.impact,
                human_only=excluded.human_only, confidence=excluded.confidence,
                source=excluded.source, oracle=excluded.oracle,
                attributes_json=excluded.attributes_json, updated_at=excluded.updated_at
            """,
            (
                node["id"], node["type"], node["statement"], node["status"], node["impact"],
                int(node["human_only"]), node["confidence"], node["source"], node.get("oracle"),
                _json(node["attributes"]), int(prior["ask_count"]) if prior else 0,
                prior["last_asked_turn"] if prior else None, prior["created_at"] if prior else now, now,
            ),
        )

    @staticmethod
    def _upsert_edge(connection: sqlite3.Connection, edge: Mapping[str, Any]) -> None:
        now = _now()
        prior = connection.execute(
            "SELECT created_at FROM edges WHERE edge_id=?", (edge["id"],)
        ).fetchone()
        try:
            connection.execute(
                """
                INSERT INTO edges(
                    edge_id,source_id,target_id,relation,status,confidence,
                    provenance,attributes_json,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(edge_id) DO UPDATE SET
                    source_id=excluded.source_id,target_id=excluded.target_id,
                    relation=excluded.relation,status=excluded.status,
                    confidence=excluded.confidence,provenance=excluded.provenance,
                    attributes_json=excluded.attributes_json,updated_at=excluded.updated_at
                """,
                (
                    edge["id"], edge["source_id"], edge["target_id"], edge["relation"],
                    edge["status"], edge["confidence"], edge["provenance"],
                    _json(edge["attributes"]), prior["created_at"] if prior else now, now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise AlignmentGraphError(f"edge {edge['id']} references an unknown node") from exc

    def _commit_event(
        self, connection: sqlite3.Connection, event_type: str, details: Mapping[str, Any]
    ) -> dict[str, Any]:
        connection.execute(
            "UPDATE controller SET revision=revision+1, updated_at=? WHERE singleton=1", (_now(),)
        )
        state = self._materialize(connection)
        state_json = _json(state)
        state_digest = hashlib.sha256(state_json.encode("utf-8")).hexdigest()
        revision = state["controller"]["revision"]
        event_id = f"event-{revision:08d}-{state_digest[:12]}"
        connection.execute(
            """
            INSERT INTO events(event_id,event_type,details_json,state_json,state_digest,created_at)
            VALUES(?,?,?,?,?,?)
            """,
            (event_id, event_type, _json(details), state_json, state_digest, _now()),
        )
        return state

    @staticmethod
    def _materialize(connection: sqlite3.Connection) -> dict[str, Any]:
        controller = connection.execute(
            "SELECT * FROM controller WHERE singleton=1"
        ).fetchone()
        if controller is None:
            raise AlignmentGraphError("alignment controller state is missing")
        nodes = [
            {
                "id": row["node_id"], "type": row["node_type"], "statement": row["statement"],
                "status": row["status"], "impact": row["impact"],
                "human_only": bool(row["human_only"]), "confidence": row["confidence"],
                "source": row["source"], "oracle": row["oracle"],
                "attributes": json.loads(row["attributes_json"]), "ask_count": row["ask_count"],
                "last_asked_turn": row["last_asked_turn"], "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in connection.execute("SELECT * FROM nodes ORDER BY node_id")
        ]
        edges = [
            {
                "id": row["edge_id"], "source_id": row["source_id"],
                "target_id": row["target_id"], "relation": row["relation"],
                "status": row["status"], "confidence": row["confidence"],
                "provenance": row["provenance"],
                "attributes": json.loads(row["attributes_json"]),
                "created_at": row["created_at"], "updated_at": row["updated_at"],
            }
            for row in connection.execute("SELECT * FROM edges ORDER BY edge_id")
        ]
        graph = {"nodes": nodes, "edges": edges}
        return {
            "schema": SCHEMA,
            "controller": {
                "run_id": controller["run_id"], "phase": controller["phase"],
                "status": controller["status"], "turn": controller["turn"],
                "stagnant_turns": controller["stagnant_turns"],
                "plan_count": controller["plan_count"], "revision": controller["revision"],
                "last_fingerprint": controller["last_fingerprint"],
                "pending_node_id": controller["pending_node_id"],
                "last_decision": json.loads(controller["last_decision_json"])
                if controller["last_decision_json"] else None,
                "handoff": json.loads(controller["handoff_json"])
                if controller["handoff_json"] else None,
                "invalidated_digests": json.loads(controller["invalidated_digests_json"] or "[]"),
                "created_at": controller["created_at"], "updated_at": controller["updated_at"],
            },
            "graph": graph,
            "graph_digest": _digest(graph),
        }

    def _restore_state(self, connection: sqlite3.Connection, state: Mapping[str, Any]) -> None:
        controller = state["controller"]
        connection.execute(
            """
            UPDATE controller SET run_id=?,phase=?,status=?,turn=?,stagnant_turns=?,
                plan_count=?,revision=?,last_fingerprint=?,pending_node_id=?,
                last_decision_json=?,handoff_json=?,invalidated_digests_json=?,created_at=?,updated_at=? WHERE singleton=1
            """,
            (
                controller["run_id"], controller["phase"], controller["status"], controller["turn"],
                controller["stagnant_turns"], controller["plan_count"], controller["revision"],
                controller["last_fingerprint"], controller["pending_node_id"],
                _json(controller["last_decision"]) if controller["last_decision"] else None,
                _json(controller["handoff"]) if controller["handoff"] else None,
                _json(controller.get("invalidated_digests", [])),
                controller["created_at"], controller["updated_at"],
            ),
        )
        for node in state["graph"]["nodes"]:
            self._upsert_node(connection, node)
            connection.execute(
                "UPDATE nodes SET ask_count=?,last_asked_turn=?,created_at=?,updated_at=? WHERE node_id=?",
                (node["ask_count"], node["last_asked_turn"], node["created_at"], node["updated_at"], node["id"]),
            )
        for edge in state["graph"]["edges"]:
            self._upsert_edge(connection, edge)
            connection.execute(
                "UPDATE edges SET created_at=?,updated_at=? WHERE edge_id=?",
                (edge["created_at"], edge["updated_at"], edge["id"]),
            )


def _normalize_update(value: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(value, Mapping):
        raise AlignmentGraphError("graph update must be an object")
    unknown_top_level = set(value) - {"nodes", "edges", "gaps"}
    if unknown_top_level:
        raise AlignmentGraphError(
            "graph update has unknown fields: " + ", ".join(sorted(unknown_top_level))
        )
    raw_nodes = value.get("nodes", [])
    raw_edges = value.get("edges", [])
    if "gaps" in value:
        raw_nodes = [
            {
                "id": gap.get("id"), "type": "unknown", "statement": gap.get("summary"),
                "impact": gap.get("impact", 1), "human_only": gap.get("human_only", False),
                "status": "resolved" if gap.get("status") == "resolved" else "candidate",
                "confidence": "low", "source": "agent", "attributes": {},
            }
            for gap in value["gaps"]
        ]
    if isinstance(raw_nodes, (str, bytes)) or not isinstance(raw_nodes, Sequence):
        raise AlignmentGraphError("nodes must be a list")
    if isinstance(raw_edges, (str, bytes)) or not isinstance(raw_edges, Sequence):
        raise AlignmentGraphError("edges must be a list")
    nodes: list[dict[str, Any]] = []
    for raw in raw_nodes:
        if not isinstance(raw, Mapping):
            raise AlignmentGraphError("each node must be an object")
        unknown = set(raw) - {
            "id", "type", "statement", "status", "impact", "human_only",
            "confidence", "source", "oracle", "attributes",
        }
        if unknown:
            raise AlignmentGraphError(
                "node has unknown fields: " + ", ".join(sorted(unknown))
            )
        try:
            impact = int(raw.get("impact", 3))
        except (TypeError, ValueError) as exc:
            raise AlignmentGraphError("node impact must be an integer") from exc
        if not 1 <= impact <= 5:
            raise AlignmentGraphError("node impact must be between 1 and 5")
        if bool(raw.get("human_only", False)) and raw.get("source", "agent") == "agent" and raw.get("status", "candidate") in ACCEPTED_STATUSES:
            raise AlignmentGraphError(
                "agent evidence cannot resolve a requester-only alignment field"
            )
        attributes = raw.get("attributes", {})
        if not isinstance(attributes, Mapping):
            raise AlignmentGraphError("node attributes must be an object")
        nodes.append(
            {
                "id": _identifier(raw.get("id"), "node id"),
                "type": _enum(raw.get("type"), NODE_TYPES, "node type"),
                "statement": _text(raw.get("statement"), "node statement"),
                "status": _enum(raw.get("status", "candidate"), NODE_STATUSES, "node status"),
                "impact": impact,
                "human_only": bool(raw.get("human_only", False)),
                "confidence": _enum(raw.get("confidence", "low"), CONFIDENCES, "node confidence"),
                "source": _enum(raw.get("source", "agent"), SOURCES, "node source"),
                "oracle": None if raw.get("oracle") is None else _text(raw.get("oracle"), "node oracle"),
                "attributes": dict(attributes),
            }
        )
    edges: list[dict[str, Any]] = []
    for raw in raw_edges:
        if not isinstance(raw, Mapping):
            raise AlignmentGraphError("each edge must be an object")
        unknown = set(raw) - {
            "id", "source_id", "target_id", "relation", "status",
            "confidence", "provenance", "attributes",
        }
        if unknown:
            raise AlignmentGraphError(
                "edge has unknown fields: " + ", ".join(sorted(unknown))
            )
        attributes = raw.get("attributes", {})
        if not isinstance(attributes, Mapping):
            raise AlignmentGraphError("edge attributes must be an object")
        edges.append(
            {
                "id": _identifier(raw.get("id"), "edge id"),
                "source_id": _identifier(raw.get("source_id"), "edge source id"),
                "target_id": _identifier(raw.get("target_id"), "edge target id"),
                "relation": _enum(raw.get("relation"), EDGE_RELATIONS, "edge relation"),
                "status": _enum(raw.get("status", "active"), EDGE_STATUSES, "edge status"),
                "confidence": _enum(raw.get("confidence", "medium"), CONFIDENCES, "edge confidence"),
                "provenance": _text(raw.get("provenance", "unspecified"), "edge provenance"),
                "attributes": dict(attributes),
            }
        )
    return nodes, edges


def _alignment_readiness(
    nodes: Sequence[Mapping[str, Any]], edges: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    reasons: list[str] = []
    active_edges = [edge for edge in edges if edge["status"] == "active"]
    superseded_ids = {
        edge["target_id"] for edge in active_edges if edge["relation"] == "supersedes"
    }
    for node_type in REQUIRED_ALIGNMENT_TYPES:
        if not any(node["type"] == node_type and node["status"] in ACCEPTED_STATUSES for node in nodes):
            reasons.append(f"missing supported {node_type}")
    if any(
        node["human_only"] and node["status"] in {"candidate", "disputed"}
        for node in nodes
    ):
        reasons.append("a requester-only question remains unresolved")
    if any(node["status"] == "disputed" and node["impact"] >= 4 for node in nodes):
        reasons.append("a high-impact disagreement remains unresolved")
    researchable = [
        node
        for node in nodes
        if node["type"] in RESEARCHABLE_TYPES
        and not node["human_only"]
        and node["id"] not in superseded_ids
        and node["status"] not in {"resolved", "accepted", "rejected"}
    ]
    if not researchable:
        reasons.append("no executable research question is represented")
    for node in researchable:
        if not node.get("oracle"):
            reasons.append(f"research node {node['id']} has no closure oracle")
    researchable_ids = {node["id"] for node in researchable}
    for node in nodes:
        if node["type"] != "evidence" or node["status"] not in ACCEPTED_STATUSES:
            continue
        anchor = node["attributes"].get("anchor")
        if not isinstance(anchor, Mapping) or not anchor.get("kind") or not anchor.get("ref"):
            reasons.append(f"supported evidence node {node['id']} has no structured anchor")
            continue
        informs_current_slot = bool(
            _evidence_paths_to_slots(node["id"], {item["id"]: item for item in nodes}, active_edges, researchable_ids)
        )
        if (
            not informs_current_slot
            and node["attributes"].get("handoff_disposition") != "alignment_only"
        ):
            reasons.append(
                f"evidence node {node['id']} needs a current research edge or alignment_only disposition"
            )
    return {"ready": not reasons, "reasons": reasons}


def _accepted_statements(
    nodes: Mapping[str, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    node_type: str,
) -> list[str]:
    values = nodes.values() if isinstance(nodes, Mapping) else nodes
    return sorted(
        str(node["statement"])
        for node in values
        if node["type"] == node_type and node["status"] in ACCEPTED_STATUSES
    )


def _evidence_paths_to_slots(
    source_id: str,
    nodes: Mapping[str, Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    slot_ids: set[str],
) -> list[tuple[str, list[dict[str, Any]]]]:
    """Return relation-preserving paths from evidence through the active graph."""

    outgoing: dict[str, list[tuple[Mapping[str, Any], str, str]]] = {}
    for edge in edges:
        if edge["status"] != "active":
            continue
        if edge["relation"] == "supersedes":
            outgoing.setdefault(edge["target_id"], []).append((edge, edge["source_id"], "reverse"))
        elif edge["relation"] == "refines":
            outgoing.setdefault(edge["source_id"], []).append((edge, edge["target_id"], "forward"))
            outgoing.setdefault(edge["target_id"], []).append((edge, edge["source_id"], "reverse"))
        else:
            outgoing.setdefault(edge["source_id"], []).append((edge, edge["target_id"], "forward"))
    results: list[tuple[str, list[dict[str, Any]]]] = []
    queue: list[tuple[str, list[dict[str, Any]], set[str]]] = [(source_id, [], {source_id})]
    while queue:
        current, path, visited = queue.pop(0)
        for edge, target, direction in outgoing.get(current, []):
            if target in visited or target not in nodes:
                continue
            next_path = path + [
                {
                    "edge_id": edge["id"],
                    "relation": edge["relation"],
                    "source_id": edge["source_id"],
                    "target_id": target,
                    "direction": direction,
                }
            ]
            if target in slot_ids:
                results.append((target, next_path))
                continue
            queue.append((target, next_path, visited | {target}))
    return results


def _load_update(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AlignmentGraphError(f"cannot read graph update: {exc}") from exc
    if isinstance(value, list):
        value = {"gaps": value}
    if not isinstance(value, Mapping):
        raise AlignmentGraphError("graph update file must contain an object")
    return value


def init(workspace: Path, run_id: str) -> dict[str, Any]:
    return AlignmentGraphStore(database_path(workspace, run_id)).initialize(run_id)


def plan(workspace: Path, run_id: str, update_file: Path) -> dict[str, Any]:
    return AlignmentGraphStore(database_path(workspace, run_id)).plan(_load_update(update_file))


def record(
    workspace: Path, run_id: str, node_id: str, outcome: str, fingerprint: str
) -> dict[str, Any]:
    return AlignmentGraphStore(database_path(workspace, run_id)).record(
        node_id, outcome, fingerprint
    )


def confirm(
    workspace: Path,
    run_id: str,
    confirmation: str,
    expected_digest: str | None = None,
) -> dict[str, Any]:
    return AlignmentGraphStore(database_path(workspace, run_id)).confirm(
        confirmation, expected_digest
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("init")
    initialize.add_argument("--run-id", required=True)
    planning = commands.add_parser("plan")
    planning.add_argument("--run-id", required=True)
    planning.add_argument("--graph-file", "--gaps-file", dest="graph_file", type=Path, required=True)
    recording = commands.add_parser("record")
    recording.add_argument("--run-id", required=True)
    recording.add_argument("--node-id", "--gap-id", dest="node_id", required=True)
    recording.add_argument("--outcome", choices=tuple(sorted(OUTCOMES)), required=True)
    recording.add_argument("--fingerprint", required=True)
    confirmation = commands.add_parser("confirm")
    confirmation.add_argument("--run-id", required=True)
    confirmation.add_argument("--confirmation", required=True)
    confirmation.add_argument("--expected-digest", required=True)
    compilation = commands.add_parser("compile")
    compilation.add_argument("--run-id", required=True)
    compilation.add_argument(
        "--output",
        type=Path,
        help="handoff JSON path (default: the alignment run directory/handoff.json)",
    )
    schema = commands.add_parser(
        "schema", help="show the graph-update contract and a strict UTF-8 example"
    )
    schema.add_argument("--output", type=Path, help="write the schema without a UTF-8 BOM")
    status = commands.add_parser("status")
    status.add_argument("--run-id", required=True)
    rebuild = commands.add_parser("rebuild")
    rebuild.add_argument("--run-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        workspace = args.workspace.resolve()
        if args.command == "schema":
            result = _schema_document()
            if args.output:
                output = args.output if args.output.is_absolute() else workspace / args.output
                output = output.resolve()
                try:
                    output.relative_to(workspace)
                except ValueError as exc:
                    raise AlignmentGraphError("schema output must remain in the workspace") from exc
                _atomic_write_json(output, result)
                result = {**result, "persisted_path": str(output)}
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        store = AlignmentGraphStore(database_path(workspace, args.run_id))
        if args.command == "init":
            result = store.initialize(args.run_id)
        elif args.command == "plan":
            graph_file = args.graph_file if args.graph_file.is_absolute() else workspace / args.graph_file
            result = store.plan(_load_update(graph_file))
        elif args.command == "record":
            result = store.record(args.node_id, args.outcome, args.fingerprint)
        elif args.command == "confirm":
            result = store.confirm(args.confirmation, args.expected_digest)
        elif args.command == "compile":
            result = store.compile_handoff()
            output = args.output or (store.database.parent / "handoff.json")
            output = output if output.is_absolute() else workspace / output
            output = output.resolve()
            try:
                output.relative_to(workspace)
            except ValueError as exc:
                raise AlignmentGraphError("handoff output must remain in the workspace") from exc
            _atomic_write_json(output, result)
            result = {**result, "persisted_path": str(output)}
        elif args.command == "rebuild":
            result = store.rebuild_materialized()
        else:
            result = store.status()
    except (AlignmentGraphError, OSError, sqlite3.Error) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _schema_document() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "encoding": "UTF-8 without BOM",
        "node": {
            "required": ["id", "type", "statement"],
            "allowed_fields": [
                "id", "type", "statement", "status", "impact", "human_only",
                "confidence", "source", "oracle", "attributes",
            ],
            "types": sorted(NODE_TYPES),
            "statuses": sorted(NODE_STATUSES),
            "sources": sorted(SOURCES),
        },
        "edge": {
            "required": ["id", "source_id", "target_id", "relation"],
            "allowed_fields": [
                "id", "source_id", "target_id", "relation", "status",
                "confidence", "provenance", "attributes",
            ],
            "relations": sorted(EDGE_RELATIONS),
            "statuses": sorted(EDGE_STATUSES),
        },
        "example_update": {
            "nodes": [
                {
                    "id": "evidence-1", "type": "evidence",
                    "statement": "A bounded reconnaissance finding.",
                    "status": "supported", "source": "reconnaissance",
                    "attributes": {"anchor": {"kind": "source", "ref": "https://example.test"}},
                },
                {
                    "id": "question-1", "type": "research_question",
                    "statement": "Which implementation decision does the evidence support?",
                    "oracle": "The alternatives are tested against anchored evidence.",
                },
            ],
            "edges": [
                {
                    "id": "edge-1", "source_id": "evidence-1",
                    "target_id": "question-1", "relation": "informs",
                }
            ],
        },
    }


if __name__ == "__main__":
    raise SystemExit(main())
