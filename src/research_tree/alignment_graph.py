"""SQLite-backed temporal heterogeneous multigraph for pre-research alignment."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

log = logging.getLogger(__name__)

SCHEMA = 3
MAX_TURNS = 6
# Per-node/per-axis stall threshold (#496): a requester-only point that stayed
# quiet this many turns with no active divergence axis is *locally stalled*.
# This is no longer a global escape hatch — see MAX_TURNS for the (separately
# governed) total-turn bound and plan() for the stall decision.
MAX_STAGNANT_TURNS = 2
MAX_ASKS_PER_NODE = 2
AXIS_STATUSES = frozenset({"open", "converged"})
DIALOGUE_MODES = frozenset({"handoff_ready", "divergent", "converging", "stalled"})
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
        "claim",
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
    {
        "candidate",
        "supported",
        "disputed",
        "resolved",
        "accepted",
        "deferred",
        "rejected",
        "isolated",
        "corroborated",
        "superseded",
        "contested",
        "unasserted",
    }
)
EDGE_STATUSES = frozenset({"active", "superseded", "rejected"})
CONFIDENCES = frozenset({"low", "medium", "high"})
TRACK_PRIORITIES = frozenset({"P0", "P1", "P2"})
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
ACCEPTED_STATUSES = frozenset({"supported", "corroborated", "resolved", "accepted"})
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


def _axis_id(node_id: str, description: str) -> str:
    """Deterministic axis id so re-declaring a direction touches, not forks."""

    return "axis-" + hashlib.sha256(_json([node_id, description]).encode("utf-8")).hexdigest()[:12]


def _normalize_axes(value: Any) -> list[dict[str, Any]]:
    """Validate caller-declared divergence axes (#496): strings or {id?, description}."""

    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise AlignmentGraphError("new axes must be a list")
    axes: list[dict[str, Any]] = []
    for raw in value:
        if isinstance(raw, Mapping):
            unknown = set(raw) - {"id", "description"}
            if unknown:
                raise AlignmentGraphError("divergence axis has unknown fields: " + ", ".join(sorted(unknown)))
            axis_id = None if raw.get("id") is None else _identifier(raw["id"], "axis id")
            description = _text(raw.get("description"), "axis description")
        elif isinstance(raw, str):
            axis_id = None
            description = _text(raw, "axis description")
        else:
            raise AlignmentGraphError("each divergence axis must be a string or an object")
        axes.append({"id": axis_id, "description": description})
    return axes


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _normalize_node_status(value: Any) -> str:
    """Check graph node statuses against the unified graph vocabulary.

    Values outside :data:`NODE_STATUSES` fall through to the SpeechAct
    vocabulary check, which defaults unknown values to ``candidate`` with a
    deprecation warning so stored graph state is surfaced without crashing.
    """

    text = str(value)
    if text in NODE_STATUSES:
        return text
    try:
        from .speech_acts import normalize_status as _normalize
    except ImportError:  # packaged single-file layout: speech_acts ships beside this script (#470)
        from speech_acts import normalize_status as _normalize

    return _normalize(value)


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


def _run_dir(workspace: Path, run_id: str, project_id: str | None = None) -> Path:
    root = workspace.resolve()
    run_id = _identifier(run_id, "run id")
    resolved_project = _identifier(project_id or f"alignment-{run_id}", "project id")
    target = (root / ".research-tree" / "projects" / resolved_project / "runs" / run_id / "alignment").resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise AlignmentGraphError("alignment database must remain in the workspace") from exc
    return target


def database_path(workspace: Path, run_id: str, project_id: str | None = None) -> Path:
    """Resolve one alignment database under the sole project/run authority."""
    return _run_dir(workspace, run_id, project_id) / "alignment.db"


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
            handoff_invalidated = self._invalidate_handoff_if_confirmed(connection)
            self._commit_event(
                connection,
                "graph_merged",
                {
                    "node_ids": [node["id"] for node in nodes],
                    "edge_ids": [edge["id"] for edge in edges],
                    "handoff_invalidated": handoff_invalidated,
                },
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
                connection.execute("UPDATE controller SET pending_node_id=? WHERE singleton=1", (node["id"],))
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
        self, node_id: str, outcome: str, fingerprint: str, new_axes: Sequence[Any] | None = None
    ) -> dict[str, Any]:
        node_id = _identifier(node_id, "node id")
        outcome = _enum(outcome, OUTCOMES, "outcome")
        axes = _normalize_axes(new_axes)
        with self._connect() as connection:
            self._require_schema(connection)
            node = connection.execute("SELECT * FROM nodes WHERE node_id=?", (node_id,)).fetchone()
            if node is None:
                raise AlignmentGraphError(f"unknown graph node: {node_id}")
            controller = connection.execute("SELECT * FROM controller WHERE singleton=1").fetchone()
            hashed = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
            changed = hashed != controller["last_fingerprint"]
            turn = int(controller["turn"]) + 1
            stagnant = int(node["stagnant_turns"])
            status = node["status"]
            quiet = not changed
            if outcome == "answered":
                try:
                    from .speech_acts import AuthorityTransitionError, SpeechAct
                    from .speech_acts import transition as _speech_transition
                except ImportError:  # packaged single-file layout (#470)
                    from speech_acts import AuthorityTransitionError, SpeechAct
                    from speech_acts import transition as _speech_transition

                normalized = _normalize_node_status(status)
                speech_act = SpeechAct(
                    kind="answered",
                    speaker_role="agent",
                    speaker_id="alignment-graph",
                    addressee="human",
                    authority_scope="research_owner",
                    timestamp=_now(),
                )
                try:
                    status = _speech_transition(normalized, speech_act)
                except AuthorityTransitionError as error:
                    log.warning(
                        "alignment_graph_record_speech_transition_rejected",
                        extra={
                            "node_id": node_id,
                            "from_status": normalized,
                            "to_status": "candidate",
                            "speech_act_kind": speech_act.kind,
                            "error": str(error),
                        },
                    )
                    raise
                stagnant = 0
            elif outcome == "changed":
                stagnant = 0
            elif outcome == "reopened":
                status = "candidate"
                stagnant = 0
            elif quiet:
                stagnant += 1
            self._update_node_axes(connection, node_id, outcome, quiet, bool(axes), turn)
            opened_axes: list[str] = []
            if axes:
                # A user-implied new direction is the opposite of a stall: the
                # node's local convergence resets and each axis opens fresh.
                stagnant = 0
                for axis in axes:
                    opened_axes.append(self._open_axis(connection, node_id, axis, turn))
            connection.execute(
                "UPDATE nodes SET status=?, stagnant_turns=?, updated_at=? WHERE node_id=?",
                (status, stagnant, _now(), node_id),
            )
            global_stagnant = connection.execute("SELECT COALESCE(MAX(stagnant_turns), 0) FROM nodes").fetchone()[0]
            connection.execute(
                """
                UPDATE controller
                SET turn=?, stagnant_turns=?, last_fingerprint=?, pending_node_id=NULL
                WHERE singleton=1
                """,
                (turn, global_stagnant, hashed),
            )
            handoff_invalidated = self._invalidate_handoff_if_confirmed(connection)
            state = self._commit_event(
                connection,
                "response_recorded",
                {
                    "node_id": node_id,
                    "outcome": outcome,
                    "state_changed": changed,
                    "opened_axes": opened_axes,
                    "handoff_invalidated": handoff_invalidated,
                },
            )
        dialogue_mode = state["divergence"]["mode"]
        return {
            "turn": state["controller"]["turn"],
            "stagnant_turns": stagnant,
            "state_changed": changed,
            "opened_axes": opened_axes,
            "dialogue_mode": dialogue_mode,
            "next_action": "reconnaissance" if dialogue_mode == "stalled" else "plan",
        }

    @staticmethod
    def _open_axis(connection: sqlite3.Connection, node_id: str, axis: Mapping[str, Any], turn: int) -> str:
        axis_id = axis["id"] or _axis_id(node_id, axis["description"])
        existing = connection.execute("SELECT * FROM divergence_axes WHERE axis_id=?", (axis_id,)).fetchone()
        if existing is not None:
            if existing["node_id"] != node_id:
                raise AlignmentGraphError(
                    f"divergence axis {axis_id} belongs to node {existing['node_id']}, not {node_id}"
                )
            connection.execute(
                "UPDATE divergence_axes SET status='open', stagnant_turns=0, last_turn=?, updated_at=? WHERE axis_id=?",
                (turn, _now(), axis_id),
            )
            return axis_id
        now = _now()
        connection.execute(
            """
            INSERT INTO divergence_axes(
                axis_id, node_id, description, status, opened_turn, last_turn, stagnant_turns, created_at, updated_at
            ) VALUES(?, ?, ?, 'open', ?, ?, 0, ?, ?)
            """,
            (axis_id, node_id, axis["description"], turn, turn, now, now),
        )
        return axis_id

    @staticmethod
    def _update_node_axes(
        connection: sqlite3.Connection, node_id: str, outcome: str, quiet: bool, axes_declared: bool, turn: int
    ) -> None:
        """Advance the open axes hanging on the recorded node (#496 lifecycle)."""

        now = _now()
        for row in connection.execute(
            "SELECT * FROM divergence_axes WHERE node_id=? ORDER BY axis_id", (node_id,)
        ).fetchall():
            axis_id = row["axis_id"]
            if outcome == "answered" and row["status"] == "open":
                connection.execute(
                    "UPDATE divergence_axes SET status='converged', stagnant_turns=0, updated_at=? WHERE axis_id=?",
                    (now, axis_id),
                )
            elif outcome == "reopened" and row["status"] == "converged":
                connection.execute(
                    "UPDATE divergence_axes SET status='open', stagnant_turns=0, updated_at=? WHERE axis_id=?",
                    (now, axis_id),
                )
            elif quiet and not axes_declared and row["status"] == "open":
                connection.execute(
                    "UPDATE divergence_axes SET stagnant_turns=stagnant_turns+1, last_turn=?, updated_at=? WHERE axis_id=?",
                    (turn, now, axis_id),
                )
            elif row["status"] == "open":
                connection.execute(
                    "UPDATE divergence_axes SET stagnant_turns=0, last_turn=?, updated_at=? WHERE axis_id=?",
                    (turn, now, axis_id),
                )

    def confirm(self, confirmation: str, expected_digest: str | None = None) -> dict[str, Any]:
        text = " ".join(confirmation.split())
        if not text:
            raise AlignmentGraphError("handoff confirmation must be nonempty")
        if text.casefold() in {"ok", "okay", "yes", "continue", "go ahead", "可以", "继续"}:
            raise AlignmentGraphError("generic acknowledgement is not handoff confirmation")
        with self._connect() as connection:
            self._require_schema(connection)
            state = self._materialize(connection)
            readiness = _alignment_readiness(state["graph"]["nodes"], state["graph"]["edges"])
            if not readiness["ready"]:
                raise AlignmentGraphError("alignment graph is not ready: " + "; ".join(readiness["reasons"]))
            last_decision = state["controller"].get("last_decision") or {}
            if last_decision.get("action") != "await_human_confirmation":
                raise AlignmentGraphError("cannot confirm before the handoff draft is shown")
            if expected_digest is None:
                raise AlignmentGraphError("handoff confirmation must include the alignment digest shown in the draft")
            if expected_digest != state["graph_digest"]:
                raise AlignmentGraphError("alignment graph changed after the displayed handoff draft")
            connection.execute(
                "UPDATE nodes SET status='accepted', updated_at=? WHERE node_type='strategy' AND status IN ('supported','resolved')",
                (_now(),),
            )
            confirmed_state = self._materialize(connection)
            handoff = {
                "confirmed_at": _now(),
                "confirmation_digest": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "alignment_digest": confirmed_state["graph_digest"],
                "stale": False,
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
        handoff = state["controller"].get("handoff")
        if not isinstance(handoff, Mapping) or handoff.get("stale"):
            raise AlignmentGraphError("stale_handoff_confirmation")
        if state["controller"]["status"] != "autonomous":
            raise AlignmentGraphError("alignment must be explicitly confirmed before compilation")
        if handoff.get("alignment_digest") != state["graph_digest"]:
            raise AlignmentGraphError("stale_handoff_confirmation")
        nodes = {node["id"]: node for node in state["graph"]["nodes"]}
        active_edges = [edge for edge in state["graph"]["edges"] if edge["status"] == "active"]
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
        strategy_node = next(
            node for node in nodes.values() if node["type"] == "strategy" and node["status"] in ACCEPTED_STATUSES
        )
        strategy_tracks = _strategy_tracks(strategy_node)
        tracks_by_id = {track["id"]: track for track in strategy_tracks}
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
            track_id = _research_track_id(node, tracks_by_id)
            if track_id is None:
                raise AlignmentGraphError(f"research node {node['id']} is not assigned to a strategy track")
            track = tracks_by_id[track_id]
            slots[node["id"]] = {
                "status": "open",
                "track_id": track_id,
                "track_closure_oracle": track["closure_oracle"],
                "evidence_boundary": track["evidence_boundary"],
                "priority": track["priority"],
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
                raise AlignmentGraphError(f"supported evidence node {source['id']} has no structured anchor")
            for target_id, path in _evidence_paths_to_slots(source["id"], nodes, active_edges, set(slots)):
                evidence_paths.setdefault((source["id"], target_id), []).append(path)
        for (evidence_id, target_id), paths in sorted(evidence_paths.items()):
            source = nodes[evidence_id]
            anchor = source["attributes"]["anchor"]
            compiled_evidence_ids.add(evidence_id)
            finding_id = "alignment-" + hashlib.sha256(f"{evidence_id}:{target_id}".encode("utf-8")).hexdigest()[:20]
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
                    "validation_result": None,
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
        strategy = strategy_node["statement"]
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
            "strategy_tracks": strategy_tracks,
        }
        return {
            "schema": 1,
            "kind": "alignment-handoff",
            "run_id": state["controller"]["run_id"],
            "alignment_revision": state["controller"]["revision"],
            "alignment_digest": handoff["alignment_digest"],
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
            "alignment_graph": state["graph"],
        }

    def status(self) -> dict[str, Any]:
        with self._connect() as connection:
            self._require_schema(connection)
            return self._materialize(connection)

    def rebuild_materialized(self) -> dict[str, Any]:
        with self._connect() as connection:
            self._require_schema(connection)
            event = connection.execute("SELECT state_json FROM events ORDER BY sequence DESC LIMIT 1").fetchone()
            if event is None:
                raise AlignmentGraphError("alignment event log is empty")
            state = json.loads(event["state_json"])
            connection.execute("DELETE FROM divergence_axes")
            connection.execute("DELETE FROM edges")
            connection.execute("DELETE FROM nodes")
            self._restore_state(connection, state)
        return self.status()

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO metadata(key, value) VALUES('schema', '3');
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
                stagnant_turns INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE divergence_axes(
                axis_id TEXT PRIMARY KEY,
                node_id TEXT NOT NULL REFERENCES nodes(node_id),
                description TEXT NOT NULL,
                status TEXT NOT NULL,
                opened_turn INTEGER NOT NULL,
                last_turn INTEGER NOT NULL,
                stagnant_turns INTEGER NOT NULL DEFAULT 0,
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

    @staticmethod
    def _upsert_node(connection: sqlite3.Connection, node: Mapping[str, Any]) -> None:
        now = _now()
        prior = connection.execute(
            "SELECT ask_count, last_asked_turn, stagnant_turns, created_at FROM nodes WHERE node_id=?", (node["id"],)
        ).fetchone()
        connection.execute(
            """
            INSERT INTO nodes(
                node_id,node_type,statement,status,impact,human_only,confidence,
                source,oracle,attributes_json,ask_count,last_asked_turn,stagnant_turns,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(node_id) DO UPDATE SET
                node_type=excluded.node_type, statement=excluded.statement,
                status=excluded.status, impact=excluded.impact,
                human_only=excluded.human_only, confidence=excluded.confidence,
                source=excluded.source, oracle=excluded.oracle,
                attributes_json=excluded.attributes_json, updated_at=excluded.updated_at
            """,
            (
                node["id"],
                node["type"],
                node["statement"],
                node["status"],
                node["impact"],
                int(node["human_only"]),
                node["confidence"],
                node["source"],
                node.get("oracle"),
                _json(node["attributes"]),
                int(prior["ask_count"]) if prior else 0,
                prior["last_asked_turn"] if prior else None,
                int(prior["stagnant_turns"]) if prior else 0,
                prior["created_at"] if prior else now,
                now,
            ),
        )

    @staticmethod
    def _upsert_edge(connection: sqlite3.Connection, edge: Mapping[str, Any]) -> None:
        now = _now()
        prior = connection.execute("SELECT created_at FROM edges WHERE edge_id=?", (edge["id"],)).fetchone()
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
                    edge["id"],
                    edge["source_id"],
                    edge["target_id"],
                    edge["relation"],
                    edge["status"],
                    edge["confidence"],
                    edge["provenance"],
                    _json(edge["attributes"]),
                    prior["created_at"] if prior else now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise AlignmentGraphError(f"edge {edge['id']} references an unknown node") from exc

    @staticmethod
    def _invalidate_handoff_if_confirmed(connection: sqlite3.Connection) -> bool:
        controller = connection.execute("SELECT status, handoff_json FROM controller WHERE singleton=1").fetchone()
        if controller is None or controller["status"] != "autonomous":
            return False
        handoff = json.loads(controller["handoff_json"]) if controller["handoff_json"] else {}
        handoff.update(
            {
                "stale": True,
                "stale_at": _now(),
                "stale_reason": "alignment_graph_changed",
            }
        )
        connection.execute(
            """
            UPDATE controller
            SET status='alignment', phase='alignment', handoff_json=?
            WHERE singleton=1
            """,
            (_json(handoff),),
        )
        return True

    def _commit_event(
        self, connection: sqlite3.Connection, event_type: str, details: Mapping[str, Any]
    ) -> dict[str, Any]:
        connection.execute("UPDATE controller SET revision=revision+1, updated_at=? WHERE singleton=1", (_now(),))
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
        controller = connection.execute("SELECT * FROM controller WHERE singleton=1").fetchone()
        if controller is None:
            raise AlignmentGraphError("alignment controller state is missing")
        nodes = [
            {
                "id": row["node_id"],
                "type": row["node_type"],
                "statement": row["statement"],
                "status": _normalize_node_status(row["status"]),
                "impact": row["impact"],
                "human_only": bool(row["human_only"]),
                "confidence": row["confidence"],
                "source": row["source"],
                "oracle": row["oracle"],
                "attributes": json.loads(row["attributes_json"]),
                "ask_count": row["ask_count"],
                "last_asked_turn": row["last_asked_turn"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in connection.execute("SELECT * FROM nodes ORDER BY node_id")
        ]
        edges = [
            {
                "id": row["edge_id"],
                "source_id": row["source_id"],
                "target_id": row["target_id"],
                "relation": row["relation"],
                "status": row["status"],
                "confidence": row["confidence"],
                "provenance": row["provenance"],
                "attributes": json.loads(row["attributes_json"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in connection.execute("SELECT * FROM edges ORDER BY edge_id")
        ]
        graph = {"nodes": nodes, "edges": edges}
        divergence_axes = [
            {
                "axis_id": row["axis_id"],
                "node_id": row["node_id"],
                "description": row["description"],
                "status": row["status"],
                "opened_turn": row["opened_turn"],
                "last_turn": row["last_turn"],
                "stagnant_turns": row["stagnant_turns"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in connection.execute("SELECT * FROM divergence_axes ORDER BY node_id, axis_id")
        ]
        node_stagnation = {
            row["node_id"]: int(row["stagnant_turns"])
            for row in connection.execute("SELECT node_id, stagnant_turns FROM nodes")
        }
        state = {
            "schema": SCHEMA,
            "controller": {
                "run_id": controller["run_id"],
                "phase": controller["phase"],
                "status": controller["status"],
                "turn": controller["turn"],
                "stagnant_turns": controller["stagnant_turns"],
                "plan_count": controller["plan_count"],
                "revision": controller["revision"],
                "last_fingerprint": controller["last_fingerprint"],
                "pending_node_id": controller["pending_node_id"],
                "last_decision": json.loads(controller["last_decision_json"])
                if controller["last_decision_json"]
                else None,
                "handoff": json.loads(controller["handoff_json"]) if controller["handoff_json"] else None,
                "created_at": controller["created_at"],
                "updated_at": controller["updated_at"],
            },
            "graph": graph,
            # Divergence-aware dialogue state (#496). Kept OUTSIDE `graph` so
            # graph_digest keeps meaning graph content only.
            "divergence": {
                "axes": divergence_axes,
                "node_stagnation": node_stagnation,
            },
            "graph_digest": _digest(graph),
        }
        state["divergence"]["mode"] = _dialogue_mode(state)
        return state

    def _restore_state(self, connection: sqlite3.Connection, state: Mapping[str, Any]) -> None:
        controller = state["controller"]
        connection.execute(
            """
            UPDATE controller SET run_id=?,phase=?,status=?,turn=?,stagnant_turns=?,
                plan_count=?,revision=?,last_fingerprint=?,pending_node_id=?,
                last_decision_json=?,handoff_json=?,created_at=?,updated_at=? WHERE singleton=1
            """,
            (
                controller["run_id"],
                controller["phase"],
                controller["status"],
                controller["turn"],
                controller["stagnant_turns"],
                controller["plan_count"],
                controller["revision"],
                controller["last_fingerprint"],
                controller["pending_node_id"],
                _json(controller["last_decision"]) if controller["last_decision"] else None,
                _json(controller["handoff"]) if controller["handoff"] else None,
                controller["created_at"],
                controller["updated_at"],
            ),
        )
        for node in state["graph"]["nodes"]:
            self._upsert_node(connection, node)
            connection.execute(
                "UPDATE nodes SET ask_count=?,last_asked_turn=?,stagnant_turns=?,created_at=?,updated_at=? WHERE node_id=?",
                (
                    node["ask_count"],
                    node["last_asked_turn"],
                    int(state["divergence"]["node_stagnation"].get(node["id"], 0)),
                    node["created_at"],
                    node["updated_at"],
                    node["id"],
                ),
            )
        for edge in state["graph"]["edges"]:
            self._upsert_edge(connection, edge)
            connection.execute(
                "UPDATE edges SET created_at=?,updated_at=? WHERE edge_id=?",
                (edge["created_at"], edge["updated_at"], edge["id"]),
            )
        for axis in state["divergence"]["axes"]:
            connection.execute(
                """
                INSERT INTO divergence_axes(
                    axis_id,node_id,description,status,opened_turn,last_turn,stagnant_turns,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(axis_id) DO UPDATE SET
                    node_id=excluded.node_id,description=excluded.description,status=excluded.status,
                    opened_turn=excluded.opened_turn,last_turn=excluded.last_turn,
                    stagnant_turns=excluded.stagnant_turns,updated_at=excluded.updated_at
                """,
                (
                    axis["axis_id"],
                    axis["node_id"],
                    axis["description"],
                    axis["status"],
                    axis["opened_turn"],
                    axis["last_turn"],
                    axis["stagnant_turns"],
                    axis["created_at"],
                    axis["updated_at"],
                ),
            )


def _normalize_update(value: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(value, Mapping):
        raise AlignmentGraphError("graph update must be an object")
    unknown_top_level = set(value) - {"nodes", "edges", "gaps"}
    if unknown_top_level:
        raise AlignmentGraphError("graph update has unknown fields: " + ", ".join(sorted(unknown_top_level)))
    raw_nodes = value.get("nodes", [])
    raw_edges = value.get("edges", [])
    if "gaps" in value:
        raw_nodes = [
            {
                "id": gap.get("id"),
                "type": "unknown",
                "statement": gap.get("summary"),
                "impact": gap.get("impact", 1),
                "human_only": gap.get("human_only", False),
                "status": "resolved" if gap.get("status") == "resolved" else "candidate",
                "confidence": "low",
                "source": "agent",
                "attributes": {},
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
            "id",
            "type",
            "statement",
            "status",
            "impact",
            "human_only",
            "confidence",
            "source",
            "oracle",
            "attributes",
        }
        if unknown:
            raise AlignmentGraphError("node has unknown fields: " + ", ".join(sorted(unknown)))
        try:
            impact = int(raw.get("impact", 3))
        except (TypeError, ValueError) as exc:
            raise AlignmentGraphError("node impact must be an integer") from exc
        if not 1 <= impact <= 5:
            raise AlignmentGraphError("node impact must be between 1 and 5")
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
            "id",
            "source_id",
            "target_id",
            "relation",
            "status",
            "confidence",
            "provenance",
            "attributes",
        }
        if unknown:
            raise AlignmentGraphError("edge has unknown fields: " + ", ".join(sorted(unknown)))
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


def _dialogue_mode(state: Mapping[str, Any]) -> str:
    """Classify the dialogue from per-node/per-axis state (#496).

    ``handoff_ready`` — the graph supports a strategy handoff; ``divergent`` —
    at least one active divergence axis (stay in dialogue with an exploratory
    move); ``converging`` — some requester-only point is still below the stall
    threshold; ``stalled`` — nothing new and no active axis anywhere
    (agent-side reconnaissance is acceptable).
    """

    if _alignment_readiness(state["graph"]["nodes"], state["graph"]["edges"])["ready"]:
        return "handoff_ready"
    for axis in state["divergence"]["axes"]:
        if axis["status"] == "open" and axis["stagnant_turns"] < MAX_STAGNANT_TURNS:
            return "divergent"
    stagnation = state["divergence"]["node_stagnation"]
    for node in state["graph"]["nodes"]:
        if (
            node["human_only"]
            and node["status"] in {"candidate", "disputed"}
            and stagnation.get(node["id"], 0) < MAX_STAGNANT_TURNS
        ):
            return "converging"
    return "stalled"


def _alignment_readiness(nodes: Sequence[Mapping[str, Any]], edges: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    reasons: list[str] = []
    active_edges = [edge for edge in edges if edge["status"] == "active"]
    superseded_ids = {edge["target_id"] for edge in active_edges if edge["relation"] == "supersedes"}
    for node_type in REQUIRED_ALIGNMENT_TYPES:
        if not any(node["type"] == node_type and node["status"] in ACCEPTED_STATUSES for node in nodes):
            reasons.append(f"missing supported {node_type}")
    if any(node["human_only"] and node["status"] in {"candidate", "disputed"} for node in nodes):
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
    strategy_nodes = [node for node in nodes if node["type"] == "strategy" and node["status"] in ACCEPTED_STATUSES]
    if strategy_nodes:
        try:
            tracks = _strategy_tracks(strategy_nodes[0])
            tracks_by_id = {track["id"]: track for track in tracks}
            coverage = {track_id: 0 for track_id in tracks_by_id}
            for node in researchable:
                track_id = _research_track_id(node, tracks_by_id)
                if track_id is None:
                    reasons.append(f"research node {node['id']} is not assigned to a strategy track")
                    continue
                coverage[track_id] += 1
            for track in tracks:
                if track["active"] and coverage[track["id"]] == 0:
                    reasons.append(f"strategy track {track['id']} has no executable research question")
        except AlignmentGraphError as error:
            reasons.append(str(error))
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
        if not informs_current_slot and node["attributes"].get("handoff_disposition") != "alignment_only":
            reasons.append(f"evidence node {node['id']} needs a current research edge or alignment_only disposition")
    return {"ready": not reasons, "reasons": reasons}


def _strategy_tracks(strategy: Mapping[str, Any]) -> list[dict[str, Any]]:
    attributes = strategy.get("attributes")
    if not isinstance(attributes, Mapping):
        raise AlignmentGraphError("strategy attributes must be an object")
    raw_tracks = attributes.get("tracks")
    if raw_tracks is None:
        return [
            {
                "id": f"track-{strategy['id']}",
                "priority": "P0" if strategy["impact"] >= 5 else "P1" if strategy["impact"] >= 3 else "P2",
                "closure_oracle": "Every slot mapped to this strategy track meets its closure oracle.",
                "evidence_boundary": "confirmed alignment graph and bounded repository evidence",
                "active": True,
            }
        ]
    if isinstance(raw_tracks, (str, bytes)) or not isinstance(raw_tracks, Sequence) or not raw_tracks:
        raise AlignmentGraphError("strategy tracks must be a non-empty list")
    tracks: list[dict[str, Any]] = []
    for raw_track in raw_tracks:
        if not isinstance(raw_track, Mapping):
            raise AlignmentGraphError("strategy track must be an object")
        unknown = set(raw_track) - {"id", "priority", "closure_oracle", "evidence_boundary", "active"}
        if unknown:
            raise AlignmentGraphError("strategy track has unknown fields: " + ", ".join(sorted(unknown)))
        tracks.append(
            {
                "id": _identifier(raw_track.get("id"), "strategy track id"),
                "priority": _enum(raw_track.get("priority"), TRACK_PRIORITIES, "strategy track priority"),
                "closure_oracle": _text(raw_track.get("closure_oracle"), "strategy track closure_oracle"),
                "evidence_boundary": _text(raw_track.get("evidence_boundary"), "strategy track evidence_boundary"),
                "active": bool(raw_track.get("active", True)),
            }
        )
    if len({track["id"] for track in tracks}) != len(tracks):
        raise AlignmentGraphError("strategy track ids must be unique")
    return sorted(tracks, key=lambda track: track["id"])


def _research_track_id(node: Mapping[str, Any], tracks_by_id: Mapping[str, Mapping[str, Any]]) -> str | None:
    attributes = node.get("attributes")
    if not isinstance(attributes, Mapping):
        return None
    track_id = attributes.get("track_id")
    if track_id is None and len(tracks_by_id) == 1:
        return next(iter(tracks_by_id))
    if track_id is None:
        return None
    try:
        track_id = _identifier(track_id, "research track id")
    except AlignmentGraphError:
        return None
    return track_id if track_id in tracks_by_id else None


def _accepted_statements(
    nodes: Mapping[str, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    node_type: str,
) -> list[str]:
    values = nodes.values() if isinstance(nodes, Mapping) else nodes
    return sorted(
        str(node["statement"]) for node in values if node["type"] == node_type and node["status"] in ACCEPTED_STATUSES
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


def init(workspace: Path, run_id: str, *, project_id: str | None = None) -> dict[str, Any]:
    return AlignmentGraphStore(database_path(workspace, run_id, project_id)).initialize(run_id)


def plan(workspace: Path, run_id: str, update_file: Path, *, project_id: str | None = None) -> dict[str, Any]:
    return AlignmentGraphStore(database_path(workspace, run_id, project_id)).plan(_load_update(update_file))


def record(
    workspace: Path,
    run_id: str,
    node_id: str,
    outcome: str,
    fingerprint: str,
    *,
    project_id: str | None = None,
    new_axes: Sequence[Any] | None = None,
) -> dict[str, Any]:
    return AlignmentGraphStore(database_path(workspace, run_id, project_id)).record(
        node_id, outcome, fingerprint, new_axes
    )


def confirm(
    workspace: Path,
    run_id: str,
    confirmation: str,
    expected_digest: str | None = None,
    *,
    project_id: str | None = None,
) -> dict[str, Any]:
    return AlignmentGraphStore(database_path(workspace, run_id, project_id)).confirm(confirmation, expected_digest)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--project-id")
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
    recording.add_argument(
        "--axis",
        action="append",
        default=None,
        metavar="DESCRIPTION",
        help="declare a divergence axis opened by the user's answer (repeatable, #496)",
    )
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
    schema = commands.add_parser("schema", help="show the graph-update contract and a strict UTF-8 example")
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
        if not args.project_id:
            raise AlignmentGraphError("--project-id is required for a project-scoped alignment run")
        store = AlignmentGraphStore(database_path(workspace, args.run_id, args.project_id))
        if args.command == "init":
            result = store.initialize(args.run_id)
        elif args.command == "plan":
            graph_file = args.graph_file if args.graph_file.is_absolute() else workspace / args.graph_file
            result = store.plan(_load_update(graph_file))
        elif args.command == "record":
            result = store.record(args.node_id, args.outcome, args.fingerprint, args.axis)
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
                "id",
                "type",
                "statement",
                "status",
                "impact",
                "human_only",
                "confidence",
                "source",
                "oracle",
                "attributes",
            ],
            "types": sorted(NODE_TYPES),
            "statuses": sorted(NODE_STATUSES),
            "sources": sorted(SOURCES),
        },
        "edge": {
            "required": ["id", "source_id", "target_id", "relation"],
            "allowed_fields": [
                "id",
                "source_id",
                "target_id",
                "relation",
                "status",
                "confidence",
                "provenance",
                "attributes",
            ],
            "relations": sorted(EDGE_RELATIONS),
            "statuses": sorted(EDGE_STATUSES),
        },
        "divergence_axis_declaration": {
            "required": ["description"],
            "allowed_fields": ["id", "description"],
            "statuses": sorted(AXIS_STATUSES),
        },
        "example_update": {
            "nodes": [
                {
                    "id": "evidence-1",
                    "type": "evidence",
                    "statement": "A bounded reconnaissance finding.",
                    "status": "supported",
                    "source": "reconnaissance",
                    "attributes": {"anchor": {"kind": "source", "ref": "https://example.test"}},
                },
                {
                    "id": "question-1",
                    "type": "research_question",
                    "statement": "Which implementation decision does the evidence support?",
                    "oracle": "The alternatives are tested against anchored evidence.",
                },
            ],
            "edges": [
                {
                    "id": "edge-1",
                    "source_id": "evidence-1",
                    "target_id": "question-1",
                    "relation": "informs",
                }
            ],
        },
    }


if __name__ == "__main__":
    raise SystemExit(main())
