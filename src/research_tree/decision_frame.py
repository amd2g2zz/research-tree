"""Evidence-aware requester intent and the pre-strategy DecisionFrame gate."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

try:
    from .domain import ArtifactRef, RuntimeStoreError, canonical_json_bytes, validate_identifier
except ImportError:  # packaged single-file layout: domain ships beside this script (#470)
    from domain import (  # type: ignore[no-redef]
        ArtifactRef,
        RuntimeStoreError,
        canonical_json_bytes,
        validate_identifier,
    )
try:
    from .turn_contract import (
        NODE_ID_RE,
        RESPONSE_CLASS_DISCRIMINATION,
        RESPONSE_CLASS_GENERATION,
        RESPONSE_CLASSES,
        ContractTerms,
        CostCap,
    )
except ImportError:  # packaged single-file layout: the seam ships beside this script (#470)
    from turn_contract import (  # type: ignore[no-redef]
        NODE_ID_RE,
        RESPONSE_CLASS_DISCRIMINATION,
        RESPONSE_CLASS_GENERATION,
        RESPONSE_CLASSES,
        ContractTerms,
        CostCap,
    )

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


# --- Issue #490: user-response policy table over contract terms -----------
#
# The hook's five prompt-signal classes stop being metadata-only: the table
# below maps an observed signal (category / confidence / rule from
# ``lifecycle_hook.classify_prompt_signal``) plus the outstanding ask (the
# latest turn record's contract terms) onto deterministic contract-term
# adjustments — a ``cost_cap`` adjustment, ``taboos`` refresh, and a
# ``target_gap`` directive — plus the user move typed into the seam's
# response classes. Rule-governed bookkeeping per the 2026-09-03 scope
# ruling; the full comparison (policy table vs bandit vs MDP) and the rule
# rows live in the openspec change ``user-response-contract-signals``.
# ``ClarificationPolicy`` is deliberately untouched: the consumption point
# is contract emission (#489), not action selection.

USER_SIGNAL_CATEGORIES = frozenset({"correction", "interruption", "insight", "answer", "neutral"})
GAP_DIRECTIVES = frozenset({"advance", "reopen", "redirect", "keep"})
USER_MOVE_ADVANCE = "advance"
USER_MOVE_REOPEN = "reopen"
USER_MOVE_REDIRECT = "redirect"
USER_MOVE_KEEP = "keep"
_SIGNAL_CONFIDENCES = frozenset({"high", "medium", "low"})
# One correction bounds the next response to two sentences; a repeated
# correction drops to the one-sentence ``discrimination`` floor. A rule
# carrying the #453 ``+continuation`` downgrade never overturns anything.
_CORRECTION_GENERATION_BUDGET = 2
_CONTINUATION_RULE_SUFFIX = "+continuation"


@dataclass(frozen=True, slots=True)
class UserMoveVerdict:
    """Deterministic contract-term adjustments for one observed user response."""

    user_move: str
    signal_category: str
    signal_confidence: str
    signal_rule: str
    gap_directive: str
    cost_cap: CostCap | None = None
    taboo_additions: tuple[str, ...] = ()
    taboo_removals: tuple[str, ...] = ()
    gap_target: str | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if self.user_move not in RESPONSE_CLASSES:
            raise DecisionFrameValidationError(
                f"user move must be one of the seam response classes: {self.user_move!r}"
            )
        if self.signal_category not in USER_SIGNAL_CATEGORIES:
            raise DecisionFrameValidationError(f"signal category is unsupported: {self.signal_category!r}")
        if self.signal_confidence not in _SIGNAL_CONFIDENCES:
            raise DecisionFrameValidationError(f"signal confidence is unsupported: {self.signal_confidence!r}")
        _text(self.signal_rule, "signal rule")
        if self.gap_directive not in GAP_DIRECTIVES:
            raise DecisionFrameValidationError(f"gap directive is unsupported: {self.gap_directive!r}")
        if self.cost_cap is not None and not isinstance(self.cost_cap, CostCap):
            raise DecisionFrameValidationError(f"cost_cap must be a CostCap: {self.cost_cap!r}")
        additions = _node_ids(self.taboo_additions, "taboo_additions")
        removals = _node_ids(self.taboo_removals, "taboo_removals")
        if set(additions) & set(removals):
            raise DecisionFrameValidationError("taboo_additions and taboo_removals must not overlap")
        object.__setattr__(self, "taboo_additions", additions)
        object.__setattr__(self, "taboo_removals", removals)
        if self.gap_target is not None:
            _node_ids((self.gap_target,), "gap_target")
        _text(self.reason, "verdict reason")

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_move": self.user_move,
            "category": self.signal_category,
            "confidence": self.signal_confidence,
            "rule": self.signal_rule,
            "cost_cap": self.cost_cap.to_dict() if self.cost_cap is not None else None,
            "taboo_additions": list(self.taboo_additions),
            "taboo_removals": list(self.taboo_removals),
            "gap_directive": self.gap_directive,
            "gap_target": self.gap_target,
            "reason": self.reason,
        }


def _node_ids(values: Sequence[str], label: str) -> tuple[str, ...]:
    nodes = tuple(values)
    if any(not isinstance(item, str) or NODE_ID_RE.fullmatch(item) is None for item in nodes):
        raise DecisionFrameValidationError(f"{label} entries must be alignment-graph node ids: {list(nodes)}")
    if len(set(nodes)) != len(nodes):
        raise DecisionFrameValidationError(f"{label} entries must be unique: duplicate in {list(nodes)}")
    return nodes


def _cap_rank(cap: CostCap) -> tuple[int, int]:
    """Rank caps by tightness; lower is tighter (``discrimination``/1 is the floor)."""
    class_rank = 0 if cap.response_class == RESPONSE_CLASS_DISCRIMINATION else 1
    budget = cap.max_sentences if cap.max_sentences is not None else 10**9
    return (class_rank, budget)


def _lower_cost_cap(computed: CostCap, emitted: CostCap | None) -> CostCap:
    """A correction never raises an emitted cap: keep the tighter of the two."""
    if emitted is None or _cap_rank(computed) <= _cap_rank(emitted):
        return computed
    return emitted


def _next_candidate(candidates: Sequence[str], exclude: Sequence[str]) -> str | None:
    excluded = set(exclude)
    for node in candidates:
        if node not in excluded:
            return node
    return None


def resolve_user_response_policy(
    signal: Mapping[str, Any],
    terms: ContractTerms | None = None,
    *,
    previous_category: str | None = None,
    candidates: Sequence[str] = (),
) -> UserMoveVerdict:
    """Resolve the user-response policy table for one observed signal.

    First match wins over the rows documented in the openspec change
    ``user-response-contract-signals``: continuation-qualified corrections
    keep the course; answers taboo the asked node and advance; corrections
    lower the response-production ceiling and re-open the corrected node
    (repeated corrections drop to the one-sentence floor); interruptions
    redirect selection toward the new material and raise the ceiling;
    insights raise the ceiling without redirecting; neutral turns change
    nothing. ``candidates`` (the caller's gap-ranking order) resolve the
    advance/redirect gap target; without candidates the directive alone is
    returned. Raises ``DecisionFrameValidationError`` on malformed input.
    """
    if not isinstance(signal, Mapping):
        raise DecisionFrameValidationError("user-response signal must be a mapping")
    category = signal.get("category")
    confidence = signal.get("confidence")
    rule = signal.get("rule")
    if category not in USER_SIGNAL_CATEGORIES:
        raise DecisionFrameValidationError(f"user-response signal category is unsupported: {category!r}")
    if confidence not in _SIGNAL_CONFIDENCES:
        raise DecisionFrameValidationError(f"user-response signal confidence is unsupported: {confidence!r}")
    if not isinstance(rule, str) or not rule.strip():
        raise DecisionFrameValidationError("user-response signal rule must be a non-empty string")
    if previous_category is not None and previous_category not in USER_SIGNAL_CATEGORIES:
        raise DecisionFrameValidationError(f"previous signal category is unsupported: {previous_category!r}")
    if terms is not None and not isinstance(terms, ContractTerms):
        raise DecisionFrameValidationError(f"terms must be ContractTerms: {terms!r}")
    candidate_nodes = _node_ids(candidates, "candidates")

    asked = terms.target_gap if terms is not None else None
    emitted_cap = terms.cost_cap if terms is not None else None
    tabooed = list(terms.taboos) if terms is not None else []
    provenance = {
        "signal_category": category,
        "signal_confidence": confidence,
        "signal_rule": rule,
    }

    if category == "correction" and rule.endswith(_CONTINUATION_RULE_SUFFIX):
        return UserMoveVerdict(
            user_move=RESPONSE_CLASS_GENERATION,
            gap_directive=USER_MOVE_KEEP,
            reason="correction carried continuation semantics; the course is kept",
            **provenance,
        )
    if category == "answer":
        if asked is not None:
            return UserMoveVerdict(
                user_move=RESPONSE_CLASS_DISCRIMINATION,
                taboo_additions=(asked,),
                gap_directive=USER_MOVE_ADVANCE,
                gap_target=_next_candidate(candidate_nodes, (asked, *tabooed)),
                reason="the ask was answered; the node becomes taboo and selection advances",
                **provenance,
            )
        return UserMoveVerdict(
            user_move=RESPONSE_CLASS_DISCRIMINATION,
            gap_directive=USER_MOVE_KEEP,
            reason="an answer without an outstanding ask settles nothing",
            **provenance,
        )
    if category == "correction":
        repeated = previous_category == "correction"
        cap = _lower_cost_cap(
            CostCap(
                response_class=RESPONSE_CLASS_DISCRIMINATION if repeated else RESPONSE_CLASS_GENERATION,
                max_sentences=1 if repeated else _CORRECTION_GENERATION_BUDGET,
            ),
            emitted_cap,
        )
        return UserMoveVerdict(
            user_move=RESPONSE_CLASS_GENERATION,
            cost_cap=cap,
            taboo_removals=(asked,) if asked is not None else (),
            gap_directive=USER_MOVE_REOPEN if asked is not None else USER_MOVE_KEEP,
            gap_target=asked,
            reason=(
                "repeated correction drops the ceiling to the one-sentence floor and re-opens the corrected node"
                if repeated
                else "correction lowers the response-production ceiling and re-opens the corrected node"
            ),
            **provenance,
        )
    if category == "interruption":
        return UserMoveVerdict(
            user_move=RESPONSE_CLASS_GENERATION,
            cost_cap=CostCap(response_class=RESPONSE_CLASS_GENERATION, max_sentences=None),
            gap_directive=USER_MOVE_REDIRECT,
            gap_target=_next_candidate(candidate_nodes, (asked, *tabooed)),
            reason="interruption/new material redirects selection; the interrupted node stays open",
            **provenance,
        )
    if category == "insight":
        return UserMoveVerdict(
            user_move=RESPONSE_CLASS_GENERATION,
            cost_cap=CostCap(response_class=RESPONSE_CLASS_GENERATION, max_sentences=None),
            gap_directive=USER_MOVE_KEEP,
            reason="insight enriches the current point without redirecting selection",
            **provenance,
        )
    return UserMoveVerdict(
        user_move=RESPONSE_CLASS_GENERATION,
        gap_directive=USER_MOVE_KEEP,
        reason="neutral turn; contract terms stay unchanged",
        **provenance,
    )


__all__ = [
    "DECISION_FRAME_KIND",
    "DECISION_FRAME_SCHEMA_VERSION",
    "GAP_DIRECTIVES",
    "USER_SIGNAL_CATEGORIES",
    "ClarificationDecision",
    "ClarificationPolicy",
    "DecisionFrame",
    "DecisionFrameValidationError",
    "IntentHypothesis",
    "UserMoveVerdict",
    "resolve_user_response_policy",
]
