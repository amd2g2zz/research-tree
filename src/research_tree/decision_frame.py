"""Evidence-aware requester intent and the pre-strategy DecisionFrame gate."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping, Sequence

from .domain import ArtifactRef, RuntimeStoreError, canonical_json_bytes, validate_identifier


DECISION_FRAME_KIND = "decision-frame"
DECISION_FRAME_SCHEMA_VERSION = 1
HYPOTHESIS_OWNERS = frozenset({"requester", "research", "shared"})
HYPOTHESIS_DISPOSITIONS = frozenset(
    {"unresolved", "selected", "accepted", "rejected", "reframed", "retained_consequence", "deferred"}
)
POLICY_ACTIONS = frozenset({"reconnaissance", "ask_user", "reframe", "ready"})
FRAME_STATUSES = frozenset(
    {"clarification_required", "reconnaissance_required", "reframe_required", "ready_for_strategy", "superseded"}
)
_RESOLVED_DISPOSITIONS = frozenset({"selected", "accepted", "rejected", "reframed", "retained_consequence"})


class DecisionFrameValidationError(RuntimeStoreError):
    """Raised when a DecisionFrame would lose intent or lineage evidence."""


@dataclass(frozen=True, slots=True)
class IntentHypothesis:
    """One competing interpretation of the request."""

    id: str
    interpretation: str
    ambiguity: str
    owner: str
    researchable: bool
    decision_consequence: str
    source_refs: tuple[str, ...]
    disposition: str
    next_action: str
    primary_decision_id: str
    material: bool = True
    evidence_ranked: bool = False
    no_progress: bool = False

    def __post_init__(self) -> None:
        _identifier(self.id, "hypothesis id")
        _text(self.interpretation, "hypothesis interpretation")
        _text(self.ambiguity, "hypothesis ambiguity")
        if self.owner not in HYPOTHESIS_OWNERS:
            raise DecisionFrameValidationError(f"hypothesis owner is unsupported: {self.owner!r}")
        if not isinstance(self.researchable, bool):
            raise DecisionFrameValidationError("hypothesis researchable must be bool")
        _text(self.decision_consequence, "hypothesis decision_consequence")
        if isinstance(self.source_refs, (str, bytes)) or not isinstance(self.source_refs, Sequence):
            raise DecisionFrameValidationError("hypothesis source_refs must be a sequence")
        refs = tuple(_text(ref, "hypothesis source_ref") for ref in self.source_refs)
        if not refs:
            raise DecisionFrameValidationError("hypothesis source_refs must not be empty")
        object.__setattr__(self, "source_refs", refs)
        if self.disposition not in HYPOTHESIS_DISPOSITIONS:
            raise DecisionFrameValidationError(f"hypothesis disposition is unsupported: {self.disposition!r}")
        _text(self.next_action, "hypothesis next_action")
        _identifier(self.primary_decision_id, "hypothesis primary_decision_id")
        if not isinstance(self.material, bool) or not isinstance(self.evidence_ranked, bool):
            raise DecisionFrameValidationError("hypothesis material/evidence_ranked must be bool")
        if not isinstance(self.no_progress, bool):
            raise DecisionFrameValidationError("hypothesis no_progress must be bool")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "interpretation": self.interpretation,
            "ambiguity": self.ambiguity,
            "owner": self.owner,
            "researchable": self.researchable,
            "decision_consequence": self.decision_consequence,
            "source_refs": list(self.source_refs),
            "disposition": self.disposition,
            "next_action": self.next_action,
            "primary_decision_id": self.primary_decision_id,
            "material": self.material,
            "evidence_ranked": self.evidence_ranked,
            "no_progress": self.no_progress,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "IntentHypothesis":
        if not isinstance(value, Mapping):
            raise DecisionFrameValidationError("hypothesis must be a mapping")
        required = {
            "id",
            "interpretation",
            "ambiguity",
            "owner",
            "researchable",
            "decision_consequence",
            "source_refs",
            "disposition",
            "next_action",
            "primary_decision_id",
            "material",
            "evidence_ranked",
        }
        missing = required - set(value)
        extra = set(value) - (required | {"no_progress"})
        if missing or extra:
            raise DecisionFrameValidationError(
                f"hypothesis keys invalid; missing={sorted(missing)}, extra={sorted(extra)}"
            )
        return cls(
            id=value["id"],
            interpretation=value["interpretation"],
            ambiguity=value["ambiguity"],
            owner=value["owner"],
            researchable=value["researchable"],
            decision_consequence=value["decision_consequence"],
            source_refs=tuple(value["source_refs"]),
            disposition=value["disposition"],
            next_action=value["next_action"],
            primary_decision_id=value["primary_decision_id"],
            material=value["material"],
            evidence_ranked=value["evidence_ranked"],
            no_progress=value.get("no_progress", False),
        )


@dataclass(frozen=True, slots=True)
class ClarificationDecision:
    """Deterministic next action for unresolved intent."""

    action: str
    reason: str
    hypothesis_ids: tuple[str, ...]
    question: str | None = None

    def __post_init__(self) -> None:
        if self.action not in POLICY_ACTIONS:
            raise DecisionFrameValidationError(f"policy action is unsupported: {self.action!r}")
        _text(self.reason, "policy reason")
        ids = tuple(_identifier(item, "policy hypothesis_id") for item in self.hypothesis_ids)
        if len(set(ids)) != len(ids):
            raise DecisionFrameValidationError("policy hypothesis_ids must be unique")
        object.__setattr__(self, "hypothesis_ids", ids)
        if self.question is not None:
            _text(self.question, "policy question")
            if len(self.question) > 500:
                raise DecisionFrameValidationError("policy question exceeds 500 characters")
        if self.action == "ask_user" and not self.question:
            raise DecisionFrameValidationError("ask_user policy requires a question")
        if self.action != "ask_user" and self.question is not None:
            raise DecisionFrameValidationError("only ask_user policy may contain a question")

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "hypothesis_ids": list(self.hypothesis_ids),
            "question": self.question,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "ClarificationDecision":
        if not isinstance(value, Mapping) or set(value) != {"action", "reason", "hypothesis_ids", "question"}:
            raise DecisionFrameValidationError("policy must contain action, reason, hypothesis_ids, and question")
        return cls(
            action=value["action"],
            reason=value["reason"],
            hypothesis_ids=tuple(value["hypothesis_ids"]),
            question=value["question"],
        )


class ClarificationPolicy:
    """Select reconnaissance or one bounded requester question without keywords."""

    def evaluate(self, frame: "DecisionFrame") -> ClarificationDecision:
        return _evaluate_policy(frame.hypotheses)


@dataclass(frozen=True, slots=True)
class DecisionFrame:
    """Immutable intent decision surface that precedes strategy formation."""

    frame_id: str
    run_id: str
    requester_wording: str
    primary_decision: Mapping[str, str]
    hypotheses: tuple[IntentHypothesis, ...]
    target_ref: ArtifactRef | None = None
    selected_hypothesis_id: str | None = None
    status: str | None = None
    policy: ClarificationDecision | None = None
    parent_refs: tuple[ArtifactRef, ...] = ()
    schema_version: int = DECISION_FRAME_SCHEMA_VERSION
    content_hash: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.frame_id, "frame_id")
        _identifier(self.run_id, "run_id")
        _text(self.requester_wording, "requester_wording")
        if len(self.requester_wording) > 20_000:
            raise DecisionFrameValidationError("requester_wording exceeds 20000 characters")
        decision = _decision(self.primary_decision)
        object.__setattr__(self, "primary_decision", decision)
        hypotheses = tuple(self.hypotheses)
        if not hypotheses:
            raise DecisionFrameValidationError("DecisionFrame requires at least one hypothesis")
        if any(not isinstance(item, IntentHypothesis) for item in hypotheses):
            raise DecisionFrameValidationError("hypotheses must contain IntentHypothesis values")
        if len({item.id for item in hypotheses}) != len(hypotheses):
            raise DecisionFrameValidationError("hypothesis ids must be unique")
        if any(item.primary_decision_id != decision["id"] for item in hypotheses):
            raise DecisionFrameValidationError("every hypothesis must trace to primary_decision")
        object.__setattr__(self, "hypotheses", hypotheses)
        if self.target_ref is not None and not isinstance(self.target_ref, ArtifactRef):
            object.__setattr__(self, "target_ref", ArtifactRef.from_dict(self.target_ref))
        refs = tuple(self.parent_refs)
        if any(not isinstance(item, ArtifactRef) for item in refs):
            raise DecisionFrameValidationError("parent_refs must contain ArtifactRef values")
        object.__setattr__(self, "parent_refs", refs)
        selected = self.selected_hypothesis_id
        if selected is None:
            selected_candidates = [item.id for item in hypotheses if item.disposition == "selected"]
            if len(selected_candidates) == 1:
                selected = selected_candidates[0]
                object.__setattr__(self, "selected_hypothesis_id", selected)
        if selected is not None:
            _identifier(selected, "selected_hypothesis_id")
            selected_item = next((item for item in hypotheses if item.id == selected), None)
            if selected_item is None or selected_item.disposition != "selected":
                raise DecisionFrameValidationError("selected_hypothesis_id must identify a selected hypothesis")
        policy = self.policy or _evaluate_policy(hypotheses)
        if not isinstance(policy, ClarificationDecision):
            policy = ClarificationDecision.from_dict(policy)
        object.__setattr__(self, "policy", policy)
        computed_status = _status_for(hypotheses, policy)
        if self.status is None:
            object.__setattr__(self, "status", computed_status)
        elif self.status not in FRAME_STATUSES:
            raise DecisionFrameValidationError(f"frame status is unsupported: {self.status!r}")
        elif self.status != computed_status and self.status != "superseded":
            raise DecisionFrameValidationError("frame status does not match hypotheses and policy")
        if self.schema_version != DECISION_FRAME_SCHEMA_VERSION:
            raise DecisionFrameValidationError("unsupported DecisionFrame schema_version")
        expected = _digest(self._unsigned_dict())
        if self.content_hash is not None and self.content_hash != expected:
            raise DecisionFrameValidationError("DecisionFrame content_hash does not match canonical payload")
        object.__setattr__(self, "content_hash", expected)

    @classmethod
    def create(cls, **kwargs: Any) -> "DecisionFrame":
        return cls(**kwargs)

    def _unsigned_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "frame_id": self.frame_id,
            "run_id": self.run_id,
            "target_ref": self.target_ref.to_dict() if self.target_ref else None,
            "requester_wording": self.requester_wording,
            "primary_decision": dict(self.primary_decision),
            "hypotheses": [item.to_dict() for item in self.hypotheses],
            "selected_hypothesis_id": self.selected_hypothesis_id,
            "status": self.status,
            "policy": self.policy.to_dict(),
            "parent_refs": [item.to_dict() for item in self.parent_refs],
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._unsigned_dict(), "content_hash": self.content_hash}

    @classmethod
    def from_dict(cls, value: Any) -> "DecisionFrame":
        if not isinstance(value, Mapping):
            raise DecisionFrameValidationError("DecisionFrame must be a mapping")
        expected = {
            "schema_version",
            "frame_id",
            "run_id",
            "target_ref",
            "requester_wording",
            "primary_decision",
            "hypotheses",
            "selected_hypothesis_id",
            "status",
            "policy",
            "parent_refs",
            "content_hash",
        }
        if set(value) != expected:
            raise DecisionFrameValidationError(f"DecisionFrame keys invalid: {sorted(set(value) ^ expected)}")
        return cls(
            frame_id=value["frame_id"],
            run_id=value["run_id"],
            requester_wording=value["requester_wording"],
            primary_decision=value["primary_decision"],
            hypotheses=tuple(IntentHypothesis.from_dict(item) for item in value["hypotheses"]),
            target_ref=None if value["target_ref"] is None else ArtifactRef.from_dict(value["target_ref"]),
            selected_hypothesis_id=value["selected_hypothesis_id"],
            status=value["status"],
            policy=ClarificationDecision.from_dict(value["policy"]),
            parent_refs=tuple(ArtifactRef.from_dict(item) for item in value["parent_refs"]),
            schema_version=value["schema_version"],
            content_hash=value["content_hash"],
        )


def _evaluate_policy(hypotheses: Sequence[IntentHypothesis]) -> ClarificationDecision:
    unresolved = sorted(
        (item for item in hypotheses if item.material and item.disposition not in _RESOLVED_DISPOSITIONS),
        key=lambda item: item.id,
    )
    if not unresolved:
        selected = tuple(item.id for item in hypotheses if item.disposition == "selected")
        return ClarificationDecision("ready", "all material hypotheses have an explicit disposition", selected)
    stalled = [item for item in unresolved if item.no_progress]
    if stalled:
        return ClarificationDecision(
            "reframe",
            "reconnaissance made no progress; reframe or retain the explicit consequence",
            tuple(item.id for item in stalled),
        )
    researchable = [item for item in unresolved if item.researchable]
    if researchable and len(researchable) == len(unresolved):
        return ClarificationDecision(
            "reconnaissance",
            "available evidence can investigate the unresolved interpretations",
            tuple(item.id for item in researchable),
        )
    requester = [item for item in unresolved if item.owner == "requester" and not item.researchable]
    if requester:
        selected = requester[: min(3, len(requester))]
        labels = "; ".join(item.interpretation for item in selected)
        return ClarificationDecision(
            "ask_user",
            "a material requester-owned choice cannot be ranked by available evidence",
            tuple(item.id for item in selected),
            f"Which interpretation should guide the primary decision: {labels}?",
        )
    return ClarificationDecision(
        "reconnaissance",
        "unresolved shared ambiguity is bounded for evidence gathering",
        tuple(item.id for item in unresolved),
    )


def _status_for(hypotheses: Sequence[IntentHypothesis], policy: ClarificationDecision) -> str:
    if policy.action == "ready":
        return "ready_for_strategy"
    if policy.action == "ask_user":
        return "clarification_required"
    if policy.action == "reframe":
        return "reframe_required"
    return "reconnaissance_required"


def _decision(value: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"id", "statement", "success_signal"}:
        raise DecisionFrameValidationError("primary_decision requires id, statement, and success_signal")
    return {
        "id": _identifier(value["id"], "primary_decision id"),
        "statement": _text(value["statement"], "primary_decision statement"),
        "success_signal": _text(value["success_signal"], "primary_decision success_signal"),
    }


def _identifier(value: Any, label: str) -> str:
    try:
        return validate_identifier(value, label)
    except (TypeError, ValueError, RuntimeStoreError) as error:
        raise DecisionFrameValidationError(str(error)) from error


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DecisionFrameValidationError(f"{label} must be a non-empty string")
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


__all__ = [
    "DECISION_FRAME_KIND",
    "DECISION_FRAME_SCHEMA_VERSION",
    "ClarificationDecision",
    "ClarificationPolicy",
    "DecisionFrame",
    "DecisionFrameValidationError",
    "IntentHypothesis",
]
