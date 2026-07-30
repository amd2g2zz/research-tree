"""Intent-constrained recursive research DAG.

The engine owns durable state and graph invariants.  It does not search or
invent research directions: agents submit query, evidence, cognition, gap, and
child-frame proposals.  A child is admitted only through an explicit gap and
inherits the applicable constraint environment from its parent frame.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from research_repository import atomic_write_json, default_repository, pages_dir, saved_page_path, workspace
from research_strategy import rank_frontier


SCHEMA = 2
_SNAPSHOT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_PROPOSAL_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_REQUEST_SHA256 = re.compile(r"[0-9a-f]{64}")
_REVIEW_ROLES = {"source_triager", "source_adversary"}
ACTIVE = {"open", "acquiring", "aggregating", "reviewing", "extracting", "expanded", "waiting_child", "blocked_on_user"}
TERMINAL = {
    "resolved", "contradicted", "insufficient_evidence", "gap_user_input",
    "gap_access", "merged", "deferred_budget", "pruned_irrelevant",
}
FRAME_STATES = ACTIVE | TERMINAL
DEFAULT_DESCENT_POLICY = {
    # Depth counts recursive calls from a root frame, which has depth zero.
    # These are convergence limits, not pruning rules: an unselected gap stays
    # in the deferred frontier and can be revisited by a later research run.
    "max_calls_per_frame": 3,
    "max_depth": 4,
    "max_frames": 24,
    "score_margin": 0.12,
    "return_revisit_confidence": 0.5,
}
MAX_QUERY_PLAN_ITEMS = 32
_PROVIDER_LABEL = re.compile(r"[a-z0-9_-]{1,64}\Z")
_TOPIC_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_CONTRACT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_DELIVERABLE_KIND = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_CONTENT_KIND = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
AGGREGATION_SCHEMA = 2
INTENT_CONTRACT_SCHEMA = 1
MAX_TOPIC_CLUSTERS = 128
MAX_INTENT_DELIVERABLES = 32
MAX_INTENT_FRAMES = 12
MAX_INTENT_QUESTIONS = 16
MAX_DECISION_QUESTIONS = 32
MAX_INTENT_MATERIALS = 64
MAX_MATERIAL_BYTES = 25_000_000
_TEXTUAL_MATERIAL_SUFFIXES = {".md", ".txt", ".html"}
_SOURCE_RELATIONS = {"representative", "corroborating", "near_duplicate", "contradictory", "irrelevant"}
_DECISION_IMPACTS = {"high", "medium", "low"}
_DECISION_QUESTION_STATUSES = {"supported", "conditional", "gap_child", "need_user_input", "insufficient"}
_DECISION_RECOMMENDATIONS = {"approve", "conditional", "preflight_only", "defer", "reject"}
_PARAMETER_BASES = {"user_constraint", "direct_evidence", "transfer_method", "assumption", "need_user_input"}
_SOURCE_COVERAGE_DISPOSITIONS = {"cited", "context_only", "needs_followup", "excluded"}
DECISION_SYNTHESIS_SCHEMA = 1
_QUALITY_COMPONENTS = (
    "authority", "directness", "traceability", "temporal_fit", "capture_completeness", "independence",
)
_QUALITY_WEIGHTS = {
    "authority": 0.25,
    "directness": 0.20,
    "traceability": 0.20,
    "temporal_fit": 0.15,
    "capture_completeness": 0.10,
    "independence": 0.10,
}
_TOPIC_CONFIDENCE_COMPONENTS = (
    "source_quality", "corroboration", "independence", "temporal_coherence", "scope_match",
)
_TOPIC_CONFIDENCE_WEIGHTS = {
    "source_quality": 0.30,
    "corroboration": 0.20,
    "independence": 0.20,
    "temporal_coherence": 0.15,
    "scope_match": 0.15,
}
_TEMPORAL_FIELDS = {"published_at", "updated_at", "event_at"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_time(value: str) -> datetime:
    """Parse an ISO-8601 instant or date into a timezone-aware value."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("time value must be a non-empty ISO-8601 string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _normalise_temporal_scope(value: object) -> dict | None:
    """Validate a frame's resolved temporal boundary before it reaches search."""

    if value is None:
        return None
    if not isinstance(value, dict) or not value:
        raise ValueError("temporal_scope must be a non-empty object when supplied")
    unknown = set(value) - {"field", "start", "end"}
    if unknown:
        raise ValueError("temporal_scope contains an unsupported field")
    field = value.get("field", "published_at")
    if field not in _TEMPORAL_FIELDS:
        raise ValueError("temporal_scope field must be published_at, updated_at, or event_at")
    start = value.get("start")
    end = value.get("end")
    if start is None and end is None:
        raise ValueError("temporal_scope requires a start or end")
    normalized = {"field": field}
    if start is not None:
        if not isinstance(start, str):
            raise ValueError("temporal_scope start must be an ISO-8601 string")
        parse_time(start)
        normalized["start"] = start.strip()
    if end is not None:
        if not isinstance(end, str):
            raise ValueError("temporal_scope end must be an ISO-8601 string")
        parse_time(end)
        normalized["end"] = end.strip()
    if "start" in normalized and "end" in normalized and parse_time(normalized["start"]) > parse_time(normalized["end"]):
        raise ValueError("temporal_scope start is after end")
    return normalized


def safe_snapshot_id(value: str) -> str:
    if not isinstance(value, str) or not _SNAPSHOT_ID.fullmatch(value):
        raise ValueError("snapshot id must use only letters, digits, dots, underscores, or hyphens")
    return value


def _read_json(value: str, expected: type):
    parsed = json.loads(value)
    if not isinstance(parsed, expected):
        raise ValueError(f"expected JSON {expected.__name__}")
    return parsed


def _capture_metadata(value):
    """Keep only bounded, auditable source-capture facts in graph state."""

    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("evidence capture metadata must be an object")
    status = value.get("status")
    if status not in {"complete", "possibly_truncated"}:
        raise ValueError("evidence capture status must be complete or possibly_truncated")
    method = value.get("method")
    if not isinstance(method, str) or not method.strip() or len(method) > 128 or any(ord(item) < 32 for item in method):
        raise ValueError("evidence capture method must be a short non-empty string")
    normalized = {"status": status, "method": method.strip()}
    for key in ("character_count", "limit_chars"):
        amount = value.get(key)
        if isinstance(amount, bool) or not isinstance(amount, int) or not 0 <= amount <= 10_000_000:
            raise ValueError(f"evidence capture {key} must be a non-negative integer")
        normalized[key] = amount
    if normalized["character_count"] > normalized["limit_chars"]:
        raise ValueError("evidence capture character_count exceeds limit_chars")
    completeness = value.get("completeness")
    if completeness is not None:
        if completeness != "metadata_limited":
            raise ValueError("evidence capture completeness is invalid")
        normalized["completeness"] = completeness
    full_text = value.get("full_text")
    if full_text is not None:
        if not isinstance(full_text, bool):
            raise ValueError("evidence capture full_text must be a boolean")
        normalized["full_text"] = full_text
    content_kind = value.get("content_kind")
    if content_kind is not None:
        if not isinstance(content_kind, str) or not _CONTENT_KIND.fullmatch(content_kind):
            raise ValueError("evidence capture content_kind is invalid")
        normalized["content_kind"] = content_kind
    metadata_character_count = value.get("metadata_character_count")
    metadata_limit_chars = value.get("metadata_limit_chars")
    if metadata_character_count is not None or metadata_limit_chars is not None:
        if (
            isinstance(metadata_character_count, bool) or not isinstance(metadata_character_count, int)
            or isinstance(metadata_limit_chars, bool) or not isinstance(metadata_limit_chars, int)
            or not 0 <= metadata_character_count <= metadata_limit_chars <= 10_000_000
        ):
            raise ValueError("evidence capture metadata character bounds are invalid")
        normalized["metadata_character_count"] = metadata_character_count
        normalized["metadata_limit_chars"] = metadata_limit_chars
    metadata_truncated = value.get("text_possibly_truncated")
    if metadata_truncated is not None:
        if not isinstance(metadata_truncated, bool):
            raise ValueError("evidence capture text_possibly_truncated must be a boolean")
        normalized["text_possibly_truncated"] = metadata_truncated
    return normalized


def _discovery_provenance(value) -> list[dict]:
    """Persist bounded discovery origins separately from page capture transport."""

    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 64:
        raise ValueError("evidence discovered_by must be a bounded list")
    normalized = []
    seen = set()
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("evidence discovered_by entries must be objects")
        provider = item.get("provider")
        plan_index = item.get("plan_index")
        candidate_id = item.get("candidate_id")
        candidate_url = item.get("candidate_url")
        if not isinstance(provider, str) or not _PROVIDER_LABEL.fullmatch(provider):
            raise ValueError("evidence discovered_by provider is invalid")
        if isinstance(plan_index, bool) or not isinstance(plan_index, int) or plan_index < 0:
            raise ValueError("evidence discovered_by plan_index is invalid")
        if candidate_id is not None and (not isinstance(candidate_id, str) or len(candidate_id) > 1024):
            raise ValueError("evidence discovered_by candidate_id is invalid")
        if not isinstance(candidate_url, str) or not candidate_url or len(candidate_url) > 4096:
            raise ValueError("evidence discovered_by candidate_url is invalid")
        normalized_item = {
            "provider": provider,
            "plan_index": plan_index,
            "candidate_id": candidate_id,
            "candidate_url": candidate_url,
        }
        key = tuple(normalized_item.items())
        if key not in seen:
            normalized.append(normalized_item)
            seen.add(key)
    return normalized


def _capture_provider(value) -> str:
    if value is None:
        return "unknown"
    if not isinstance(value, str) or not _PROVIDER_LABEL.fullmatch(value):
        raise ValueError("evidence capture_provider is invalid")
    return value


def _score(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0:
        raise ValueError(f"{label} must be a number in [0, 1]")
    return round(float(value), 6)


def _short_text(value, label: str, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or any(ord(item) < 32 for item in value):
        raise ValueError(f"{label} must be a bounded non-empty string")
    return value.strip()


def _sha256_file(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _score_components(value, label: str, keys: tuple[str, ...], weights: dict[str, float]) -> tuple[dict[str, float], float]:
    """Validate agent assessments and calculate a versioned deterministic score."""

    if not isinstance(value, dict) or set(value) != set(keys):
        joined = ", ".join(keys)
        raise ValueError(f"{label} must contain exactly: {joined}")
    normalized = {key: _score(value[key], f"{label}.{key}") for key in keys}
    return normalized, round(sum(normalized[key] * weights[key] for key in keys), 6)


def _bounded_text_list(value, label: str, maximum_items: int = 64, maximum_chars: int = 2048) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > maximum_items:
        raise ValueError(f"{label} must be a bounded list")
    return [_short_text(item, label, maximum_chars) for item in value]


def _canonical_json_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ResearchState:
    def __init__(self, data: dict):
        self.data = data

    @classmethod
    def create(cls, intent: str, clauses: list, reference_time: str | None,
               materials: list | None = None) -> "ResearchState":
        if not isinstance(intent, str) or not intent.strip():
            raise ValueError("intent must be a non-empty string")
        timestamp = reference_time or now_iso()
        parse_time(timestamp)
        normalised = []
        for index, clause in enumerate(clauses):
            item = dict(clause)
            item.setdefault("id", f"c{index + 1}")
            item.setdefault("raw", "")
            item.setdefault("strength", "hard")
            item.setdefault("scope", ["query", "source", "frame", "report"])
            item.setdefault("evaluator", "semantic")
            item.setdefault("status", "enforced")
            normalised.append(item)
        return cls({
            "schema": SCHEMA,
            "created_at": now_iso(),
            "reference_time": timestamp,
            "intent_versions": [{
                "version": 1, "raw": intent, "created_at": now_iso(),
                "clauses": normalised,
            }],
            "current_intent_version": 1,
            "frames": {}, "evidence": {}, "cognitions": {}, "gaps": {}, "frontier": {},
            "derivation_edges": [], "relations": [], "events": [], "command_receipts": {}, "seq": 0,
            "descent_policy": dict(DEFAULT_DESCENT_POLICY),
            "materials": cls._registered_materials(materials or []),
            "intent_contract": {
                "schema": INTENT_CONTRACT_SCHEMA, "status": "pending", "version": 0,
                "contract": None, "questions": [], "answers": {}, "created_at": now_iso(),
                "updated_at": now_iso(),
            },
            "decision_synthesis": {
                "schema": DECISION_SYNTHESIS_SCHEMA, "status": "not_required",
                "synthesis": None, "sha256": None, "updated_at": now_iso(),
            },
        })

    @classmethod
    def load(cls) -> "ResearchState":
        data = default_repository().load_data()
        if data.get("schema") != SCHEMA:
            raise ValueError("unsupported research state schema")
        return cls(data)

    def save(self) -> None:
        default_repository().save_data(self.data)

    def event(self, action: str, **payload) -> None:
        record = {"ts": now_iso(), "action": action, **payload}
        self.data["events"].append(record)
        default_repository().append_event(record)

    def new_id(self, prefix: str) -> str:
        self.data["seq"] += 1
        digest = hashlib.sha256(f"{prefix}:{self.data['seq']}:{now_iso()}".encode()).hexdigest()[:10]
        return f"{prefix}_{self.data['seq']:04d}_{digest}"

    def current_intent(self) -> dict:
        version = self.data["current_intent_version"]
        return next(item for item in self.data["intent_versions"] if item["version"] == version)

    def active_clauses(self) -> list[dict]:
        return self.current_intent()["clauses"]

    def active_clause_ids(self) -> set[str]:
        return {item["id"] for item in self.active_clauses()}

    def intent_contract(self) -> dict:
        """Return the durable pre-research contract, preserving legacy runs."""

        contract = self.data.get("intent_contract")
        if contract is None:
            # Snapshots created before the preflight contract can remain
            # readable. New runs always receive the explicit contract above.
            return {"schema": 0, "status": "ready", "legacy": True, "contract": None,
                    "questions": [], "answers": {}}
        if not isinstance(contract, dict) or contract.get("schema") != INTENT_CONTRACT_SCHEMA:
            raise ValueError("intent contract is invalid")
        status = contract.get("status")
        if status not in {"pending", "needs_clarification", "ready"}:
            raise ValueError("intent contract status is invalid")
        return contract

    def require_intent_ready(self) -> None:
        contract = self.intent_contract()
        if contract["status"] != "ready":
            raise ValueError("intent contract must be ready before research frames or queries can be created")

    def decision_questions(self) -> list[dict]:
        """Return the normalized decision questions for new decision-aware runs."""

        record = self.intent_contract()
        contract = record.get("contract")
        if not isinstance(contract, dict):
            return []
        questions = contract.get("decision_questions", [])
        if not isinstance(questions, list):
            raise ValueError("intent contract decision_questions is invalid")
        return questions

    def decision_synthesis_required(self) -> bool:
        return bool(self.decision_questions())

    def _decision_synthesis_record(self) -> dict:
        record = self.data.get("decision_synthesis")
        if record is None:
            return {
                "schema": DECISION_SYNTHESIS_SCHEMA, "status": "not_required",
                "synthesis": None, "sha256": None,
            }
        if not isinstance(record, dict) or record.get("schema") != DECISION_SYNTHESIS_SCHEMA:
            raise ValueError("decision synthesis record is invalid")
        return record

    def blocked_clauses(self) -> list[dict]:
        return [item for item in self.active_clauses()
                if item.get("status") in {"ambiguous", "conflicted", "blocked_on_user", "missing_input"}]

    def blocked_clauses_for(self, frame: dict) -> list[dict]:
        applicable = set(frame.get("intent_clause_ids", []))
        return [item for item in self.blocked_clauses() if item["id"] in applicable]

    def descent_policy(self) -> dict:
        """Return a validated, backward-compatible convergence policy."""
        stored = self.data.get("descent_policy", {})
        if not isinstance(stored, dict):
            raise ValueError("descent_policy must be an object")
        policy = dict(DEFAULT_DESCENT_POLICY)
        policy.update({key: stored[key] for key in DEFAULT_DESCENT_POLICY if key in stored})
        for key in ("max_calls_per_frame", "max_depth", "max_frames"):
            value = policy[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"descent_policy.{key} must be a non-negative integer")
        if policy["max_frames"] < 1:
            raise ValueError("descent_policy.max_frames must be at least one")
        for key in ("score_margin", "return_revisit_confidence"):
            try:
                value = float(policy[key])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"descent_policy.{key} must be numeric") from exc
            if value < 0:
                raise ValueError(f"descent_policy.{key} must be non-negative")
            policy[key] = value
        return policy

    def frame_depth(self, frame_id: str, seen: set[str] | None = None) -> int:
        """Return the longest known derivation depth for a frame.

        ``depth`` is persisted on newly-created frames. The edge fallback keeps
        snapshots made before this field was added usable, and using the longest
        parent path is conservative when an equivalent child is merged into the
        DAG from multiple parents.
        """
        frame = self.data["frames"][frame_id]
        depth = frame.get("depth")
        if isinstance(depth, int) and not isinstance(depth, bool) and depth >= 0:
            return depth
        seen = set() if seen is None else set(seen)
        if frame_id in seen:
            raise ValueError("frame derivation graph contains a cycle")
        seen.add(frame_id)
        parent_gaps = [edge["from"] for edge in self.data["derivation_edges"]
                       if edge.get("kind") == "expands_to" and edge.get("to") == frame_id
                       and edge.get("from") in self.data["gaps"]]
        if not parent_gaps:
            return 0
        return max(self.frame_depth(self.data["gaps"][gap_id]["frame_id"], seen) + 1
                   for gap_id in parent_gaps)

    def convergence_budget(self, frame_id: str) -> dict:
        """Expose the current bounded-descent capacity without mutating state."""
        policy = self.descent_policy()
        frame = self.data["frames"][frame_id]
        calls = int(frame.get("descent", {}).get("calls", 0))
        depth = self.frame_depth(frame_id)
        used = len(self.data["frames"])
        return {
            "frame_depth": depth,
            "max_depth": policy["max_depth"],
            "remaining_depth": max(0, policy["max_depth"] - depth),
            "calls_used": calls,
            "max_calls_per_frame": policy["max_calls_per_frame"],
            "remaining_calls": max(0, policy["max_calls_per_frame"] - calls),
            "frames_used": used,
            "max_frames": policy["max_frames"],
            "remaining_new_frames": max(0, policy["max_frames"] - used),
        }

    def _outgoing(self, node_id: str) -> list[str]:
        return [edge["to"] for edge in self.data["derivation_edges"] if edge["from"] == node_id]

    def _reaches(self, start: str, target: str) -> bool:
        todo, seen = [start], set()
        while todo:
            current = todo.pop()
            if current == target:
                return True
            if current in seen:
                continue
            seen.add(current)
            todo.extend(self._outgoing(current))
        return False

    def edge(self, source: str, target: str, kind: str) -> None:
        if source == target or self._reaches(target, source):
            raise ValueError(f"derivation edge would create a cycle: {source} -> {target}")
        self.data["derivation_edges"].append({"from": source, "to": target, "kind": kind})

    def relation(self, source: str, target: str, kind: str, note: str = "") -> None:
        self.data["relations"].append({"from": source, "to": target, "kind": kind, "note": note})

    def effective_clause_ids(self, proposal: dict, parent_gap: str | None = None) -> list[str]:
        if "intent_clause_ids" in proposal:
            clause_ids = proposal["intent_clause_ids"]
        elif parent_gap:
            parent_frame = self.data["frames"][self.data["gaps"][parent_gap]["frame_id"]]
            clause_ids = parent_frame["intent_clause_ids"]
        else:
            clause_ids = [item["id"] for item in self.active_clauses()]
        if not isinstance(clause_ids, list) or not all(isinstance(item, str) for item in clause_ids):
            raise ValueError("intent_clause_ids must be a list of clause ids")
        unknown = set(clause_ids) - self.active_clause_ids()
        if unknown:
            raise ValueError(f"unknown intent clause ids: {', '.join(sorted(unknown))}")
        return list(dict.fromkeys(clause_ids))

    def frame_key(self, proposal: dict, clause_ids: list[str]) -> str:
        payload = {
            "focus": proposal.get("focus", "").strip().lower(),
            "information_gap": proposal.get("information_gap", "").strip(),
            "discriminator": proposal.get("discriminator", "").strip(),
            "scope": proposal.get("scope", ""),
            "temporal_scope": proposal.get("temporal_scope"),
            "expected_update": proposal.get("expected_update", ""),
            "evidence_requirement": proposal.get("evidence_requirement", ""),
            "intent_clause_ids": sorted(clause_ids),
            "contract_ref": proposal.get("contract_ref"),
            "deliverable_ids": sorted(proposal.get("deliverable_ids", [])),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def add_frame(self, proposal: dict, parent_gap: str | None = None) -> tuple[str, bool]:
        proposal = dict(proposal)
        required = ("focus", "information_gap", "discriminator", "expected_update", "evidence_requirement")
        missing = [field for field in required if not str(proposal.get(field, "")).strip()]
        if missing:
            raise ValueError(f"frame proposal missing: {', '.join(missing)}")
        clause_ids = self.effective_clause_ids(proposal, parent_gap)
        contract_ref = proposal.get("contract_ref")
        if contract_ref is not None and (not isinstance(contract_ref, str) or not _CONTRACT_ID.fullmatch(contract_ref)):
            raise ValueError("frame contract_ref is invalid")
        deliverable_ids = proposal.get("deliverable_ids", [])
        if not isinstance(deliverable_ids, list) or not all(
            isinstance(item, str) and _CONTRACT_ID.fullmatch(item) for item in deliverable_ids
        ):
            raise ValueError("frame deliverable_ids must be a bounded list of contract ids")
        if len(deliverable_ids) > MAX_INTENT_DELIVERABLES:
            raise ValueError("frame deliverable_ids exceeds the contract limit")
        proposal["deliverable_ids"] = list(dict.fromkeys(deliverable_ids))
        child_depth = 0
        parent_frame = None
        if parent_gap:
            parent_frame_id = self.data["gaps"][parent_gap]["frame_id"]
            parent_frame = self.data["frames"][parent_frame_id]
            child_depth = self.frame_depth(parent_frame_id) + 1
            if child_depth > self.descent_policy()["max_depth"]:
                raise ValueError("recursive depth budget exhausted; leave the gap deferred or return a bounded result")
        if "temporal_scope" in proposal:
            resolved_temporal_scope = _normalise_temporal_scope(proposal["temporal_scope"])
            if parent_frame and parent_frame.get("temporal_scope") and resolved_temporal_scope is None:
                raise ValueError("a child frame cannot remove its parent temporal_scope")
        elif parent_frame:
            resolved_temporal_scope = parent_frame.get("temporal_scope")
        else:
            resolved_temporal_scope = None
        proposal["temporal_scope"] = resolved_temporal_scope
        key = self.frame_key(proposal, clause_ids)
        for existing_id, existing in self.data["frames"].items():
            if existing["canonical_key"] == key:
                if parent_gap:
                    self.relation(parent_gap, existing_id, "reuses", "equivalent frame")
                return existing_id, False
        if len(self.data["frames"]) >= self.descent_policy()["max_frames"]:
            raise ValueError("global frame budget exhausted; defer the gap or merge an equivalent frame")
        frame_id = self.new_id("f")
        inherited = list(proposal.get("constraint_env", []))
        if parent_gap:
            inherited = list(dict.fromkeys(parent_frame.get("constraint_env", []) + inherited))
        frame = {
            "id": frame_id, "type": "frame", "created_at": now_iso(),
            "intent_version": self.data["current_intent_version"],
            "focus": proposal["focus"], "information_gap": proposal["information_gap"],
            "discriminator": proposal["discriminator"], "expected_update": proposal["expected_update"],
            "evidence_requirement": proposal["evidence_requirement"],
            "intent_clause_ids": clause_ids,
            "contract_ref": contract_ref,
            "deliverable_ids": proposal["deliverable_ids"],
            "trigger_cognition_ids": proposal.get("trigger_cognition_ids", []),
            "constraint_env": inherited,
            "temporal_scope": proposal.get("temporal_scope"),
            "priority": float(proposal.get("priority", 0.5)),
            "state": "open", "query_plan": [], "evidence_ids": [],
            "cognition_ids": [], "gap_ids": [], "return": None,
            "collection": None,
            "review": {"expected_roles": [], "completed_roles": []},
            "descent": {"active_child_id": None, "returned_child_ids": [], "calls": 0},
            "depth": child_depth, "parent_gap_id": parent_gap,
            "canonical_key": key,
        }
        self.data["frames"][frame_id] = frame
        if parent_gap:
            self.edge(parent_gap, frame_id, "expands_to")
        self.event("frame_created", frame_id=frame_id, parent_gap=parent_gap, focus=frame["focus"])
        return frame_id, True

    @staticmethod
    def _material_path(value: object) -> str:
        if not isinstance(value, str) or not value.strip() or "\x00" in value:
            raise ValueError("material path must be a non-empty workspace-relative path")
        root = workspace().resolve()
        candidate = (workspace() / value).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError("material path must stay inside the research workspace") from exc
        if not candidate.is_file():
            raise FileNotFoundError("material path must reference an existing file")
        if candidate.stat().st_size > MAX_MATERIAL_BYTES:
            raise ValueError(f"material exceeds {MAX_MATERIAL_BYTES} byte limit")
        return str(candidate.relative_to(root)).replace("\\", "/")

    @classmethod
    def _registered_materials(cls, values: list) -> dict[str, dict]:
        if not isinstance(values, list) or len(values) > MAX_INTENT_MATERIALS:
            raise ValueError("materials must be a bounded list")
        registered = {}
        for index, raw in enumerate(values):
            if not isinstance(raw, dict):
                raise ValueError("material entries must be objects")
            material_id = raw.get("material_id", raw.get("id", f"material-{index + 1}"))
            if not isinstance(material_id, str) or not _CONTRACT_ID.fullmatch(material_id) or material_id in registered:
                raise ValueError("material requires a unique material_id")
            local_path = cls._material_path(raw.get("path"))
            target = workspace() / local_path
            description = _short_text(raw.get("description", material_id), "material description", 2048)
            registered[material_id] = {
                "material_id": material_id,
                "local_path": local_path,
                "sha256": _sha256_file(target),
                "byte_count": target.stat().st_size,
                "description": description,
                "media_type": str(raw.get("media_type", target.suffix.lower().lstrip(".") or "unknown"))[:64],
                "text_extractable": target.suffix.lower() in _TEXTUAL_MATERIAL_SUFFIXES,
                "registered_at": now_iso(),
            }
        return registered

    def register_material(self, proposal: dict, replace: bool = False) -> dict:
        """Add a hash-bound user file while requirements are still negotiable."""

        contract = self.intent_contract()
        if contract.get("status") not in {"pending", "needs_clarification"}:
            raise ValueError("materials can be registered only before the intent contract is ready")
        registered = self._registered_materials([proposal])
        material_id, record = next(iter(registered.items()))
        existing = self.data.setdefault("materials", {}).get(material_id)
        if existing is not None and not replace:
            raise ValueError("material is already registered; use replace to register a revised file")
        self.data["materials"][material_id] = record
        self.event("material_registered", material_id=material_id, replace=bool(existing),
                   sha256=record["sha256"], byte_count=record["byte_count"])
        return {"material_id": material_id, "replaced": bool(existing), "material": record}

    def _normalise_intent_contract(self, proposal: dict) -> dict:
        if not isinstance(proposal, dict):
            raise ValueError("intent contract must be an object")
        status = proposal.get("status")
        if status not in {"ready", "needs_clarification"}:
            raise ValueError("intent contract status must be ready or needs_clarification")
        summary = _short_text(proposal.get("summary"), "intent contract summary", 4096)
        deliverables = proposal.get("deliverables")
        if not isinstance(deliverables, list) or not 1 <= len(deliverables) <= MAX_INTENT_DELIVERABLES:
            raise ValueError("intent contract requires one or more bounded deliverables")
        normalized_deliverables = []
        requested_frame_refs: dict[str, object] = {}
        requested_dependencies: dict[str, object] = {}
        seen_deliverables = set()
        for index, item in enumerate(deliverables):
            if not isinstance(item, dict):
                raise ValueError("intent contract deliverables must be objects")
            deliverable_id = item.get("id", f"deliverable-{index + 1}")
            kind = item.get("kind")
            if (not isinstance(deliverable_id, str) or not _CONTRACT_ID.fullmatch(deliverable_id)
                    or deliverable_id in seen_deliverables):
                raise ValueError("intent contract deliverables require unique ids")
            if not isinstance(kind, str) or not _DELIVERABLE_KIND.fullmatch(kind):
                raise ValueError("intent contract deliverable kind is invalid")
            seen_deliverables.add(deliverable_id)
            requested_frame_refs[deliverable_id] = item.get("research_frame_refs")
            requested_dependencies[deliverable_id] = item.get("depends_on_deliverable_ids")
            normalized_deliverables.append({
                "id": deliverable_id,
                "kind": kind,
                "description": _short_text(item.get("description"), "intent contract deliverable description", 4096),
                "required": bool(item.get("required", True)),
                "requires_research": bool(item.get("requires_research", kind in {"research_report", "experiment_plan", "design_plan"})),
                "requires_material_analysis": bool(item.get("requires_material_analysis", kind in {"material_analysis", "experiment_plan", "design_plan"})),
                "requires_design": bool(item.get("requires_design", kind in {"experiment_plan", "design_plan", "implementation_plan"})),
                "research_frame_refs": [],
                "depends_on_deliverable_ids": [],
            })

        material_uses = proposal.get("user_materials", [])
        if not isinstance(material_uses, list) or len(material_uses) > MAX_INTENT_MATERIALS:
            raise ValueError("intent contract user_materials must be a bounded list")
        normalized_materials = []
        seen_materials = set()
        registered = self.data.get("materials", {})
        for item in material_uses:
            if not isinstance(item, dict):
                raise ValueError("intent contract user_materials entries must be objects")
            material_id = item.get("material_id", item.get("id"))
            material_status = item.get("status")
            if (not isinstance(material_id, str) or not _CONTRACT_ID.fullmatch(material_id)
                    or material_id in seen_materials):
                raise ValueError("intent contract user_materials require unique material ids")
            if material_status not in {"provided", "missing", "optional"}:
                raise ValueError("intent contract material status is invalid")
            if material_status == "provided" and material_id not in registered:
                raise ValueError("a provided contract material must be registered in the workspace")
            seen_materials.add(material_id)
            entry = {
                "material_id": material_id,
                "status": material_status,
                "description": _short_text(item.get("description"), "intent contract material description", 2048),
                "intended_use": _short_text(item.get("intended_use", "inform the requested deliverables"), "intent contract material intended_use", 2048),
                "required": bool(item.get("required", material_status != "optional")),
            }
            if material_id in registered:
                entry["registered"] = {key: registered[material_id][key] for key in ("local_path", "sha256", "byte_count", "media_type")}
            normalized_materials.append(entry)

        questions = proposal.get("clarifying_questions", [])
        if not isinstance(questions, list) or len(questions) > MAX_INTENT_QUESTIONS:
            raise ValueError("intent contract clarifying_questions must be a bounded list")
        normalized_questions = []
        seen_questions = set()
        for index, item in enumerate(questions):
            if not isinstance(item, dict):
                raise ValueError("intent contract clarifying questions must be objects")
            question_id = item.get("id", f"question-{index + 1}")
            if not isinstance(question_id, str) or not _CONTRACT_ID.fullmatch(question_id) or question_id in seen_questions:
                raise ValueError("intent contract clarifying questions require unique ids")
            seen_questions.add(question_id)
            normalized_questions.append({
                "id": question_id,
                "question": _short_text(item.get("question"), "intent contract question", 2048),
                "why": _short_text(item.get("why"), "intent contract question rationale", 2048),
                "blocking": bool(item.get("blocking", True)),
            })
        if status == "needs_clarification" and not any(item["blocking"] for item in normalized_questions):
            raise ValueError("needs_clarification requires at least one blocking question")
        if status == "ready" and any(item["blocking"] for item in normalized_questions):
            raise ValueError("a ready intent contract cannot retain blocking questions")

        frames = proposal.get("research_frames", [])
        if not isinstance(frames, list) or len(frames) > MAX_INTENT_FRAMES or not all(isinstance(item, dict) for item in frames):
            raise ValueError("intent contract research_frames must be a bounded list of objects")
        normalized_frames = []
        seen_frame_refs = set()
        for index, frame in enumerate(frames):
            normalized_frame = dict(frame)
            frame_ref = normalized_frame.get("contract_ref", normalized_frame.get("ref", f"research-frame-{index + 1}"))
            if not isinstance(frame_ref, str) or not _CONTRACT_ID.fullmatch(frame_ref) or frame_ref in seen_frame_refs:
                raise ValueError("intent contract research_frames require unique contract_ref values")
            seen_frame_refs.add(frame_ref)
            normalized_frame["contract_ref"] = frame_ref
            normalized_frame.pop("ref", None)
            normalized_frames.append(normalized_frame)
        for deliverable in normalized_deliverables:
            requested = requested_frame_refs[deliverable["id"]]
            if requested is None:
                refs = list(seen_frame_refs) if deliverable["requires_research"] else []
            else:
                if not isinstance(requested, list) or not all(
                    isinstance(item, str) and _CONTRACT_ID.fullmatch(item) for item in requested
                ):
                    raise ValueError("deliverable research_frame_refs must be a list of contract refs")
                refs = list(dict.fromkeys(requested))
            unknown_refs = set(refs) - seen_frame_refs
            if unknown_refs:
                raise ValueError("deliverable research_frame_refs includes an unknown research frame")
            if status == "ready" and deliverable["required"] and deliverable["requires_research"] and not refs:
                raise ValueError("a required research deliverable requires one or more declared research frames")
            deliverable["research_frame_refs"] = sorted(refs)

        deliverables_by_id = {item["id"]: item for item in normalized_deliverables}
        dependencies_by_id: dict[str, list[str]] = {}
        for deliverable in normalized_deliverables:
            deliverable_id = deliverable["id"]
            requested = requested_dependencies[deliverable_id]
            if requested is None:
                # A design that needs material analysis has an executable
                # prerequisite by default. This makes the analysis an input to
                # the design task rather than a parallel optional summary.
                dependencies = [
                    candidate["id"] for candidate in normalized_deliverables
                    if candidate["id"] != deliverable_id
                    and candidate["kind"] == "material_analysis"
                    and candidate["required"]
                    and deliverable["requires_material_analysis"]
                    and deliverable["kind"] != "material_analysis"
                ]
            else:
                if not isinstance(requested, list) or not all(
                    isinstance(item, str) and _CONTRACT_ID.fullmatch(item) for item in requested
                ):
                    raise ValueError("deliverable depends_on_deliverable_ids must be a list of deliverable ids")
                dependencies = list(dict.fromkeys(requested))
            unknown_dependencies = set(dependencies) - set(deliverables_by_id)
            if unknown_dependencies:
                raise ValueError("deliverable depends_on_deliverable_ids includes an unknown deliverable")
            if deliverable_id in dependencies:
                raise ValueError("deliverable cannot depend on itself")
            dependencies_by_id[deliverable_id] = sorted(dependencies)
            deliverable["depends_on_deliverable_ids"] = sorted(dependencies)

        visited_dependencies, visiting_dependencies = set(), set()

        def visit_deliverable(deliverable_id: str) -> None:
            if deliverable_id in visiting_dependencies:
                raise ValueError("intent contract deliverable dependencies contain a cycle")
            if deliverable_id in visited_dependencies:
                return
            visiting_dependencies.add(deliverable_id)
            for dependency_id in dependencies_by_id[deliverable_id]:
                visit_deliverable(dependency_id)
            visiting_dependencies.remove(deliverable_id)
            visited_dependencies.add(deliverable_id)

        for deliverable_id in sorted(dependencies_by_id):
            visit_deliverable(deliverable_id)

        decision_questions = proposal.get("decision_questions", [])
        if decision_questions is None:
            decision_questions = []
        if not isinstance(decision_questions, list) or len(decision_questions) > MAX_DECISION_QUESTIONS:
            raise ValueError("intent contract decision_questions must be a bounded list")
        normalized_decision_questions = []
        seen_decision_questions = set()
        for index, item in enumerate(decision_questions):
            if not isinstance(item, dict):
                raise ValueError("intent contract decision_questions entries must be objects")
            question_id = item.get("id", f"decision-{index + 1}")
            if (
                not isinstance(question_id, str)
                or not _CONTRACT_ID.fullmatch(question_id)
                or question_id in seen_decision_questions
            ):
                raise ValueError("intent contract decision_questions require unique ids")
            impact = item.get("impact", "high")
            if impact not in _DECISION_IMPACTS:
                raise ValueError("intent contract decision question impact is invalid")
            requested_deliverables = item.get("deliverable_ids", [])
            if requested_deliverables is None:
                requested_deliverables = []
            if not isinstance(requested_deliverables, list) or not all(
                isinstance(value, str) and _CONTRACT_ID.fullmatch(value) for value in requested_deliverables
            ):
                raise ValueError("intent contract decision question deliverable_ids must be a list of deliverable ids")
            deliverable_ids = list(dict.fromkeys(requested_deliverables))
            unknown_deliverables = set(deliverable_ids) - set(deliverables_by_id)
            if unknown_deliverables:
                raise ValueError("intent contract decision question references an unknown deliverable")
            seen_decision_questions.add(question_id)
            normalized_decision_questions.append({
                "id": question_id,
                "question": _short_text(item.get("question"), "intent contract decision question", 4096),
                "why_it_matters": _short_text(
                    item.get("why_it_matters", item.get("why", "affects the requested decision")),
                    "intent contract decision question rationale", 2048,
                ),
                "impact": impact,
                "deliverable_ids": deliverable_ids,
            })
        for frame in normalized_frames:
            frame["deliverable_ids"] = sorted(
                deliverable["id"] for deliverable in normalized_deliverables
                if frame["contract_ref"] in deliverable["research_frame_refs"]
            )
        requires_material_analysis = any(
            item["required"] and item["requires_material_analysis"] for item in normalized_deliverables
        )
        supplied_materials = [item for item in normalized_materials if item["status"] == "provided"]
        required_missing_materials = [item for item in normalized_materials if item["status"] == "missing" and item["required"]]
        if status == "ready" and required_missing_materials:
            raise ValueError("a ready intent contract cannot retain missing required material")
        if status == "ready" and requires_material_analysis and not supplied_materials:
            raise ValueError("a material-analysis deliverable requires at least one provided material")
        if status == "ready" and requires_material_analysis:
            non_textual = [
                item["material_id"] for item in normalized_materials
                if item["status"] == "provided" and item["required"]
                and not bool(registered.get(item["material_id"], {}).get(
                    "text_extractable",
                    Path(registered.get(item["material_id"], {}).get("local_path", "")).suffix.lower()
                    in _TEXTUAL_MATERIAL_SUFFIXES,
                ))
            ]
            if non_textual:
                raise ValueError("a required material-analysis deliverable needs text-extractable material or an explicit extraction step")
        return {
            "summary": summary,
            "deliverables": normalized_deliverables,
            "research_questions": _bounded_text_list(proposal.get("research_questions"), "intent contract research_questions"),
            "decision_questions": normalized_decision_questions,
            "design_requirements": _bounded_text_list(proposal.get("design_requirements"), "intent contract design_requirements"),
            "writing_requirements": _bounded_text_list(proposal.get("writing_requirements"), "intent contract writing_requirements"),
            "acceptance_criteria": _bounded_text_list(proposal.get("acceptance_criteria"), "intent contract acceptance_criteria"),
            "assumptions": _bounded_text_list(proposal.get("assumptions"), "intent contract assumptions"),
            "other_constraints": _bounded_text_list(proposal.get("other_constraints"), "intent contract other_constraints"),
            "user_materials": normalized_materials,
            "clarifying_questions": normalized_questions,
            "research_frames": normalized_frames,
        }

    def analyze_intent(self, proposal: dict) -> dict:
        """Record an analyst's requirements contract before any search frame exists."""

        current = self.intent_contract()
        if current.get("legacy"):
            raise ValueError("legacy research state cannot add an intent contract")
        if self.data["frames"]:
            raise ValueError("cannot replace the intent contract after research frames exist; create a revised research run")
        normalized = self._normalise_intent_contract(proposal)
        status = proposal["status"]
        version = int(current.get("version", 0)) + 1
        record = {
            "schema": INTENT_CONTRACT_SCHEMA, "status": status, "version": version,
            "contract": normalized, "questions": normalized["clarifying_questions"],
            "answers": dict(current.get("answers", {})), "created_at": current.get("created_at", now_iso()),
            "updated_at": now_iso(),
        }
        self.data["intent_contract"] = record
        self.data["decision_synthesis"] = {
            "schema": DECISION_SYNTHESIS_SCHEMA,
            "status": "pending" if normalized["decision_questions"] else "not_required",
            "synthesis": None,
            "sha256": None,
            "updated_at": now_iso(),
        }
        created_frames = []
        if status == "ready":
            for frame_proposal in normalized["research_frames"]:
                frame_id, created = self.add_frame(frame_proposal)
                if created:
                    created_frames.append(frame_id)
        self.event("intent_contract_recorded", status=status, version=version,
                   created_frame_ids=created_frames, question_ids=[item["id"] for item in record["questions"]])
        return {"status": status, "version": version, "created_frame_ids": created_frames,
                "questions": record["questions"]}

    def answer_intent_questions(self, answers: dict) -> dict:
        current = self.intent_contract()
        if current.get("status") != "needs_clarification":
            raise ValueError("intent questions can be answered only while clarification is required")
        if not isinstance(answers, dict) or not answers:
            raise ValueError("intent answers must be a non-empty object")
        known = {item["id"] for item in current.get("questions", [])}
        if not set(answers).issubset(known):
            raise ValueError("intent answers include an unknown question")
        normalized = {key: _short_text(value, "intent answer", 4096) for key, value in answers.items()}
        merged = dict(current.get("answers", {}))
        merged.update(normalized)
        current["answers"] = merged
        unanswered = sorted(known - set(merged))
        current["status"] = "needs_clarification" if unanswered else "pending"
        current["updated_at"] = now_iso()
        self.event("intent_questions_answered", question_ids=sorted(normalized))
        return {"status": current["status"], "answered_question_ids": sorted(normalized),
                "unanswered_question_ids": unanswered}

    def bootstrap(self, proposals: list) -> dict:
        self.require_intent_ready()
        if not isinstance(proposals, list) or not proposals:
            raise ValueError("bootstrap requires one or more frame proposals")
        return {"frame_ids": [self.add_frame(item)[0] for item in proposals]}

    def material_audit(self) -> dict:
        issues = []
        for material_id, record in self.data.get("materials", {}).items():
            try:
                local_path = self._material_path(record.get("local_path"))
                target = workspace() / local_path
                if _sha256_file(target) != record.get("sha256"):
                    issues.append({"material_id": material_id, "issue": "material content hash changed"})
            except (OSError, ValueError, FileNotFoundError) as exc:
                issues.append({"material_id": material_id, "issue": str(exc)})
        return {"ok": not issues, "issues": issues}

    def set_clause(self, clause_id: str, status: str, interpretation: str = "") -> dict:
        allowed = {"enforced", "ambiguous", "conflicted", "blocked_on_user", "missing_input", "assumed"}
        if status not in allowed:
            raise ValueError("invalid clause status")
        intent = self.current_intent()
        clauses = [dict(item) for item in intent["clauses"]]
        found = False
        for clause in clauses:
            if clause["id"] == clause_id:
                clause["status"] = status
                if interpretation:
                    clause["interpretation"] = interpretation
                found = True
        if not found:
            raise ValueError(f"unknown clause: {clause_id}")
        version = max(item["version"] for item in self.data["intent_versions"]) + 1
        self.data["intent_versions"].append({"version": version, "raw": intent["raw"],
                                              "created_at": now_iso(), "clauses": clauses})
        self.data["current_intent_version"] = version
        self.event("intent_revised", clause_id=clause_id, status=status, version=version)
        return {"intent_version": version, "clause_id": clause_id, "status": status}

    def formulate(self, frame_id: str, plan: list) -> dict:
        self.require_intent_ready()
        frame = self.data["frames"][frame_id]
        if frame["state"] != "open":
            raise ValueError("only open frames can be formulated")
        if self.blocked_clauses_for(frame):
            raise ValueError("cannot formulate a frame blocked by unresolved intent clauses")
        if not isinstance(plan, list) or not plan or len(plan) > MAX_QUERY_PLAN_ITEMS:
            raise ValueError(f"query plan must contain 1-{MAX_QUERY_PLAN_ITEMS} items")
        if not all(isinstance(item, dict) and isinstance(item.get("query"), str) and item["query"].strip() for item in plan):
            raise ValueError("query plan requires non-empty objects with string query")
        frame["query_plan"] = plan
        frame["collection"] = None
        frame["aggregation"] = {
            "status": "pending", "path": None, "sha256": None,
            "source_manifest_sha256": None, "summary": None, "clusters": [],
        }
        frame["review"] = {"expected_roles": [], "completed_roles": []}
        frame["state"] = "acquiring"
        self.event("query_formulated", frame_id=frame_id, queries=[item["query"] for item in plan])
        return {"frame_id": frame_id, "state": frame["state"]}

    def collection_ready(self, frame_id: str, collection: dict) -> dict:
        """Open the saved-source aggregation barrier after coordinator collection.

        Search discovery and source capture happen outside the semantic DAG, but
        their immutable records must exist before a review worker can be
        scheduled.  This transition is coordinator-only; worker commands never
        get an operation that can invoke it.
        """

        frame = self.data["frames"][frame_id]
        if frame["state"] != "acquiring":
            raise ValueError("collection can be marked ready only while acquiring")
        if not isinstance(collection, dict):
            raise ValueError("collection must be an object")
        request_sha256 = collection.get("request_sha256")
        if not isinstance(request_sha256, str) or not _REQUEST_SHA256.fullmatch(request_sha256):
            raise ValueError("collection request_sha256 must be a SHA-256 digest")
        discovery_path = self._saved_collection_path(collection.get("discovery_path"), "discovery")
        source_manifest_path = self._saved_collection_path(collection.get("source_manifest_path"), "sources")
        review_roles = collection.get("review_roles")
        if not isinstance(review_roles, list) or len(review_roles) != len(set(review_roles)):
            raise ValueError("collection review_roles must be a unique list")
        if set(review_roles) != _REVIEW_ROLES:
            raise ValueError("collection review_roles must include the required source reviewers")
        summary = self._collection_summary(collection.get("summary"))
        manifest_file = workspace() / source_manifest_path
        try:
            manifest_payload = json.loads(manifest_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("collection source manifest is unreadable") from exc
        if not isinstance(manifest_payload, dict) or self._collection_summary(manifest_payload.get("summary")) != summary:
            raise ValueError("collection summary must match the saved source manifest")
        manifest_sha256 = _sha256_file(manifest_file)
        # Validate the manifest before opening the aggregation stage. This
        # prevents a coordinator from binding an arbitrary on-disk file after
        # collection has been declared complete.
        self._reviewable_source_records({
            "id": frame_id,
            "collection": {
                "source_manifest_path": source_manifest_path,
                "request_sha256": request_sha256,
                "source_manifest_sha256": manifest_sha256,
            },
        })
        frame["collection"] = {
            "discovery_path": discovery_path,
            "source_manifest_path": source_manifest_path,
            "request_sha256": request_sha256,
            "source_manifest_sha256": manifest_sha256,
            "summary": summary,
        }
        frame["aggregation"] = {
            "status": "pending", "path": None, "sha256": None,
            "source_manifest_sha256": manifest_sha256, "summary": None, "clusters": [],
        }
        frame["review"] = {"expected_roles": list(review_roles), "completed_roles": []}
        frame["state"] = "aggregating"
        self.event("collection_ready", frame_id=frame_id, request_sha256=request_sha256,
                   discovery_path=discovery_path, source_manifest_path=source_manifest_path,
                   source_manifest_sha256=manifest_sha256, review_roles=review_roles, summary=summary)
        return {"frame_id": frame_id, "state": frame["state"], "review_roles": list(review_roles),
                "aggregation": frame["aggregation"],
                "collection": frame["collection"]}

    @staticmethod
    def _saved_collection_path(value: object, directory: str) -> str:
        if not isinstance(value, str) or not value or "\x00" in value:
            raise ValueError(f"collection {directory} path must be a non-empty relative path")
        root = (workspace() / "research_drift" / directory).resolve()
        candidate = (workspace() / value).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"collection {directory} path must stay inside research_drift/{directory}") from exc
        if not candidate.is_file():
            raise ValueError(f"collection {directory} record must already exist")
        return str(candidate.relative_to(workspace().resolve())).replace("\\", "/")

    @staticmethod
    def _collection_summary(value: object) -> dict:
        if not isinstance(value, dict):
            raise ValueError("collection summary must be an object")
        required = ("candidate_count", "capture_limit", "captured_count", "failed_count", "deferred_count")
        summary = {}
        for key in required:
            amount = value.get(key)
            if isinstance(amount, bool) or not isinstance(amount, int) or not 0 <= amount <= 1_000_000:
                raise ValueError(f"collection summary {key} must be a bounded non-negative integer")
            summary[key] = amount
        if summary["captured_count"] + summary["failed_count"] + summary["deferred_count"] != summary["candidate_count"]:
            raise ValueError("collection summary counts must equal candidate_count")
        if "origin_coverage" in value:
            coverage = value["origin_coverage"]
            expected = {"candidate_origins", "captured_origins", "failed_origins", "deferred_origins", "capture_transports"}
            if not isinstance(coverage, dict) or set(coverage) != expected:
                raise ValueError("collection origin_coverage has an invalid shape")
            normalized_coverage = {}
            for key in sorted(expected):
                counts = coverage[key]
                if not isinstance(counts, dict) or len(counts) > 64:
                    raise ValueError("collection origin_coverage counts must be bounded objects")
                normalized_counts = {}
                for provider, amount in counts.items():
                    if (
                        not isinstance(provider, str) or not _PROVIDER_LABEL.fullmatch(provider)
                        or isinstance(amount, bool) or not isinstance(amount, int) or amount < 0
                    ):
                        raise ValueError("collection origin_coverage contains an invalid provider count")
                    normalized_counts[provider] = amount
                normalized_coverage[key] = dict(sorted(normalized_counts.items()))
            candidates = set(normalized_coverage["candidate_origins"])
            if not (
                set(normalized_coverage["captured_origins"]).issubset(candidates)
                and set(normalized_coverage["failed_origins"]).issubset(candidates)
                and set(normalized_coverage["deferred_origins"]).issubset(candidates)
            ):
                raise ValueError("collection origin_coverage outcome providers must be candidate origins")
            summary["origin_coverage"] = normalized_coverage
        return summary

    def aggregate_sources(self, frame_id: str, clusters: list, source_manifest_sha256: str) -> dict:
        """Persist a hash-bound semantic aggregation before source review.

        Every captured page has exactly one primary topic assessment, while a
        long source may also be associated with other topics.  This avoids the
        false choice between duplicate suppression and losing a cross-cutting
        or contradictory source.  The agent supplies reasoned rubric
        components; score values are calculated here deterministically.
        """

        frame = self.data["frames"][frame_id]
        if frame["state"] != "aggregating":
            raise ValueError("source aggregation requires an aggregating frame after saved-source collection")
        aggregation = frame.get("aggregation", {})
        if aggregation.get("status") == "complete":
            raise ValueError("source aggregation is already complete for this collection")
        expected_manifest_sha = frame.get("collection", {}).get("source_manifest_sha256")
        if not isinstance(source_manifest_sha256, str) or source_manifest_sha256 != expected_manifest_sha:
            raise ValueError("source aggregation must bind the current source manifest sha256")
        if not isinstance(clusters, list) or len(clusters) > MAX_TOPIC_CLUSTERS:
            raise ValueError(f"source aggregation requires at most {MAX_TOPIC_CLUSTERS} topic clusters")
        sources = self._reviewable_source_records(frame)
        if not sources and clusters:
            raise ValueError("empty saved collection cannot contain topic clusters")
        if sources and not clusters:
            raise ValueError("every captured source requires a primary topic assessment")

        primary_assignments: dict[str, str] = {}
        seen_keys = set()
        normalized_clusters = []
        for proposal in clusters:
            if not isinstance(proposal, dict):
                raise ValueError("topic clusters must contain objects")
            topic_key = proposal.get("topic_key")
            if not isinstance(topic_key, str) or not _TOPIC_KEY.fullmatch(topic_key) or topic_key in seen_keys:
                raise ValueError("topic cluster requires a unique topic_key")
            seen_keys.add(topic_key)
            topic = _short_text(proposal.get("topic"), "topic cluster topic", 1024)
            context_signature = _short_text(proposal.get("context_signature"), "topic cluster context_signature", 1024)
            dedup_rationale = _short_text(proposal.get("dedup_rationale"), "topic cluster dedup_rationale")
            confidence_components, confidence_score = _score_components(
                proposal.get("confidence_components"), "topic cluster confidence_components",
                _TOPIC_CONFIDENCE_COMPONENTS, _TOPIC_CONFIDENCE_WEIGHTS,
            )
            confidence_rationale = _short_text(proposal.get("confidence_rationale"), "topic cluster confidence_rationale")

            raw_sources = proposal.get("sources")
            if not isinstance(raw_sources, list) or not raw_sources:
                raise ValueError("topic cluster requires one or more scored sources")
            normalized_sources = []
            source_paths = set()
            for source in raw_sources:
                if not isinstance(source, dict):
                    raise ValueError("topic cluster sources must contain objects")
                local_path = source.get("local_path")
                if not isinstance(local_path, str) or local_path not in sources:
                    raise ValueError("topic cluster can contain only captured source paths from this collection")
                if local_path in source_paths:
                    raise ValueError("a topic cluster must not repeat a source")
                source_paths.add(local_path)
                source_record = sources[local_path]
                supplied_hash = source.get("content_sha256")
                if not isinstance(supplied_hash, str) or supplied_hash != source_record["content_sha256"]:
                    raise ValueError("topic source content_sha256 must match the saved page and manifest")
                relation = source.get("relation")
                if relation not in _SOURCE_RELATIONS:
                    raise ValueError("topic source relation is invalid")
                primary = source.get("primary")
                if not isinstance(primary, bool):
                    raise ValueError("topic source primary must be a boolean")
                if primary:
                    if local_path in primary_assignments:
                        raise ValueError("a captured source can have only one primary topic assessment")
                    primary_assignments[local_path] = topic_key
                quality_components, quality_score = _score_components(
                    source.get("quality_components"), "topic source quality_components",
                    _QUALITY_COMPONENTS, _QUALITY_WEIGHTS,
                )
                normalized_sources.append({
                    "local_path": local_path,
                    "content_sha256": source_record["content_sha256"],
                    "relation": relation,
                    "primary": primary,
                    "quality_components": quality_components,
                    "quality_score": quality_score,
                    "assessment_confidence": _score(source.get("assessment_confidence"), "topic source assessment_confidence"),
                    "rationale": _short_text(source.get("rationale"), "topic source rationale"),
                })

            representatives = proposal.get("representative_local_paths")
            if not isinstance(representatives, list) or not representatives or len(representatives) > len(normalized_sources):
                raise ValueError("topic cluster requires one or more representative_local_paths")
            if any(not isinstance(path, str) or path not in source_paths for path in representatives):
                raise ValueError("topic representatives must be scored sources in the same topic cluster")
            if len(set(representatives)) != len(representatives):
                raise ValueError("topic representatives must not repeat a source")

            unresolved = proposal.get("unresolved", [])
            if not isinstance(unresolved, list) or len(unresolved) > 32:
                raise ValueError("topic cluster unresolved must be a bounded list")
            normalized_unresolved = [_short_text(item, "topic cluster unresolved", 1024) for item in unresolved]
            cluster_seed = f"{topic_key}\0" + "\0".join(
                f"{item['local_path']}:{item['content_sha256']}" for item in sorted(normalized_sources, key=lambda item: item["local_path"])
            )
            normalized_clusters.append({
                "cluster_id": "topic_" + hashlib.sha256(cluster_seed.encode("utf-8")).hexdigest()[:16],
                "topic_key": topic_key,
                "topic": topic,
                "context_signature": context_signature,
                "dedup_rationale": dedup_rationale,
                "sources": sorted(normalized_sources, key=lambda item: item["local_path"]),
                "representative_local_paths": list(representatives),
                "confidence_components": confidence_components,
                "confidence_score": confidence_score,
                "confidence_rationale": confidence_rationale,
                "unresolved": normalized_unresolved,
            })
        if set(primary_assignments) != set(sources):
            raise ValueError("topic aggregation must give every captured source exactly one primary topic assessment")

        relative_path = f"research_drift/aggregation/{frame_id}.json"
        artifact = {
            "schema": AGGREGATION_SCHEMA,
            "frame_id": frame_id,
            "request_sha256": frame["collection"]["request_sha256"],
            "source_manifest_sha256": source_manifest_sha256,
            "generated_at": now_iso(),
            "quality_rubric": {"version": "quality-v1", "weights": _QUALITY_WEIGHTS},
            "topic_confidence_rubric": {"version": "topic-confidence-v1", "weights": _TOPIC_CONFIDENCE_WEIGHTS},
            "clusters": normalized_clusters,
        }
        target = workspace() / relative_path
        atomic_write_json(target, artifact)
        aggregation_sha256 = _sha256_file(target)
        summary = {
            "cluster_count": len(normalized_clusters),
            "source_count": len(sources),
            "primary_source_count": len(primary_assignments),
            "representative_count": sum(len(item["representative_local_paths"]) for item in normalized_clusters),
            "low_quality_source_count": sum(
                item["quality_score"] < 0.5
                for cluster in normalized_clusters for item in cluster["sources"] if item["primary"]
            ),
            "low_confidence_cluster_count": sum(item["confidence_score"] < 0.5 for item in normalized_clusters),
        }
        frame["aggregation"] = {
            "status": "complete", "path": relative_path, "sha256": aggregation_sha256,
            "source_manifest_sha256": source_manifest_sha256, "summary": summary,
            "clusters": normalized_clusters,
        }
        frame["state"] = "reviewing"
        self.event("source_aggregation_recorded", frame_id=frame_id, aggregation_path=relative_path,
                   aggregation_sha256=aggregation_sha256, source_manifest_sha256=source_manifest_sha256,
                   summary=summary)
        return {"frame_id": frame_id, "state": frame["state"], "aggregation": frame["aggregation"]}

    def add_evidence(self, frame_id: str, proposals: list, reviewer_role: str | None = None) -> dict:
        frame = self.data["frames"][frame_id]
        review = frame["state"] == "reviewing"
        if not review:
            raise ValueError("evidence requires a reviewing frame after saved-source collection")
        if frame.get("aggregation", {}).get("status") != "complete":
            raise ValueError("evidence requires completed topic aggregation and quality scoring")
        if not isinstance(proposals, list):
            raise ValueError("evidence proposals must be a list")
        expected_roles = frame.get("review", {}).get("expected_roles", [])
        completed_roles = frame.get("review", {}).get("completed_roles", [])
        if reviewer_role not in expected_roles:
            raise ValueError("reviewing evidence requires an expected reviewer_role")
        if reviewer_role in completed_roles:
            raise ValueError("reviewer_role has already completed this collection")
        reviewable_records = self._reviewable_source_records(frame)
        primary_assessments = self._primary_source_assessments(frame)
        added = []
        for proposal in proposals:
            if not isinstance(proposal, dict):
                raise ValueError("evidence proposals must contain objects")
            path = proposal.get("local_path", "")
            if not isinstance(path, str) or not path:
                raise ValueError("accepted evidence must have a saved local_path")
            absolute = saved_page_path(path)
            if not absolute.is_file():
                raise ValueError(f"accepted evidence must have saved local_path: {path}")
            normalized_path = str(absolute.relative_to(workspace().resolve())).replace("\\", "/")
            canonical = reviewable_records.get(normalized_path)
            if canonical is None:
                raise ValueError("review evidence must be an unchanged captured source from the current source manifest")
            assessment = primary_assessments.get(normalized_path)
            if assessment is None:
                raise ValueError("review evidence must have a primary topic assessment")
            override = proposal.get("selection_override_rationale", "")
            if override:
                override = _short_text(override, "selection_override_rationale", 2048)
            if (assessment["quality_score"] < 0.5 or not assessment["representative"]) and not override:
                raise ValueError("reviewing a low-quality or non-representative source requires selection_override_rationale")
            captured_evidence = canonical["evidence"]
            capture = _capture_metadata(captured_evidence.get("capture"))
            discovered_by = _discovery_provenance(captured_evidence.get("discovered_by"))
            discovery_providers = list(dict.fromkeys(item["provider"] for item in discovered_by))
            if not discovery_providers:
                raw_discovery_providers = captured_evidence.get("discovery_providers", [])
                if not isinstance(raw_discovery_providers, list) or not all(
                    isinstance(item, str) and _PROVIDER_LABEL.fullmatch(item) for item in raw_discovery_providers
                ):
                    raise ValueError("captured source discovery_providers is invalid")
                discovery_providers = list(dict.fromkeys(raw_discovery_providers))
            capture_provider = _capture_provider(captured_evidence.get("capture_provider"))
            if discovery_providers:
                provider = discovery_providers[0]
            else:
                provider = _capture_provider(captured_evidence.get("provider"))
            raw = absolute.read_bytes()
            content_hash = hashlib.sha256(raw).hexdigest()
            if canonical["content_sha256"] != content_hash:
                raise ValueError("review evidence must be an unchanged captured source from the current source manifest")
            evidence_id = next((item_id for item_id, item in self.data["evidence"].items()
                                if item.get("content_hash") == content_hash), None)
            # Reusing an ancestor evidence node from a descendant frame would
            # introduce child -> evidence -> cognition -> gap -> child. Keep
            # the content hash, but create a new evidence version in that case.
            if evidence_id is not None and evidence_id not in frame["evidence_ids"] and self._reaches(evidence_id, frame_id):
                evidence_id = None
            if evidence_id is None:
                evidence_id = self.new_id("e")
                item = {
                    "id": evidence_id, "type": "evidence", "created_at": now_iso(),
                    "url": captured_evidence.get("url", ""), "title": captured_evidence.get("title", ""),
                    "provider": provider,
                    "discovery_providers": discovery_providers,
                    "discovered_by": discovered_by,
                    "capture_provider": capture_provider,
                    "local_path": path.replace("\\", "/"),
                    "content_hash": content_hash,
                    "retrieved_at": captured_evidence.get("retrieved_at", now_iso()),
                    "published_at": captured_evidence.get("published_at"),
                    "updated_at": captured_evidence.get("updated_at"),
                    "event_at": captured_evidence.get("event_at"),
                    "credibility": assessment["quality_score"],
                    "capture": capture,
                    "aggregation_assessment": {
                        "cluster_id": assessment["cluster_id"],
                        "topic_key": assessment["topic_key"],
                        "topic": assessment["topic"],
                        "cluster_confidence": assessment["cluster_confidence"],
                        "cluster_confidence_components": assessment["cluster_confidence_components"],
                        "quality_components": assessment["quality_components"],
                        "quality_score": assessment["quality_score"],
                        "assessment_confidence": assessment["assessment_confidence"],
                        "relation": assessment["relation"],
                        "representative": assessment["representative"],
                        "selection_override_rationale": override or None,
                    },
                }
                self.data["evidence"][evidence_id] = item
            if evidence_id not in frame["evidence_ids"]:
                frame["evidence_ids"].append(evidence_id)
                self.edge(frame_id, evidence_id, "retrieves")
            added.append(evidence_id)
        completed_roles = frame["review"].setdefault("completed_roles", [])
        completed_roles.append(reviewer_role)
        expected_roles = frame["review"].get("expected_roles", [])
        if set(completed_roles) == set(expected_roles):
            frame["state"] = "extracting"
        self.event("source_review_recorded", frame_id=frame_id, reviewer_role=reviewer_role,
                   evidence_ids=added, completed_roles=list(completed_roles), state=frame["state"])
        return {"frame_id": frame_id, "evidence_ids": added, "reviewer_role": reviewer_role,
                "completed_roles": list(completed_roles), "state": frame["state"]}

    def enrich_evidence_publication_time(self, evidence_id: str, published_at: str,
                                         locator: str, rationale: str) -> dict:
        """Attach a missing publication date to saved evidence with a raw-text witness.

        Provider metadata is preferred during collection. This repair path exists
        for primary pages that expose a date in their captured text but whose
        transport did not normalize it. It never changes the saved page or an
        existing date, and the witness is retained in the evidence node and log.
        """

        evidence = self.data["evidence"].get(evidence_id)
        if not isinstance(evidence, dict) or evidence.get("type") != "evidence":
            raise ValueError("publication-time enrichment references an unknown evidence id")
        if evidence.get("published_at"):
            raise ValueError("publication-time enrichment cannot replace an existing published_at")
        normalized_time = _short_text(published_at, "publication-time enrichment published_at", 128)
        parse_time(normalized_time)
        normalized_locator = _short_text(locator, "publication-time enrichment locator", 1024)
        normalized_rationale = _short_text(rationale, "publication-time enrichment rationale", 2048)
        local_path = evidence.get("local_path")
        if not isinstance(local_path, str) or not local_path:
            raise ValueError("publication-time enrichment evidence has no saved local_path")
        page = saved_page_path(local_path)
        if not page.is_file() or _sha256_file(page) != evidence.get("content_hash"):
            raise ValueError("publication-time enrichment requires an unchanged saved page")
        try:
            captured_text = page.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError("publication-time enrichment cannot read the saved page") from exc
        if normalized_locator not in captured_text:
            raise ValueError("publication-time enrichment locator is not present in the saved page")

        enrichment = {
            "published_at": normalized_time,
            "locator": normalized_locator,
            "rationale": normalized_rationale,
            "recorded_at": now_iso(),
        }
        evidence["published_at"] = normalized_time
        evidence["publication_time_enrichment"] = enrichment
        self.event("evidence_publication_time_enriched", evidence_id=evidence_id,
                   local_path=local_path, **enrichment)
        return {"evidence_id": evidence_id, "published_at": normalized_time,
                "locator": normalized_locator}

    @staticmethod
    def _reviewable_source_hashes(frame: dict) -> dict[str, str]:
        """Return the current collection's captured pages keyed by local path."""

        return {path: item["content_sha256"] for path, item in ResearchState._reviewable_source_records(frame).items()}

    @staticmethod
    def _reviewable_source_records(frame: dict) -> dict[str, dict]:
        """Return immutable captured-source packets from the current manifest."""

        collection = frame.get("collection")
        if not isinstance(collection, dict):
            raise ValueError("reviewing frame is missing saved-source collection metadata")
        manifest_path = ResearchState._saved_collection_path(collection.get("source_manifest_path"), "sources")
        manifest_file = workspace() / manifest_path
        expected_manifest_sha = collection.get("source_manifest_sha256")
        if expected_manifest_sha is not None:
            if not isinstance(expected_manifest_sha, str) or not _REQUEST_SHA256.fullmatch(expected_manifest_sha):
                raise ValueError("current source manifest sha256 is invalid")
            if _sha256_file(manifest_file) != expected_manifest_sha:
                raise ValueError("saved source manifest no longer matches its collection hash")
        try:
            payload = json.loads(manifest_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("saved source manifest is unreadable") from exc
        request_sha256 = collection.get("request_sha256")
        if (
            not isinstance(payload, dict)
            or payload.get("schema") not in {1, 2}
            or payload.get("frame_id") != frame.get("id")
            or payload.get("request_sha256") != request_sha256
        ):
            raise ValueError("saved source manifest does not match the current collection")
        records = payload.get("records") if isinstance(payload, dict) else None
        if not isinstance(records, list):
            raise ValueError("saved source manifest has no records")
        sources = {}
        for record in records:
            if not isinstance(record, dict) or record.get("status") != "captured":
                continue
            evidence = record.get("evidence")
            content_hash = record.get("content_sha256")
            path = evidence.get("local_path") if isinstance(evidence, dict) else None
            if not isinstance(path, str) or not isinstance(content_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", content_hash):
                raise ValueError("saved source manifest has an invalid captured record")
            try:
                saved_page = saved_page_path(path)
                normalized = str(saved_page.relative_to(workspace().resolve())).replace("\\", "/")
            except ValueError as exc:
                raise ValueError("saved source manifest has an invalid captured page path") from exc
            if not saved_page.is_file() or _sha256_file(saved_page) != content_hash:
                raise ValueError("saved source manifest captured page no longer matches its content hash")
            if normalized in sources and sources[normalized]["content_sha256"] != content_hash:
                raise ValueError("saved source manifest has conflicting captured page hashes")
            sources[normalized] = {"content_sha256": content_hash, "evidence": dict(evidence)}
        return sources

    @staticmethod
    def _verified_aggregation(frame: dict) -> dict:
        """Read the content-addressed aggregation bound to this collection."""

        collection = frame.get("collection")
        aggregation = frame.get("aggregation")
        if not isinstance(collection, dict) or not isinstance(aggregation, dict) or aggregation.get("status") != "complete":
            raise ValueError("reviewing frame is missing a completed source aggregation")
        path = ResearchState._saved_collection_path(aggregation.get("path"), "aggregation")
        target = workspace() / path
        expected_hash = aggregation.get("sha256")
        if not isinstance(expected_hash, str) or not _REQUEST_SHA256.fullmatch(expected_hash):
            raise ValueError("source aggregation sha256 is invalid")
        if _sha256_file(target) != expected_hash:
            raise ValueError("saved source aggregation no longer matches its content hash")
        try:
            artifact = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("saved source aggregation is unreadable") from exc
        if (
            not isinstance(artifact, dict)
            or artifact.get("schema") != AGGREGATION_SCHEMA
            or artifact.get("frame_id") != frame.get("id")
            or artifact.get("request_sha256") != collection.get("request_sha256")
            or artifact.get("source_manifest_sha256") != collection.get("source_manifest_sha256")
            or artifact.get("clusters") != aggregation.get("clusters")
        ):
            raise ValueError("saved source aggregation does not match the current collection")
        # This also rechecks the manifest and every captured page, so a frozen
        # aggregation cannot silently mask later source mutation.
        ResearchState._reviewable_source_records(frame)
        return artifact

    @staticmethod
    def _primary_source_assessments(frame: dict) -> dict[str, dict]:
        """Return each source's single primary topic assessment for review."""

        artifact = ResearchState._verified_aggregation(frame)
        assessments = {}
        for cluster in artifact["clusters"]:
            for source in cluster["sources"]:
                if source["primary"]:
                    assessments[source["local_path"]] = {
                        "cluster_id": cluster["cluster_id"],
                        "topic_key": cluster["topic_key"],
                        "topic": cluster["topic"],
                        "cluster_confidence": cluster["confidence_score"],
                        "cluster_confidence_components": cluster["confidence_components"],
                        "representative": source["local_path"] in cluster["representative_local_paths"],
                        **source,
                    }
        return assessments

    def _cognition_assessment(self, frame: dict, spans: list[dict]) -> dict:
        """Translate selected source assessments into a conservative claim cap."""

        clusters = {}
        for span in spans:
            evidence = self.data["evidence"][span["evidence_id"]]
            assessment = evidence.get("aggregation_assessment")
            if not isinstance(assessment, dict):
                raise ValueError("cognition evidence is missing an aggregation assessment")
            quality = _score(assessment.get("quality_score"), "evidence assessment quality_score")
            cluster_confidence = _score(assessment.get("cluster_confidence"), "evidence assessment cluster_confidence")
            assessment_confidence = _score(assessment.get("assessment_confidence"), "evidence assessment assessment_confidence")
            strength = round(0.45 * quality + 0.40 * cluster_confidence + 0.15 * assessment_confidence, 6)
            cluster_id = assessment.get("cluster_id")
            if not isinstance(cluster_id, str) or not cluster_id:
                raise ValueError("evidence assessment cluster_id is invalid")
            existing = clusters.get(cluster_id)
            if existing is None or strength > existing["support_ceiling"]:
                clusters[cluster_id] = {
                    "cluster_id": cluster_id,
                    "topic_key": assessment.get("topic_key"),
                    "quality_score": quality,
                    "cluster_confidence": cluster_confidence,
                    "assessment_confidence": assessment_confidence,
                    "support_ceiling": strength,
                }
        if not clusters:
            raise ValueError("cognition requires assessed saved-source evidence")
        # The cap is deliberately the strongest relevant topic assessment, not
        # a count-based boost. Multiple near-duplicates must not manufacture a
        # high-confidence claim; stronger corroboration belongs in the topic
        # aggregation rubric before extraction.
        cap = max(item["support_ceiling"] for item in clusters.values())
        return {"confidence_cap": cap, "clusters": sorted(clusters.values(), key=lambda item: item["cluster_id"])}

    def _normalise_source_coverage(self, frame: dict, coverage: object, cognitions: list, gaps: list) -> list[dict]:
        """Require an explicit disposition for every reviewer-selected source.

        The extractor may still choose a source as context only, but it cannot
        silently omit a strong representative source from the decision record.
        """

        if not isinstance(coverage, list):
            raise ValueError("decision-aware extraction requires source coverage")
        proposed_gap_refs = set()
        for proposal in gaps:
            if not isinstance(proposal, dict):
                raise ValueError("gap proposals must contain objects")
            proposal_ref = proposal.get("proposal_ref")
            if proposal_ref is None:
                continue
            if not isinstance(proposal_ref, str) or not _PROPOSAL_REF.fullmatch(proposal_ref):
                raise ValueError("gap proposal_ref must use only letters, digits, dots, underscores, or hyphens")
            if proposal_ref in proposed_gap_refs:
                raise ValueError(f"duplicate gap proposal_ref: {proposal_ref}")
            proposed_gap_refs.add(proposal_ref)
        cited_evidence_ids = {
            span.get("evidence_id")
            for proposal in cognitions if isinstance(proposal, dict)
            for span in proposal.get("source_spans", []) if isinstance(span, dict)
            and isinstance(span.get("evidence_id"), str)
        }
        expected = set(frame["evidence_ids"])
        normalized = []
        seen = set()
        for item in coverage:
            if not isinstance(item, dict):
                raise ValueError("source coverage entries must be objects")
            evidence_id = item.get("evidence_id")
            disposition = item.get("disposition")
            if not isinstance(evidence_id, str) or evidence_id not in expected or evidence_id in seen:
                raise ValueError("source coverage requires one unique frame evidence_id per entry")
            if disposition not in _SOURCE_COVERAGE_DISPOSITIONS:
                raise ValueError("source coverage disposition is invalid")
            rationale = _short_text(item.get("rationale"), "source coverage rationale", 2048)
            gap_ids = item.get("gap_ids", [])
            gap_refs = item.get("gap_refs", [])
            if not isinstance(gap_ids, list) or not all(isinstance(value, str) for value in gap_ids):
                raise ValueError("source coverage gap_ids must be a list of gap ids")
            if not isinstance(gap_refs, list) or not all(isinstance(value, str) for value in gap_refs):
                raise ValueError("source coverage gap_refs must be a list of proposal refs")
            if disposition == "cited" and evidence_id not in cited_evidence_ids:
                raise ValueError("cited source coverage must be used by a cognition in the same extraction")
            if disposition == "needs_followup":
                if not gap_ids and not gap_refs:
                    raise ValueError("needs_followup source coverage must reference a gap")
                unknown_existing = set(gap_ids) - set(frame["gap_ids"])
                if unknown_existing:
                    raise ValueError("source coverage references an unknown existing frame gap")
                unknown_refs = set(gap_refs) - proposed_gap_refs
                if unknown_refs:
                    raise ValueError("source coverage references an unknown gap proposal_ref")
            seen.add(evidence_id)
            normalized.append({
                "evidence_id": evidence_id,
                "disposition": disposition,
                "rationale": rationale,
                "gap_ids": list(dict.fromkeys(gap_ids)),
                "gap_refs": list(dict.fromkeys(gap_refs)),
            })
        if seen != expected:
            missing = sorted(expected - seen)
            raise ValueError(f"source coverage omits reviewer-selected evidence: {', '.join(missing)}")
        return normalized

    def _frame_source_coverage_issues(self, frame: dict) -> list[str]:
        if not self.decision_synthesis_required() or not frame.get("evidence_ids"):
            return []
        coverage = frame.get("evidence_coverage")
        if not isinstance(coverage, list):
            return ["missing source coverage"]
        expected = set(frame["evidence_ids"])
        covered = {
            item.get("evidence_id") for item in coverage
            if isinstance(item, dict) and isinstance(item.get("evidence_id"), str)
        }
        issues = []
        if covered != expected or len(coverage) != len(covered):
            issues.append("source coverage does not exactly match reviewer-selected evidence")
        cognition_sources = {
            span.get("evidence_id")
            for cognition_id in frame.get("cognition_ids", [])
            for span in self.data["cognitions"].get(cognition_id, {}).get("source_spans", [])
            if isinstance(span, dict)
        }
        for item in coverage:
            if not isinstance(item, dict):
                issues.append("invalid source coverage entry")
                continue
            disposition = item.get("disposition")
            evidence_id = item.get("evidence_id")
            if disposition not in _SOURCE_COVERAGE_DISPOSITIONS or not str(item.get("rationale", "")).strip():
                issues.append("source coverage entry has invalid disposition or rationale")
            if disposition == "cited" and evidence_id not in cognition_sources:
                issues.append(f"cited source coverage has no cognition: {evidence_id}")
            if disposition == "needs_followup" and not item.get("gap_ids"):
                issues.append(f"needs_followup source coverage has no persisted gap: {evidence_id}")
        return issues

    def source_coverage_audit(self) -> dict:
        if not self.decision_synthesis_required():
            return {"ok": True, "required": False, "issues": []}
        issues = []
        for frame in self.data["frames"].values():
            for issue in self._frame_source_coverage_issues(frame):
                issues.append({"frame_id": frame["id"], "issue": issue})
        return {"ok": not issues, "required": True, "issues": issues}

    def _decision_synthesis_basis(self) -> dict:
        """Build the immutable research facts a decision synthesis is allowed to use."""

        cited_evidence_ids = sorted({
            span.get("evidence_id")
            for cognition in self.data["cognitions"].values()
            for span in cognition.get("source_spans", [])
            if isinstance(span, dict) and isinstance(span.get("evidence_id"), str)
            and span["evidence_id"] in self.data["evidence"]
        })

        return {
            "intent_contract_version": self.intent_contract().get("version"),
            "decision_questions": self.decision_questions(),
            "frames": [{
                "id": frame["id"], "state": frame.get("state"), "return": frame.get("return"),
                "cognition_ids": list(frame.get("cognition_ids", [])),
                "gap_ids": list(frame.get("gap_ids", [])),
                "evidence_coverage": frame.get("evidence_coverage", []),
                "aggregation_unresolved": [
                    {"cluster_id": cluster.get("cluster_id"), "unresolved": cluster.get("unresolved", [])}
                    for cluster in frame.get("aggregation", {}).get("clusters", [])
                    if isinstance(cluster, dict) and cluster.get("unresolved")
                ],
            } for frame in sorted(self.data["frames"].values(), key=lambda item: item["id"])],
            "cognitions": [{
                "id": item["id"], "frame_id": item.get("frame_id"), "claim": item.get("claim"),
                "confidence": item.get("confidence"), "evidence_time": item.get("evidence_time"),
                "source_spans": item.get("source_spans", []),
            } for item in sorted(self.data["cognitions"].values(), key=lambda item: item["id"])],
            "gaps": [{
                "id": item["id"], "frame_id": item.get("frame_id"), "status": item.get("status"),
                "description": item.get("description"), "discriminator": item.get("discriminator"),
            } for item in sorted(self.data["gaps"].values(), key=lambda item: item["id"])],
            "cited_evidence_times": [{
                "id": evidence_id,
                "content_hash": self.data["evidence"][evidence_id].get("content_hash"),
                "published_at": self.data["evidence"][evidence_id].get("published_at"),
                "updated_at": self.data["evidence"][evidence_id].get("updated_at"),
                "event_at": self.data["evidence"][evidence_id].get("event_at"),
                "publication_time_enrichment": self.data["evidence"][evidence_id].get("publication_time_enrichment"),
            } for evidence_id in cited_evidence_ids],
        }

    def extract(self, frame_id: str, cognitions: list, gaps: list, coverage: list | None = None) -> dict:
        frame = self.data["frames"][frame_id]
        if frame["state"] != "extracting":
            raise ValueError("cognition extraction requires extracting frame")
        if not isinstance(cognitions, list) or not isinstance(gaps, list):
            raise ValueError("cognition and gap proposals must be lists")
        normalized_coverage = None
        if self.decision_synthesis_required():
            normalized_coverage = self._normalise_source_coverage(frame, coverage, cognitions, gaps)
        created_cognition, created_gaps = [], []
        cognition_refs: dict[str, str] = {}
        gap_refs: dict[str, str] = {}
        relationship_specs = []
        for proposal in cognitions:
            spans = proposal.get("source_spans", [])
            if not spans:
                raise ValueError("cognition requires source_spans")
            for span in spans:
                if span.get("evidence_id") not in frame["evidence_ids"] or not span.get("locator"):
                    raise ValueError("source span must reference frame evidence and locator")
            claim = str(proposal.get("claim", "")).strip()
            if not claim:
                raise ValueError("cognition requires claim")
            context_signature = str(proposal.get("context_signature", "")).strip()
            if not context_signature:
                raise ValueError("cognition requires context_signature")
            claim_key = str(proposal.get("claim_key", context_signature)).strip()
            if not claim_key:
                raise ValueError("cognition claim_key must not be empty")
            polarity = proposal.get("polarity", "unknown")
            if polarity not in {"supports", "refutes", "unknown"}:
                raise ValueError("cognition polarity must be supports, refutes, or unknown")
            evidence_time = proposal.get("evidence_time")
            try:
                parse_time(evidence_time)
            except ValueError as exc:
                raise ValueError(f"cognition requires valid evidence_time: {exc}") from exc
            assessment = self._cognition_assessment(frame, spans)
            requested_confidence = _score(proposal.get("confidence", 0.5), "cognition confidence")
            effective_confidence = min(requested_confidence, assessment["confidence_cap"])
            cognition_id = self.new_id("k")
            item = {
                "id": cognition_id, "type": "cognition", "created_at": now_iso(),
                "claim": claim, "context_signature": context_signature, "claim_key": claim_key,
                "polarity": polarity,
                "asserted_at": proposal.get("asserted_at", now_iso()),
                "evidence_time": evidence_time,
                "confidence": effective_confidence,
                "confidence_requested": requested_confidence,
                "confidence_cap": assessment["confidence_cap"],
                "evidence_assessment": assessment,
                "source_spans": spans, "frame_id": frame_id,
            }
            self.data["cognitions"][cognition_id] = item
            frame["cognition_ids"].append(cognition_id)
            for span in spans:
                self.edge(span["evidence_id"], cognition_id, "extracts")
            created_cognition.append(cognition_id)
            proposal_ref = proposal.get("proposal_ref")
            if proposal_ref is not None:
                if not isinstance(proposal_ref, str) or not _PROPOSAL_REF.fullmatch(proposal_ref):
                    raise ValueError("cognition proposal_ref must use only letters, digits, dots, underscores, or hyphens")
                if proposal_ref in cognition_refs:
                    raise ValueError(f"duplicate cognition proposal_ref: {proposal_ref}")
                cognition_refs[proposal_ref] = cognition_id
            relationship_specs.append((cognition_id, proposal))
        for proposal in gaps:
            raw_trigger_ids = proposal.get("trigger_cognition_ids", [])
            if not isinstance(raw_trigger_ids, list) or not all(isinstance(item, str) for item in raw_trigger_ids):
                raise ValueError("trigger_cognition_ids must be a list of cognition ids")
            trigger_refs = proposal.get("trigger_cognition_refs", [])
            if not isinstance(trigger_refs, list) or not all(isinstance(item, str) for item in trigger_refs):
                raise ValueError("trigger_cognition_refs must be a list of proposal refs")
            unresolved_refs = [item for item in trigger_refs if item not in cognition_refs]
            if unresolved_refs:
                raise ValueError(f"gap references unknown cognition proposal_ref: {', '.join(sorted(set(unresolved_refs)))}")
            trigger_ids = list(dict.fromkeys([*raw_trigger_ids, *(cognition_refs[item] for item in trigger_refs)]))
            if not trigger_ids or not all(item in frame["cognition_ids"] for item in trigger_ids):
                raise ValueError("gap must cite cognitions extracted from this frame")
            description = str(proposal.get("description", "")).strip()
            discriminator = str(proposal.get("discriminator", "")).strip()
            if not description or not discriminator:
                raise ValueError("gap requires description and discriminator")
            proposal_ref = proposal.get("proposal_ref")
            if proposal_ref is not None:
                if not isinstance(proposal_ref, str) or not _PROPOSAL_REF.fullmatch(proposal_ref):
                    raise ValueError("gap proposal_ref must use only letters, digits, dots, underscores, or hyphens")
                if proposal_ref in gap_refs:
                    raise ValueError(f"duplicate gap proposal_ref: {proposal_ref}")
            gap_id = self.new_id("g")
            item = {
                "id": gap_id, "type": "gap", "created_at": now_iso(), "frame_id": frame_id,
                "description": description, "discriminator": discriminator,
                "expected_update": proposal.get("expected_update", ""),
                "evidence_requirement": proposal.get("evidence_requirement", ""),
                "expected_information_gain": float(proposal.get("expected_information_gain", 0.5)),
                "acquisition_cost": float(proposal.get("acquisition_cost", 0.5)),
                "trigger_cognition_ids": trigger_ids,
                "status": proposal.get("status", "open"),
            }
            if proposal_ref is not None:
                item["proposal_ref"] = proposal_ref
                gap_refs[proposal_ref] = gap_id
            self.data["gaps"][gap_id] = item
            frame["gap_ids"].append(gap_id)
            for cognition_id in trigger_ids:
                self.edge(cognition_id, gap_id, "exposes")
            self.data.setdefault("frontier", {})[gap_id] = {
                "gap_id": gap_id, "status": "deferred", "created_at": now_iso(),
                "revisit_conditions": ["selected child returns low confidence", "new contradictory cognition", "temporal evidence changes"],
            }
            created_gaps.append(gap_id)
        if normalized_coverage is not None:
            persisted_coverage = []
            for item in normalized_coverage:
                gap_ids = list(item["gap_ids"])
                gap_ids.extend(gap_refs[reference] for reference in item["gap_refs"])
                persisted_coverage.append({
                    "evidence_id": item["evidence_id"],
                    "disposition": item["disposition"],
                    "rationale": item["rationale"],
                    "gap_ids": list(dict.fromkeys(gap_ids)),
                })
            frame["evidence_coverage"] = persisted_coverage
        reactivation_requests = []
        relationship_records = []
        for cognition_id, proposal in relationship_specs:
            cognition = self.data["cognitions"][cognition_id]
            for field, kind, reason in (
                ("contradicts_cognition_ids", "contradicts", "new contradictory cognition"),
                ("updates_cognition_ids", "updates", "newer temporal evidence"),
            ):
                target_ids = proposal.get(field, [])
                if not isinstance(target_ids, list) or not all(isinstance(item, str) for item in target_ids):
                    raise ValueError(f"{field} must be a list of cognition ids")
                for target_id in dict.fromkeys(target_ids):
                    if target_id == cognition_id or target_id not in self.data["cognitions"]:
                        raise ValueError(f"{field} contains an unknown or self cognition id")
                    target = self.data["cognitions"][target_id]
                    if kind == "updates" and parse_time(cognition["evidence_time"]) <= parse_time(target["evidence_time"]):
                        raise ValueError("updates_cognition_ids require strictly newer evidence_time")
                    self.relation(cognition_id, target_id, kind, "extractor-declared relation")
                    relationship_records.append({"from": cognition_id, "to": target_id, "kind": kind})
                    reactivation_requests.append((target["frame_id"], reason))
        reactivations = []
        for target_frame_id, reason in dict.fromkeys(reactivation_requests):
            reactivation = self.reactivate_frontier(target_frame_id, reason)
            target_frame = self.data["frames"][target_frame_id]
            if reactivation["gap_ids"] and target_frame["state"] in {"resolved", "contradicted", "insufficient_evidence"}:
                target_frame["state"] = "expanded"
                target_frame["return"] = None
                self.event("frame_reopened_for_reconsideration", frame_id=target_frame_id, reason=reason)
            if reactivation["gap_ids"]:
                reactivations.append(reactivation)
        frame["state"] = "expanded"
        self.event("cognition_extracted", frame_id=frame_id, cognitions=created_cognition, gaps=created_gaps,
                    relations=relationship_records, frontier_reactivations=reactivations)
        return {"frame_id": frame_id, "cognition_ids": created_cognition, "gap_ids": created_gaps,
                "cognition_refs": cognition_refs, "gap_refs": gap_refs, "relations": relationship_records,
                "frontier_reactivations": reactivations}

    def _normalise_decision_synthesis(self, proposal: dict) -> dict:
        if not isinstance(proposal, dict):
            raise ValueError("decision synthesis must be an object")
        questions = {item["id"]: item for item in self.decision_questions()}
        if not questions:
            raise ValueError("decision synthesis is not required for this intent contract")
        recommendation = proposal.get("recommendation")
        if recommendation not in _DECISION_RECOMMENDATIONS:
            raise ValueError("decision synthesis recommendation is invalid")
        overall_status = proposal.get("overall_status")
        if overall_status not in {"supported", "conditional", "need_user_input", "insufficient"}:
            raise ValueError("decision synthesis overall_status is invalid")
        assessments = proposal.get("question_assessments")
        if not isinstance(assessments, list) or len(assessments) != len(questions):
            raise ValueError("decision synthesis must assess every decision question exactly once")
        normalised_assessments = []
        seen_questions = set()
        known_cognitions = set(self.data["cognitions"])
        known_gaps = set(self.data["gaps"])
        for item in assessments:
            if not isinstance(item, dict):
                raise ValueError("decision question assessments must be objects")
            question_id = item.get("decision_question_id")
            if question_id not in questions or question_id in seen_questions:
                raise ValueError("decision synthesis references an unknown or repeated decision question")
            status = item.get("status")
            if status not in _DECISION_QUESTION_STATUSES:
                raise ValueError("decision question assessment status is invalid")
            supporting = item.get("supporting_cognition_ids", [])
            refuting = item.get("refuting_cognition_ids", [])
            gap_ids = item.get("gap_ids", [])
            user_questions = item.get("user_questions", [])
            conditions = item.get("conditions_to_change", [])
            for field, values, known in (
                ("supporting_cognition_ids", supporting, known_cognitions),
                ("refuting_cognition_ids", refuting, known_cognitions),
                ("gap_ids", gap_ids, known_gaps),
            ):
                if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
                    raise ValueError(f"decision question {field} must be a list of ids")
                if not set(values).issubset(known):
                    raise ValueError(f"decision question {field} references an unknown id")
            if not isinstance(user_questions, list) or not isinstance(conditions, list):
                raise ValueError("decision question user_questions and conditions_to_change must be lists")
            normalized_user_questions = _bounded_text_list(user_questions, "decision question user_questions", 16, 2048)
            normalized_conditions = _bounded_text_list(conditions, "decision question conditions_to_change", 32, 2048)
            supporting = list(dict.fromkeys(supporting))
            refuting = list(dict.fromkeys(refuting))
            gap_ids = list(dict.fromkeys(gap_ids))
            if status == "supported" and not supporting:
                raise ValueError("a supported decision question requires supporting cited cognitions")
            if status == "conditional" and (not supporting or not normalized_conditions):
                raise ValueError("a conditional decision question requires support and conditions_to_change")
            if status == "gap_child":
                if not gap_ids or not normalized_conditions:
                    raise ValueError("a gap_child decision question requires gap_ids and conditions_to_change")
                if not any(self.data["gaps"][gap_id].get("status") in {"expanded", "merged"} for gap_id in gap_ids):
                    raise ValueError("a gap_child decision question requires a recursively expanded or merged gap")
            if status == "need_user_input" and not normalized_user_questions:
                raise ValueError("a need_user_input decision question requires a user question")
            if status == "insufficient" and not normalized_conditions:
                raise ValueError("an insufficient decision question requires conditions_to_change")
            normalised_assessments.append({
                "decision_question_id": question_id,
                "status": status,
                "conclusion": _short_text(item.get("conclusion"), "decision question conclusion", 4096),
                "supporting_cognition_ids": supporting,
                "refuting_cognition_ids": refuting,
                "gap_ids": gap_ids,
                "user_questions": normalized_user_questions,
                "conditions_to_change": normalized_conditions,
                "action": _short_text(item.get("action"), "decision question action", 4096),
            })
            seen_questions.add(question_id)
        if seen_questions != set(questions):
            raise ValueError("decision synthesis omits a decision question")
        high_impact = [
            item for item in normalised_assessments
            if questions[item["decision_question_id"]]["impact"] == "high"
        ]
        if recommendation == "approve" and any(item["status"] != "supported" for item in high_impact):
            raise ValueError("cannot approve while a high-impact decision question is unresolved")
        if overall_status == "supported" and any(item["status"] != "supported" for item in normalised_assessments):
            raise ValueError("a supported decision synthesis cannot retain unresolved questions")
        if overall_status == "need_user_input" and not any(
            item["status"] == "need_user_input" for item in normalised_assessments
        ):
            raise ValueError("need_user_input overall status requires a matching decision question")

        provenance = proposal.get("parameter_provenance", [])
        if not isinstance(provenance, list) or len(provenance) > 128:
            raise ValueError("decision synthesis parameter_provenance must be a bounded list")
        normalised_provenance = []
        seen_parameters = set()
        known_materials = set(self.data.get("materials", {}))
        for index, item in enumerate(provenance):
            if not isinstance(item, dict):
                raise ValueError("parameter provenance entries must be objects")
            parameter_id = item.get("id", f"parameter-{index + 1}")
            if (
                not isinstance(parameter_id, str)
                or not _CONTRACT_ID.fullmatch(parameter_id)
                or parameter_id in seen_parameters
            ):
                raise ValueError("parameter provenance requires unique ids")
            basis = item.get("basis")
            if basis not in _PARAMETER_BASES:
                raise ValueError("parameter provenance basis is invalid")
            cognition_ids = item.get("cognition_ids", [])
            material_ids = item.get("material_ids", [])
            if not isinstance(cognition_ids, list) or not all(isinstance(value, str) for value in cognition_ids):
                raise ValueError("parameter provenance cognition_ids must be a list of ids")
            if not isinstance(material_ids, list) or not all(isinstance(value, str) for value in material_ids):
                raise ValueError("parameter provenance material_ids must be a list of ids")
            if not set(cognition_ids).issubset(known_cognitions):
                raise ValueError("parameter provenance references an unknown cognition")
            if not set(material_ids).issubset(known_materials):
                raise ValueError("parameter provenance references an unknown material")
            if basis in {"direct_evidence", "transfer_method"} and not cognition_ids:
                raise ValueError("evidence-based parameter provenance requires cited cognition ids")
            if basis == "user_constraint" and not material_ids and not str(item.get("rationale", "")).strip():
                raise ValueError("user-constraint parameter provenance requires material ids or rationale")
            value = item.get("value")
            if isinstance(value, bool) or value is None:
                raise ValueError("parameter provenance value is required")
            if not isinstance(value, str):
                value = str(value)
            normalised_provenance.append({
                "id": parameter_id,
                "parameter": _short_text(item.get("parameter"), "parameter provenance parameter", 2048),
                "value": _short_text(value, "parameter provenance value", 2048),
                "basis": basis,
                "cognition_ids": list(dict.fromkeys(cognition_ids)),
                "material_ids": list(dict.fromkeys(material_ids)),
                "rationale": _short_text(item.get("rationale"), "parameter provenance rationale", 4096),
                "decision_effect": _short_text(item.get("decision_effect"), "parameter provenance decision_effect", 4096),
            })
            seen_parameters.add(parameter_id)
        contract = self.intent_contract().get("contract", {})
        requires_design = any(
            isinstance(item, dict) and item.get("required") and item.get("requires_design")
            for item in contract.get("deliverables", [])
        )
        if requires_design and not normalised_provenance:
            raise ValueError("a required design deliverable needs parameter provenance")
        return {
            "overall_status": overall_status,
            "recommendation": recommendation,
            "summary": _short_text(proposal.get("summary"), "decision synthesis summary", 4096),
            "question_assessments": sorted(normalised_assessments, key=lambda item: item["decision_question_id"]),
            "parameter_provenance": sorted(normalised_provenance, key=lambda item: item["id"]),
        }

    def decision_synthesis_audit(self) -> dict:
        if not self.decision_synthesis_required():
            return {"ok": True, "required": False, "issues": [], "status": "not_required"}
        issues = []
        try:
            record = self._decision_synthesis_record()
            if record.get("status") != "ready" or not isinstance(record.get("synthesis"), dict):
                issues.append("decision synthesis is not ready")
            else:
                normalised = self._normalise_decision_synthesis(record["synthesis"])
                digest = _canonical_json_hash(normalised)
                if record.get("synthesis") != normalised:
                    issues.append("decision synthesis is not normalized")
                if record.get("sha256") != digest:
                    issues.append("decision synthesis hash does not match its content")
                if record.get("basis_sha256") != _canonical_json_hash(self._decision_synthesis_basis()):
                    issues.append("decision synthesis no longer matches the current research basis")
        except ValueError as exc:
            issues.append(str(exc))
        return {"ok": not issues, "required": True, "issues": issues,
                "status": self._decision_synthesis_record().get("status")}

    def synthesize_decision(self, proposal: dict) -> dict:
        self.require_intent_ready()
        if not self.decision_synthesis_required():
            raise ValueError("decision synthesis is not required for this intent contract")
        active = [frame["id"] for frame in self.data["frames"].values() if frame["state"] in ACTIVE]
        if active:
            raise ValueError("cannot synthesize a decision while research frames remain active")
        coverage = self.source_coverage_audit()
        if not coverage["ok"]:
            raise ValueError("cannot synthesize a decision before source coverage passes")
        normalised = self._normalise_decision_synthesis(proposal)
        digest = _canonical_json_hash(normalised)
        basis_sha256 = _canonical_json_hash(self._decision_synthesis_basis())
        self.data["decision_synthesis"] = {
            "schema": DECISION_SYNTHESIS_SCHEMA,
            "status": "ready",
            "synthesis": normalised,
            "sha256": digest,
            "basis_sha256": basis_sha256,
            "updated_at": now_iso(),
        }
        self.event("decision_synthesized", recommendation=normalised["recommendation"],
                   overall_status=normalised["overall_status"], sha256=digest)
        return {"status": "ready", "sha256": digest, "basis_sha256": basis_sha256,
                "recommendation": normalised["recommendation"],
                "overall_status": normalised["overall_status"]}

    def frontier(self, frame_id: str) -> list[dict]:
        return rank_frontier(self.data, frame_id)

    def frontier_decision(self, frame_id: str, frontier: list[dict] | None = None) -> dict:
        """Recommend whether a frame should descend, review, or return.

        Ranking is intentionally advisory. A close score pair is evidence that
        the heuristic cannot decide, not an instruction to discard either
        branch. In that case a Branch Selector may still choose one, but must
        supply the existing explicit selection rationale. Depth and call limits
        are hard stops; the global frame limit still permits a zero-cost merge
        into an already equivalent frame.
        """
        ranked = self.frontier(frame_id) if frontier is None else list(frontier)
        policy = self.descent_policy()
        budget = self.convergence_budget(frame_id)
        decision = {
            "frame_id": frame_id,
            "recommendation": "return",
            "reason_code": "no_deferred_frontier",
            "reason": "no deferred alternative remains; return a bounded result",
            "recommended_gap_id": None,
            "runner_up_gap_id": None,
            "score_margin": policy["score_margin"],
            "observed_margin": None,
            "budget": budget,
            "new_frame_budget_available": budget["remaining_new_frames"] > 0,
            "allow_existing_merge": False,
        }
        if not ranked:
            return decision
        if budget["frame_depth"] >= budget["max_depth"]:
            decision.update({
                "reason_code": "max_depth_reached",
                "reason": "recursive depth budget reached; retain the frontier and return a bounded result",
            })
            return decision
        if budget["calls_used"] >= budget["max_calls_per_frame"]:
            decision.update({
                "reason_code": "per_frame_call_budget_reached",
                "reason": "per-frame recursive call budget reached; retain the frontier and return a bounded result",
            })
            return decision

        top = ranked[0]
        decision["recommended_gap_id"] = top["gap_id"]
        if budget["remaining_new_frames"] <= 0:
            # We cannot know whether a future child proposal will deduplicate
            # until the proposal is supplied. A merge does not consume budget.
            decision.update({
                "reason_code": "global_frame_budget_reached",
                "reason": "global new-frame budget reached; return a bounded result unless an equivalent existing frame can be merged",
                "allow_existing_merge": True,
            })
            return decision

        if len(ranked) == 1:
            decision.update({
                "recommendation": "descend",
                "reason_code": "single_frontier_candidate",
                "reason": "one deferred alternative remains and recursive capacity is available",
            })
            return decision

        runner_up = ranked[1]
        observed_margin = round(top["score"] - runner_up["score"], 6)
        decision.update({"runner_up_gap_id": runner_up["gap_id"], "observed_margin": observed_margin})
        if observed_margin >= policy["score_margin"]:
            decision.update({
                "recommendation": "descend",
                "reason_code": "clear_frontier_leader",
                "reason": "the leading frontier alternative exceeds the runner-up by at least score_margin",
            })
        else:
            decision.update({
                "recommendation": "review",
                "reason_code": "ambiguous_frontier_scores",
                "reason": "the leading alternatives are within score_margin; a documented selector rationale may choose one or return",
            })
        return decision

    def reactivate_frontier(self, frame_id: str, reason: str) -> dict:
        """Record why still-deferred alternatives deserve another ranking pass.

        This deliberately does not reopen an already-expanded gap.  Reopening
        it would repeatedly construct the same child frame and turn a failed
        branch into a loop.  Instead, it adds a bounded ranking signal to the
        sibling alternatives that were deliberately kept in the frontier.
        """
        frame = self.data["frames"][frame_id]
        reason = str(reason).strip()
        if not reason:
            raise ValueError("frontier reactivation requires a reason")
        reactivated = []
        for gap_id in frame["gap_ids"]:
            gap = self.data["gaps"][gap_id]
            item = self.data.get("frontier", {}).get(gap_id)
            if gap["status"] != "open" or not item or item.get("status", "deferred") != "deferred":
                continue
            item["reactivation_count"] = int(item.get("reactivation_count", 0)) + 1
            item["last_reactivated_at"] = now_iso()
            reasons = item.setdefault("reactivation_reasons", [])
            if reason not in reasons:
                reasons.append(reason)
            reactivated.append(gap_id)
        if reactivated:
            self.event("frontier_reactivated", frame_id=frame_id, gap_ids=reactivated, reason=reason)
        return {"frame_id": frame_id, "gap_ids": reactivated, "reason": reason}

    def descend(self, frame_id: str, gap_id: str, proposal: dict, selection_rationale: str) -> dict:
        gap = self.data["gaps"][gap_id]
        frame = self.data["frames"][frame_id]
        if gap["frame_id"] != frame_id:
            raise ValueError("selected gap does not belong to the parent frame")
        if frame["state"] != "expanded":
            raise ValueError("only an expanded frame can select a recursive descent")
        descent = frame.setdefault("descent", {"active_child_id": None, "returned_child_ids": [], "calls": 0})
        if descent.get("active_child_id"):
            raise ValueError("a frame may have only one active recursive child")
        if gap["status"] != "open":
            raise ValueError("only open gaps can expand")
        if not str(selection_rationale).strip():
            raise ValueError("recursive descent requires a selection rationale")
        if descent.get("calls", 0) >= self.descent_policy()["max_calls_per_frame"]:
            raise ValueError("frame exceeded its recursive descent call budget")
        ranked = self.frontier(frame_id)
        selected = next((item for item in ranked if item["gap_id"] == gap_id), None)
        if selected is None:
            raise ValueError("selected gap is not in the deferred frontier")
        decision = self.frontier_decision(frame_id, ranked)
        if decision["reason_code"] in {"max_depth_reached", "per_frame_call_budget_reached"}:
            raise ValueError(f"recursive descent blocked: {decision['reason']}")
        proposal = dict(proposal)
        proposal.setdefault("information_gap", gap["description"])
        proposal.setdefault("discriminator", gap["discriminator"])
        proposal.setdefault("expected_update", gap["expected_update"])
        proposal.setdefault("evidence_requirement", gap["evidence_requirement"])
        proposal.setdefault("trigger_cognition_ids", gap["trigger_cognition_ids"])
        proposal.setdefault("intent_clause_ids", frame["intent_clause_ids"])
        frame_id, created = self.add_frame(proposal, parent_gap=gap_id)
        gap["status"] = "expanded" if created else "merged"
        self.data["frontier"][gap_id]["status"] = "active"
        descent["active_child_id"] = frame_id
        descent["calls"] = descent.get("calls", 0) + 1
        frame = self.data["frames"][gap["frame_id"]]
        frame["state"] = "waiting_child"
        self.relation(gap["frame_id"], frame_id, "calls", selection_rationale)
        override = (decision["recommendation"] != "descend" or
                    decision["recommended_gap_id"] != gap_id)
        if override:
            self.event("frontier_recommendation_overridden", parent_frame_id=gap["frame_id"], gap_id=gap_id,
                       recommendation=decision["recommendation"], reason_code=decision["reason_code"],
                       recommended_gap_id=decision["recommended_gap_id"], rationale=selection_rationale)
        self.event("recursive_descent", parent_frame_id=gap["frame_id"], gap_id=gap_id, child_frame_id=frame_id,
                   created=created, frontier_score=selected["score"],
                   recommendation=decision["recommendation"], reason_code=decision["reason_code"])
        return {"gap_id": gap_id, "frame_id": frame_id, "created": created, "frontier_score": selected["score"],
                "recommendation": decision["recommendation"], "selection_overrode_recommendation": override}

    def expand(self, gap_id: str, proposal: dict) -> dict:
        return self.descend(self.data["gaps"][gap_id]["frame_id"], gap_id, proposal, "manual descent selection")

    def return_child(self, frame_id: str, child_frame_id: str, rationale: str) -> dict:
        frame = self.data["frames"][frame_id]
        descent = frame.setdefault("descent", {"active_child_id": None, "returned_child_ids": [], "calls": 0})
        if frame["state"] != "waiting_child" or descent.get("active_child_id") != child_frame_id:
            raise ValueError("child is not the active recursive call for this frame")
        child = self.data["frames"][child_frame_id]
        if child["state"] not in TERMINAL:
            raise ValueError("a recursive child can return only after reaching a terminal state")
        if not str(rationale).strip():
            raise ValueError("recursive return requires a reduction rationale")
        descent["returned_child_ids"].append(child_frame_id)
        descent["active_child_id"] = None
        frame["state"] = "expanded"
        confidence = float(child.get("return", {}).get("confidence", 1.0))
        threshold = self.descent_policy()["return_revisit_confidence"]
        reactivation = {"frame_id": frame_id, "gap_ids": [], "reason": ""}
        if confidence < threshold:
            reactivation = self.reactivate_frontier(frame_id, "selected child returned low confidence")
        self.relation(child_frame_id, frame_id, "returns_to", rationale)
        self.event("recursive_return", parent_frame_id=frame_id, child_frame_id=child_frame_id, rationale=rationale)
        return {"frame_id": frame_id, "child_frame_id": child_frame_id, "state": frame["state"],
                "frontier_reactivation": reactivation}

    def finish(self, frame_id: str, state: str, summary: str, confidence: float = 0.0) -> dict:
        if state not in TERMINAL:
            raise ValueError("finish requires a terminal state")
        frame = self.data["frames"][frame_id]
        if frame["state"] != "expanded" and not (
            state == "gap_user_input" and frame["state"] in {"open", "blocked_on_user"}
        ):
            raise ValueError("finish requires an expanded frame after collection and extraction")
        if frame.get("descent", {}).get("active_child_id"):
            raise ValueError("cannot return while a recursive child is active")
        if frame["state"] == "expanded":
            decision = self.frontier_decision(frame_id)
            if decision["recommendation"] == "descend":
                raise ValueError(
                    "cannot finish while a clear frontier descent remains; select the recommended gap or exhaust its budget"
                )
        if state in {"resolved", "contradicted"} and not frame["cognition_ids"]:
            raise ValueError(f"{state} requires at least one cited cognition")
        coverage_issues = self._frame_source_coverage_issues(frame)
        if coverage_issues:
            raise ValueError("cannot finish before source coverage passes: " + "; ".join(coverage_issues))
        frame["state"] = state
        frame["return"] = {"summary": summary, "confidence": float(confidence), "at": now_iso()}
        self.event("frame_finished", frame_id=frame_id, state=state, confidence=confidence)
        return {"frame_id": frame_id, "state": state}

    def reopen(self, frame_id: str, reason: str) -> dict:
        frame = self.data["frames"][frame_id]
        if frame["state"] not in TERMINAL:
            raise ValueError("only terminal frames can reopen")
        frame["state"] = "open"
        frame["return"] = None
        self.event("frame_reopened", frame_id=frame_id, reason=reason)
        return {"frame_id": frame_id, "state": "open"}

    def next(self) -> dict:
        intent_contract = self.intent_contract()
        if intent_contract["status"] == "pending":
            return {"action": "analyze_intent", "intent": self.current_intent()["raw"],
                    "registered_materials": list(self.data.get("materials", {}).values()),
                    "prior_answers": intent_contract.get("answers", {}),
                    "reason": "derive the required research, material-analysis, design, and writing contract before creating search frames"}
        if intent_contract["status"] == "needs_clarification":
            return {"action": "clarify_intent", "questions": intent_contract.get("questions", []),
                    "reason": "user intent has unresolved, decision-relevant ambiguity or missing inputs"}

        def runnable(state: str) -> list[dict]:
            return [frame for frame in self.data["frames"].values()
                    if frame["state"] == state and not self.blocked_clauses_for(frame)]

        open_frames = runnable("open")
        if open_frames:
            frame = max(open_frames, key=lambda item: (item["priority"], item["created_at"]))
            return {"action": "formulate", "frame": frame}
        acquiring = runnable("acquiring")
        if acquiring:
            return {"action": "discover_and_materialize", "frame": acquiring[0],
                    "reason": "run every eligible provider, archive raw responses, and persist the bounded source set"}
        aggregating = runnable("aggregating")
        if aggregating:
            return {"action": "aggregate_saved_sources", "frame": aggregating[0],
                    "reason": "saved sources require hash-bound topic de-duplication and rubric-scored quality/confidence before review"}
        reviewing = runnable("reviewing")
        if reviewing:
            frame = reviewing[0]
            self._verified_aggregation(frame)
            review = frame.get("review", {})
            expected = review.get("expected_roles", [])
            completed = set(review.get("completed_roles", []))
            return {"action": "review_saved_sources", "frame": frame,
                    "remaining_roles": [role for role in expected if role not in completed],
                    "reason": "saved source collection must be reviewed before cognition extraction"}
        extracting = runnable("extracting")
        if extracting:
            return {"action": "extract", "frame": extracting[0],
                    "reason": "propose cited cognitions and information gaps"}
        expanded = runnable("expanded")
        if expanded:
            frame = expanded[0]
            frontier = self.frontier(frame["id"])
            decision = self.frontier_decision(frame["id"], frontier)
            if frontier and decision["recommendation"] != "return":
                return {"action": "choose_descent", "frame": frame, "frontier": frontier,
                        "decision": decision, "reason": decision["reason"]}
            return {"action": "return", "frame": frame,
                    "frontier": frontier, "decision": decision, "reason": decision["reason"]}
        waiting = runnable("waiting_child")
        if waiting:
            return {"action": "await_child", "frame": waiting[0],
                    "reason": "the selected recursive call must return before the parent can continue"}
        blocked = []
        seen = set()
        for frame in self.data["frames"].values():
            if frame["state"] not in ACTIVE:
                continue
            for clause in self.blocked_clauses_for(frame):
                if clause["id"] not in seen:
                    blocked.append(clause)
                    seen.add(clause["id"])
        if blocked:
            return {"action": "clarify", "clauses": blocked,
                    "reason": "remaining active frames need user resolution"}
        decision = self.decision_synthesis_audit()
        if decision["required"] and not decision["ok"]:
            return {"action": "synthesize_decision", "decision_questions": self.decision_questions(),
                    "decision_synthesis": self._decision_synthesis_record(),
                    "reason": "all research frames are terminal but the decision evidence, conditions, and unknowns have not been synthesized"}
        return {"action": "freeze_ready", "reason": "no executable frames remain"}

    def time_audit(self) -> dict:
        issues = []
        warnings = []
        for frame in self.data["frames"].values():
            scope = frame.get("temporal_scope") or {}
            start = end = None
            scope_valid = True
            if scope:
                field = scope.get("field", "published_at")
                try:
                    start = parse_time(scope["start"]) if scope.get("start") else None
                    end = parse_time(scope["end"]) if scope.get("end") else None
                except ValueError as exc:
                    issues.append({"frame_id": frame["id"], "issue": f"invalid temporal scope: {exc}"})
                    scope_valid = False
                if scope_valid and start and end and start > end:
                    issues.append({"frame_id": frame["id"], "issue": "temporal scope start is after end"})
                    scope_valid = False
                if scope_valid:
                    cited_evidence_ids = {
                        span.get("evidence_id")
                        for cognition_id in frame["cognition_ids"]
                        for span in self.data["cognitions"][cognition_id].get("source_spans", [])
                        if isinstance(span, dict) and isinstance(span.get("evidence_id"), str)
                    }
                    for evidence_id in frame["evidence_ids"]:
                        evidence = self.data["evidence"][evidence_id]
                        value = evidence.get(field)
                        target = issues if evidence_id in cited_evidence_ids else warnings
                        if not value:
                            target.append({"frame_id": frame["id"], "evidence_id": evidence_id,
                                           "issue": f"missing {field}",
                                           "used_by_cognition": evidence_id in cited_evidence_ids})
                            continue
                        try:
                            observed = parse_time(value)
                        except ValueError as exc:
                            target.append({"frame_id": frame["id"], "evidence_id": evidence_id,
                                           "issue": f"invalid {field}: {exc}",
                                           "used_by_cognition": evidence_id in cited_evidence_ids})
                            continue
                        if start and observed < start or end and observed > end:
                            target.append({"frame_id": frame["id"], "evidence_id": evidence_id,
                                           "issue": f"{field} outside temporal scope",
                                           "used_by_cognition": evidence_id in cited_evidence_ids})
            for cognition_id in frame["cognition_ids"]:
                cognition = self.data["cognitions"][cognition_id]
                if not str(cognition.get("context_signature", "")).strip():
                    issues.append({"frame_id": frame["id"], "cognition_id": cognition_id,
                                   "issue": "missing context_signature"})
                try:
                    cognition_time = parse_time(cognition.get("evidence_time"))
                except ValueError as exc:
                    issues.append({"frame_id": frame["id"], "cognition_id": cognition_id,
                                   "issue": f"invalid evidence_time: {exc}"})
                    continue
                if start and cognition_time < start or end and cognition_time > end:
                    issues.append({"frame_id": frame["id"], "cognition_id": cognition_id,
                                   "issue": "evidence_time outside temporal scope"})
        return {"ok": not issues, "issues": issues, "warnings": warnings, "validated_at": now_iso()}

    def publication_audit(self) -> dict:
        issues = []
        for frame in self.data["frames"].values():
            if frame["state"] in {"resolved", "contradicted"} and not frame["cognition_ids"]:
                issues.append({"frame_id": frame["id"], "issue": "terminal claim has no cited cognition"})
        return {"ok": not issues, "issues": issues}

    def aggregation_audit(self) -> dict:
        """Validate every collection-derived assessment before it can freeze."""

        issues = []
        for frame in self.data["frames"].values():
            if not frame.get("collection"):
                continue
            try:
                self._verified_aggregation(frame)
            except ValueError as exc:
                issues.append({"frame_id": frame["id"], "issue": str(exc)})
        return {"ok": not issues, "issues": issues}

    def delivery_research_audit(self) -> dict:
        """Ensure required research deliverables retain an auditable terminal input."""

        record = self.intent_contract()
        contract = record.get("contract")
        if record.get("legacy") or not isinstance(contract, dict):
            return {"ok": True, "issues": []}
        deliverables = contract.get("deliverables", [])
        if not isinstance(deliverables, list):
            return {"ok": False, "issues": [{"issue": "intent contract deliverables are invalid"}]}
        issues = []
        frames = list(self.data["frames"].values())
        for deliverable in deliverables:
            if not isinstance(deliverable, dict) or not (
                deliverable.get("required") and deliverable.get("requires_research")
            ):
                continue
            deliverable_id = deliverable.get("id")
            refs = deliverable.get("research_frame_refs")
            if refs is None:
                # Compatibility with runs created before explicit frame binding.
                candidates = frames
            else:
                candidates = [
                    frame for frame in frames
                    if frame.get("contract_ref") in refs or deliverable_id in frame.get("deliverable_ids", [])
                ]
            if not candidates:
                issues.append({"deliverable_id": deliverable_id, "issue": "required research has no bound frame"})
                continue
            terminal = [frame for frame in candidates if frame.get("state") in TERMINAL]
            if not terminal:
                issues.append({"deliverable_id": deliverable_id, "issue": "required research has no terminal bound frame"})
                continue
            if not any(frame.get("cognition_ids") for frame in terminal):
                issues.append({"deliverable_id": deliverable_id, "issue": "required research has no cited cognition"})
        return {"ok": not issues, "issues": issues}

    def freeze(self, snapshot_id: str | None = None) -> dict:
        self.require_intent_ready()
        active = [frame["id"] for frame in self.data["frames"].values() if frame["state"] in ACTIVE]
        if active:
            raise ValueError(f"cannot freeze with active frames: {', '.join(active)}")
        audit = self.time_audit()
        if not audit["ok"]:
            raise ValueError("cannot freeze before temporal audit passes")
        publication = self.publication_audit()
        if not publication["ok"]:
            raise ValueError("cannot freeze with unsupported terminal claims")
        aggregation = self.aggregation_audit()
        if not aggregation["ok"]:
            raise ValueError("cannot freeze before saved-source aggregation audit passes")
        delivery_research = self.delivery_research_audit()
        if not delivery_research["ok"]:
            raise ValueError("cannot freeze before required research deliverables have terminal cited inputs")
        coverage = self.source_coverage_audit()
        if not coverage["ok"]:
            raise ValueError("cannot freeze before source coverage audit passes")
        decision = self.decision_synthesis_audit()
        if not decision["ok"]:
            raise ValueError("cannot freeze before decision synthesis audit passes")
        materials = self.material_audit()
        if not materials["ok"]:
            raise ValueError("cannot freeze before user material audit passes")
        snapshot_id = safe_snapshot_id(snapshot_id or f"research-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
        self.event("snapshot_frozen", snapshot_id=snapshot_id)
        return default_repository().write_snapshot(snapshot_id, self.data, now_iso())

    def status(self) -> dict:
        states = {}
        for frame in self.data["frames"].values():
            states[frame["state"]] = states.get(frame["state"], 0) + 1
        intent_contract = self.intent_contract()
        return {"intent_version": self.data["current_intent_version"], "reference_time": self.data["reference_time"],
                "intent_contract": {"status": intent_contract["status"], "version": intent_contract.get("version", 0),
                                     "questions": intent_contract.get("questions", [])},
                "decision_synthesis": {
                    "required": self.decision_synthesis_required(),
                    "status": self._decision_synthesis_record().get("status"),
                    "audit": self.decision_synthesis_audit(),
                },
                "frames": len(self.data["frames"]), "evidence": len(self.data["evidence"]),
                "cognitions": len(self.data["cognitions"]), "gaps": len(self.data["gaps"]),
                "frame_states": states, "blocked_clauses": self.blocked_clauses(),
                "descent_policy": self.descent_policy(), "next": self.next()}
