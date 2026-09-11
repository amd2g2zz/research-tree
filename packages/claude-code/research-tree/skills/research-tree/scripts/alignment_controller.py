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

try:  # the two-layer contract seam (#504); the graph imports the contract, never the reverse (#489)
    from .decision_frame import resolve_user_response_policy
    from .turn_contract import (
        DEFAULT_MAX_CHARS_PER_TURN,
        DEFAULT_MAX_QUESTIONS_PER_TURN,
        RESPONSE_CLASS_DISCRIMINATION,
        RESPONSE_CLASS_GENERATION,
        RESPONSE_CLASSES,
        AgentTurnBudget,
        ContractTerms,
        CostCap,
        TurnContractError,
        verify_traces,
    )
except ImportError:  # packaged single-file layout: the seam ships beside this script (#470)
    try:
        from decision_frame import resolve_user_response_policy  # type: ignore[no-redef]
        from turn_contract import (  # type: ignore[no-redef]
            DEFAULT_MAX_CHARS_PER_TURN,
            DEFAULT_MAX_QUESTIONS_PER_TURN,
            RESPONSE_CLASS_DISCRIMINATION,
            RESPONSE_CLASS_GENERATION,
            RESPONSE_CLASSES,
            AgentTurnBudget,
            ContractTerms,
            CostCap,
            TurnContractError,
            verify_traces,
        )
    except ImportError:  # seam unavailable: contract emission degrades fail-open (#489)
        resolve_user_response_policy = None  # type: ignore[assignment]
        verify_traces = None  # type: ignore[assignment]
        RESPONSE_CLASS_DISCRIMINATION = "discrimination"  # type: ignore[assignment]
        RESPONSE_CLASS_GENERATION = "generation"  # type: ignore[assignment]
        RESPONSE_CLASSES = ("discrimination", "generation")  # type: ignore[assignment]
        DEFAULT_MAX_QUESTIONS_PER_TURN = 1  # type: ignore[assignment]
        DEFAULT_MAX_CHARS_PER_TURN = 1200  # type: ignore[assignment]
        ContractTerms = None  # type: ignore[assignment]
        CostCap = None  # type: ignore[assignment]
        AgentTurnBudget = None  # type: ignore[assignment]
        TurnContractError = ValueError  # type: ignore[assignment]

SCHEMA = 3
# Turn-cap bound (#491): reaching it never exits alignment. It triggers the
# explicit `alignment_incomplete` blocked disposition (user extension or waive
# required); the exit itself is decided by the alignment score below.
MAX_TURNS = 6
# Issue #500: profile vocabulary the SKILL layer may declare per turn. The
# engine never infers the profile — it only gates the structural posture.
USER_PROFILES = frozenset({"novice", "expert"})
# Per-node/per-axis stall threshold (#496): a requester-only point that stayed
# quiet this many turns with no active divergence axis is *locally stalled*.
# This is no longer a global escape hatch — see MAX_TURNS for the (separately
# governed) total-turn bound and plan() for the stall decision.
MAX_STAGNANT_TURNS = 2
MAX_ASKS_PER_NODE = 2
# --- Alignment exit policy (#491) -------------------------------------------------
# Alignment exits by a deterministic score over graph state, never by a silent
# strategy switch. The score starts at ALIGNMENT_SCORE_MAX and subtracts
# penalties for alignment residue (weights in score points below); offering
# and accepting the handoff requires reaching ALIGNMENT_SCORE_EXIT_THRESHOLD
# or a recorded explicit user waive (AlignmentGraphStore.waive).
ALIGNMENT_SCORE_MAX = 100
ALIGNMENT_SCORE_EXIT_THRESHOLD = ALIGNMENT_SCORE_MAX
ALIGNMENT_SCORE_OPEN_GAP_WEIGHT = 20  # per impact point (1-5) of an open requester-only gap
ALIGNMENT_SCORE_EXHAUSTED_ASK_WEIGHT = 10  # per open requester-only gap whose MAX_ASKS_PER_NODE budget is spent
ALIGNMENT_SCORE_OPEN_AXIS_WEIGHT = 10  # per open divergence axis (#496), on any node
# Impact at or above this counts as "high-impact" (same bar as the
# high-impact disagreement rule in _alignment_readiness).
ALIGNMENT_HIGH_IMPACT = 4
# Dialogue turns granted when the user responds after an
# `alignment_incomplete` blocked disposition (extension by engagement).
ALIGNMENT_EXTENSION_TURNS = 3
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

    def plan(
        self,
        update: Mapping[str, Any] | None = None,
        *,
        user_signal: Mapping[str, str] | None = None,
        previous_category: str | None = None,
        user_profile: str | None = None,
    ) -> dict[str, Any]:
        # Issue #500: the user profile is a turn-context INPUT set by the
        # SKILL layer from conversation signals; the engine never infers it.
        if user_profile is not None and user_profile not in USER_PROFILES:
            raise AlignmentGraphError(
                f"user_profile must be one of {sorted(USER_PROFILES)} or None, not {user_profile!r}"
            )
        if update is not None:
            self.merge(update)
        with self._connect() as connection:
            self._require_schema(connection)
            state = self._materialize(connection)
            nodes = state["graph"]["nodes"]
            readiness = _alignment_readiness(nodes, state["graph"]["edges"])
            controller = state["controller"]
            stagnation = state["divergence"]["node_stagnation"]
            active_axes: dict[str, list[dict[str, Any]]] = {}
            for axis in state["divergence"]["axes"]:
                if axis["status"] == "open" and axis["stagnant_turns"] < MAX_STAGNANT_TURNS:
                    active_axes.setdefault(axis["node_id"], []).append(axis)
            for axis_group in active_axes.values():
                axis_group.sort(key=lambda axis: (axis["stagnant_turns"], -axis["opened_turn"], axis["axis_id"]))
            # Divergence-aware eligibility (#496): MAX_ASKS_PER_NODE bounds
            # re-asking one dimension; an active axis is a NEW dimension on the
            # node and carries its own ask allowance. A locally stalled node
            # (stagnation at the threshold, no active axis) is skipped — it is
            # a stall, not a reason to abandon the dialogue elsewhere. A node
            # whose latest recorded response was ``answered`` is a taboos
            # exclusion too (#489): re-asking needs a new axis, not repetition.
            last_outcomes = _last_response_outcomes(connection)
            eligible = [
                node
                for node in nodes
                if node["last_asked_turn"] != controller["turn"]
                and (node["id"] in active_axes or last_outcomes.get(node["id"]) != "answered")
                and (
                    (
                        node["human_only"]
                        and node["status"] in {"candidate", "disputed"}
                        and (node["ask_count"] < MAX_ASKS_PER_NODE or node["id"] in active_axes)
                        and (stagnation.get(node["id"], 0) < MAX_STAGNANT_TURNS or node["id"] in active_axes)
                    )
                    # An active divergence axis is a user-raised direction
                    # nobody explored yet (#491 score gate): it is askable on
                    # any node, settled or not, so a below-threshold score has
                    # a dialogue move to make before any user decision.
                    or node["id"] in active_axes
                )
            ]
            eligible.sort(
                key=lambda node: (0 if node["id"] in active_axes else 1, -node["impact"], node["ask_count"], node["id"])
            )
            score = _alignment_score(nodes, state["divergence"]["axes"])
            exit_allowed = (
                score >= ALIGNMENT_SCORE_EXIT_THRESHOLD or _active_waive(connection, state["graph_digest"]) is not None
            )
            extension_deadline = _extension_deadline(connection)
            extended = extension_deadline is not None and controller["turn"] <= extension_deadline
            escalation = _escalation_nodes(nodes)
            # Contract emission (#489): resolve the observed user move into
            # the #490 policy verdict BEFORE the ask is selected, so the gap
            # directive steers the candidate order itself. The signal comes
            # from the caller or, fail-open, from the run's persisted
            # alignment_user_move feed records.
            previous_terms = _previous_contract_terms(controller)
            signal = user_signal
            resolved_previous = previous_category
            if signal is None and resolve_user_response_policy is not None:
                feed_signal, feed_previous = _user_move_signal_from_feed(self.database.parent.parent)
                signal = feed_signal
                if resolved_previous is None:
                    resolved_previous = feed_previous
            verdict = None
            if signal is not None and resolve_user_response_policy is not None:
                try:
                    verdict = resolve_user_response_policy(
                        signal,
                        previous_terms,
                        previous_category=resolved_previous,
                        candidates=[node["id"] for node in eligible],
                    )
                except ValueError:
                    verdict = None  # untrusted signal input: rank-order emission (fail-open)
            if verdict is not None:
                eligible = [node for node in eligible if node["id"] not in set(verdict.taboo_additions)]
                if verdict.gap_target is not None:
                    forced = next((node for node in nodes if node["id"] == verdict.gap_target), None)
                    if forced is not None:
                        eligible = [forced] + [node for node in eligible if node["id"] != forced["id"]]
            # Per-turn question budget (#527, the agent-side dual of the
            # cost_cap): every ask consumes the allowance, and the spent
            # count reads the persisted graph state (nodes asked this turn),
            # so no schema change. record() advances the turn, which resets
            # it; per-node MAX_ASKS_PER_NODE is unchanged.
            turn_budget = _agent_turn_budget(previous_terms)
            max_questions = turn_budget.max_questions if turn_budget is not None else DEFAULT_MAX_QUESTIONS_PER_TURN
            asked_this_turn = sum(1 for node in nodes if node["last_asked_turn"] == controller["turn"])
            question_budget = {"max_questions": max_questions, "asked_this_turn": asked_this_turn}
            if readiness["ready"] and exit_allowed:
                decision: dict[str, Any] = {
                    "action": "await_human_confirmation",
                    "reason": "the alignment graph supports a strategy handoff",
                    "question": None,
                }
            elif not exit_allowed and controller["turn"] >= MAX_TURNS and not extended:
                # Turn cap reached with the score still below the exit
                # threshold (#491): the open points are the user's decision —
                # never a silent strategy switch to reconnaissance.
                decision = _blocked_disposition(
                    nodes,
                    state["divergence"]["axes"],
                    score,
                    "alignment turn budget reached with the alignment score below the exit threshold; "
                    "the open points need your decision",
                )
            elif eligible and asked_this_turn < max_questions:
                node = eligible[0]
                connection.execute(
                    "UPDATE nodes SET ask_count=ask_count+1, last_asked_turn=? WHERE node_id=?",
                    (controller["turn"], node["id"]),
                )
                connection.execute("UPDATE controller SET pending_node_id=? WHERE singleton=1", (node["id"],))
                axis_group = active_axes.get(node["id"])
                if axis_group:
                    axis = axis_group[0]
                    decision = {
                        "action": "ask_one",
                        "node_id": node["id"],
                        "gap_id": node["id"],
                        "axis_id": axis["axis_id"],
                        "axis": axis["description"],
                        "question": f"Explore the opened divergence axis: {axis['description']}",
                        "reason": "the user's answer opened an unexplored direction on this point; continue in dialogue",
                    }
                else:
                    decision = {
                        "action": "ask_one",
                        "node_id": node["id"],
                        "gap_id": node["id"],
                        "question": f"Ask one open-ended question about: {node['statement']}",
                        "reason": "highest-impact unresolved point that only the requester can settle",
                    }
                decision["question_budget"] = {
                    **question_budget,
                    "asked_this_turn": asked_this_turn + 1,
                    "remaining": max(0, max_questions - asked_this_turn - 1),
                }
            elif eligible:
                # The per-turn question budget is spent (#527): until
                # record() resets it, the engine emits a NON-QUESTION
                # decision — the composer's mirror/teach/gather postures
                # (prompt-layer craft vocabulary) — keeping the dialogue gap
                # target so the turn stays contract-grounded. The action
                # reuses the existing non-question vocabulary.
                node = eligible[0]
                axis_group = active_axes.get(node["id"])
                decision = {
                    "action": "reconnaissance",
                    "node_id": node["id"],
                    "gap_id": node["id"],
                    "question": None,
                    "reason": (
                        "the per-turn question budget is spent; compose a non-question turn "
                        "(mirror/teach/gather) grounded in the graph until the next turn resets it"
                    ),
                }
                if axis_group:
                    axis = axis_group[0]
                    decision["axis_id"] = axis["axis_id"]
                    decision["axis"] = axis["description"]
                decision["question_budget"] = {**question_budget, "remaining": 0}
            elif escalation:
                # Ask budget spent on a high-impact requester-only point with
                # no dialogue move left (#491): name it for the user's decision
                # instead of abandoning it to reconnaissance.
                decision = _blocked_disposition(
                    nodes,
                    state["divergence"]["axes"],
                    score,
                    "the ask budget is spent on a high-impact requester-only point without convergence; "
                    "it needs your decision",
                )
            else:
                requester_nodes = [
                    node for node in nodes if node["human_only"] and node["status"] in {"candidate", "disputed"}
                ]
                if requester_nodes and all(
                    stagnation.get(node["id"], 0) >= MAX_STAGNANT_TURNS for node in requester_nodes
                ):
                    reason = "no open divergence axis remains and every requester-only question is locally stalled"
                else:
                    reason = "; ".join(readiness["reasons"][:3]) or "remaining uncertainty is agent-verifiable"
                decision = {
                    "action": "reconnaissance",
                    "reason": reason,
                    "question": None,
                }
            # Canonical loop step 1 (#489): emit the turn's contract terms
            # next to the decision — additive keys; the action output above is
            # unchanged and the terms persist via last_decision_json.
            if ContractTerms is not None and nodes:
                terms = _emit_contract_terms(
                    nodes,
                    decision,
                    active_axes,
                    stagnation,
                    last_outcomes,
                    previous_terms,
                    verdict,
                    user_profile=user_profile,
                    surveyed_gaps=_gaps_with_recorded_survey(connection),
                )
                if terms is not None:
                    decision["contract_terms"] = terms.to_dict()
            if verdict is not None:
                decision["user_move_policy"] = verdict.to_dict()
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
            "alignment_score": score,
            "alignment_exit_threshold": ALIGNMENT_SCORE_EXIT_THRESHOLD,
        }

    def record(
        self,
        node_id: str,
        outcome: str,
        fingerprint: str,
        new_axes: Sequence[Any] | None = None,
        *,
        traces: Sequence[Mapping[str, Any]] | None = None,
        user_move: str | None = None,
        question_count: int | None = None,
        turn_chars: int | None = None,
    ) -> dict[str, Any]:
        node_id = _identifier(node_id, "node id")
        outcome = _enum(outcome, OUTCOMES, "outcome")
        for name, measured in (("question_count", question_count), ("turn_chars", turn_chars)):
            if measured is not None and (isinstance(measured, bool) or not isinstance(measured, int) or measured < 0):
                raise AlignmentGraphError(f"{name} must be a nonnegative integer or None, not {measured!r}")
        axes = _normalize_axes(new_axes)
        normalized_traces: list[dict[str, Any]] | None = None
        if traces is not None:
            normalized_traces = [dict(trace) for trace in traces]
        typed_user_move: str | None = None
        if user_move is not None:
            if user_move not in RESPONSE_CLASSES:
                raise AlignmentGraphError(
                    f"user_move must be one of the turn_contract response classes {RESPONSE_CLASSES}: {user_move!r}"
                )
            typed_user_move = user_move
        with self._connect() as connection:
            self._require_schema(connection)
            node = connection.execute("SELECT * FROM nodes WHERE node_id=?", (node_id,)).fetchone()
            if node is None:
                raise AlignmentGraphError(f"unknown graph node: {node_id}")
            controller = connection.execute("SELECT * FROM controller WHERE singleton=1").fetchone()
            verified: tuple[str, ...] = ()
            terms = _controller_row_terms(controller)
            if normalized_traces is not None and verify_traces is not None and terms is not None:
                # Canonical loop step 3 (#489): verify the recorded traces
                # against the last plan's emitted terms BEFORE any state
                # mutation; a missing required trace fails naming the term.
                verified = verify_traces(terms, normalized_traces)
            # Issue #527: record-time agent-turn-budget verification — the
            # dual of the user-side cost_cap. Flag-not-block: an over-budget
            # turn stays valid continuity grounding; the named violations
            # feed the #525 discipline telemetry.
            turn_budget_violations = _verify_agent_turn_budget(terms, question_count, turn_chars)
            budget_checked = terms is not None and terms.agent_turn_budget is not None
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
            event_details: dict[str, Any] = {
                "node_id": node_id,
                "outcome": outcome,
                "state_changed": changed,
                "opened_axes": opened_axes,
                "handoff_invalidated": handoff_invalidated,
            }
            if normalized_traces is not None:
                event_details["traces"] = normalized_traces
            if typed_user_move is not None:
                event_details["user_move"] = typed_user_move
            if budget_checked:
                event_details["turn_budget_violations"] = turn_budget_violations
            state = self._commit_event(connection, "response_recorded", event_details)
        dialogue_mode = state["divergence"]["mode"]
        # record() must not advise the escape plan() would refuse (#491): a
        # stalled dialogue with an exhausted high-impact gap escalates instead.
        stalled_next = "alignment_incomplete" if _escalation_nodes(state["graph"]["nodes"]) else "reconnaissance"
        result = {
            "turn": state["controller"]["turn"],
            "stagnant_turns": stagnant,
            "state_changed": changed,
            "opened_axes": opened_axes,
            "dialogue_mode": dialogue_mode,
            "next_action": stalled_next if dialogue_mode == "stalled" else "plan",
        }
        if normalized_traces is not None:
            result["verified_traces"] = verified
        if budget_checked:
            result["turn_budget_violations"] = turn_budget_violations
        return result

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
            score = _alignment_score(state["graph"]["nodes"], state["divergence"]["axes"])
            if score < ALIGNMENT_SCORE_EXIT_THRESHOLD and _active_waive(connection, state["graph_digest"]) is None:
                # User pressure cannot bypass the score gate (#491); only a
                # recorded explicit waive unlocks a below-threshold exit.
                raise AlignmentGraphError(
                    f"alignment score {score} is below the exit threshold {ALIGNMENT_SCORE_EXIT_THRESHOLD}; "
                    "alignment is incomplete: resolve the open points or record an explicit waive"
                )
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

    def waive(self, reason: str) -> dict[str, Any]:
        """Record an explicit user waive of the alignment-exit gate (#491).

        The waive is the user's recorded decision to proceed despite an
        alignment score below ``ALIGNMENT_SCORE_EXIT_THRESHOLD`` (or a turn
        cap with open gaps). It is bound to the graph digest at waive time:
        any later graph change expires it and the gate re-engages. Generic
        acknowledgements are rejected, same bar as handoff confirmation.
        """
        text = " ".join(str(reason).split())
        if not text:
            raise AlignmentGraphError("waive reason must be nonempty")
        if text.casefold() in {"ok", "okay", "yes", "continue", "go ahead", "可以", "继续"}:
            raise AlignmentGraphError("generic acknowledgement is not an alignment waive")
        with self._connect() as connection:
            self._require_schema(connection)
            state = self._materialize(connection)
            nodes = state["graph"]["nodes"]
            score = _alignment_score(nodes, state["divergence"]["axes"])
            details = {
                "reason": text,
                "reason_digest": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "graph_digest": state["graph_digest"],
                "alignment_score": score,
                "alignment_exit_threshold": ALIGNMENT_SCORE_EXIT_THRESHOLD,
                "blocked_nodes": sorted(
                    node["id"] for node in nodes if node["human_only"] and node["status"] in {"candidate", "disputed"}
                ),
            }
            self._commit_event(connection, "alignment_waived", details)
        return {
            "waived": True,
            "graph_digest": details["graph_digest"],
            "alignment_score": score,
            "alignment_exit_threshold": ALIGNMENT_SCORE_EXIT_THRESHOLD,
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


def _alignment_score(nodes: Sequence[Mapping[str, Any]], axes: Sequence[Mapping[str, Any]]) -> int:
    """Deterministic alignment-exit score over graph state (#491).

    Returns an integer 0..``ALIGNMENT_SCORE_MAX``: full convergence (no open
    requester-only gap, no spent ask budget on an open gap, no open divergence
    axis) scores the maximum and exits without user intervention; every piece
    of residue subtracts its weight, so exiting is gated by alignment quality,
    not by the turn counter. Exact integer arithmetic keeps the score stable
    across reopens and event-log rebuilds.
    """

    penalty = 0
    for node in nodes:
        if node["human_only"] and node["status"] in {"candidate", "disputed"}:
            penalty += ALIGNMENT_SCORE_OPEN_GAP_WEIGHT * int(node["impact"])
            if node["ask_count"] >= MAX_ASKS_PER_NODE:
                penalty += ALIGNMENT_SCORE_EXHAUSTED_ASK_WEIGHT
    penalty += ALIGNMENT_SCORE_OPEN_AXIS_WEIGHT * sum(1 for axis in axes if axis["status"] == "open")
    return max(0, ALIGNMENT_SCORE_MAX - penalty)


def _escalation_nodes(nodes: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Open requester-only gaps whose ask budget is spent at high impact (#491).

    These are named in the blocked disposition for the user's decision instead
    of being abandoned to reconnaissance. An active divergence axis on the
    node keeps the node askable first (#496 extra allowance composes); stalled
    gaps that never exhausted their ask budget keep the #496 stall behavior.
    """

    return sorted(
        (
            node
            for node in nodes
            if node["human_only"]
            and node["status"] in {"candidate", "disputed"}
            and node["ask_count"] >= MAX_ASKS_PER_NODE
            and node["impact"] >= ALIGNMENT_HIGH_IMPACT
        ),
        key=lambda node: (-node["impact"], node["id"]),
    )


def _blocked_disposition(
    nodes: Sequence[Mapping[str, Any]], axes: Sequence[Mapping[str, Any]], score: int, reason: str
) -> dict[str, Any]:
    """Build the ``alignment_incomplete`` blocked disposition (#491).

    The disposition names every open requester-only gap (impact-descending,
    with its spent-ask flag), the open divergence axes, and the score versus
    the exit threshold, and states the two resolutions: extend the dialogue or
    record an explicit waive.
    """

    open_gaps = sorted(
        (node for node in nodes if node["human_only"] and node["status"] in {"candidate", "disputed"}),
        key=lambda node: (-node["impact"], node["id"]),
    )
    return {
        "action": "alignment_incomplete",
        "reason": reason,
        "question": None,
        "alignment_score": score,
        "alignment_exit_threshold": ALIGNMENT_SCORE_EXIT_THRESHOLD,
        "blocked_nodes": [
            {
                "node_id": node["id"],
                "impact": node["impact"],
                "asks_exhausted": node["ask_count"] >= MAX_ASKS_PER_NODE,
            }
            for node in open_gaps
        ],
        "exhausted_ask_nodes": [node["id"] for node in open_gaps if node["ask_count"] >= MAX_ASKS_PER_NODE],
        "open_axes": [axis["description"] for axis in axes if axis["status"] == "open"],
        "requires": "extend the dialogue by answering, or record an explicit waive",
    }


# --- Contract emission (#489): the canonical two-layer loop ----------------
#
# ADR-008 canonical loop step 1 and 3: each turn the engine emits structured
# contract terms (target_gap / required_traces / cost_cap / taboos) alongside
# the existing decision, and after the turn verifies the recorded traces
# against the emitted terms. The enumerated space is contract terms and trace
# types (turn_contract registry) — never behaviors; the prompt layer composes
# the turn freely from the craft material (references/alignment-craft.md).
# target_gap ranking reuses the #496 divergence-aware eligibility, taboos
# carry MAX_ASKS_PER_NODE / stall exclusions (#491/#496 migrate into the
# term), and the #490 policy (resolve_user_response_policy) applies the
# observed user move — its persisted alignment_user_move feed records are the
# default transport, kept literal here so the graph does not import the hook.

USER_MOVE_FEED_ROUTE = "alignment_user_move"
_USER_MOVE_FEED_SCAN = 64
_OPEN_GAP_STATUSES = frozenset({"candidate", "disputed"})


def _last_response_outcomes(connection: sqlite3.Connection) -> dict[str, str]:
    """Latest recorded outcome per node, from the append-only event log."""

    outcomes: dict[str, str] = {}
    for row in connection.execute(
        "SELECT details_json FROM events WHERE event_type='response_recorded' ORDER BY sequence"
    ):
        details = json.loads(row["details_json"])
        node_id = details.get("node_id")
        outcome = details.get("outcome")
        if isinstance(node_id, str) and isinstance(outcome, str):
            outcomes[node_id] = outcome
    return outcomes


def _gaps_with_recorded_survey(connection: sqlite3.Connection) -> frozenset[str]:
    """Gap ids with a recorded possibility-survey trace (issue #500).

    Read from the append-only ``response_recorded`` event log — a survey
    counts once recorded against the gap, whatever later turns did.
    """

    surveyed: set[str] = set()
    for row in connection.execute(
        "SELECT details_json FROM events WHERE event_type='response_recorded' ORDER BY sequence"
    ):
        details = json.loads(row["details_json"])
        if not isinstance(details, Mapping):
            continue
        traces = details.get("traces")
        if not isinstance(traces, Sequence):
            continue
        if any(isinstance(t, Mapping) and t.get("type") == "possibility-survey" for t in traces):
            node_id = details.get("node_id")
            if isinstance(node_id, str):
                surveyed.add(node_id)
    return frozenset(surveyed)


def _contract_terms_of_decision(decision: Any) -> Any:
    """Parse a decision's emitted contract terms, when still parseable."""

    if ContractTerms is None or not isinstance(decision, Mapping):
        return None
    value = decision.get("contract_terms")
    if not isinstance(value, Mapping):
        return None
    try:
        return ContractTerms.from_dict(value)
    except TurnContractError:
        return None


def _previous_contract_terms(controller: Mapping[str, Any]) -> Any:
    """The outstanding ask: the last plan's emitted terms, when still parseable."""

    decision = controller.get("last_decision") if isinstance(controller, Mapping) else None
    return _contract_terms_of_decision(decision)


def _controller_row_terms(controller: sqlite3.Row) -> Any:
    """The last plan's emitted terms read from the persisted controller row."""

    if ContractTerms is None:
        return None
    raw = controller["last_decision_json"]
    if not raw:
        return None
    try:
        return _contract_terms_of_decision(json.loads(raw))
    except ValueError:
        return None


def _verify_agent_turn_budget(
    terms: Any,
    question_count: int | None,
    turn_chars: int | None,
) -> list[dict[str, int]]:
    """Record-time agent-turn-budget check (#527): flag-not-block.

    A recorded turn exceeding ``max_questions`` or ``max_chars`` is a named
    violation; the turn remains valid as continuity grounding (#514 ruling)
    and each entry names the dimension, the limit, and the observed value so
    the #525 discipline telemetry can count it. Empty when no budget was
    carried or nothing was exceeded.
    """

    budget = getattr(terms, "agent_turn_budget", None) if terms is not None else None
    if budget is None:
        return []
    violations: list[dict[str, int]] = []
    if question_count is not None and question_count > budget.max_questions:
        violations.append({"dimension": "max_questions", "limit": budget.max_questions, "observed": question_count})
    if turn_chars is not None and turn_chars > budget.max_chars:
        violations.append({"dimension": "max_chars", "limit": budget.max_chars, "observed": turn_chars})
    return violations


def _user_move_signal_from_feed(run_root: Path) -> tuple[Mapping[str, str] | None, str | None]:
    """Read the newest (and previous) #490 user-move feed record, fail-open.

    The hook persists one ``alignment_user_move`` record per classified
    alignment-phase prompt, with a fixed-width UTC timestamp prefix, so
    lexicographic order is chronological. Newest = the prompt the agent is
    answering; previous = the repeated-correction input. Bounded scan; any
    problem degrades to no signal (rank-order emission).
    """

    try:
        paths = sorted(
            (item for item in (run_root / "events").iterdir() if item.is_file() and item.suffix == ".json"),
            key=lambda item: item.name,
            reverse=True,
        )[:_USER_MOVE_FEED_SCAN]
    except OSError:
        return None, None
    signal: dict[str, str] | None = None
    previous: str | None = None
    for path in paths:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(record, Mapping) or record.get("route") != USER_MOVE_FEED_ROUTE:
            continue
        category = record.get("category")
        confidence = record.get("confidence")
        rule = record.get("rule")
        if not (isinstance(category, str) and isinstance(confidence, str) and isinstance(rule, str)):
            continue
        if signal is None:
            signal = {"category": category, "confidence": confidence, "rule": rule}
        else:
            previous = category
            break
    return signal, previous


def _emission_taboos(
    nodes: Sequence[Mapping[str, Any]],
    active_axis_nodes: set[str],
    stagnation: Mapping[str, int],
    last_outcomes: Mapping[str, str],
) -> tuple[str, ...]:
    """Nodes the composer must not re-ask this turn (#489 taboos term).

    Already-answered nodes (their latest recorded response was ``answered``),
    open requester-only gaps whose MAX_ASKS_PER_NODE budget is spent, and
    locally stalled gaps (#496 stagnation at the threshold) — unless an
    active divergence axis re-opens the node.
    """

    taboos: set[str] = set()
    for node in nodes:
        if not node["human_only"]:
            continue
        node_id = node["id"]
        if node_id in active_axis_nodes:
            continue
        if last_outcomes.get(node_id) == "answered":
            taboos.add(node_id)
        if node["status"] in _OPEN_GAP_STATUSES and (
            node["ask_count"] >= MAX_ASKS_PER_NODE or stagnation.get(node_id, 0) >= MAX_STAGNANT_TURNS
        ):
            taboos.add(node_id)
    return tuple(sorted(taboos))


def _base_cost_cap(action: str) -> Any:
    """The asking-shape cap: open-ended elicitation is generation; a confirm is one sentence."""

    if CostCap is None:
        return None
    if action == "await_human_confirmation":
        return CostCap(response_class=RESPONSE_CLASS_DISCRIMINATION, max_sentences=1)
    return CostCap(response_class=RESPONSE_CLASS_GENERATION, max_sentences=None)


# Issue #527 required-trace queueing: at most this many required traces are
# emitted per turn (priority order); the remainder is deferred in the terms
# and re-emitted as required by the next turn's emission.
MAX_REQUIRED_TRACES_PER_TURN = 2


def _agent_turn_budget(previous_terms: Any) -> Any:
    """The agent output ceiling emitted with the terms (#527).

    The dual of the user-side cost cap: one question per interactive turn
    and a per-turn character bound (tier-settable by #526 — these are the
    engine-floor defaults). A budget carried by the previous terms is kept,
    the same carry rule as the cap.
    """

    if AgentTurnBudget is None:
        return None
    if previous_terms is not None and previous_terms.agent_turn_budget is not None:
        return previous_terms.agent_turn_budget
    return AgentTurnBudget(
        max_questions=DEFAULT_MAX_QUESTIONS_PER_TURN,
        max_chars=DEFAULT_MAX_CHARS_PER_TURN,
    )


def _gap_required_traces(node: Mapping[str, Any], *, reopened: bool, cap: Any) -> tuple[str, ...]:
    """Required traces from gap shape + response-production class (#489).

    A misunderstood-intent gap (disputed target, or a correction-driven
    reopen) requires the turn to restate the corrected understanding
    (``guess-statement``). A proposal-shaped gap requires the possibility
    space be surveyed before an open question (``possibility-survey``), or
    the option set be shown when the user's next move is a pointing response
    (``option-set`` under a discrimination cap). All names are frozen
    registry entries; alternatives are resolved by the cap class, never by
    OR-semantics in the terms.
    """

    if node["status"] == "disputed" or reopened:
        return ("guess-statement",)
    # Issue #498: a proposal-shaped gap always also requires the
    # complexity-constraint proportionality assessment — the necessity check
    # the engine verifies structurally (layer 1 of the ladder).
    if cap is not None and cap.response_class == RESPONSE_CLASS_DISCRIMINATION:
        return ("option-set", "proportionality_assessment")
    return ("possibility-survey", "proportionality_assessment")


def _fallback_target(nodes: Sequence[Mapping[str, Any]], active_axes_by_node: Mapping[str, Any]) -> str | None:
    """Turn center for non-asking decisions: top open gap, else axis node, else strategy."""

    open_gaps = sorted(
        (node for node in nodes if node["human_only"] and node["status"] in _OPEN_GAP_STATUSES),
        key=lambda node: (-node["impact"], node["id"]),
    )
    if open_gaps:
        return str(open_gaps[0]["id"])
    if active_axes_by_node:
        return min(active_axes_by_node)
    strategies = sorted(
        (node for node in nodes if node["type"] == "strategy" and node["status"] in ACCEPTED_STATUSES),
        key=lambda node: node["id"],
    )
    if strategies:
        return str(strategies[0]["id"])
    if nodes:
        return str(sorted(nodes, key=lambda node: (-node["impact"], node["id"]))[0]["id"])
    return None


def _is_interactive_turn(decision: Mapping[str, Any]) -> bool:
    """A composer turn grounded in a dialogue gap (issue #527).

    The ask itself, or the question-budget non-question turn (which carries
    ``gap_id`` without a question). Exit and blocked decisions are not
    interactive: their terms never gain a trace gate.
    """

    return str(decision.get("action")) == "ask_one" or "gap_id" in decision


def _emit_contract_terms(
    nodes: Sequence[Mapping[str, Any]],
    decision: Mapping[str, Any],
    active_axes_by_node: Mapping[str, Any],
    stagnation: Mapping[str, int],
    last_outcomes: Mapping[str, str],
    previous_terms: Any,
    verdict: Any,
    *,
    user_profile: str | None = None,
    surveyed_gaps: frozenset[str] | None = None,
) -> Any:
    """Build the turn's ContractTerms from the graph state and the #490 verdict."""

    if ContractTerms is None or not nodes:
        return None
    directive = verdict.gap_directive if verdict is not None else "keep"
    taboos = set(_emission_taboos(nodes, set(active_axes_by_node), stagnation, last_outcomes))
    if verdict is not None:
        taboos |= set(verdict.taboo_additions)
        taboos -= set(verdict.taboo_removals)
    interactive = _is_interactive_turn(decision)
    if interactive and "node_id" in decision:
        target: str | None = str(decision["node_id"])
    elif verdict is not None and verdict.gap_target is not None:
        target = verdict.gap_target
    else:
        target = _fallback_target(nodes, active_axes_by_node)
    if target is None:
        return None
    taboos.discard(target)
    if verdict is not None and verdict.cost_cap is not None:
        cap = verdict.cost_cap
    elif previous_terms is not None:
        # A move that leaves the cap alone keeps the emitted ceiling (#490).
        cap = previous_terms.cost_cap
    else:
        cap = _base_cost_cap(str(decision["action"]))
    # Issue #527 required-trace queueing: a priority-ordered wishlist —
    # carried deferrals first (oldest obligation first), then the gap-shape
    # and #500 novice-posture requirements — of which at most
    # MAX_REQUIRED_TRACES_PER_TURN are required this turn; the remainder is
    # deferred in the emitted terms and re-emitted as required next turn.
    # Nothing is silently dropped: non-interactive turns carry the queue
    # forward untouched instead of gating (the requester's exit confirmation
    # must not fail on composition traces).
    wishlist: list[str] = []
    if interactive:
        for name in previous_terms.deferred_traces if previous_terms is not None else ():
            if name not in wishlist:
                wishlist.append(name)
    novice_active = user_profile == "novice" and interactive and CostCap is not None
    if novice_active:
        # Issue #500 interview posture, as emission policy (not a menu): a
        # novice points rather than composes, so the cap drops to the
        # discrimination floor, the turn must show options (show-then-point),
        # and the possibility space must be mapped (survey on record) before
        # anything open-ended is asked of them.
        cap = CostCap(response_class=RESPONSE_CLASS_DISCRIMINATION, max_sentences=1)
    if interactive:
        node = next((item for item in nodes if item["id"] == target), None)
        if node is not None:
            gap_traces = _gap_required_traces(node, reopened=(directive == "reopen"), cap=cap)
            # The misunderstood-intent floor outranks the novice posture:
            # echo-guess or mirror first, ask second (alignment-craft.md).
            misunderstood = gap_traces[:1] if gap_traces and gap_traces[0] == "guess-statement" else ()
            for name in misunderstood:
                if name not in wishlist:
                    wishlist.append(name)
            if novice_active:
                surveyed = target in (surveyed_gaps or frozenset())
                for name in ("possibility-survey", "option-set"):
                    if name == "possibility-survey" and surveyed:
                        continue
                    if name not in wishlist:
                        wishlist.append(name)
            for name in gap_traces[len(misunderstood) :]:
                if name not in wishlist:
                    wishlist.append(name)
    required = tuple(wishlist[:MAX_REQUIRED_TRACES_PER_TURN])
    deferred = tuple(wishlist[MAX_REQUIRED_TRACES_PER_TURN:])
    if not interactive and previous_terms is not None:
        deferred = tuple(previous_terms.deferred_traces)
    return ContractTerms(
        target_gap=target,
        required_traces=required,
        cost_cap=cap,
        taboos=tuple(sorted(taboos)),
        agent_turn_budget=_agent_turn_budget(previous_terms),
        deferred_traces=deferred,
    )


def _active_waive(connection: sqlite3.Connection, graph_digest: str) -> dict[str, Any] | None:
    """Latest recorded waive still bound to the current graph content (#491).

    A waive is accepted only while its ``graph_digest`` equals the current
    one: any graph change (merge or a state-changing record) expires it and
    the exit gate re-engages.
    """

    for row in connection.execute(
        "SELECT details_json FROM events WHERE event_type='alignment_waived' ORDER BY sequence DESC"
    ):
        details = json.loads(row["details_json"])
        if details.get("graph_digest") == graph_digest:
            return details
    return None


def _extension_deadline(connection: sqlite3.Connection) -> int | None:
    """Turn bound granted by user engagement after the latest blocked disposition (#491).

    The first user response recorded after the newest ``alignment_incomplete``
    plan decision grants ``ALIGNMENT_EXTENSION_TURNS`` further dialogue turns
    from that response's turn; past the deadline the blocked disposition
    returns and a fresh user response is required to extend again. Derived
    from the append-only event log, so no schema change is needed.
    """

    newer_responses = 0
    block_found = False
    for row in connection.execute("SELECT event_type, details_json FROM events ORDER BY sequence DESC"):
        if row["event_type"] == "response_recorded":
            newer_responses += 1
        elif (
            row["event_type"] == "plan_selected"
            and json.loads(row["details_json"]).get("action") == "alignment_incomplete"
        ):
            block_found = True
            break
    if not block_found or newer_responses == 0:
        return None
    total_responses = connection.execute("SELECT COUNT(*) FROM events WHERE event_type='response_recorded'").fetchone()[
        0
    ]
    first_response = connection.execute(
        "SELECT state_json FROM events WHERE event_type='response_recorded' ORDER BY sequence ASC LIMIT 1 OFFSET ?",
        (total_responses - newer_responses,),
    ).fetchone()
    if first_response is None:
        return None
    first_response_turn = int(json.loads(first_response["state_json"])["controller"]["turn"])
    return first_response_turn + ALIGNMENT_EXTENSION_TURNS


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


def plan(
    workspace: Path,
    run_id: str,
    update_file: Path,
    *,
    project_id: str | None = None,
    user_signal: Mapping[str, str] | None = None,
    previous_category: str | None = None,
) -> dict[str, Any]:
    return AlignmentGraphStore(database_path(workspace, run_id, project_id)).plan(
        _load_update(update_file),
        user_signal=user_signal,
        previous_category=previous_category,
    )


def record(
    workspace: Path,
    run_id: str,
    node_id: str,
    outcome: str,
    fingerprint: str,
    *,
    project_id: str | None = None,
    new_axes: Sequence[Any] | None = None,
    traces: Sequence[Mapping[str, Any]] | None = None,
    user_move: str | None = None,
) -> dict[str, Any]:
    return AlignmentGraphStore(database_path(workspace, run_id, project_id)).record(
        node_id, outcome, fingerprint, new_axes, traces=traces, user_move=user_move
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


def waive(workspace: Path, run_id: str, reason: str, *, project_id: str | None = None) -> dict[str, Any]:
    return AlignmentGraphStore(database_path(workspace, run_id, project_id)).waive(reason)


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
    waiving = commands.add_parser("waive", help="record an explicit user waive of the alignment-exit gate (#491)")
    waiving.add_argument("--run-id", required=True)
    waiving.add_argument("--reason", required=True)
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
        elif args.command == "waive":
            result = store.waive(args.reason)
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
