"""Single SQLite-backed authority for canonical research-run lifecycle state."""

from __future__ import annotations

import hashlib
import importlib.resources
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .contradictions import (
    DISPUTE_PACKET_KIND,
    PROVIDER_VALIDATION_KIND,
    ClaimBoundary,
    ContradictionDetector,
    ContradictionStatus,
    DisputeAuditTrail,
    DisputeDisposition,
    DisputeDispositionError,
    DisputePacket,
    PressureLedger,
    PressureSignal,
    append_signal,
    claim_from_mapping,
    dispute_packet_from_payload,
    evaluate_dispute,
    render_contradiction_packet,
)
from .decision_frame import DECISION_FRAME_KIND, DecisionFrame
from .decision_map import BLUEPRINT_TARGET_KIND
from .domain import (
    ArtifactRef,
    ArtifactRevision,
    InvalidIdentifierError,
    RuntimeStoreError,
    canonical_json_bytes,
    thaw_json,
    validate_identifier,
)
from .feedback import (
    CORRECTION_ACTION_ROLES,
    CORRECTION_AFFECTED_ROLES,
    CORRECTION_EVENT_KIND,
    CORRECTION_ROLE_KINDS,
    STALE_STATE_QUARANTINE_KIND,
    CorrectionBinding,
    CorrectionEvent,
)
from .host_attempts import HostAttemptError, outcome_from_mapping, worker_finished_eligible
from .host_events import HostEvent, HostEventError, HostEventSequenceError
from .independent_review import (
    ALIGNMENT_VERIFICATION_ROLE,
    DELIVERY_REVIEW_ROLE,
    IndependentReviewError,
    validate_alignment_verification_payload,
    validate_delivery_review_payload,
    verify_identity_independent,
)
from .policy import AdaptiveResearchPolicy
from .run_ledger import LedgerConflictError, RunLedger
from .search_portfolio import PortfolioExecution, SearchPortfolio
from .source_capture import ACQUISITION_RECEIPT_KIND, ANALYSIS_CHECKPOINT_KIND, SOURCE_CAPTURE_KIND
from .strategy_projection import (
    STRATEGY_PROJECTION_INVALIDATION_KIND,
    STRATEGY_PROJECTION_INVALIDATION_SCHEMA_VERSION,
    STRATEGY_PROJECTION_KIND,
    StrategyProjection,
    StrategyProjectionError,
    authority_fingerprint,
    latest_confirmed,
    macro_stage,
    validate_falsifiability,
    validate_strategy_projection_invalidation,
)
from .work_items import WORK_ITEM_KIND, CanonicalWorkItemCompiler

FINDING_PACK_KIND = "finding-pack"
CONTRADICTION_PACKET_KIND = "contradiction-packet"
CONTRADICTION_RESOLUTION_KIND = "contradiction-resolution"
CONTRADICTION_RETRACTION_KIND = "contradiction-retraction"
CONTRADICTION_SUCCESSOR_WORK_KIND = "contradiction-successor-work"
STALE_DELIVERY_CLAIM_KIND = "stale-delivery-claim"
SEARCH_PORTFOLIO_LINEAGE_KIND = "search-portfolio-lineage"
HUMAN_DECISION_REOPEN_KIND = "human-decision-reopen"
TECHNICAL_PACKAGE_KIND_ALIAS = "technical-research-package"
HUMAN_RESEARCH_REPORT_KIND = "human-research-report"

logger = logging.getLogger(__name__)


LIFECYCLE_STATES = (
    "alignment",
    "handoff_pending",
    "autonomous_research",
    "synthesis",
    "readiness",
    "delivery_pending",
    "awaiting_acceptance",
    "completed",
    "paused",
    "blocked",
    "superseded",
    "authority_blocked",
    "failed",
)
RESEARCH_RUN_STATE_KIND = "research-run-state"
LIFECYCLE_EVENT_KIND = "lifecycle-event"
REJECTED_TRANSITION_KIND = "lifecycle-rejection"
HOST_EVENT_KIND = "host-event"
HOST_EVENT_PROJECTION_KIND = "host-event-projection"
LEASE_KIND = "attempt-lease"
COMPLETION_RECORD_KIND = "completion-record"
CORRECTION_SENSITIVE_EVENTS = frozenset(
    {
        "alignment_projection_ready",
        "handoff_confirmed",
        "deliveries_compiled",
        "delivery_accepted",
    }
)


GOAL_CONTRIBUTION_ASSESSMENT_KIND = "goal-contribution-assessment"
CONTRIBUTION_VERDICTS = ("advances", "partial", "no_contribution", "contradicts")
_CONTRIBUTION_BLOCKING_VERDICTS = frozenset({"no_contribution", "contradicts"})


class CoordinatorError(RuntimeStoreError):
    """Base coordinator boundary error."""


class CoordinatorConfigError(CoordinatorError):
    """Raised when the canonical governance matrix is missing or malformed.

    ADR-002 mandates that the lifecycle transition matrix is the single
    authority. Silent fallback to a hardcoded table violates that
    contract by hiding governance drift.
    """


class CoordinatorConflictError(CoordinatorError):
    """Raised for stale revisions, invalid lineage, or unverifiable work."""


class CoordinatorEventConflictError(CoordinatorConflictError):
    """Raised when one event id is reused with a changed payload."""


def _projection_entry_ids(entries: Any) -> set[str]:
    ids: set[str] = set()
    for entry in entries or ():
        if isinstance(entry, Mapping) and isinstance(entry.get("id"), str) and entry["id"].strip():
            ids.add(entry["id"])
        elif isinstance(entry, str) and entry.strip():
            ids.add(entry)
    return ids


def _string_tokens(value: Any) -> set[str]:
    """Non-empty trimmed string members of a sequence value."""

    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return set()
    return {entry.strip() for entry in value if isinstance(entry, str) and entry.strip()}


def _mapping_entries(value: Any) -> tuple[Mapping[str, Any], ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return ()
    return tuple(entry for entry in value if isinstance(entry, Mapping))


def _served_evidence_standards(serves: Mapping[str, Any], projection: Mapping[str, Any]) -> dict[str, frozenset[str]]:
    """Evidence standards declared per served success oracle (serves order kept)."""

    served: dict[str, frozenset[str]] = {}
    for oracle_id in serves.get("oracle_ids") or ():
        if not isinstance(oracle_id, str) or not oracle_id.strip():
            continue
        standards: set[str] = set()
        for oracle in _mapping_entries(projection.get("success_oracles")):
            if oracle.get("id") == oracle_id:
                standards |= _string_tokens(oracle.get("evidence_standard_ids"))
        served[oracle_id] = frozenset(standards)
    return served


def _claim_evidence_tokens(pack: Mapping[str, Any], claim_id: str) -> frozenset[str]:
    """Evidence tokens a claim actually carries: grounding identities, provenance
    clusters, and the evidence artifacts its groundings and grounding refs name."""

    tokens: set[str] = set()
    for grounding in _mapping_entries(pack.get("claim_groundings")):
        if grounding.get("claim_id") != claim_id:
            continue
        token = grounding.get("grounding_id")
        if isinstance(token, str) and token.strip():
            tokens.add(token.strip())
        anchor = grounding.get("anchor")
        if isinstance(anchor, Mapping):
            token = anchor.get("ref")
            if isinstance(token, str) and token.strip():
                tokens.add(token.strip())
            reference = anchor.get("artifact_ref")
            if isinstance(reference, Mapping):
                token = reference.get("artifact_id")
                if isinstance(token, str) and token.strip():
                    tokens.add(token.strip())
    for assessment in _mapping_entries(pack.get("claim_assessments")):
        if assessment.get("claim_id") != claim_id:
            continue
        tokens |= _string_tokens(assessment.get("grounding_ids"))
        tokens |= _string_tokens(assessment.get("provenance_clusters"))
        for reference in _mapping_entries(assessment.get("grounding_refs")):
            token = reference.get("artifact_id")
            if isinstance(token, str) and token.strip():
                tokens.add(token.strip())
    return frozenset(tokens)


def _claim_oracle_mapping(
    pack: Mapping[str, Any],
    claim_id: str,
    standards_by_oracle: Mapping[str, frozenset[str]],
) -> tuple[str, str] | None:
    """First served oracle whose evidence standards intersect the claim's evidence
    tokens, as ``(oracle_id, standard_id)``; None when the claim maps to none."""

    tokens = _claim_evidence_tokens(pack, claim_id)
    if not tokens:
        return None
    for oracle_id, standards in standards_by_oracle.items():
        overlap = sorted(tokens & standards)
        if overlap:
            return oracle_id, overlap[0]
    return None


def assess_goal_contribution(pack: Mapping[str, Any], slot: Mapping[str, Any], projection: Mapping[str, Any]):
    """Classify one Finding Pack's contribution to the goal its Decision Slot serves.

    Pure truth table over the pack payload, the slot payload, and the confirmed
    StrategyProjection payload; it never reads the ledger and never reads any
    worker-supplied ``confidence`` field (the verdict is evidence-only by design).

    Verdicts, in short-circuit order:
      1. any pack effect contradicting a slot alternative      -> CONTRADICTS
      2. a supports effect on a slot alternative               -> ADVANCES
      3. a corroborated claim grounding a served oracle's evidence
         standard (the claim's grounding identities, provenance
         clusters, or grounding evidence artifact ids intersect the
         served oracle's ``evidence_standard_ids``)            -> ADVANCES
      4. effects on slot alternatives, claims whose evidence maps
         to a served oracle, or validation against the slot    -> PARTIAL
      5. otherwise, or unverifiable serves wiring (fail-closed) -> NO_CONTRIBUTION
    """

    serves = slot.get("serves") if isinstance(slot, Mapping) else None
    slot_id = slot.get("id") if isinstance(slot, Mapping) else None
    if not isinstance(serves, Mapping):
        return (
            "no_contribution",
            f"Decision Slot {slot_id} carries no serves link to a confirmed strategy-projection target",
        )
    target_id = serves.get("target_id")
    oracle_ids = serves.get("oracle_ids") if isinstance(serves.get("oracle_ids"), Sequence) else ()
    if not isinstance(target_id, str) or not target_id.strip():
        return ("no_contribution", f"Decision Slot {slot_id} serves.target_id is missing")
    projection_targets = _projection_entry_ids(projection.get("decision_targets"))
    projection_oracles = _projection_entry_ids(projection.get("success_oracles"))
    if target_id not in projection_targets:
        return (
            "no_contribution",
            f"serves.target_id {target_id} is not a confirmed strategy-projection decision target",
        )
    unknown_oracles = [oracle_id for oracle_id in oracle_ids if oracle_id not in projection_oracles]
    if unknown_oracles:
        return (
            "no_contribution",
            f"serves.oracle_id {unknown_oracles[0]} is not a confirmed strategy-projection success oracle",
        )
    alternatives = {
        option
        for option in (slot.get("alternatives") if isinstance(slot.get("alternatives"), Sequence) else ())
        if isinstance(option, str) and option.strip()
    }
    effects = pack.get("option_effects") if isinstance(pack.get("option_effects"), Sequence) else ()
    touched = [
        effect
        for effect in effects
        if isinstance(effect, Mapping) and isinstance(effect.get("option"), str) and effect["option"] in alternatives
    ]
    contradicted = next((effect for effect in touched if effect.get("effect") == "contradicts"), None)
    if contradicted is not None:
        return (
            "contradicts",
            f"option_effect contradicts Decision Slot alternative {contradicted['option']} served by target {target_id}",
        )
    supported = next((effect for effect in touched if effect.get("effect") in {"supports"}), None)
    if supported is not None:
        return (
            "advances",
            f"option_effect supports Decision Slot alternative {supported['option']} served by target {target_id}",
        )
    assessments = pack.get("claim_assessments") if isinstance(pack.get("claim_assessments"), Sequence) else ()
    standards_by_oracle = _served_evidence_standards(serves, projection)
    mapping = next(
        (
            (str(assessment["claim_id"]), mapped)
            for assessment in _mapping_entries(assessments)
            if assessment.get("state") == "corroborated"
            and isinstance(assessment.get("claim_id"), str)
            and assessment["claim_id"].strip()
            for mapped in (_claim_oracle_mapping(pack, assessment["claim_id"], standards_by_oracle),)
            if mapped is not None
        ),
        None,
    )
    if mapping is not None:
        claim_id, (oracle_id, standard_id) = mapping
        return (
            "advances",
            f"corroborated claim {claim_id} grounds served oracle {oracle_id} via evidence standard {standard_id}",
        )
    touches_oracle = any(
        _claim_oracle_mapping(pack, str(assessment.get("claim_id")), standards_by_oracle) is not None
        for assessment in _mapping_entries(assessments)
        if isinstance(assessment.get("claim_id"), str) and assessment["claim_id"].strip()
    )
    if touched or touches_oracle or pack.get("validation_result") is not None:
        return (
            "partial",
            f"Finding Pack touches Decision Slot {slot_id} without advancing its alternatives or evidence standards",
        )
    return (
        "no_contribution",
        f"Finding Pack {pack.get('id')} touches neither the Decision Slot alternatives nor the served evidence standards",
    )


def partition_goal_contributions(
    ledger: RunLedger,
    round_id: str,
    finding_packs: Sequence[ArtifactRevision],
) -> tuple[tuple[ArtifactRevision, ...], tuple[ArtifactRevision, ...]]:
    """Split candidate packs into (contributing, deferred) for tree consumption.

    Packs whose latest recorded goal-contribution assessment carries a blocking
    verdict (``no_contribution`` or ``contradicts``) are deferred: they never
    enter the tree transition consumed set. In a run with a confirmed projection
    a pending pack with NO recorded assessment is deferred as well (fail closed):
    the compile hook assesses every compile-passed pack, so a missing assessment
    means the hook was interrupted and the pack stays pending instead of being
    silently waved into the consumed set. On-demand re-assessment is not done
    here because the surrounding tree transition already pins ``expected_revision``;
    appending mid-partition would strand it. Runs without a confirmed projection
    have no goal wiring, so every pack contributes (prior behavior unchanged).
    """

    if not finding_packs:
        return (), ()
    snapshot = ledger.load_run(round_id)
    if latest_confirmed(snapshot.artifacts) is None:
        return tuple(finding_packs), ()
    contributing: list[ArtifactRevision] = []
    deferred: list[ArtifactRevision] = []
    for pack in finding_packs:
        if _pack_is_goal_blocking(snapshot.artifacts, pack):
            logger.warning(
                "goal_contribution_pack_deferred: %s@%s (blocking or unassessed verdict)", pack.id, pack.revision
            )
            deferred.append(pack)
        else:
            contributing.append(pack)
    return tuple(contributing), tuple(deferred)


def _pack_is_goal_blocking(artifacts: Sequence[ArtifactRevision], pack: ArtifactRevision) -> bool:
    assessments = sorted(
        (
            item
            for item in artifacts
            if item.kind == GOAL_CONTRIBUTION_ASSESSMENT_KIND
            and item.payload.get("finding_pack_id") == pack.id
            and item.payload.get("finding_pack_revision") == pack.revision
        ),
        key=lambda item: (item.created_at, item.revision),
    )
    if not assessments:
        # Fail closed: an unassessed pack in a goal-wired run stays pending with a
        # visible reason instead of being consumed on a default allow.
        return True
    return assessments[-1].payload.get("verdict") in _CONTRIBUTION_BLOCKING_VERDICTS


class StaleStateError(CoordinatorConflictError):
    """A control action referenced state quarantined by a correction."""

    def __init__(self, action: str, *, reason: str = "stale_digest") -> None:
        self.action = action
        self.reason = reason
        self.next_action = "reenter_alignment"
        super().__init__(reason)


class IllegalTransitionError(CoordinatorError):
    """Raised when a requested lifecycle edge or actor is not allowed."""


class CompletionBlockedError(CoordinatorError):
    """Raised when canonical completion obligations remain unresolved."""

    def __init__(self, unmet_obligations: Sequence[str]) -> None:
        self.unmet_obligations = tuple(unmet_obligations)
        super().__init__("completion_blocked: " + ", ".join(self.unmet_obligations))


@dataclass(frozen=True, slots=True)
class CoordinatorResult:
    code: int
    category: str
    retryability: str
    run_id: str
    safe_message: str
    unmet_obligations: tuple[str, ...] = ()
    evidence_refs: tuple[ArtifactRef, ...] = ()
    next_action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "category": self.category,
            "retryability": self.retryability,
            "run_id": self.run_id,
            "safe_message": self.safe_message,
            "unmet_obligations": list(self.unmet_obligations),
            "evidence_refs": [ref.to_dict() for ref in self.evidence_refs],
            "next_action": self.next_action,
        }


# This is the checked-in lifecycle matrix reduced to executable edges. Guards
# are evaluated by the operation that owns the relevant obligation set.
_TRANSITIONS: dict[tuple[str, str], tuple[str, str]] = {
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


def _load_lifecycle_transitions() -> dict[tuple[str, str], tuple[str, str]]:
    """Load the canonical lifecycle matrix. Raises on missing/malformed.

    The hardcoded ``_TRANSITIONS`` dict is no longer a silent fallback —
    any governance drift now surfaces as ``CoordinatorConfigError``.

    Lookup order:
    1. ``importlib.resources`` from the installed wheel (canonical for production)
    2. Repo-relative path (canonical for editable / dev installs)
    """

    # All candidates use Traversable/Path objects that implement read_text().
    candidates: list[tuple[Any, str]] = [
        # (path, source-label) — try wheel resource first
        (importlib.resources.files("research_tree").joinpath("data/lifecycle-matrix-v1.json"), "wheel_resource"),
        # then repo-relative (editable install / dev)
        (
            Path(__file__).resolve().parents[2]
            / "openspec"
            / "changes"
            / "unify-research-runtime-alpha2"
            / "registries"
            / "lifecycle-matrix-v1.json",
            "repo_relative",
        ),
    ]

    last_error: Exception | None = None
    for path, source in candidates:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, AttributeError) as error:
            logger.error("canonical_lifecycle_matrix_candidate_missing: %s (source=%s, error=%s)", path, source, error)
            last_error = error
            continue
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, ValueError) as error:
            logger.error("canonical_lifecycle_matrix_malformed_json: %s (source=%s)", path, source)
            raise CoordinatorConfigError(
                f"canonical_lifecycle_matrix_malformed_json: {path} (source={source})"
            ) from error
        transitions = payload.get("transitions") if isinstance(payload, Mapping) else None
        if not transitions:
            logger.error("canonical_lifecycle_matrix_malformed_no_transitions: %s (source=%s)", path, source)
            raise CoordinatorConfigError(
                f"canonical_lifecycle_matrix_malformed_no_transitions: {path} (source={source})"
            )
        loaded = {
            (str(item["from"]), str(item["event"])): (str(item["to"]), str(item["actor"])) for item in transitions
        }
        if not loaded:
            logger.error("canonical_lifecycle_matrix_empty_transitions: %s (source=%s)", path, source)
            raise CoordinatorConfigError(f"canonical_lifecycle_matrix_empty_transitions: {path} (source={source})")
        return loaded

    # No source succeeded — surface the most specific error.
    raise CoordinatorConfigError(
        f"canonical_lifecycle_matrix_missing_or_unreadable: tried {[s for _, s in candidates]}; last_error={last_error!r}"
    )


_TRANSITIONS = _load_lifecycle_transitions()


def _ref(value: ArtifactRef | Mapping[str, Any], label: str) -> ArtifactRef:
    if isinstance(value, ArtifactRef):
        return value
    try:
        return ArtifactRef.from_dict(value)
    except (TypeError, ValueError, RuntimeStoreError) as error:
        raise CoordinatorConflictError(f"{label} must be an exact artifact reference") from error


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _delivery_revision_value(artifact: ArtifactRevision, field: str) -> str:
    payload = artifact.payload
    manifest = payload.get("manifest") if isinstance(payload, Mapping) else None
    value = manifest.get(field) if isinstance(manifest, Mapping) else None
    if isinstance(value, str) and value.strip():
        return value
    return f"{artifact.id}@{artifact.revision}"


def _delivery_pair_digest(run_id: str, technical_revision: str, human_revision: str) -> str:
    from .acceptance import delivery_pair_digest

    return delivery_pair_digest(run_id, technical_revision, human_revision)


def _same_payload(existing: ArtifactRevision, payload: Mapping[str, Any]) -> bool:
    return canonical_json_bytes(thaw_json(existing.payload)) == canonical_json_bytes(payload)


class ResearchRunCoordinator:
    """The sole writer of lifecycle and completion state for one RunLedger."""

    event_conflict_error = CoordinatorEventConflictError
    stale_state_error = StaleStateError

    STATE_REGIONS = ("cognitive", "workflow", "authority", "epistemic", "delivery")

    def __init__(
        self,
        ledger: RunLedger,
        *,
        actor_id: str = "coordinator",
        policy: AdaptiveResearchPolicy | None = None,
    ) -> None:
        if not isinstance(ledger, RunLedger):
            raise CoordinatorConflictError("ResearchRunCoordinator requires a RunLedger")
        self.ledger = ledger
        self.actor_id = validate_identifier(actor_id, "actor_id")
        self.policy = policy

    def _load(self, reference: ArtifactRef, kind: str) -> ArtifactRevision:
        try:
            item = self.ledger.get_artifact(reference)
        except RuntimeStoreError as error:
            raise CoordinatorConflictError(f"unresolved {kind} reference") from error
        if item.kind != kind:
            raise CoordinatorConflictError(f"reference must identify {kind}")
        return item

    def _resolve_current(self, item: ArtifactRevision, kind: str, run_id: str) -> ArtifactRef:
        if not isinstance(item, ArtifactRevision) or item.kind != kind or item.round_id != run_id:
            raise CoordinatorConflictError(f"{kind} must belong to run {run_id}")
        reference = ArtifactRef(item.round_id, item.id, item.revision)
        stored = self._load(reference, kind)
        if stored != item or not self.ledger.is_latest_artifact(reference):
            raise CoordinatorConflictError(f"stale {kind} lineage")
        return reference

    def _states(self, run_id: str) -> tuple[ArtifactRevision, ...]:
        return tuple(item for item in self.ledger.load_run(run_id).artifacts if item.kind == RESEARCH_RUN_STATE_KIND)

    def _latest_state(self, run_id: str) -> ArtifactRevision:
        states = self._states(run_id)
        if not states:
            raise CoordinatorConflictError("run is not initialized")
        return max(states, key=lambda item: item.revision)

    def state(self, run_id: str) -> ArtifactRevision:
        validate_identifier(run_id, "run_id")
        return self._latest_state(run_id)

    def persist_decision_frame(self, frame: DecisionFrame, *, expected_revision: int) -> ArtifactRevision:
        """Persist an immutable DecisionFrame with exact replay semantics."""

        if not isinstance(frame, DecisionFrame):
            raise CoordinatorConflictError("decision_frame must be a DecisionFrame")
        try:
            existing = [
                item
                for item in self.ledger.load_run(frame.run_id).artifacts
                if item.id == frame.frame_id and item.kind == DECISION_FRAME_KIND
            ]
        except RuntimeStoreError as error:
            raise CoordinatorConflictError("decision_frame_run_missing") from error
        if existing:
            current = max(existing, key=lambda item: item.revision)
            if not _same_payload(current, frame.to_dict()):
                raise CoordinatorConflictError("decision_frame_conflict")
            return current
        try:
            return self.ledger.append_decision_frame(
                frame.run_id,
                frame.frame_id,
                frame.to_dict(),
                parent_refs=frame.parent_refs,
                expected_revision=expected_revision,
            )
        except LedgerConflictError as error:
            raise CoordinatorConflictError("stale_revision") from error

    def require_decision_frame(
        self,
        frame_ref: ArtifactRef | Mapping[str, Any],
        *,
        run_id: str | None = None,
        target_ref: ArtifactRef | Mapping[str, Any] | None = None,
    ) -> ArtifactRevision:
        """Resolve the exact current ready frame without mutating lifecycle state."""

        try:
            reference = frame_ref if isinstance(frame_ref, ArtifactRef) else ArtifactRef.from_dict(frame_ref)
            artifact = self.ledger.get_artifact(reference)
        except (TypeError, ValueError, RuntimeStoreError) as error:
            raise CoordinatorConflictError("decision_frame_ref_invalid") from error
        if artifact.kind != DECISION_FRAME_KIND:
            raise CoordinatorConflictError("decision_frame_kind_invalid")
        if run_id is not None and artifact.round_id != validate_identifier(run_id, "run_id"):
            raise CoordinatorConflictError("decision_frame_cross_run")
        if not self.ledger.is_latest_artifact(reference):
            raise CoordinatorConflictError("decision_frame_stale")
        try:
            frame = DecisionFrame.from_dict(dict(artifact.payload))
        except RuntimeStoreError as error:
            raise CoordinatorConflictError("decision_frame_invalid") from error
        if frame.status != "ready_for_strategy":
            raise CoordinatorConflictError("decision_frame_not_ready_for_strategy")
        if target_ref is not None:
            expected_target = target_ref if isinstance(target_ref, ArtifactRef) else ArtifactRef.from_dict(target_ref)
            if frame.target_ref != expected_target:
                raise CoordinatorConflictError("decision_frame_target_mismatch")
        return artifact

    def persist_strategy_projection(
        self, projection: StrategyProjection, *, expected_revision: int
    ) -> ArtifactRevision:
        """Append an immutable projection, replaying an identical write.

        Persist accepts any valid projection status (draft through confirmed): the
        status alone confers no authority. Advancing the run past alignment requires
        the ``alignment_projection_ready`` transition, whose guard enforces the
        falsifiability review on the exact revision for every caller, and confirmation
        additionally requires the displayed status plus the digest-bearing confirmation.
        """

        if not isinstance(projection, StrategyProjection):
            raise CoordinatorConflictError("strategy_projection_invalid")
        try:
            existing = [
                item
                for item in self.ledger.load_run(projection.run_id).artifacts
                if item.id == projection.projection_id and item.kind == STRATEGY_PROJECTION_KIND
            ]
        except RuntimeStoreError as error:
            raise CoordinatorConflictError("strategy_projection_run_missing") from error
        payload = projection.to_dict()
        if existing:
            current = max(existing, key=lambda item: item.revision)
            if not _same_payload(current, payload):
                raise CoordinatorEventConflictError("strategy_projection_conflict")
            return projection
        current = self._latest_state(projection.run_id)
        if current.payload.get("state") != "alignment":
            raise CoordinatorConflictError("strategy_projection_requires_alignment")
        try:
            self.require_decision_frame(
                projection.decision_frame_ref, run_id=projection.run_id, target_ref=projection.target_ref
            )
            self._load(projection.alignment_handoff_ref, "alignment-handoff")
            self._load(projection.target_ref, "blueprint-target")
            if (
                projection.alignment_handoff_ref
                not in self._load(projection.target_ref, "blueprint-target").parent_refs
            ):
                raise CoordinatorConflictError("strategy_projection_handoff_lineage")
            self.ledger.append_strategy_projection(
                projection.run_id,
                projection.projection_id,
                payload,
                parent_refs=(projection.decision_frame_ref, projection.alignment_handoff_ref, projection.target_ref),
                expected_revision=expected_revision,
            )
            return projection
        except StrategyProjectionError as error:
            raise CoordinatorConflictError("strategy_projection_invalid") from error
        except LedgerConflictError as error:
            raise CoordinatorConflictError("stale_revision") from error

    def require_strategy_projection(
        self,
        projection_ref: ArtifactRef,
        *,
        run_id: str,
        require_displayed: bool = False,
    ) -> tuple[ArtifactRevision, StrategyProjection]:
        try:
            artifact = self.ledger.get_artifact(projection_ref)
            projection = StrategyProjection.from_dict(dict(artifact.payload))
        except (RuntimeStoreError, StrategyProjectionError, TypeError, ValueError) as error:
            raise CoordinatorConflictError("strategy_projection_invalid") from error
        if artifact.kind != STRATEGY_PROJECTION_KIND or artifact.round_id != run_id or projection.run_id != run_id:
            raise CoordinatorConflictError("strategy_projection_cross_run")
        if not self.ledger.is_latest_artifact(projection_ref):
            raise CoordinatorConflictError("strategy_projection_stale")
        if require_displayed and projection.status not in {"displayed", "confirmed"}:
            raise CoordinatorConflictError("strategy_projection_not_displayed")
        return artifact, projection

    def display_strategy(
        self, run_id: str, projection: StrategyProjection, *, expected_revision: int, idempotency_key: str | None = None
    ) -> ArtifactRevision:
        if isinstance(projection, ArtifactRevision):
            artifact, projection = self.require_strategy_projection(
                ArtifactRef(run_id, projection.id, projection.revision), run_id=run_id
            )
        else:
            artifact, _ = self.require_strategy_projection(
                ArtifactRef(run_id, projection.projection_id, projection.revision), run_id=run_id
            )
        if artifact.payload.get("display_digest") != projection.display_digest:
            raise CoordinatorConflictError("strategy_projection_stale")
        # Field-specific falsifiability pre-check: a rejected display names the violated
        # oracle rule and appends no artifact. Enforcement itself lives in the
        # transition guard (_guard_passes), which re-validates the same projection
        # content for EVERY caller of alignment_projection_ready — display_strategy
        # included — so no run may advance past alignment on an unfalsifiable
        # projection, whatever caller drove the transition.
        try:
            validate_falsifiability(projection)
        except StrategyProjectionError as error:
            raise CoordinatorConflictError(str(error)) from error
        # Issue #462 display gate: the projection content may only advance to a
        # displayed state once an independent subagent verification of the same
        # authority-bearing content exists. The transition guard re-enforces
        # this for every caller of alignment_projection_ready.
        self.require_independent_alignment_verification(run_id, projection)
        return self.transition(
            run_id,
            "alignment_projection_ready",
            "coordinator",
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
            payload={
                "projection_ref": ArtifactRef(run_id, artifact.id, artifact.revision).to_dict(),
                "display_digest": projection.display_digest,
            },
        )

    def require_independent_alignment_verification(self, run_id: str, projection: StrategyProjection) -> None:
        """Reject with ``independent_verification_required`` when no independent subagent
        alignment verification covers this projection (#462 display gate)."""

        failure = self._independent_alignment_verification_failure(run_id, projection)
        if failure is not None:
            raise CoordinatorConflictError(failure)

    def confirm_handoff(
        self,
        run_id: str,
        *,
        projection_ref: ArtifactRef,
        confirmation: str,
        expected_revision: int,
        actor: str = "human",
        idempotency_key: str | None = None,
    ) -> ArtifactRevision:
        if not isinstance(confirmation, str) or not confirmation.strip():
            raise CoordinatorConflictError("confirmation_required")
        if confirmation.strip().lower() in {"ok", "okay", "yes", "continue", "go ahead", "proceed"}:
            raise CoordinatorConflictError("generic_confirmation")
        artifact, projection = self.require_strategy_projection(projection_ref, run_id=run_id, require_displayed=True)
        if projection.display_digest not in confirmation:
            raise CoordinatorConflictError("confirmation_digest_mismatch")
        # Issue #292 gate 1: the display digest alone cannot vouch for the
        # authority-bearing fields — the user's confirmation must embed the
        # authority fingerprint so a stale scope/authority cannot survive a
        # broader authorization.
        expected_fingerprint = authority_fingerprint(projection)
        if "authority-fingerprint" not in confirmation:
            raise CoordinatorConflictError("authority_fingerprint_required")
        if expected_fingerprint not in confirmation:
            raise CoordinatorConflictError("authority_fingerprint_mismatch")
        # Defense in depth: the guard cannot vouch for artifacts written before the gate
        # existed or outside the coordinator, so confirmation re-validates the projection
        # content itself — a single gate failure must not fail the whole chain open.
        try:
            validate_falsifiability(projection)
        except StrategyProjectionError as error:
            raise CoordinatorConflictError(str(error)) from error
        payload = {
            "projection_ref": ArtifactRef(run_id, artifact.id, artifact.revision).to_dict(),
            "display_digest": projection.display_digest,
            "authority_fingerprint": expected_fingerprint,
            "confirmation": confirmation,
        }
        return self.transition(
            run_id,
            "handoff_confirmed",
            actor,
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
            payload=payload,
        )

    def revise_strategy(
        self,
        run_id: str,
        *,
        projection_ref: ArtifactRef,
        changes: Mapping[str, Any],
        expected_revision: int,
    ) -> ArtifactRevision:
        """Revise a strategy projection under #471 supersede semantics.

        Before any confirmation the revision is written exactly as before. Once
        an authoritative confirmed projection exists, that confirmation is the
        human's authorization of the exact displayed content, so a revision can
        never silently replace it: the prior confirmed revision is invalidated
        by a ``strategy-projection-invalidation`` marker artifact, the revision
        itself is written as an unconfirmed ``draft`` — never ``displayed`` —
        and re-display requires the full independent alignment gate on the new
        revision (fresh verification bound to the new revision and fingerprint).
        """

        artifact, projection = self.require_strategy_projection(projection_ref, run_id=run_id)
        values = projection.to_dict()
        values.update(dict(changes))
        values.update(
            {
                "projection_id": projection.projection_id,
                "run_id": run_id,
                "revision": projection.revision + 1,
            }
        )
        values["decision_frame_ref"] = projection.decision_frame_ref
        values["alignment_handoff_ref"] = projection.alignment_handoff_ref
        values["target_ref"] = projection.target_ref
        values.pop("schema_version", None)
        values.pop("kind", None)
        values.pop("display_payload", None)
        values.pop("display_digest", None)
        values.pop("content_hash", None)
        confirmed = latest_confirmed(self.ledger.load_run(run_id).artifacts)
        post_confirm = confirmed is not None
        # Validate the revised content before any ledger write: a rejected
        # revision must not leave an invalidation marker behind.
        values["status"] = "draft" if post_confirm else "displayed"
        revised = StrategyProjection.create(**values)
        parent_refs = [
            ArtifactRef(run_id, artifact.id, artifact.revision),
            revised.decision_frame_ref,
            revised.alignment_handoff_ref,
            revised.target_ref,
        ]
        if post_confirm:
            parent_refs.append(
                self._append_projection_invalidation(run_id, confirmed, expected_revision=expected_revision)
            )
        try:
            return self.ledger.append_strategy_projection(
                run_id,
                revised.projection_id,
                revised.to_dict(),
                parent_refs=tuple(parent_refs),
                expected_revision=expected_revision + (1 if post_confirm else 0),
            )
        except LedgerConflictError as error:
            raise CoordinatorConflictError("stale_revision") from error

    def _append_projection_invalidation(
        self,
        run_id: str,
        confirmed: ArtifactRevision,
        *,
        expected_revision: int,
    ) -> ArtifactRef:
        """Append the #471 marker that voids a confirmed projection's authorization."""

        superseded = StrategyProjection.from_dict(dict(confirmed.payload))
        marker_id = f"{confirmed.id}-invalidation-{confirmed.revision}"
        payload = {
            "schema": STRATEGY_PROJECTION_INVALIDATION_SCHEMA_VERSION,
            "id": marker_id,
            "run_id": run_id,
            "superseded_projection_ref": ArtifactRef(run_id, confirmed.id, confirmed.revision).to_dict(),
            "superseded_display_digest": superseded.display_digest,
            "superseded_authority_fingerprint": authority_fingerprint(superseded),
            "reason": "post-confirm strategy revision invalidates the confirmed authorization pending the full display gate",
        }
        validate_strategy_projection_invalidation(payload)
        marker = self.ledger.append_artifact(
            run_id,
            marker_id,
            STRATEGY_PROJECTION_INVALIDATION_KIND,
            payload,
            parent_refs=(ArtifactRef(run_id, confirmed.id, confirmed.revision),),
            expected_revision=expected_revision,
        )
        return ArtifactRef(run_id, marker.id, marker.revision)

    def initialize(
        self,
        *,
        run_id: str,
        alignment_handoff: ArtifactRevision,
        blueprint_target: ArtifactRevision,
        expected_revision: int,
        idempotency_key: str | None = None,
    ) -> ArtifactRevision:
        validate_identifier(run_id, "run_id")
        try:
            existing = self._latest_state(run_id)
        except CoordinatorConflictError:
            existing = None
        if existing is not None:
            if idempotency_key is None or existing.payload.get("idempotency_key") == idempotency_key:
                return existing
            raise CoordinatorConflictError("run is already initialized")
        handoff_ref = self._resolve_current(alignment_handoff, "alignment-handoff", run_id)
        target_ref = self._resolve_current(blueprint_target, "blueprint-target", run_id)
        if handoff_ref not in blueprint_target.parent_refs:
            raise CoordinatorConflictError("blueprint-target lineage does not include alignment-handoff")
        payload = self._state_payload(
            state="alignment",
            lifecycle_revision=0,
            obligations=(),
            legal_actions=("alignment_projection_ready", "authority_impossible", "supersede"),
            idempotency_key=idempotency_key,
        )
        payload["macro_stage"] = 1
        payload["state_digest"] = _digest({key: value for key, value in payload.items() if key != "state_digest"})
        authority = self._lineage_authority(blueprint_target, alignment_handoff)
        if authority is not None:
            bindings, task_id, domain_id = authority
            payload.update(
                authority_streams={role: binding.artifact_ref.artifact_id for role, binding in bindings.items()},
                task_id=task_id,
                domain_id=domain_id,
            )
            payload["state_digest"] = _digest({key: value for key, value in payload.items() if key != "state_digest"})
        try:
            return self.ledger.append_artifact(
                run_id,
                "run-state",
                RESEARCH_RUN_STATE_KIND,
                payload,
                parent_refs=(handoff_ref, target_ref),
                expected_revision=expected_revision,
            )
        except LedgerConflictError as error:
            raise CoordinatorConflictError("stale_revision") from error

    def _lineage_authority(
        self, target: ArtifactRevision, handoff: ArtifactRevision
    ) -> tuple[dict[str, CorrectionBinding], str, str] | None:
        artifacts = {"decision_map": target, "handoff": handoff}
        child = handoff
        for role in ("strategy", "working_brief", "intent_model"):
            matches = [
                self.ledger.get_artifact(ref)
                for ref in child.parent_refs
                if self.ledger.get_artifact(ref).kind == CORRECTION_ROLE_KINDS[role]
            ]
            if len(matches) != 1:
                return None
            child = artifacts[role] = matches[0]
        task_id = artifacts["working_brief"].payload.get("task_id")
        domain_id = artifacts["working_brief"].payload.get("domain_id")
        if artifacts["intent_model"].payload.get("task_id") != task_id:
            return None
        try:
            validate_identifier(task_id, "task_id")
            validate_identifier(domain_id, "domain_id")
        except (InvalidIdentifierError, TypeError, ValueError):
            return None
        return (
            {role: CorrectionBinding.from_artifact(role, artifacts[role]) for role in CORRECTION_AFFECTED_ROLES},
            task_id,
            domain_id,
        )

    def _current_authority(self, current: ArtifactRevision) -> dict[str, CorrectionBinding]:
        streams = current.payload.get("authority_streams")
        if not isinstance(streams, Mapping) or set(streams) != set(CORRECTION_AFFECTED_ROLES):
            raise CoordinatorConflictError("current state lacks authoritative role streams")
        artifacts = {}
        for role in CORRECTION_AFFECTED_ROLES:
            candidates = [
                item
                for item in self.ledger.load_run(current.round_id).artifacts
                if item.id == streams[role]
                and item.kind == CORRECTION_ROLE_KINDS[role]
                and self.ledger.is_latest_artifact(self._artifact_ref(item))
            ]
            if len(candidates) != 1:
                raise CoordinatorConflictError(f"current authority is unresolved: {role}")
            artifacts[role] = candidates[0]
        for child_role, parent_role in (
            ("working_brief", "intent_model"),
            ("strategy", "working_brief"),
            ("handoff", "strategy"),
            ("decision_map", "handoff"),
        ):
            if self._artifact_ref(artifacts[parent_role]) not in artifacts[child_role].parent_refs:
                raise CoordinatorConflictError("current authority lineage is inconsistent")
        return {role: CorrectionBinding.from_artifact(role, artifacts[role]) for role in CORRECTION_AFFECTED_ROLES}

    @staticmethod
    def _state_payload(
        *,
        state: str,
        lifecycle_revision: int,
        obligations: Sequence[str],
        legal_actions: Sequence[str],
        idempotency_key: str | None = None,
        reason: str | None = None,
        macro_stage_value: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "state": state,
            "lifecycle_revision": lifecycle_revision,
            "unmet_obligations": sorted(set(obligations)),
            "legal_next_actions": list(legal_actions),
        }
        if macro_stage_value is not None:
            body["macro_stage"] = macro_stage_value
        body["state_digest"] = _digest(body)
        if idempotency_key is not None:
            body["idempotency_key"] = idempotency_key
        if reason is not None:
            body["reason"] = reason
        return body

    @staticmethod
    def _next_actions(state: str) -> tuple[str, ...]:
        actions = sorted(event for (source, event), _ in _TRANSITIONS.items() if source == state)
        return tuple(actions)

    def _find_event_key(self, run_id: str, key: str) -> ArtifactRevision | None:
        for item in self.ledger.load_run(run_id).artifacts:
            if (
                item.kind in {LIFECYCLE_EVENT_KIND, HOST_EVENT_KIND, REJECTED_TRANSITION_KIND}
                and item.payload.get("idempotency_key") == key
            ):
                return item
        return None

    def _append_transition(
        self,
        *,
        run_id: str,
        current: ArtifactRevision,
        event: str,
        actor: str,
        target_state: str,
        expected_revision: int,
        idempotency_key: str | None,
        payload: Mapping[str, Any],
    ) -> ArtifactRevision:
        key = idempotency_key or f"{event}:{current.revision}:{_digest(payload)[:16]}"
        prior = self._find_event_key(run_id, key)
        if prior is not None:
            if not _same_payload(
                prior,
                {
                    **dict(payload),
                    "event": event,
                    "from": current.payload["state"],
                    "to": target_state,
                    "actor": actor,
                    "idempotency_key": key,
                },
            ):
                raise CoordinatorEventConflictError("event_id_conflict")
            return self._latest_state(run_id)
        event_id = "event-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        event_payload = {
            "event_id": event_id,
            "idempotency_key": key,
            "event": event,
            "from": current.payload["state"],
            "to": target_state,
            "actor": actor,
            "payload": dict(payload),
        }
        event_ref = ArtifactRef(run_id, event_id, 1)
        state_payload = self._state_payload(
            state=target_state,
            lifecycle_revision=int(current.payload.get("lifecycle_revision", 0)) + 1,
            obligations=payload.get("unmet_obligations", current.payload.get("unmet_obligations", ())),
            legal_actions=self._next_actions(target_state),
            idempotency_key=key,
            macro_stage_value=macro_stage(target_state, prior_stage=current.payload.get("macro_stage")),
        )
        state_payload["transition_payload"] = dict(payload)
        state_payload["previous_state_ref"] = ArtifactRef(run_id, current.id, current.revision).to_dict()
        self._carry_correction_context(current, state_payload)
        if "authority_binding" in payload:
            state_payload["active_authority"] = dict(payload["authority_binding"])
        if "projection_ref" in payload:
            state_payload["strategy_projection_ref"] = dict(payload["projection_ref"])
            state_payload["strategy_display_digest"] = payload.get("display_digest")
        state_payload["state_digest"] = _digest(
            {key: value for key, value in state_payload.items() if key != "state_digest"}
        )
        try:
            created = self.ledger.append_artifact_batch(
                run_id,
                (
                    (
                        event_id,
                        LIFECYCLE_EVENT_KIND,
                        event_payload,
                        (ArtifactRef(run_id, current.id, current.revision),),
                    ),
                    (
                        "run-state",
                        RESEARCH_RUN_STATE_KIND,
                        state_payload,
                        (ArtifactRef(run_id, current.id, current.revision), event_ref),
                    ),
                ),
                expected_revision=expected_revision,
            )
        except LedgerConflictError as error:
            raise CoordinatorConflictError("stale_revision") from error
        return created[-1]

    def record_same_round_replan(
        self,
        run_id: str,
        *,
        reason: str,
        expected_revision: int,
        replan_id: str | None = None,
        affected_refs: Sequence[ArtifactRef] = (),
        affected_slot_ids: Sequence[str] = (),
        guidance_defect: str | None = None,
    ) -> ArtifactRevision:
        """Record a method/depth/evidence correction without changing run identity."""

        current = self._latest_state(run_id)
        if not isinstance(reason, str) or not reason.strip():
            raise CoordinatorConflictError("replan reason is required")
        refs = tuple(affected_refs)
        if any(not isinstance(ref, ArtifactRef) or ref.round_id != run_id for ref in refs):
            raise CoordinatorConflictError("replan references must belong to the run")
        slot_ids = [str(value) for value in affected_slot_ids]
        if any(not value.strip() for value in slot_ids):
            raise CoordinatorConflictError("replan affected_slot_ids entries must be non-empty strings")
        if guidance_defect is not None and (not isinstance(guidance_defect, str) or not guidance_defect.strip()):
            raise CoordinatorConflictError("replan guidance_defect must be a non-empty string")
        artifact_id = replan_id or "same-round-replan-" + hashlib.sha256(reason.encode("utf-8")).hexdigest()[:20]
        payload = {
            "classification": "same_round_replan",
            "reason": reason.strip(),
            "affected_refs": [ref.to_dict() for ref in refs],
            "source_state_ref": ArtifactRef(run_id, current.id, current.revision).to_dict(),
            "affected_slot_ids": slot_ids,
            "guidance_defect": guidance_defect,
        }
        try:
            return self.ledger.append_artifact(
                run_id,
                artifact_id,
                "same-round-replan",
                payload,
                parent_refs=(ArtifactRef(run_id, current.id, current.revision), *refs),
                expected_revision=expected_revision,
            )
        except LedgerConflictError as error:
            raise CoordinatorConflictError("stale_revision") from error

    def assess_finding_pack_contribution(
        self,
        run_id: str,
        finding: ArtifactRevision,
        *,
        expected_revision: int,
    ) -> ArtifactRevision | None:
        """Assess one Finding Pack's contribution to the goal its slot serves.

        Returns the goal-contribution-assessment artifact, or None when the
        run has no confirmed StrategyProjection (prior ingestion behavior). A
        blocking verdict additionally wires the guidance-adjust retry: a
        same-round replan with slot granularity and the guidance defect, a
        successor Work Item with adjusted guidance and, once per slot, a
        method_switch policy consultation with a redecomposition_flagged
        successor marker on the second consecutive no_contribution (third and
        further verdicts in the streak are deduplicated by logical pack
        identity and still replan but never repeat the consult). Worker
        confidence is never an input.
        """

        validate_identifier(run_id, "run_id")
        if not isinstance(finding, ArtifactRevision) or finding.kind != FINDING_PACK_KIND or finding.round_id != run_id:
            raise CoordinatorConflictError("contribution assessment requires a run Finding Pack")
        snapshot = self.ledger.load_run(run_id)
        projection = latest_confirmed(snapshot.artifacts)
        if projection is None:
            return None
        slot = self._contribution_slot(snapshot.artifacts, finding)
        projection_payload = thaw_json(projection.payload)
        verdict, reason = assess_goal_contribution(thaw_json(finding.payload), slot, projection_payload)
        assessment_id = (
            "goal-contribution-"
            + hashlib.sha256(
                canonical_json_bytes(
                    {
                        "finding_pack_id": finding.id,
                        "finding_pack_revision": finding.revision,
                        "slot_id": slot.get("id"),
                        "projection_id": projection_payload.get("projection_id"),
                        "projection_revision": projection_payload.get("revision"),
                    }
                )
            ).hexdigest()[:20]
        )
        try:
            assessment = self.ledger.append_artifact(
                run_id,
                assessment_id,
                GOAL_CONTRIBUTION_ASSESSMENT_KIND,
                {
                    "schema": 1,
                    "id": assessment_id,
                    "round_id": run_id,
                    "finding_pack_id": finding.id,
                    "finding_pack_revision": finding.revision,
                    "slot_id": slot.get("id"),
                    "projection_id": projection_payload.get("projection_id"),
                    "projection_revision": projection_payload.get("revision"),
                    "projection_digest": projection.payload.get("display_digest"),
                    "verdict": verdict,
                    "reason": reason,
                },
                parent_refs=(
                    ArtifactRef(run_id, finding.id, finding.revision),
                    ArtifactRef(run_id, projection.id, projection.revision),
                ),
                expected_revision=expected_revision,
            )
        except LedgerConflictError as error:
            raise CoordinatorConflictError("stale_revision") from error
        if verdict not in _CONTRIBUTION_BLOCKING_VERDICTS:
            return assessment
        consecutive = self._consecutive_no_contribution(run_id, str(slot.get("id")))
        self._record_contribution_retry(run_id, finding, slot, verdict, reason, consecutive)
        return assessment

    def _contribution_slot(self, artifacts, finding):
        target_id = finding.payload.get("blueprint_target_id")
        slot_id = finding.payload.get("decision_slot_id")
        candidates = [item for item in artifacts if item.kind == BLUEPRINT_TARGET_KIND and item.id == target_id]
        target = max(candidates, key=lambda item: item.revision, default=None)
        if target is None:
            raise CoordinatorConflictError(f"unknown blueprint target for assessment: {target_id}")
        for slot in target.payload.get("slots", ()):
            if isinstance(slot, Mapping) and slot.get("id") == slot_id:
                return thaw_json(slot)
        raise CoordinatorConflictError(f"Decision Slot absent from Blueprint Target: {slot_id}")

    def _consecutive_no_contribution(self, run_id: str, slot_id: str) -> int:
        """Count the trailing no_contribution run along the slot assessment chain.

        Assessments are deduplicated by logical pack identity first: only the
        latest assessment per finding pack id participates, so recompiling the
        same finding at revision+1 never double-counts the streak.
        """

        snapshot = self.ledger.load_run(run_id)
        chain = sorted(
            (
                item
                for item in snapshot.artifacts
                if item.kind == GOAL_CONTRIBUTION_ASSESSMENT_KIND and item.payload.get("slot_id") == slot_id
            ),
            key=lambda item: (item.created_at, item.revision, str(item.payload.get("finding_pack_id"))),
        )
        latest_by_pack: dict[str, ArtifactRevision] = {}
        for item in chain:
            pack_id = str(item.payload.get("finding_pack_id"))
            current = latest_by_pack.get(pack_id)
            if current is None or (item.created_at, item.revision) >= (current.created_at, current.revision):
                latest_by_pack[pack_id] = item
        ordered = sorted(latest_by_pack.values(), key=lambda item: (item.created_at, item.revision))
        count = 0
        for item in reversed(ordered):
            if item.payload.get("verdict") == "no_contribution":
                count += 1
            else:
                break
        return count

    def _slot_method_switch_consulted(self, run_id: str, slot_id: str) -> bool:
        """Whether this slot already produced a method_switch policy consultation.

        The escalation is one-shot per slot: the second consecutive
        no_contribution consults the policy once; third and further verdicts in
        the streak still record the slot-granularity replan and a retry
        successor, but never repeat the consult or the redecomposition flag.
        """

        return any(
            item.kind == WORK_ITEM_KIND
            and item.payload.get("decision_slot_id") == slot_id
            and item.payload.get("policy_proposal_kind") == "method_switch"
            for item in self.ledger.load_run(run_id).artifacts
        )

    def _record_contribution_retry(
        self,
        run_id: str,
        finding: ArtifactRevision,
        slot: Mapping[str, Any],
        verdict: str,
        reason: str,
        consecutive: int,
    ) -> ArtifactRevision:
        slot_id = str(slot.get("id"))
        self.record_same_round_replan(
            run_id,
            reason=reason,
            expected_revision=self.ledger.get_revision(run_id),
            affected_slot_ids=(slot_id,),
            guidance_defect=reason,
        )
        snapshot = self.ledger.load_run(run_id)
        ordinal = 1 + sum(
            1
            for item in snapshot.artifacts
            if item.kind == WORK_ITEM_KIND
            and item.payload.get("decision_slot_id") == slot_id
            and item.payload.get("guidance_defect")
        )
        escalate = consecutive >= 2 and not self._slot_method_switch_consulted(run_id, slot_id)
        proposal = self._method_switch_proposal(slot) if escalate else None
        target = max(
            (
                item
                for item in snapshot.artifacts
                if item.kind == BLUEPRINT_TARGET_KIND and item.id == finding.payload.get("blueprint_target_id")
            ),
            key=lambda item: item.revision,
            default=None,
        )
        if target is None:
            raise CoordinatorConflictError(
                f"unknown blueprint target for contribution retry: {finding.payload.get('blueprint_target_id')}"
            )
        touchpoints = slot.get("repository_touchpoints")
        return CanonicalWorkItemCompiler(self.ledger).compile(
            round_id=run_id,
            work_item_id=f"work-{slot_id}-retry-{ordinal}",
            blueprint_target=target,
            decision_slot_id=slot_id,
            kind="repository_analysis" if touchpoints else "external_research",
            scope=slot.get("question", f"Close Decision Slot {slot_id}")
            + f" Adjusted after goal-contribution retry ({verdict}): {reason}",
            exclusions="Do not close the Decision Slot, select an alternative, or add unrelated scope."
            + f" Previous guidance was defective: {reason}",
            decision_change_reason="The result can change the selected alternative among: "
            + ", ".join(str(option) for option in slot.get("alternatives", ()))
            + ".",
            depends_on=(),
            methods=("repository_inspection",) if touchpoints else ("primary_docs",),
            budget={"tool_calls": 8, "time": "bounded"},
            completion_rule="Return a Finding Pack or state why evidence is unavailable.",
            guidance_defect=reason,
            redecomposition_flagged=escalate,
            policy_proposal_id=proposal.action_id if proposal is not None else None,
            policy_proposal_kind=proposal.kind if proposal is not None else None,
            expected_revision=self.ledger.get_revision(run_id),
        )

    def _method_switch_proposal(self, slot: Mapping[str, Any]):
        """Consult the scheduling policy with a method_switch deficit (ADR-006).

        The consult must stay reachable on every wired path, including the ledger
        compile hook that constructs a bare ``ResearchRunCoordinator(ledger)``:
        when no policy was injected, a default policy is constructed for the
        consultation (used locally; the coordinator instance is never mutated).
        """

        policy = self.policy if self.policy is not None else AdaptiveResearchPolicy()
        slot_id = str(slot.get("id"))
        validation = slot.get("validation") if isinstance(slot.get("validation"), Mapping) else {}
        closure_oracle = str(validation.get("oracle") or slot.get("evidence_standard") or "").strip()
        if not closure_oracle:
            closure_oracle = f"Decision Slot {slot_id} closes with evidence"
        priority = str(slot.get("priority")) if str(slot.get("priority")) in {"P0", "P1", "P2", "P3"} else "P1"
        evaluation = policy.evaluate(
            slots=[
                {
                    "slot_id": slot_id,
                    "question": str(slot.get("question") or f"Close Decision Slot {slot_id}"),
                    "priority": priority,
                    "closure_oracle": closure_oracle,
                    "missing_dimensions": ("method_switch",),
                }
            ]
        )
        proposal = evaluation.proposals[0] if evaluation.proposals else None
        if proposal is not None and proposal.kind != "method_switch":
            return None
        return proposal

    def persist_search_portfolio_lineage(
        self,
        *,
        run_id: str,
        attempt_id: str,
        portfolio: SearchPortfolio,
        execution: PortfolioExecution,
        capture_refs: Sequence[ArtifactRef],
        receipt_refs: Sequence[ArtifactRef],
        checkpoint_refs: Sequence[ArtifactRef],
        finding_refs: Sequence[ArtifactRef],
        intent_ref: ArtifactRef,
        brief_ref: ArtifactRef,
        strategy_ref: ArtifactRef,
        decision_map_ref: ArtifactRef,
        pivot_correction: CorrectionEvent | None = None,
        expected_revision: int,
    ) -> ArtifactRevision:
        """Persist one evidence-bound SearchPortfolio execution for an attempt."""

        if not isinstance(portfolio, SearchPortfolio) or not isinstance(execution, PortfolioExecution):
            raise CoordinatorConflictError("search_portfolio_lineage_values_invalid")
        validate_identifier(run_id, "run_id")
        validate_identifier(attempt_id, "attempt_id")
        if portfolio.run_id != run_id or execution.portfolio_id != portfolio.portfolio_id:
            raise CoordinatorConflictError("search_portfolio_lineage_identity_mismatch")
        intent = self._resolve_lineage_parent(run_id, intent_ref, "portfolio_intent", ("intent-model",))
        brief = self._resolve_lineage_parent(run_id, brief_ref, "portfolio_brief", ("working-brief",))
        strategy = self._resolve_lineage_parent(
            run_id, strategy_ref, "portfolio_strategy", ("research-strategy", STRATEGY_PROJECTION_KIND)
        )
        decision_map = self._resolve_lineage_parent(
            run_id, decision_map_ref, "portfolio_decision_map", ("blueprint-target",)
        )
        if intent.id != portfolio.intent_revision or brief.id != portfolio.brief_revision:
            raise CoordinatorConflictError("search_portfolio_lineage_revision_mismatch")
        slots = decision_map.payload.get("decision_slots", ())
        if not any(isinstance(item, Mapping) and item.get("id") == portfolio.slot_id for item in slots):
            raise CoordinatorConflictError("search_portfolio_lineage_slot_mismatch")
        assessments = execution.assessments
        if any(item.attempt_id != attempt_id or item.decision_slot_id != portfolio.slot_id for item in assessments):
            raise CoordinatorConflictError("search_portfolio_lineage_assessment_mismatch")

        resolved_captures = self._resolve_lineage_refs(
            run_id, attempt_id, capture_refs, "portfolio_capture", (SOURCE_CAPTURE_KIND,), ("committed",)
        )
        resolved_receipts = self._resolve_lineage_refs(
            run_id, attempt_id, receipt_refs, "portfolio_receipt", (ACQUISITION_RECEIPT_KIND,), ("succeeded",)
        )
        resolved_checkpoints = self._resolve_lineage_refs(
            run_id, attempt_id, checkpoint_refs, "portfolio_checkpoint", (ANALYSIS_CHECKPOINT_KIND,), ()
        )
        resolved_findings = self._resolve_lineage_refs(
            run_id, attempt_id, finding_refs, "portfolio_finding", (FINDING_PACK_KIND,), ()
        )
        declared = {
            "capture": {value for batch in execution.batches for item in batch.outcomes for value in item.capture_refs}
            | {value for item in assessments for value in item.capture_refs},
            "receipt": {value for batch in execution.batches for item in batch.outcomes for value in item.receipt_refs}
            | {value for item in assessments for value in item.receipt_refs},
            "checkpoint": {
                value for batch in execution.batches for item in batch.outcomes for value in item.checkpoint_refs
            }
            | {value for item in assessments for value in item.checkpoint_refs},
        }
        supplied = {
            "capture": {item.id for item in resolved_captures},
            "receipt": {item.id for item in resolved_receipts},
            "checkpoint": {item.id for item in resolved_checkpoints},
        }
        if declared != supplied:
            raise CoordinatorConflictError("search_portfolio_lineage_evidence_mismatch")

        current = self._latest_state(run_id)
        lineage_id = f"portfolio-lineage-{portfolio.portfolio_id}-{attempt_id}"
        if any(
            item.kind == SEARCH_PORTFOLIO_LINEAGE_KIND and item.id == lineage_id
            for item in self.ledger.load_run(run_id).artifacts
        ):
            raise CoordinatorConflictError("search_portfolio_lineage_already_exists")
        lineage_ref = ArtifactRef(run_id, lineage_id, 1)
        evidence_refs = tuple(
            ArtifactRef(run_id, item.id, item.revision)
            for item in (*resolved_captures, *resolved_receipts, *resolved_checkpoints, *resolved_findings)
        )
        lineage_payload = {
            "portfolio": portfolio.to_dict(),
            "execution": execution.to_dict(),
            "attempt_id": attempt_id,
            "capture_refs": [item.to_dict() for item in evidence_refs if item.artifact_id in supplied["capture"]],
            "receipt_refs": [item.to_dict() for item in evidence_refs if item.artifact_id in supplied["receipt"]],
            "checkpoint_refs": [item.to_dict() for item in evidence_refs if item.artifact_id in supplied["checkpoint"]],
            "finding_refs": [
                item.to_dict() for item in evidence_refs if item.artifact_id in {item.id for item in resolved_findings}
            ],
            "status": "pending_human_reopen"
            if any(item.authority_disposition == "requires_requester_reopen" for item in assessments)
            else "recorded",
        }
        parents = (
            ArtifactRef(run_id, current.id, current.revision),
            ArtifactRef(run_id, intent.id, intent.revision),
            ArtifactRef(run_id, brief.id, brief.revision),
            ArtifactRef(run_id, strategy.id, strategy.revision),
            ArtifactRef(run_id, decision_map.id, decision_map.revision),
            *evidence_refs,
        )
        entries: list[tuple[str, str, Any, Sequence[ArtifactRef]]] = [
            (lineage_id, SEARCH_PORTFOLIO_LINEAGE_KIND, lineage_payload, parents)
        ]
        pivot = next((item for item in assessments if item.disposition == "pivot"), None)
        reopen = next((item for item in assessments if item.authority_disposition == "requires_requester_reopen"), None)
        if pivot is not None and reopen is None:
            if not isinstance(pivot_correction, CorrectionEvent):
                raise CoordinatorConflictError("portfolio_pivot_correction_required")
            strategy_binding = pivot_correction.affected.get("strategy")
            if (
                pivot_correction.run_id != run_id
                or strategy_binding is None
                or strategy_binding.artifact_ref != strategy_ref
            ):
                raise CoordinatorConflictError("portfolio_pivot_correction_mismatch")
            self._validate_correction_for_apply(pivot_correction)
        elif reopen is not None:
            entries.append(
                (
                    f"human-decision-reopen-{reopen.assessment_id}",
                    HUMAN_DECISION_REOPEN_KIND,
                    {
                        "status": "pending",
                        "attempt_id": attempt_id,
                        "portfolio_id": portfolio.portfolio_id,
                        "decision_slot_id": portfolio.slot_id,
                        "assessment_id": reopen.assessment_id,
                        "reason": "; ".join(reopen.next_actions),
                    },
                    (ArtifactRef(run_id, current.id, current.revision), lineage_ref),
                )
            )
        try:
            lineage = self.ledger.append_artifact_batch(run_id, tuple(entries), expected_revision=expected_revision)[0]
        except LedgerConflictError as error:
            raise CoordinatorConflictError("stale_revision") from error
        if pivot is not None and reopen is None:
            self.apply_correction(pivot_correction, expected_revision=self.ledger.get_revision(run_id))
        return lineage

    def create_successor(
        self,
        run_id: str,
        *,
        successor_run_id: str,
        reason: str,
        expected_revision: int,
        actor: str = "coordinator",
    ) -> ArtifactRevision:
        """Create and link a successor before superseding this run."""

        current = self._latest_state(run_id)
        validate_identifier(successor_run_id, "successor_run_id")
        if successor_run_id == run_id or not isinstance(reason, str) or not reason.strip():
            raise CoordinatorConflictError("successor identity and reason are required")
        source_ref = ArtifactRef(run_id, current.id, current.revision)
        try:
            self.ledger.create_run(successor_run_id, parent_run_id=run_id)
        except LedgerConflictError:
            existing = self.ledger.load_run(successor_run_id)
            if existing.record.parent_round_id != run_id:
                raise CoordinatorConflictError("successor already belongs to another run")
        link_payload = {
            "status": "superseded",
            "successor_run_id": successor_run_id,
            "reason": reason.strip(),
            "actor": actor,
        }
        try:
            link = self.ledger.append_artifact(
                run_id,
                "successor-link-" + successor_run_id,
                "round-supersession",
                link_payload,
                parent_refs=(source_ref,),
                expected_revision=expected_revision,
            )
        except LedgerConflictError as error:
            raise CoordinatorConflictError("stale_revision") from error
        return self.transition(
            run_id,
            "supersede" if current.payload["state"] == "alignment" else "intent_correction",
            actor,
            expected_revision=expected_revision + 1,
            payload={"successor_ref": ArtifactRef(run_id, link.id, link.revision).to_dict()},
        )

    def apply_correction(
        self,
        value: CorrectionEvent | Mapping[str, Any],
        *,
        expected_revision: int,
    ) -> ArtifactRevision:
        """Atomically quarantine predecessor authority and re-enter alignment."""

        correction = CorrectionEvent.from_value(value)
        existing = next(
            (
                item
                for item in self.ledger.load_run(correction.run_id).artifacts
                if item.kind == CORRECTION_EVENT_KIND and item.id == correction.event_id
            ),
            None,
        )
        correction_payload = correction.to_dict()
        if existing is not None:
            if not _same_payload(existing, correction_payload):
                raise CoordinatorEventConflictError("event_id_conflict")
            successor = next(
                (
                    item
                    for item in reversed(self._states(correction.run_id))
                    if item.payload.get("correction_event_id") == correction.event_id
                ),
                None,
            )
            if successor is None:
                raise CoordinatorConflictError("correction successor state is missing")
            return successor

        current, affected_refs = self._validate_correction_for_apply(correction)

        current_ref = ArtifactRef(correction.run_id, current.id, current.revision)
        affected_ref_set = set(affected_refs)
        reachable = affected_ref_set | {current_ref}
        paths = {reference: (reference,) for reference in reachable}
        dependent_refs: list[ArtifactRef] = []
        candidates = [
            item
            for item in self.ledger.load_run(correction.run_id).artifacts
            if self._artifact_ref(item) not in affected_ref_set | {current_ref}
            and self.ledger.is_latest_artifact(self._artifact_ref(item))
        ]
        while candidates:
            found = sorted(
                (item for item in candidates if reachable.intersection(item.parent_refs)),
                key=lambda item: (item.round_id, item.id, item.revision),
            )
            if not found:
                break
            for item in found:
                reference = self._artifact_ref(item)
                parent = min(
                    (candidate for candidate in item.parent_refs if candidate in reachable),
                    key=lambda candidate: (
                        tuple((entry.round_id, entry.artifact_id, entry.revision) for entry in paths[candidate]),
                        candidate.round_id,
                        candidate.artifact_id,
                        candidate.revision,
                    ),
                )
                dependent_refs.append(reference)
                reachable.add(reference)
                paths[reference] = (*paths[parent], reference)
                candidates.remove(item)
        correction_ref = ArtifactRef(correction.run_id, correction.event_id, 1)
        quarantine_id = "quarantine-" + correction.event_id
        quarantine_ref = ArtifactRef(correction.run_id, quarantine_id, 1)
        quarantine_payload = {
            "correction_event_id": correction.event_id,
            "relation": correction.relation,
            "stale_bindings": correction_payload["affected"],
            "dependent_refs": [reference.to_dict() for reference in dependent_refs],
            "dependent_paths": [
                {
                    "artifact_ref": reference.to_dict(),
                    "path": [entry.to_dict() for entry in paths[reference]],
                }
                for reference in dependent_refs
            ],
            "source_state_ref": current_ref.to_dict(),
        }
        state_payload = self._state_payload(
            state="alignment",
            lifecycle_revision=int(current.payload.get("lifecycle_revision", 0)) + 1,
            obligations=(
                "alignment_reconfirmation",
                "strategy_reprojection",
                "handoff_reconfirmation",
                "closure_revalidation",
                "delivery_recompilation",
                "acceptance_reconfirmation",
            ),
            legal_actions=self._next_actions("alignment"),
            idempotency_key=correction.event_id,
            reason=correction.reason,
        )
        state_payload.update(
            {
                "task_id": correction.successor_task_id,
                "domain_id": correction.successor_domain_id,
                "correction_event_id": correction.event_id,
                "correction_relation": correction.relation,
                "previous_state_ref": current_ref.to_dict(),
                "quarantine_ref": quarantine_ref.to_dict(),
                "authority_streams": thaw_json(current.payload["authority_streams"]),
            }
        )
        state_payload["state_digest"] = _digest(
            {key: item for key, item in state_payload.items() if key != "state_digest"}
        )
        try:
            created = self.ledger.append_artifact_batch(
                correction.run_id,
                (
                    (
                        correction.event_id,
                        CORRECTION_EVENT_KIND,
                        correction_payload,
                        (current_ref, *affected_refs),
                    ),
                    (
                        quarantine_id,
                        STALE_STATE_QUARANTINE_KIND,
                        quarantine_payload,
                        (current_ref, correction_ref, *affected_refs, *dependent_refs),
                    ),
                    (
                        "run-state",
                        RESEARCH_RUN_STATE_KIND,
                        state_payload,
                        (current_ref, correction_ref, quarantine_ref),
                    ),
                ),
                expected_revision=expected_revision,
            )
        except LedgerConflictError as error:
            raise CoordinatorConflictError("stale_revision") from error
        return created[-1]

    def apply_contradiction(
        self,
        *,
        run_id: str,
        contradiction_id: str,
        finding_refs: Sequence[ArtifactRef | Mapping[str, Any]],
        reason: str,
        expected_revision: int,
        claim_ids: Sequence[str] | None = None,
        boundary: ClaimBoundary | str = ClaimBoundary.ADMISSION,
    ) -> ArtifactRevision:
        """Atomically persist a material conflict and reopen its run."""

        validate_identifier(run_id, "run_id")
        validate_identifier(contradiction_id, "contradiction_id")
        if not isinstance(reason, str) or not reason.strip():
            raise CoordinatorConflictError("contradiction reason is required")
        try:
            roots = tuple(
                reference if isinstance(reference, ArtifactRef) else ArtifactRef.from_dict(reference)
                for reference in finding_refs
            )
        except (TypeError, ValueError) as error:
            raise CoordinatorConflictError("contradiction finding references are invalid") from error
        if len(roots) < 2 or len(set(roots)) != len(roots):
            raise CoordinatorConflictError("contradiction requires two distinct Finding Packs")
        for reference in roots:
            finding = self._load(reference, FINDING_PACK_KIND)
            if finding.round_id != run_id or not self.ledger.is_latest_artifact(reference):
                raise CoordinatorConflictError("contradiction Finding Pack is stale or cross-run")
        claims_by_id: dict[str, tuple[dict[str, Any], ArtifactRef, Mapping[str, Any]]] = {}
        passages: dict[str, tuple[str, ...]] = {}
        typed_claims = []
        for reference in roots:
            finding = self._load(reference, FINDING_PACK_KIND)
            assessments = {
                item.get("claim_id"): item
                for item in finding.payload.get("claim_assessments", ())
                if isinstance(item, Mapping) and isinstance(item.get("claim_id"), str)
            }
            observations = finding.payload.get("observations", ())
            for raw_claim in finding.payload.get("claims", ()):
                if not isinstance(raw_claim, Mapping):
                    raise CoordinatorConflictError("contradiction Finding Pack has invalid canonical claims")
                try:
                    claim = claim_from_mapping(raw_claim)
                except (TypeError, ValueError) as error:
                    raise CoordinatorConflictError("contradiction Finding Pack has invalid canonical claims") from error
                if claim.claim_id in claims_by_id:
                    raise CoordinatorConflictError("contradiction claims must have distinct identifiers")
                typed_claims.append(claim)
                claims_by_id[claim.claim_id] = (
                    thaw_json(raw_claim),
                    reference,
                    assessments.get(claim.claim_id, {}),
                )
                passages[claim.claim_id] = tuple(
                    str(observation.get("claim"))
                    for observation in observations
                    if isinstance(observation, Mapping) and observation.get("claim_id") == claim.claim_id
                )
        unresolved = tuple(
            packet
            for packet in ContradictionDetector().detect(typed_claims, boundary=boundary)
            if packet.status in {ContradictionStatus.UNRESOLVED, ContradictionStatus.CONTESTED}
        )
        if claim_ids is not None:
            requested = tuple(sorted(claim_ids))
            if len(set(requested)) < 2:
                raise CoordinatorConflictError("contradiction claim_ids must identify two distinct claims")
            unresolved = tuple(packet for packet in unresolved if packet.claim_ids == requested)
        if len(unresolved) != 1:
            raise CoordinatorConflictError("contradiction Finding Packs must contain exactly one material conflict")
        conflict = unresolved[0]
        existing = next(
            (
                item
                for item in self.ledger.load_run(run_id).artifacts
                if item.kind == CONTRADICTION_PACKET_KIND and item.id == contradiction_id
            ),
            None,
        )
        if existing is not None:
            if tuple(ArtifactRef.from_dict(value) for value in existing.payload.get("finding_refs", ())) != roots:
                raise CoordinatorEventConflictError("contradiction_id_conflict")
            if tuple(existing.payload.get("claim_ids", ())) != conflict.claim_ids:
                raise CoordinatorEventConflictError("contradiction_claim_set_conflict")
            successor = next(
                (
                    item
                    for item in reversed(self._states(run_id))
                    if item.payload.get("contradiction_id") == contradiction_id
                ),
                None,
            )
            if successor is None:
                raise CoordinatorConflictError("contradiction successor state is missing")
            return successor

        current = self._latest_state(run_id)
        current_ref = self._artifact_ref(current)
        reachable = set(roots) | {current_ref}
        paths = {reference: (reference,) for reference in reachable}
        dependents: list[ArtifactRef] = []
        candidates = [
            item
            for item in self.ledger.load_run(run_id).artifacts
            if self._artifact_ref(item) not in reachable and self.ledger.is_latest_artifact(self._artifact_ref(item))
        ]
        while candidates:
            found = sorted(
                (item for item in candidates if reachable.intersection(item.parent_refs)),
                key=lambda item: (item.round_id, item.id, item.revision),
            )
            if not found:
                break
            for item in found:
                reference = self._artifact_ref(item)
                parent = min(
                    reachable.intersection(item.parent_refs),
                    key=lambda value: (value.round_id, value.artifact_id, value.revision),
                )
                paths[reference] = (*paths[parent], reference)
                dependents.append(reference)
                reachable.add(reference)
                candidates.remove(item)
        packet_ref = ArtifactRef(run_id, contradiction_id, 1)
        retraction_id = f"retraction-{contradiction_id}"
        retraction_ref = ArtifactRef(run_id, retraction_id, 1)
        successor_id = f"successor-{contradiction_id}"
        successor_ref = ArtifactRef(run_id, successor_id, 1)
        quarantine_id = f"quarantine-{contradiction_id}"
        quarantine_ref = ArtifactRef(run_id, quarantine_id, 1)
        execution_specs: list[tuple[str, str, dict[str, Any], tuple[ArtifactRef, ...]]] = []
        execution_result_refs: list[ArtifactRef] = []
        execution_effects: dict[str, str] = {}
        stale_delivery_specs: list[tuple[str, str, dict[str, Any], tuple[ArtifactRef, ...]]] = []
        stale_delivery_ids: list[str] = []
        dependent_refs = tuple(
            sorted(dependents, key=lambda reference: (reference.round_id, reference.artifact_id, reference.revision))
        )
        dependent_artifacts = {reference: self.ledger.get_artifact(reference) for reference in dependent_refs}
        for reference, item in sorted(
            dependent_artifacts.items(),
            key=lambda pair: (pair[0].round_id, pair[0].artifact_id, pair[0].revision),
        ):
            if item.kind == LEASE_KIND and item.payload.get("status") == "active":
                status = (
                    "cancelled"
                    if item.payload.get("execution_status") in {"unexecuted", "registered", "pending"}
                    else "quarantined"
                )
                execution_effects[item.id] = status
                execution_result_refs.append(ArtifactRef(run_id, item.id, item.revision + 1))
                execution_specs.append(
                    (
                        item.id,
                        LEASE_KIND,
                        {
                            **dict(item.payload),
                            "status": status,
                            "contradiction_id": contradiction_id,
                        },
                        (reference,),
                    )
                )
            if item.kind in {TECHNICAL_PACKAGE_KIND_ALIAS, HUMAN_RESEARCH_REPORT_KIND}:
                stale_delivery_ids.append(item.id)
                stale_delivery_specs.append(
                    (
                        f"stale-{item.id}",
                        STALE_DELIVERY_CLAIM_KIND,
                        {
                            "contradiction_id": contradiction_id,
                            "delivery_ref": reference.to_dict(),
                            "status": "stale",
                        },
                        (reference,),
                    )
                )
        packet = {
            "contradiction_id": contradiction_id,
            "run_id": run_id,
            "finding_refs": [reference.to_dict() for reference in roots],
            "claim_ids": list(conflict.claim_ids),
            "conflicting_values": list(conflict.conflicting_values),
            "unresolved_dimensions": list(conflict.unresolved_dimensions),
            "scope_dimensions": [result.to_dict() for result in conflict.scope_dimensions],
            "normalized_claims": [dict(value) for value in conflict.normalized_claims],
            "boundary": ClaimBoundary(boundary).value,
            "claim_a": claims_by_id[conflict.claim_ids[0]][0],
            "claim_b": claims_by_id[conflict.claim_ids[1]][0],
            "claim_a_ref": claims_by_id[conflict.claim_ids[0]][1].to_dict(),
            "claim_b_ref": claims_by_id[conflict.claim_ids[1]][1].to_dict(),
            "source_refs": {
                claim_id: {
                    "passages": list(passages.get(claim_id, ())),
                    "grounding_refs": thaw_json(claims_by_id[claim_id][2].get("grounding_refs", ())),
                    "provenance_clusters": thaw_json(claims_by_id[claim_id][2].get("provenance_clusters", ())),
                }
                for claim_id in conflict.claim_ids
            },
            "shared_scope": {
                name: claims_by_id[conflict.claim_ids[0]][0][name]
                for name in (
                    "subject",
                    "predicate",
                    "scope",
                    "version",
                    "time_range",
                    "platform",
                    "conditions",
                    "modality",
                )
            },
            "conflict_reason": conflict.reason,
            "reason": reason.strip(),
            "status": conflict.status.value,
            "resolution_path": "independent-experiment-or-scope-separation",
            "safe_fallback": "Retain the explicitly recorded reversible fallback until resolution.",
            "invalidated_refs": [reference.to_dict() for reference in dependent_refs],
        }
        packet["packet_digest"] = _digest(packet)
        packet["rendered"] = render_contradiction_packet(packet)
        successor = {
            "contradiction_id": contradiction_id,
            "packet_ref": packet_ref.to_dict(),
            "source_refs": [reference.to_dict() for reference in roots],
            "original_revision_refs": [reference.to_dict() for reference in roots],
            "method": "independent-source-or-revision-or-executable-experiment",
            "method_independence": "The successor must not reuse the disputed extraction or provenance cluster.",
            "oracle": "Resolve every disputed scope dimension or produce an executable counterexample.",
            "safe_fallback": packet["safe_fallback"],
            "blocks": ["decision", "readiness", "delivery", "closure", "task_release", "completion"],
        }
        invalidated_refs = [reference.to_dict() for reference in dependent_refs]
        retraction = {
            "contradiction_id": contradiction_id,
            "claim_ids": list(conflict.claim_ids),
            "retraction_digest": _digest({"contradiction_id": contradiction_id, "claim_ids": list(conflict.claim_ids)}),
            "invalidated_refs": invalidated_refs,
            "revoked_decisions": [
                reference.to_dict()
                for reference in dependent_refs
                if dependent_artifacts[reference].kind == "decision-ledger-entry"
            ],
            "stale_readiness": [
                reference.to_dict()
                for reference in dependent_refs
                if dependent_artifacts[reference].kind == "readiness-record"
            ],
            "stale_deliveries": [
                reference.to_dict()
                for reference in dependent_refs
                if dependent_artifacts[reference].kind in {TECHNICAL_PACKAGE_KIND_ALIAS, HUMAN_RESEARCH_REPORT_KIND}
            ],
            "stale_delivery_claims": sorted(stale_delivery_ids),
            "stale_closure_assessments": [
                reference.to_dict()
                for reference in dependent_refs
                if dependent_artifacts[reference].kind == "slot-closure-assessment"
            ],
            "execution_effects": execution_effects,
            "source_state_ref": current_ref.to_dict(),
        }
        quarantine = {
            "contradiction_event_id": contradiction_id,
            "relation": "reopens",
            "dependent_refs": [reference.to_dict() for reference in (*roots, *dependents)],
            "dependent_paths": [
                {"artifact_ref": reference.to_dict(), "path": [entry.to_dict() for entry in paths[reference]]}
                for reference in dependents
            ],
            "source_state_ref": current_ref.to_dict(),
        }
        state = self._state_payload(
            state="alignment",
            lifecycle_revision=int(current.payload.get("lifecycle_revision", 0)) + 1,
            obligations=("contradiction_resolution", "closure_revalidation", "delivery_recompilation"),
            legal_actions=self._next_actions("alignment"),
            idempotency_key=contradiction_id,
            reason=reason.strip(),
        )
        state.update(
            {
                "task_id": current.payload.get("task_id"),
                "domain_id": current.payload.get("domain_id"),
                "contradiction_id": contradiction_id,
                "previous_state_ref": current_ref.to_dict(),
                "quarantine_ref": quarantine_ref.to_dict(),
                "retraction_ref": retraction_ref.to_dict(),
                "successor_work_ref": successor_ref.to_dict(),
                "authority_streams": thaw_json(current.payload["authority_streams"]),
            }
        )
        state["state_digest"] = _digest({key: value for key, value in state.items() if key != "state_digest"})
        try:
            successor = self.ledger.append_artifact_batch(
                run_id,
                (
                    (contradiction_id, CONTRADICTION_PACKET_KIND, packet, (*roots,)),
                    *execution_specs,
                    *stale_delivery_specs,
                    (
                        successor_id,
                        CONTRADICTION_SUCCESSOR_WORK_KIND,
                        successor,
                        (packet_ref, *roots),
                    ),
                    (
                        retraction_id,
                        CONTRADICTION_RETRACTION_KIND,
                        retraction,
                        (
                            current_ref,
                            packet_ref,
                            successor_ref,
                            *execution_result_refs,
                        ),
                    ),
                    (
                        quarantine_id,
                        STALE_STATE_QUARANTINE_KIND,
                        quarantine,
                        (
                            current_ref,
                            packet_ref,
                            retraction_ref,
                            *roots,
                            *dependents,
                        ),
                    ),
                    (
                        "run-state",
                        RESEARCH_RUN_STATE_KIND,
                        state,
                        (current_ref, packet_ref, retraction_ref, quarantine_ref),
                    ),
                ),
                expected_revision=expected_revision,
            )[-1]
        except LedgerConflictError as error:
            raise CoordinatorConflictError("stale_revision") from error
        return successor

    def resolve_contradiction(
        self,
        *,
        packet_ref: ArtifactRevision,
        resolution_id: str,
        transition: str,
        resolver_ref: Mapping[str, Any],
        evidence_refs: Sequence[ArtifactRevision],
        selected_claim_ids: Sequence[str],
        expected_revision: int,
        prior_resolution: ArtifactRevision | None = None,
    ) -> ArtifactRevision:
        """Append one immutable resolution revision without changing the packet."""

        validate_identifier(resolution_id, "resolution_id")
        if transition not in {"resolved-a", "resolved-b", "both-limited", "superseded"}:
            raise CoordinatorConflictError("contradiction_resolution_transition_invalid")
        packet = self._load(self._artifact_ref(packet_ref), CONTRADICTION_PACKET_KIND)
        if packet != packet_ref or packet.round_id != packet_ref.round_id:
            raise CoordinatorConflictError("contradiction_packet_stale")
        prior_ref = None if prior_resolution is None else self._artifact_ref(prior_resolution)
        if prior_ref is not None:
            prior = self._load(prior_ref, CONTRADICTION_RESOLUTION_KIND)
            if prior != prior_resolution or prior.payload.get("packet_ref") != self._artifact_ref(packet).to_dict():
                raise CoordinatorConflictError("contradiction_resolution_lineage_invalid")
        if not isinstance(resolver_ref, Mapping) or not resolver_ref:
            raise CoordinatorConflictError("contradiction_resolver_ref_required")
        selected_set = {str(value) for value in selected_claim_ids}
        selected = sorted(selected_set)
        participating = {str(value) for value in packet.payload.get("claim_ids", ())}
        if not selected_set <= participating:
            raise CoordinatorConflictError("contradiction_resolution_claim_set_invalid")
        if transition in {"resolved-a", "resolved-b"} and not selected or selected == participating:
            raise CoordinatorConflictError("contradiction_resolution_claim_set_invalid")
        if transition == "both-limited" and selected:
            raise CoordinatorConflictError("contradiction_resolution_claim_set_invalid")
        evidence = tuple(self._artifact_ref(item) for item in evidence_refs)
        payload = {
            "resolution_id": resolution_id,
            "packet_ref": self._artifact_ref(packet).to_dict(),
            "transition": transition,
            "resolver_ref": dict(resolver_ref),
            "evidence_refs": [reference.to_dict() for reference in evidence],
            "prior_resolution_ref": None if prior_ref is None else prior_ref.to_dict(),
            "selected_claim_ids": selected,
            "decision_authority": transition != "superseded",
            "authorized_claim_ids": [] if transition in {"superseded", "both-limited"} else selected,
        }
        try:
            return self.ledger.append_artifact(
                packet.round_id,
                resolution_id,
                CONTRADICTION_RESOLUTION_KIND,
                payload,
                parent_refs=tuple(
                    reference
                    for reference in dict.fromkeys((self._artifact_ref(packet), prior_ref, *evidence))
                    if reference is not None
                ),
                expected_revision=expected_revision,
            )
        except LedgerConflictError as error:
            raise CoordinatorConflictError("stale_revision") from error

    def detect_and_apply_contradictions(
        self,
        *,
        run_id: str,
        blueprint_target_id: str,
        decision_slot_id: str,
        expected_revision: int,
        boundary: ClaimBoundary | str = ClaimBoundary.ADMISSION,
    ) -> tuple[ArtifactRevision, ...]:
        """Derive and persist all newly material conflicts for one canonical slot."""

        validate_identifier(run_id, "run_id")
        validate_identifier(blueprint_target_id, "blueprint_target_id")
        validate_identifier(decision_slot_id, "decision_slot_id")
        snapshot = self.ledger.load_run(run_id)
        findings = tuple(
            item
            for item in snapshot.artifacts
            if item.kind == FINDING_PACK_KIND
            and item.payload.get("blueprint_target_id") == blueprint_target_id
            and item.payload.get("decision_slot_id") == decision_slot_id
            and self.ledger.is_latest_artifact(self._artifact_ref(item))
        )
        claims: list[Any] = []
        finding_by_claim_id: dict[str, ArtifactRef] = {}
        for finding in findings:
            for raw_claim in finding.payload.get("claims", ()):
                try:
                    claim = claim_from_mapping(raw_claim)
                except (TypeError, ValueError) as error:
                    raise CoordinatorConflictError("Finding Pack has invalid canonical claims") from error
                if claim.claim_id in finding_by_claim_id:
                    raise CoordinatorConflictError("canonical claim identifiers must be unique across one slot")
                claims.append(claim)
                finding_by_claim_id[claim.claim_id] = self._artifact_ref(finding)
        applied: list[ArtifactRevision] = []
        revision = expected_revision
        for packet in ContradictionDetector().detect(claims, boundary=boundary):
            if packet.status not in {ContradictionStatus.CONTESTED, ContradictionStatus.UNRESOLVED}:
                continue
            digest = hashlib.sha256(
                canonical_json_bytes({"slot": decision_slot_id, "claims": packet.claim_ids})
            ).hexdigest()
            contradiction_id = f"contradiction-{digest[:20]}"
            finding_refs = tuple(dict.fromkeys(finding_by_claim_id[claim_id] for claim_id in packet.claim_ids))
            if len(finding_refs) < 2:
                continue
            existing = next(
                (
                    item
                    for item in snapshot.artifacts
                    if item.kind == CONTRADICTION_PACKET_KIND
                    and item.id == contradiction_id
                    and tuple(item.payload.get("claim_ids", ())) == packet.claim_ids
                ),
                None,
            )
            if existing is not None:
                continue
            applied.append(
                self.apply_contradiction(
                    run_id=run_id,
                    contradiction_id=contradiction_id,
                    finding_refs=finding_refs,
                    reason=packet.reason,
                    expected_revision=revision,
                    claim_ids=packet.claim_ids,
                    boundary=boundary,
                )
            )
            revision = self.ledger.get_revision(run_id)
        return tuple(applied)

    def _validate_correction_for_apply(
        self, correction: CorrectionEvent
    ) -> tuple[ArtifactRevision, tuple[ArtifactRef, ...]]:
        current = self._latest_state(correction.run_id)
        if correction.task_id != current.payload.get("task_id") or correction.domain_id != current.payload.get(
            "domain_id"
        ):
            raise CoordinatorConflictError("correction identity does not match current state")
        active = self._current_authority(current)
        quarantined_refs = self._quarantined_refs(correction.run_id)
        affected_refs: list[ArtifactRef] = []
        for role in CORRECTION_AFFECTED_ROLES:
            binding = correction.affected[role]
            try:
                artifact = self.ledger.get_artifact(binding.artifact_ref)
            except RuntimeStoreError as error:
                raise CoordinatorConflictError(f"unknown correction binding: {role}") from error
            if artifact.kind != CORRECTION_ROLE_KINDS[role]:
                raise CoordinatorConflictError(f"correction binding kind mismatch: {role}")
            if artifact.content_hash != binding.digest:
                raise CoordinatorConflictError(f"correction binding digest mismatch: {role}")
            if not self.ledger.is_latest_artifact(binding.artifact_ref):
                raise StaleStateError("apply_correction")
            if binding.artifact_ref in quarantined_refs or binding != active[role]:
                raise StaleStateError("apply_correction")
            affected_refs.append(binding.artifact_ref)
        return current, tuple(affected_refs)

    def _record_rejection(
        self, *, run_id: str, current: ArtifactRevision, event: str, actor: str, reason: str, expected_revision: int
    ) -> None:
        key = (
            "rejection:"
            + _digest({"state": current.payload["state"], "event": event, "actor": actor, "reason": reason})[:24]
        )
        if self._find_event_key(run_id, key) is not None:
            return
        payload = {
            "idempotency_key": key,
            "event": event,
            "actor": actor,
            "from": current.payload["state"],
            "reason": reason,
            "state_digest": current.payload["state_digest"],
        }
        try:
            self.ledger.append_artifact(
                run_id,
                "rejection-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:24],
                REJECTED_TRANSITION_KIND,
                payload,
                parent_refs=(ArtifactRef(run_id, current.id, current.revision),),
                expected_revision=expected_revision,
            )
        except LedgerConflictError as error:
            raise CoordinatorConflictError("stale_revision") from error

    def _assert_current_authority(
        self,
        run_id: str,
        action: str,
        value: Any,
    ) -> None:
        current = self._latest_state(run_id)
        correction_event_id = current.payload.get("correction_event_id")
        if correction_event_id is None:
            return
        if not isinstance(value, Mapping) or set(value) != {
            "correction_event_id",
            "bindings",
        }:
            raise StaleStateError(action)
        if value.get("correction_event_id") != correction_event_id:
            raise StaleStateError(action)
        bindings = value.get("bindings")
        if not isinstance(bindings, Mapping) or set(bindings) != set(CORRECTION_ACTION_ROLES):
            raise StaleStateError(action)
        try:
            active = self._current_authority(current)
        except CoordinatorConflictError as error:
            raise StaleStateError(action) from error
        quarantined = self._quarantined_refs(run_id)
        for role in CORRECTION_ACTION_ROLES:
            try:
                binding = CorrectionBinding.from_value(role, bindings[role])
                artifact = self.ledger.get_artifact(binding.artifact_ref)
            except (RuntimeStoreError, KeyError, TypeError, ValueError) as error:
                raise StaleStateError(action) from error
            if (
                binding != active[role]
                or artifact.kind != CORRECTION_ROLE_KINDS[role]
                or artifact.content_hash != binding.digest
                or binding.artifact_ref in quarantined
            ):
                raise StaleStateError(action)

    def _quarantined_refs(self, run_id: str) -> frozenset[ArtifactRef]:
        result: set[ArtifactRef] = set()
        for item in self.ledger.load_run(run_id).artifacts:
            if item.kind != STALE_STATE_QUARANTINE_KIND:
                continue
            stale = item.payload.get("stale_bindings")
            if isinstance(stale, Mapping):
                for role, value in stale.items():
                    try:
                        result.add(CorrectionBinding.from_value(str(role), value).artifact_ref)
                    except (RuntimeStoreError, TypeError, ValueError):
                        continue
            dependent = item.payload.get("dependent_refs")
            if isinstance(dependent, Sequence) and not isinstance(dependent, (str, bytes)):
                for value in dependent:
                    try:
                        result.add(_ref(value, "dependent_ref"))
                    except CoordinatorConflictError:
                        continue
        return frozenset(result)

    def _quarantine_paths(self, run_id: str) -> tuple[dict[str, Any], ...]:
        paths: list[dict[str, Any]] = []
        for item in self.ledger.load_run(run_id).artifacts:
            if item.kind != STALE_STATE_QUARANTINE_KIND:
                continue
            correction_event_id = item.payload.get("correction_event_id")
            for entry in item.payload.get("dependent_paths", ()):
                if not isinstance(entry, Mapping):
                    continue
                artifact_ref = entry.get("artifact_ref")
                path = entry.get("path")
                if not isinstance(artifact_ref, Mapping) or not isinstance(path, Sequence) or isinstance(path, str):
                    continue
                paths.append(
                    {
                        "correction_event_id": correction_event_id,
                        "artifact_ref": dict(artifact_ref),
                        "path": [dict(reference) for reference in path if isinstance(reference, Mapping)],
                    }
                )
        return tuple(
            sorted(
                paths,
                key=lambda entry: (
                    str(entry["correction_event_id"]),
                    str(entry["artifact_ref"].get("round_id", "")),
                    str(entry["artifact_ref"].get("artifact_id", "")),
                    int(entry["artifact_ref"].get("revision", 0)),
                ),
            )
        )

    @staticmethod
    def _carry_correction_context(
        current: ArtifactRevision,
        state_payload: dict[str, Any],
    ) -> None:
        for key in (
            "correction_event_id",
            "correction_relation",
            "quarantine_ref",
            "task_id",
            "domain_id",
            "authority_streams",
            "active_authority",
            "strategy_projection_ref",
            "strategy_display_digest",
        ):
            if key in current.payload:
                state_payload[key] = thaw_json(current.payload[key])

    def _guard_passes(
        self,
        run_id: str,
        event: str,
        payload: Mapping[str, Any] | None = None,
    ) -> tuple[bool, str | None]:
        """Evaluate the transition guard for ``event``.

        Returns ``(passed, failure_reason)``. ``failure_reason`` is ``None`` on pass
        and on undifferentiated failures (which keep their event-default reason); it is
        set when the guard can name the violated rule, e.g. the falsifiability review
        on ``alignment_projection_ready``.
        """

        inputs = self._completion_inputs(run_id)
        if event in {"alignment_projection_ready", "handoff_confirmed"}:
            projection_ref = (payload or {}).get("projection_ref")
            display_digest = (payload or {}).get("display_digest")
            try:
                reference = _ref(projection_ref, "projection_ref")
                artifact, projection = self.require_strategy_projection(reference, run_id=run_id)
            except CoordinatorConflictError:
                return False, None
            if display_digest != projection.display_digest or artifact.payload.get("display_digest") != display_digest:
                return False, None
            if event == "alignment_projection_ready":
                if projection.status not in {"displayed", "confirmed"}:
                    return False, None
                try:
                    validate_falsifiability(projection)
                except StrategyProjectionError as error:
                    return False, f"projection_unfalsifiable: {error}"
                verification_failure = self._independent_alignment_verification_failure(run_id, projection)
                if verification_failure is not None:
                    return False, verification_failure
                return True, None
            confirmation = (payload or {}).get("confirmation")
            if not (isinstance(confirmation, str) and projection.display_digest in confirmation):
                return False, None
            # Issue #292 gate 1: the fingerprint recorded at confirmation must
            # still match the projection's authority fields — a post-confirm
            # revise of scope/authority fails the guard here, blocking
            # compilation before any execution. The content checks run before
            # the status check so a tampered or replayed confirmation names the
            # violated rule even when it targets a superseded (#471) draft.
            recorded = (payload or {}).get("authority_fingerprint")
            if recorded != authority_fingerprint(projection):
                return False, "authority_fingerprint_drift"
            # Only the exact displayed/confirmed revision the human authorized
            # may pass; a #471 post-confirm revision is an unauthorized draft.
            if projection.status not in {"displayed", "confirmed"}:
                return False, "strategy_projection_not_displayed"
            return True, None
        if event == "handoff_confirmed":
            current = self._latest_state(run_id)
            if current.payload.get("correction_event_id") is not None:
                authority = (payload or {}).get("authority_binding")
                if not isinstance(authority, Mapping):
                    return False, None
                bindings = authority.get("bindings")
                if not isinstance(bindings, Mapping):
                    return False, None
                try:
                    binding = CorrectionBinding.from_value("handoff", bindings["handoff"])
                    handoff = self.ledger.get_artifact(binding.artifact_ref)
                except (RuntimeStoreError, KeyError, TypeError, ValueError):
                    return False, None
                return bool(handoff.payload.get("confirmed") is True), None
            initial = min(self._states(run_id), key=lambda item: item.revision)
            handoff = next(
                (
                    self.ledger.get_artifact(ref)
                    for ref in initial.parent_refs
                    if self.ledger.get_artifact(ref).kind == "alignment-handoff"
                ),
                None,
            )
            return bool(handoff and handoff.payload.get("confirmed") is True), None
        if event == "all_slots_closed":
            return "p0_closure_tokens" not in self._completion_obligations(run_id), None
        if event == "readiness_passed":
            return (
                bool(
                    inputs.get("readiness_ref")
                    and inputs["readiness_ref"].payload.get("status") in {"ready", "passed"}
                    and inputs.get("evaluation_ref")
                    and inputs["evaluation_ref"].payload.get("status") in {"passed", "pass"}
                ),
                None,
            )
        if event == "deliveries_compiled":
            return (
                inputs.get("technical_delivery_ref") is not None and inputs.get("human_delivery_ref") is not None
            ), None
        return True, None

    def transition(
        self,
        run_id: str,
        event: str,
        actor: str,
        *,
        expected_revision: int,
        idempotency_key: str | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> ArtifactRevision:
        """Canonical lifecycle transition with cross-region validation (#324)."""

        # Issue #324: reject forbidden cross-region payloads before any other check
        if event == "research/running":
            raise CoordinatorConflictError("cross_region_research_running_not_permitted")
        # Issue #324: forbid plan-style events from advancing canonical state
        if event in {"plan_completed", "plan_displayed", "plan_visible"}:
            raise CoordinatorConflictError("visible_plan_cannot_advance_canonical")
        current = self._latest_state(run_id)
        if current.payload.get("state") in {"alignment", "handoff_pending"} and event not in {
            "alignment_projection_ready",
            "handoff_confirmed",
        }:
            if event == "dispatch":
                raise CoordinatorConflictError("strategy_projection_confirmation_required")
        transition_payload = dict(payload or {})
        if event in CORRECTION_SENSITIVE_EVENTS:
            self._assert_current_authority(
                run_id,
                event,
                transition_payload.get("authority_binding"),
            )
        if idempotency_key is not None:
            prior = self._find_event_key(run_id, idempotency_key)
            if prior is not None:
                prior_payload = thaw_json(prior.payload)
                if (
                    prior.kind != LIFECYCLE_EVENT_KIND
                    or prior_payload.get("event") != event
                    or prior_payload.get("actor") != actor
                    or prior_payload.get("payload") != transition_payload
                ):
                    raise CoordinatorEventConflictError("event_id_conflict")
                return self._latest_state(run_id)
        edge = _TRANSITIONS.get((str(current.payload["state"]), event))
        if edge is None:
            self._record_rejection(
                run_id=run_id,
                current=current,
                event=event,
                actor=actor,
                reason="illegal_transition",
                expected_revision=expected_revision,
            )
            raise IllegalTransitionError("illegal_transition")
        target_state, required_actor = edge
        if required_actor == "human_or_operator":
            allowed = actor in {"human", "operator"}
        else:
            allowed = actor == required_actor
        if not allowed:
            self._record_rejection(
                run_id=run_id,
                current=current,
                event=event,
                actor=actor,
                reason="actor_not_allowed",
                expected_revision=expected_revision,
            )
            raise IllegalTransitionError("actor_not_allowed")
        guard_passed, guard_failure = self._guard_passes(run_id, event, transition_payload)
        if not guard_passed:
            reason = guard_failure or (
                "projection_required"
                if event in {"alignment_projection_ready", "handoff_confirmed"}
                else "guard_failed"
            )
            self._record_rejection(
                run_id=run_id,
                current=current,
                event=event,
                actor=actor,
                reason=reason,
                expected_revision=expected_revision,
            )
            raise IllegalTransitionError(reason)
        if event == "delivery_accepted":
            return self.complete(
                run_id,
                actor=actor,
                expected_revision=expected_revision,
                requirements=transition_payload,
            )
        return self._append_transition(
            run_id=run_id,
            current=current,
            event=event,
            actor=actor,
            target_state=target_state,
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
            payload=transition_payload,
        )

    def ingest_host_event(self, event: HostEvent | Mapping[str, Any]) -> ArtifactRevision:
        """Validate and atomically persist one non-authoritative host event."""

        return self.ingest_host_events((event,))[0]

    def ingest_host_events(self, events: Sequence[HostEvent | Mapping[str, Any]]) -> tuple[ArtifactRevision, ...]:
        """Atomically persist an ordered host-event batch and its projections."""

        try:
            envelopes = tuple(HostEvent.from_value(event) for event in events)
        except HostEventError as error:
            raise CoordinatorConflictError(str(error)) from error
        if not envelopes:
            raise CoordinatorConflictError("host_event_batch_empty")
        if len({event.event_id for event in envelopes}) != len(envelopes):
            raise CoordinatorEventConflictError("event_id_conflict")
        run_id = envelopes[0].run_id
        attempt_id = envelopes[0].attempt_id
        expected_revision = envelopes[0].expected_revision
        if any(
            event.run_id != run_id or event.attempt_id != attempt_id or event.expected_revision != expected_revision
            for event in envelopes
        ):
            raise CoordinatorConflictError("host_event_batch_lineage")
        artifacts = self.ledger.load_run(run_id).artifacts
        event_ids = {event.event_id for event in envelopes}
        existing_by_id = {item.id: item for item in artifacts if item.kind == HOST_EVENT_KIND and item.id in event_ids}
        if existing_by_id:
            if len(existing_by_id) != len(envelopes):
                raise CoordinatorEventConflictError("partial_event_batch")
            replay = []
            for envelope in envelopes:
                existing = existing_by_id[envelope.event_id]
                declared = envelope.to_dict()
                identity_fields = (
                    "kind",
                    "run_id",
                    "round_id",
                    "decision_slot_id",
                    "action_id",
                    "attempt_id",
                    "sequence",
                    "actor",
                    "created_at",
                    "causation_id",
                    "payload_digest",
                )
                if any(existing.payload.get(field) != declared.get(field) for field in identity_fields):
                    raise CoordinatorEventConflictError("event_id_conflict")
                replay.append(existing)
            return tuple(replay)
        current_revision = self.ledger.get_revision(run_id)
        if expected_revision != current_revision:
            raise CoordinatorConflictError("stale_revision")
        current = self._latest_state(run_id)
        lease_candidates = [
            item
            for item in artifacts
            if item.kind == LEASE_KIND
            and item.id == attempt_id
            and self.ledger.is_latest_artifact(self._artifact_ref(item))
        ]
        lease = max(lease_candidates, key=lambda item: item.revision, default=None)
        if lease is None:
            raise CoordinatorConflictError("unknown_attempt")
        if self._artifact_ref(lease) in self._quarantined_refs(run_id):
            raise StaleStateError("host_event")
        lease_payload = lease.payload
        if lease_payload.get("attempt_id") != attempt_id:
            raise CoordinatorConflictError("lease_attempt_mismatch")
        if lease_payload.get("status") != "active":
            raise CoordinatorConflictError("lease_inactive")
        expires_at = lease_payload.get("expires_at")
        if expires_at is not None:
            try:
                expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            except ValueError as error:
                raise CoordinatorConflictError("lease_expiry_invalid") from error
            if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
                raise CoordinatorConflictError("lease_expired")
        work_item = lease_payload.get("work_item")
        if isinstance(work_item, Mapping):
            for event_value, keys, label in (
                (envelopes[0].decision_slot_id, ("decision_slot_id", "slot_id"), "decision_slot"),
                (envelopes[0].action_id, ("action_id",), "action"),
            ):
                if event_value is None:
                    continue
                expected = next((work_item[key] for key in keys if key in work_item), None)
                if expected is not None and str(expected) != event_value:
                    raise CoordinatorConflictError(f"{label}_binding_mismatch")
        previous_sequences = [
            int(item.payload.get("sequence", 0))
            for item in artifacts
            if item.kind == HOST_EVENT_KIND and item.payload.get("attempt_id") == attempt_id
        ]
        expected_sequence = max(previous_sequences, default=0) + 1
        previous_events = {
            int(item.payload.get("sequence", 0)): str(item.payload.get("event_id"))
            for item in artifacts
            if item.kind == HOST_EVENT_KIND and item.payload.get("attempt_id") == attempt_id
        }
        specs = []
        for offset, envelope in enumerate(envelopes):
            required_sequence = expected_sequence + offset
            if envelope.sequence != required_sequence:
                raise HostEventSequenceError(
                    f"host event sequence must be {required_sequence}; got {envelope.sequence}"
                )
            predecessor = previous_events.get(envelope.sequence - 1)
            if envelope.sequence > 1:
                if envelope.causation_id is None:
                    raise CoordinatorConflictError("causation_required")
                if predecessor is None or predecessor != envelope.causation_id:
                    raise CoordinatorConflictError("causation_mismatch")
            elif envelope.causation_id not in (None, attempt_id):
                raise CoordinatorConflictError("causation_mismatch")
            self._validate_host_event_payload(envelope, run_id=run_id, attempt_id=attempt_id, work_item=work_item)
            previous_events[envelope.sequence] = envelope.event_id
            event_ref = ArtifactRef(run_id, envelope.event_id, 1)
            specs.extend(
                (
                    (
                        envelope.event_id,
                        HOST_EVENT_KIND,
                        {
                            **envelope.to_dict(),
                            "semantic_digest": envelope.semantic_digest,
                            "authoritative": False,
                        },
                        (ArtifactRef(run_id, current.id, current.revision),),
                    ),
                    (
                        f"host-projection-{envelope.event_id}",
                        HOST_EVENT_PROJECTION_KIND,
                        {
                            "event_ref": event_ref.to_dict(),
                            "attempt_id": envelope.attempt_id,
                            "sequence": envelope.sequence,
                            "kind": envelope.kind,
                            "status": "observed",
                            "authoritative": False,
                            "semantic_digest": envelope.semantic_digest,
                        },
                        (
                            ArtifactRef(run_id, current.id, current.revision),
                            event_ref,
                            ArtifactRef(run_id, lease.id, lease.revision),
                        ),
                    ),
                )
            )
        try:
            created = self.ledger.append_artifact_batch(run_id, tuple(specs), expected_revision=current_revision)
        except LedgerConflictError as error:
            raise CoordinatorConflictError("stale_revision") from error
        return tuple(created[::2])

    def _validate_host_event_payload(
        self, event: HostEvent, *, run_id: str, attempt_id: str, work_item: Mapping[str, Any] | None
    ) -> None:
        payload = event.payload
        if event.kind == "checkpoint_persisted":
            checkpoint = self._resolve_host_artifact_ref(
                run_id,
                attempt_id,
                payload.get("checkpoint_ref"),
                label="checkpoint",
                kinds=(ANALYSIS_CHECKPOINT_KIND,),
                statuses=(),
            )
            declared_digest = payload.get("checkpoint_digest")
            if declared_digest not in {_digest(thaw_json(checkpoint.payload)), checkpoint.content_hash}:
                raise CoordinatorConflictError("checkpoint_digest_mismatch")
            return
        if event.kind != "worker_finished":
            return
        attempt_outcome_value = payload.get("attempt_outcome")
        if attempt_outcome_value is not None:
            try:
                attempt_outcome = outcome_from_mapping(attempt_outcome_value)
            except HostAttemptError as error:
                raise CoordinatorConflictError("attempt_outcome_invalid") from error
            if not worker_finished_eligible(attempt_outcome):
                raise CoordinatorConflictError("attempt_outcome_semantic_failure")
        capture_values = payload.get("capture_refs", payload.get("source_capture_refs"))
        receipt_values = payload.get("receipt_refs")
        checkpoint_value = payload.get("checkpoint_ref", payload.get("analysis_checkpoint_ref"))
        finding_values = payload.get("finding_refs", payload.get("finding_pack_refs"))
        produced_values = payload.get("produced_artifact_refs")
        if not isinstance(capture_values, Sequence) or isinstance(capture_values, (str, bytes)) or not capture_values:
            raise CoordinatorConflictError("capture_incomplete")
        if not isinstance(receipt_values, Sequence) or isinstance(receipt_values, (str, bytes)) or not receipt_values:
            raise CoordinatorConflictError("receipt_incomplete")
        if checkpoint_value is None:
            raise CoordinatorConflictError("checkpoint_incomplete")
        if not isinstance(finding_values, Sequence) or isinstance(finding_values, (str, bytes)) or not finding_values:
            raise CoordinatorConflictError("finding_pack_incomplete")
        if not isinstance(produced_values, Sequence) or isinstance(produced_values, (str, bytes)):
            raise CoordinatorConflictError("produced_artifact_refs_invalid")
        capture_artifacts = tuple(
            self._resolve_host_artifact_ref(
                run_id,
                attempt_id,
                value,
                label="capture",
                kinds=(SOURCE_CAPTURE_KIND,),
                statuses=("committed",),
            )
            for value in capture_values
        )
        receipt_artifacts = tuple(
            self._resolve_host_artifact_ref(
                run_id,
                attempt_id,
                value,
                label="receipt",
                kinds=(ACQUISITION_RECEIPT_KIND,),
                statuses=("succeeded",),
            )
            for value in receipt_values
        )
        checkpoint = self._resolve_host_artifact_ref(
            run_id,
            attempt_id,
            checkpoint_value,
            label="checkpoint",
            kinds=(ANALYSIS_CHECKPOINT_KIND,),
            statuses=(),
        )
        finding_artifacts = tuple(
            self._resolve_host_artifact_ref(
                run_id,
                attempt_id,
                value,
                label="finding_pack",
                kinds=(FINDING_PACK_KIND,),
                statuses=(),
            )
            for value in finding_values
        )
        for value in produced_values:
            self._resolve_host_artifact_ref(
                run_id,
                attempt_id,
                value,
                label="produced_artifact",
                kinds=None,
                statuses=(),
            )
        capture_ids = {artifact.id for artifact in capture_artifacts}
        for receipt in receipt_artifacts:
            capture_id = receipt.payload.get("capture_id")
            if capture_id is not None and str(capture_id) not in capture_ids:
                raise CoordinatorConflictError("receipt_capture_mismatch")
        if checkpoint.payload.get("attempt_id") != attempt_id:
            raise CoordinatorConflictError("checkpoint_attempt_mismatch")
        for finding in finding_artifacts:
            finding_attempt = finding.payload.get("attempt_id")
            if finding_attempt is not None and str(finding_attempt) != attempt_id:
                raise CoordinatorConflictError("finding_pack_attempt_mismatch")
        portfolio_id = work_item.get("portfolio_id") if isinstance(work_item, Mapping) else None
        lineage_value = payload.get("portfolio_lineage_ref")
        if portfolio_id is not None and lineage_value is None:
            raise CoordinatorConflictError("portfolio_lineage_required")
        if lineage_value is not None:
            lineage = self._resolve_host_artifact_ref(
                run_id,
                attempt_id,
                lineage_value,
                label="portfolio_lineage",
                kinds=(SEARCH_PORTFOLIO_LINEAGE_KIND,),
                statuses=(),
            )
            if any(reference in self._quarantined_refs(run_id) for reference in lineage.parent_refs):
                raise CoordinatorConflictError("portfolio_lineage_reference_invalid")
            lineage_portfolio = lineage.payload.get("portfolio")
            if not isinstance(lineage_portfolio, Mapping) or lineage_portfolio.get("portfolio_id") != portfolio_id:
                raise CoordinatorConflictError("portfolio_lineage_identity_mismatch")
            expected_refs = {
                "capture_refs": {ArtifactRef.from_dict(item) for item in lineage.payload.get("capture_refs", ())},
                "receipt_refs": {ArtifactRef.from_dict(item) for item in lineage.payload.get("receipt_refs", ())},
                "checkpoint_refs": {ArtifactRef.from_dict(item) for item in lineage.payload.get("checkpoint_refs", ())},
                "finding_refs": {ArtifactRef.from_dict(item) for item in lineage.payload.get("finding_refs", ())},
            }
            actual_refs = {
                "capture_refs": {ArtifactRef(run_id, item.id, item.revision) for item in capture_artifacts},
                "receipt_refs": {ArtifactRef(run_id, item.id, item.revision) for item in receipt_artifacts},
                "checkpoint_refs": {ArtifactRef(run_id, checkpoint.id, checkpoint.revision)},
                "finding_refs": {ArtifactRef(run_id, item.id, item.revision) for item in finding_artifacts},
            }
            if expected_refs != actual_refs:
                raise CoordinatorConflictError("portfolio_lineage_evidence_mismatch")

    def _resolve_lineage_refs(
        self,
        run_id: str,
        attempt_id: str,
        values: Sequence[ArtifactRef],
        label: str,
        kinds: tuple[str, ...],
        statuses: tuple[str, ...],
    ) -> tuple[ArtifactRevision, ...]:
        if isinstance(values, (str, bytes)) or not values:
            raise CoordinatorConflictError(f"{label}_references_invalid")
        resolved = tuple(
            self._resolve_host_artifact_ref(run_id, attempt_id, value, label=label, kinds=kinds, statuses=statuses)
            for value in values
        )
        if len({(item.id, item.revision) for item in resolved}) != len(resolved):
            raise CoordinatorConflictError(f"{label}_references_invalid")
        return resolved

    def _resolve_lineage_parent(
        self, run_id: str, reference: ArtifactRef, label: str, kinds: tuple[str, ...]
    ) -> ArtifactRevision:
        try:
            if not isinstance(reference, ArtifactRef) or reference.round_id != run_id:
                raise ValueError("reference belongs to another run")
            artifact = self.ledger.get_artifact(reference)
            if (
                not self.ledger.is_latest_artifact(reference)
                or reference in self._quarantined_refs(run_id)
                or artifact.kind not in kinds
            ):
                raise ValueError("reference is stale or has an invalid kind")
            return artifact
        except (RuntimeStoreError, TypeError, ValueError) as error:
            raise CoordinatorConflictError(f"{label}_reference_invalid") from error

    def _resolve_host_artifact_ref(
        self,
        run_id: str,
        attempt_id: str,
        value: Any,
        *,
        label: str,
        kinds: tuple[str, ...] | None,
        statuses: tuple[str, ...],
    ) -> ArtifactRevision:
        try:
            if isinstance(value, ArtifactRef):
                reference = value
            elif isinstance(value, Mapping):
                reference = ArtifactRef.from_dict(value)
            elif isinstance(value, str):
                parts = value.split(":")
                if len(parts) != 3:
                    raise ValueError("reference must be an exact artifact reference")
                reference = ArtifactRef(parts[0], parts[1], int(parts[2]))
            else:
                raise ValueError("reference must be an exact artifact reference")
            if reference.round_id != run_id:
                raise ValueError("reference belongs to another run")
            artifact = self.ledger.get_artifact(reference)
            if not self.ledger.is_latest_artifact(reference):
                raise ValueError("reference is stale")
            if reference in self._quarantined_refs(run_id):
                raise ValueError("reference is quarantined")
            if kinds is not None and artifact.kind not in kinds:
                raise ValueError("reference kind is not allowed")
            if statuses and artifact.payload.get("status") not in statuses:
                raise ValueError("reference is not committed")
            artifact_attempt = artifact.payload.get("attempt_id")
            if artifact_attempt is not None and str(artifact_attempt) != attempt_id:
                raise ValueError("reference belongs to another attempt")
            return artifact
        except (RuntimeStoreError, TypeError, ValueError) as error:
            raise CoordinatorConflictError(f"{label}_reference_invalid") from error

    def dispatch(
        self,
        *,
        run_id: str,
        work_item: Mapping[str, Any],
        worker_id: str,
        expected_revision: int,
        attempt_id: str | None = None,
    ) -> ArtifactRevision:
        if (
            not isinstance(work_item, Mapping)
            or not work_item.get("success_oracle")
            and not work_item.get("completion_evidence")
        ):
            raise CoordinatorConflictError("unverifiable_work_item")
        self._assert_current_authority(
            run_id,
            "dispatch",
            work_item.get("authority_binding"),
        )
        frame_ref_value = work_item.get("decision_frame_ref")
        if frame_ref_value is not None:
            frame_artifact = self.require_decision_frame(
                frame_ref_value,
                run_id=run_id,
                target_ref=work_item.get("target_ref"),
            )
        elif work_item.get("canonical") or work_item.get("strategy_ref") or work_item.get("research_plan_ref"):
            raise CoordinatorConflictError("decision_frame_required")
        else:
            frame_artifact = None
        current = self._latest_state(run_id)
        if current.payload.get("state") != "autonomous_research":
            raise CoordinatorConflictError("strategy_projection_confirmation_required")
        projection_value = current.payload.get("strategy_projection_ref")
        if projection_value is None:
            raise CoordinatorConflictError("strategy_projection_confirmation_required")
        projection_artifact, projection = self.require_strategy_projection(
            _ref(projection_value, "strategy_projection_ref"),
            run_id=run_id,
            require_displayed=True,
        )
        if current.payload.get("strategy_display_digest") != projection.display_digest:
            raise CoordinatorConflictError("strategy_projection_stale")
        selected_attempt = attempt_id or "attempt-" + hashlib.sha256(canonical_json_bytes(work_item)).hexdigest()[:24]
        validate_identifier(selected_attempt, "attempt_id")
        for item in self.ledger.load_run(run_id).artifacts:
            if item.kind == LEASE_KIND and item.id == selected_attempt:
                if self._artifact_ref(item) in self._quarantined_refs(run_id):
                    raise StaleStateError("dispatch")
                return item
        policy_proposal_id = self._policy_proposal_id(run_id, work_item)
        payload = {
            "attempt_id": selected_attempt,
            "work_item": dict(work_item),
            "worker_id": _text(worker_id, "worker_id"),
            "status": "active",
            "retry_ordinal": 0,
            "idempotency_key": selected_attempt,
            "lease_revision": 1,
            "policy_proposal_id": policy_proposal_id,
        }
        parent_refs = [
            ArtifactRef(run_id, current.id, current.revision),
            ArtifactRef(run_id, projection_artifact.id, projection_artifact.revision),
        ]
        if frame_artifact is not None:
            parent_refs.append(ArtifactRef(run_id, frame_artifact.id, frame_artifact.revision))
        try:
            return self.ledger.append_artifact(
                run_id,
                selected_attempt,
                LEASE_KIND,
                payload,
                parent_refs=tuple(parent_refs),
                expected_revision=expected_revision,
            )
        except LedgerConflictError as error:
            raise CoordinatorConflictError("stale_revision") from error

    def _policy_proposal_id(self, run_id: str, work_item: Mapping[str, Any]) -> str | None:
        """Consult the scheduling policy at the dispatch decision point.

        Returns the top proposal's action id for attempt lineage when a policy
        is wired and produces a proposal for the run's decision slots; returns
        None (current behavior) when no policy is wired or nothing is proposed.
        """

        if self.policy is None:
            return None
        slots = work_item.get("decision_slots")
        if slots is None:
            target = self._target(run_id)
            slots = thaw_json(target.payload).get("decision_slots") if target is not None else None
        deficits = [
            {
                "slot_id": slot["id"],
                "question": slot.get("question", slot.get("objective", "Close the decision slot")),
                "priority": slot.get("priority", "P1"),
                "closure_oracle": slot.get("closure_oracle") or slot.get("success_oracle") or "",
            }
            for slot in slots
            if isinstance(slot, Mapping)
            and slot.get("id")
            and (slot.get("closure_oracle") or slot.get("success_oracle"))
        ]
        if not deficits:
            return None
        evaluation = self.policy.evaluate(slots=deficits)
        return evaluation.proposals[0].action_id if evaluation.proposals else None

    def self_state(self, run_id: str) -> dict:
        """Issue #324: canonical state projected across 5 orthogonal regions.

        Each region carries its own (value, revision) tuple.  Transitions advance
        exactly the affected region(s); cross-region combinations are validated
        against the region table.
        """

        if not isinstance(run_id, str) or not run_id:
            raise CoordinatorConflictError("run_id_required")
        current = self._latest_state(run_id)
        payload = thaw_json(current.payload)
        if "state" not in payload:
            raise CoordinatorConflictError("state_field_required")
        region_values = _state_regions(str(payload["state"]))
        out = {}
        for region in self.STATE_REGIONS:
            entry = region_values.get(region, {})
            out[region] = {
                "value": entry.get("value"),
                "revision": int(entry.get("revision", current.revision)),
                "updated_at": entry.get("updated_at", ""),
            }
        out["lineage"] = {
            "run_id": run_id,
            "revision": current.revision,
            "affected_forest_or_branch": payload.get("affected_forest_or_branch", ()),
            "authority": payload.get("authority", ""),
            "blockers": payload.get("blockers", ()),
            "authority_waits": payload.get("authority_waits", ()),
            "next_action": payload.get("next_action", ""),
            "expected_transition_oracle": payload.get("expected_transition_oracle", ""),
            "experiments": payload.get("experiments", ()),
        }
        return out

    @staticmethod
    def _artifact_ref(item: ArtifactRevision) -> ArtifactRef:
        return ArtifactRef(item.round_id, item.id, item.revision)

    def _latest_kind(self, run_id: str, kind: str) -> ArtifactRevision | None:
        """Return the current revision for a singleton coordinator input kind."""

        quarantined = self._quarantined_refs(run_id)
        candidates = [
            item
            for item in self.ledger.load_run(run_id).artifacts
            if item.kind == kind
            and self._artifact_ref(item) not in quarantined
            and self.ledger.is_latest_artifact(self._artifact_ref(item))
        ]
        return max(candidates, key=lambda item: (item.revision, item.id)) if candidates else None

    def _target(self, run_id: str) -> ArtifactRevision | None:
        states = self._states(run_id)
        if not states:
            return None
        current = max(states, key=lambda item: item.revision)
        if current.payload.get("correction_event_id") is not None:
            try:
                binding = self._current_authority(current)["decision_map"]
                target = self.ledger.get_artifact(binding.artifact_ref)
            except (RuntimeStoreError, CoordinatorConflictError):
                return None
            return target if target.kind == "blueprint-target" else None
        initial = min(states, key=lambda item: item.revision)
        for reference in initial.parent_refs:
            candidate = self.ledger.get_artifact(reference)
            if candidate.kind == "blueprint-target" and self.ledger.is_latest_artifact(reference):
                return candidate
        return None

    def _completion_inputs(self, run_id: str) -> dict[str, ArtifactRevision]:
        registrations = self.ledger.list_completion_input_registrations(run_id)
        result: dict[str, ArtifactRevision] = {}
        for key, role in (
            ("insight_ref", "insight"),
            ("readiness_ref", "readiness"),
            ("evaluation_ref", "evaluation"),
            ("technical_delivery_ref", "technical_delivery"),
            ("human_delivery_ref", "human_delivery"),
            ("acceptance_ref", "acceptance"),
        ):
            items = registrations.get(role, ())
            if len(items) == 1:
                result[key] = items[0]
        return result

    def _completion_manifold(self, run_id: str) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        """Resolve completion only from current typed registrations."""

        registrations = self.ledger.list_completion_input_registrations(run_id)
        diagnostics: dict[str, dict[str, Any]] = {}
        manifold: dict[str, Any] = {}

        target = self._target(run_id)
        p0_slots = (
            {
                str(slot.get("id"))
                for slot in target.payload.get("decision_slots", ())
                if isinstance(slot, Mapping) and slot.get("priority") == "P0" and slot.get("id")
            }
            if target is not None
            else set()
        )
        closure_items = registrations.get("closure", ())
        closed_by_slot: dict[str, ArtifactRevision] = {}
        for item in closure_items:
            slot_id = str(item.payload.get("slot_id", ""))
            if (
                item.payload.get("status") == "passed"
                and item.payload.get("closure_token")
                and (target is None or self._artifact_ref(target) in item.parent_refs)
            ):
                closed_by_slot.setdefault(slot_id, item)
        missing_slots = sorted(p0_slots - set(closed_by_slot))
        duplicate_slots = sorted(
            slot
            for slot in closed_by_slot
            if sum(1 for item in closure_items if str(item.payload.get("slot_id", "")) == slot) > 1
        )
        if not p0_slots:
            diagnostics["p0_closure_tokens"] = {"status": "fail", "reason": "no_p0_slots"}
        elif missing_slots:
            diagnostics["p0_closure_tokens"] = {
                "status": "fail",
                "reason": "missing_slot",
                "missing_slots": missing_slots,
            }
        elif duplicate_slots:
            diagnostics["p0_closure_tokens"] = {
                "status": "fail",
                "reason": "duplicate_slot",
                "duplicate_slots": duplicate_slots,
            }
        else:
            closure_refs = [self._artifact_ref(closed_by_slot[slot]).to_dict() for slot in sorted(closed_by_slot)]
            manifold["closure_refs"] = closure_refs
            diagnostics["p0_closure_tokens"] = {"status": "pass", "refs": closure_refs}

        singleton_specs = (
            ("insight_ref", "insight", lambda item: item.payload.get("status") == "non_blocking"),
            ("readiness_ref", "readiness", lambda item: item.payload.get("status") in {"ready", "passed"}),
            ("evaluation_ref", "evaluation", lambda item: item.payload.get("status") in {"passed", "pass"}),
        )
        for field, role, predicate in singleton_specs:
            items = registrations.get(role, ())
            if not items:
                diagnostics[field] = {"status": "fail", "reason": "not_registered"}
            elif len(items) != 1:
                diagnostics[field] = {
                    "status": "fail",
                    "reason": "ambiguous_registration",
                    "refs": [self._artifact_ref(item).to_dict() for item in items],
                }
            elif not predicate(items[0]):
                diagnostics[field] = {
                    "status": "fail",
                    "reason": "status_not_satisfied",
                    "ref": self._artifact_ref(items[0]).to_dict(),
                }
            else:
                reference = self._artifact_ref(items[0]).to_dict()
                manifold[field] = reference
                diagnostics[field] = {"status": "pass", "ref": reference}

        technical_items = registrations.get("technical_delivery", ())
        human_items = registrations.get("human_delivery", ())
        if len(technical_items) != 1:
            diagnostics["technical_delivery_ref"] = {
                "status": "fail",
                "reason": "not_registered" if not technical_items else "ambiguous_registration",
                "refs": [self._artifact_ref(item).to_dict() for item in technical_items],
            }
        elif len(human_items) != 1:
            diagnostics["technical_delivery_ref"] = {
                "status": "fail",
                "reason": "pair_incomplete",
                "ref": self._artifact_ref(technical_items[0]).to_dict(),
            }
            diagnostics["human_delivery_ref"] = {
                "status": "fail",
                "reason": "not_registered" if not human_items else "ambiguous_registration",
                "refs": [self._artifact_ref(item).to_dict() for item in human_items],
            }
        else:
            technical = technical_items[0]
            human = human_items[0]
            technical_ref = self._artifact_ref(technical)
            human_ref = self._artifact_ref(human)
            human_package_ref = human.payload.get("technical_package_ref")
            try:
                parsed_human_package_ref = ArtifactRef.from_dict(human_package_ref)
            except (RuntimeStoreError, TypeError, ValueError):
                parsed_human_package_ref = None
            pair_matches = parsed_human_package_ref == technical_ref and technical_ref in human.parent_refs
            if not pair_matches:
                reason = "pair_lineage_mismatch"
                diagnostics["technical_delivery_ref"] = {
                    "status": "fail",
                    "reason": reason,
                    "ref": technical_ref.to_dict(),
                }
                diagnostics["human_delivery_ref"] = {
                    "status": "fail",
                    "reason": reason,
                    "ref": human_ref.to_dict(),
                }
            else:
                technical_value = _delivery_revision_value(technical, "technical_revision")
                human_value = _delivery_revision_value(human, "human_revision")
                manifold["technical_delivery_ref"] = technical_ref.to_dict()
                manifold["human_delivery_ref"] = human_ref.to_dict()
                diagnostics["technical_delivery_ref"] = {
                    "status": "pass",
                    "ref": technical_ref.to_dict(),
                    "revision": technical_value,
                }
                diagnostics["human_delivery_ref"] = {
                    "status": "pass",
                    "ref": human_ref.to_dict(),
                    "revision": human_value,
                }

                acceptance_items = registrations.get("acceptance", ())
                if len(acceptance_items) != 1:
                    diagnostics["acceptance_ref"] = {
                        "status": "fail",
                        "reason": "not_registered" if not acceptance_items else "ambiguous_registration",
                        "refs": [self._artifact_ref(item).to_dict() for item in acceptance_items],
                    }
                else:
                    acceptance = acceptance_items[0]
                    acceptance_ref = self._artifact_ref(acceptance)
                    acceptance_payload = acceptance.payload
                    exact_pair = (
                        set(acceptance.parent_refs) == {technical_ref, human_ref} and len(acceptance.parent_refs) == 2
                    )
                    try:
                        from .completion_inputs import delivery_manifest_digest

                        expected_manifest_digest = delivery_manifest_digest(technical, human)
                    except (RuntimeStoreError, TypeError, ValueError):
                        expected_manifest_digest = None
                    digest_matches = (
                        acceptance_payload.get("technical_revision") == technical_value
                        and acceptance_payload.get("human_revision") == human_value
                        and acceptance_payload.get("displayed_digest")
                        == _delivery_pair_digest(run_id, technical_value, human_value)
                        and acceptance_payload.get("manifest_digest") == expected_manifest_digest
                    )
                    accepted = acceptance_payload.get("decision", acceptance_payload.get("status")) in {
                        "accepted",
                        "passed",
                    }
                    actor = acceptance_payload.get("actor")
                    actor_allowed = actor == "human" or (isinstance(actor, str) and actor.startswith("human-"))
                    if not exact_pair or not digest_matches or not accepted or not actor_allowed:
                        diagnostics["acceptance_ref"] = {
                            "status": "fail",
                            "reason": "pair_digest_mismatch" if exact_pair else "pair_lineage_mismatch",
                            "ref": acceptance_ref.to_dict(),
                        }
                    else:
                        manifold["acceptance_ref"] = acceptance_ref.to_dict()
                        diagnostics["acceptance_ref"] = {"status": "pass", "ref": acceptance_ref.to_dict()}
        goal_satisfaction = self._goal_satisfaction_diagnostic(run_id, registrations)
        diagnostics["goal_satisfaction"] = goal_satisfaction
        if goal_satisfaction["status"] == "pass":
            manifold["goal_satisfaction_refs"] = goal_satisfaction["refs"]
        independent_review = self._independent_delivery_review_diagnostic(run_id, registrations)
        diagnostics["independent_delivery_review"] = independent_review
        if independent_review["status"] == "pass":
            manifold["independent_review_refs"] = [independent_review["ref"]]
        diagnostics.setdefault(
            "technical_delivery_ref",
            {"status": "fail", "reason": "pair_incomplete"},
        )
        diagnostics.setdefault(
            "human_delivery_ref",
            {"status": "fail", "reason": "pair_incomplete"},
        )
        diagnostics.setdefault(
            "acceptance_ref",
            {"status": "fail", "reason": "pair_incomplete"},
        )
        return manifold, diagnostics

    @staticmethod
    def _projection_oracle_ids(projection_payload: Mapping[str, Any]) -> list[str]:
        """Extract the distinct success-oracle ids of a projection payload."""

        oracle_ids: list[str] = []
        for oracle in projection_payload.get("success_oracles") or ():
            if isinstance(oracle, Mapping) and isinstance(oracle.get("id"), str) and oracle["id"].strip():
                oracle_id = str(oracle["id"])
            elif isinstance(oracle, str) and oracle.strip():
                oracle_id = oracle
            else:
                continue
            if oracle_id not in oracle_ids:
                oracle_ids.append(oracle_id)
        return oracle_ids

    def _independent_alignment_verification_failure(self, run_id: str, projection: StrategyProjection) -> str | None:
        """Issue #462 display gate: require an independent alignment verification.

        A current ``alignment-verification`` registration must bind the exact
        projection content through the authority fingerprint (so a draft's
        promotion to displayed keeps its verification while any authority-field
        revision invalidates it), name a distinct execution identity for the
        verifier, and independently restate every success oracle. Issue #471:
        independence is judged against the registration's durable write-time
        principal, which must be the binding of the declared identity pair; an
        unbound or coordinator principal fails closed.
        """

        oracle_ids = self._projection_oracle_ids(projection.display_payload)
        principals = self.ledger.completion_input_registration_principals(run_id)
        for item in self.ledger.list_completion_input_registrations(run_id).get(ALIGNMENT_VERIFICATION_ROLE, ()):
            try:
                parsed = validate_alignment_verification_payload(thaw_json(item.payload))
            except IndependentReviewError:
                continue
            if parsed["authority_fingerprint"] != authority_fingerprint(projection):
                continue
            projection_ref = parsed["projection_ref"]
            if projection_ref.round_id != run_id or projection_ref.artifact_id != projection.projection_id:
                continue
            if not verify_identity_independent(
                parsed["verifier_identity"],
                parsed["session_context"],
                issuer=principals.get(ArtifactRef(item.round_id, item.id, item.revision)),
            ):
                continue
            restated = {str(entry["id"]) for entry in parsed["understood"]["success_oracles"]}
            if any(oracle_id not in restated for oracle_id in oracle_ids):
                continue
            return None
        return "independent_verification_required"

    def _independent_delivery_review_diagnostic(
        self, run_id: str, registrations: Mapping[str, tuple[ArtifactRevision, ...]]
    ) -> dict[str, Any]:
        """Issue #462 delivery gate: require an independent delivery review.

        Conjunction, not replacement: this diagnostic runs beside the #443
        goal_satisfaction diagnostic and both block ``delivery_accepted``. The
        review must be a single current ``delivery-review`` registration whose
        verifier identity is structurally independent — distinct from the
        session context and bound to the registration's durable write-time
        principal (#471); an unbound or coordinator principal fails closed —
        whose evidence custody parents are exactly the
        custody references it names and still resolve to current,
        non-quarantined run artifacts, whose per-oracle verdicts cover every
        confirmed projection oracle, and whose overall verdict is not ``unmet``.
        """

        snapshot = self.ledger.load_run(run_id)
        projection = latest_confirmed(snapshot.artifacts)
        if projection is None:
            return {"status": "fail", "reason": "independent_review_unknown"}
        oracle_ids = self._projection_oracle_ids(projection.payload)
        reviews = registrations.get(DELIVERY_REVIEW_ROLE, ())
        if not reviews:
            return {"status": "fail", "reason": "independent_review_required"}
        if len(reviews) > 1:
            return {
                "status": "fail",
                "reason": "ambiguous_registration",
                "refs": [self._artifact_ref(item).to_dict() for item in reviews],
            }
        review = reviews[0]
        review_ref = self._artifact_ref(review).to_dict()
        try:
            parsed = validate_delivery_review_payload(thaw_json(review.payload))
        except IndependentReviewError:
            return {"status": "fail", "reason": "independent_review_invalid", "ref": review_ref}
        principals = self.ledger.completion_input_registration_principals(run_id)
        if not verify_identity_independent(
            parsed["verifier_identity"],
            parsed["session_context"],
            issuer=principals.get(self._artifact_ref(review)),
        ):
            return {"status": "fail", "reason": "verifier_not_independent", "ref": review_ref}
        if set(review.parent_refs) != set(parsed["evidence_custody"]):
            return {"status": "fail", "reason": "evidence_custody_lineage", "ref": review_ref}
        latest_revision: dict[str, int] = {}
        indexed: dict[tuple[str, int], ArtifactRevision] = {}
        for item in snapshot.artifacts:
            indexed[(item.id, item.revision)] = item
            if item.revision > latest_revision.get(item.id, 0):
                latest_revision[item.id] = item.revision
        quarantined = self._quarantined_refs(run_id)
        custody_current = all(
            reference.round_id == run_id
            and reference not in quarantined
            and latest_revision.get(reference.artifact_id) == reference.revision
            and indexed.get((reference.artifact_id, reference.revision)) is not None
            for reference in parsed["evidence_custody"]
        )
        if not custody_current:
            return {"status": "fail", "reason": "evidence_custody_stale", "ref": review_ref}
        uncovered = [oracle_id for oracle_id in oracle_ids if oracle_id not in parsed["per_oracle"]]
        if uncovered:
            return {"status": "fail", "reason": "oracle_uncovered", "oracles": uncovered, "ref": review_ref}
        if parsed["verdict"] == "unmet":
            return {"status": "fail", "reason": "independent_review_unmet", "ref": review_ref}
        return {"status": "pass", "ref": review_ref}

    def _goal_satisfaction_diagnostic(
        self, run_id: str, registrations: Mapping[str, tuple[ArtifactRevision, ...]]
    ) -> dict[str, Any]:
        """Issue #429: gate completion on the confirmed projection's success oracles.

        Fail-closed semantics: a run whose confirmation record does not resolve
        to a confirmed projection can never pass (``goal_satisfaction_unknown``),
        every projection oracle needs exactly one current goal_satisfaction
        registration (duplicates fail ``oracle_duplicate``), and a missing or
        ``unmet`` verdict leaves the oracle uncovered (``oracle_uncovered``).
        A ``satisfied``/``partial`` verdict only counts when at least one of its
        evidence references resolves to a current, non-quarantined artifact of an
        admissible evidence kind in this run; a waived verdict always counts
        because the registrar already required its non-empty ``waiver_reason``.
        """

        from .completion_inputs import (
            GOAL_SATISFACTION_EVIDENCE_KINDS,
            GOAL_SATISFACTION_ROLE,
            CompletionInputError,
            validate_goal_satisfaction_payload,
        )
        from .strategy_projection import latest_confirmed

        snapshot = self.ledger.load_run(run_id)
        projection = latest_confirmed(snapshot.artifacts)
        if projection is None:
            return {"status": "fail", "reason": "goal_satisfaction_unknown"}
        oracle_ids = self._projection_oracle_ids(projection.payload)
        by_oracle: dict[str, list[tuple[ArtifactRevision, dict[str, Any]]]] = {}
        for item in registrations.get(GOAL_SATISFACTION_ROLE, ()):
            try:
                parsed = validate_goal_satisfaction_payload(thaw_json(item.payload))
            except CompletionInputError:
                continue
            by_oracle.setdefault(parsed["oracle_id"], []).append((item, parsed))
        duplicates = [oracle for oracle in oracle_ids if len(by_oracle.get(oracle, ())) > 1]
        if duplicates:
            return {"status": "fail", "reason": "oracle_duplicate", "oracles": duplicates}
        latest_revision: dict[str, int] = {}
        indexed: dict[tuple[str, int], ArtifactRevision] = {}
        for item in snapshot.artifacts:
            indexed[(item.id, item.revision)] = item
            if item.revision > latest_revision.get(item.id, 0):
                latest_revision[item.id] = item.revision
        quarantined = self._quarantined_refs(run_id)
        uncovered: list[str] = []
        for oracle in oracle_ids:
            registered = by_oracle.get(oracle, ())
            if len(registered) != 1:
                uncovered.append(oracle)
                continue
            item, parsed = registered[0]
            verdict = parsed["verdict"]
            if verdict == "unmet":
                uncovered.append(oracle)
            elif verdict == "waived":
                continue
            elif not any(
                reference.round_id == run_id
                and reference not in quarantined
                and latest_revision.get(reference.artifact_id) == reference.revision
                and indexed.get((reference.artifact_id, reference.revision)) is not None
                and indexed[(reference.artifact_id, reference.revision)].kind in GOAL_SATISFACTION_EVIDENCE_KINDS
                for reference in parsed["evidence_refs"]
            ):
                uncovered.append(oracle)
        if uncovered:
            return {"status": "fail", "reason": "oracle_uncovered", "oracles": uncovered}
        refs = [self._artifact_ref(by_oracle[oracle][0][0]).to_dict() for oracle in oracle_ids]
        return {"status": "pass", "refs": refs}

    def _completion_obligations(self, run_id: str) -> tuple[str, ...]:
        """Evaluate completion from ledger evidence, never host supplied claims."""
        _, diagnostics = self._completion_manifold(run_id)
        return tuple(field for field, detail in diagnostics.items() if detail.get("status") != "pass")

    def _acceptance_matches(
        self, acceptance: ArtifactRevision | None, technical: ArtifactRevision | None, human: ArtifactRevision | None
    ) -> bool:
        if acceptance is None or technical is None or human is None:
            return False
        if acceptance.payload.get("decision", acceptance.payload.get("status")) not in {"accepted", "passed"}:
            return False
        technical_ref = self._artifact_ref(technical)
        human_ref = self._artifact_ref(human)
        if not {technical_ref, human_ref} <= set(acceptance.parent_refs):
            return False
        return True

    def why_not_complete(self, run_id: str) -> dict[str, Any]:
        current = self._latest_state(run_id)
        missing = self._completion_obligations(run_id)
        if not missing and current.payload.get("state") == "completed":
            missing = ()
        diagnostics = self._completion_manifold(run_id)[1]
        next_actions = ["resolve:" + item for item in missing]
        goal_detail = diagnostics.get("goal_satisfaction")
        if isinstance(goal_detail, Mapping) and goal_detail.get("reason") == "oracle_uncovered":
            next_actions.extend(
                "resolve:goal_satisfaction:" + str(oracle_id) for oracle_id in goal_detail.get("oracles", ())
            )
        review_detail = diagnostics.get("independent_delivery_review")
        if isinstance(review_detail, Mapping) and review_detail.get("reason") == "oracle_uncovered":
            next_actions.extend(
                "resolve:independent_delivery_review:" + str(oracle_id)
                for oracle_id in review_detail.get("oracles", ())
            )
        return {
            "run_id": run_id,
            "state": current.payload["state"],
            "unmet_obligations": missing,
            "field_diagnostics": diagnostics,
            "next_actions": next_actions,
            "quarantined_paths": self._quarantine_paths(run_id),
            "state_digest": current.payload["state_digest"],
        }

    def complete(
        self, run_id: str, *, actor: str, expected_revision: int, requirements: Mapping[str, Any] | None = None
    ) -> ArtifactRevision:
        current = self._latest_state(run_id)
        completion_requirements = dict(requirements or {})
        self._assert_current_authority(
            run_id,
            "complete",
            completion_requirements.get("authority_binding"),
        )
        if current.payload["state"] in {"completed", "superseded"}:
            if current.payload["state"] == "completed" and self._completion_obligations(run_id):
                raise CompletionBlockedError(self._completion_obligations(run_id))
            return current
        if current.payload["state"] != "awaiting_acceptance":
            raise IllegalTransitionError("illegal_transition")
        if actor != "human":
            raise IllegalTransitionError("actor_not_allowed")
        missing = self._completion_obligations(run_id)
        if missing:
            raise CompletionBlockedError(missing)
        manifold, diagnostics = self._completion_manifold(run_id)
        missing = tuple(field for field, detail in diagnostics.items() if detail.get("status") != "pass")
        if missing:
            raise CompletionBlockedError(missing)
        manifold_digest = _digest(manifold)
        inputs = self._completion_inputs(run_id)
        event_key = "completion:" + manifold_digest[:24]
        existing = self._find_event_key(run_id, event_key)
        if existing is not None:
            return self._latest_state(run_id)
        event_id = "event-" + hashlib.sha256(event_key.encode()).hexdigest()[:24]
        event_payload = {
            "event_id": event_id,
            "idempotency_key": event_key,
            "event": "delivery_accepted",
            "actor": actor,
            "from": current.payload["state"],
            "to": "completed",
        }
        event_ref = ArtifactRef(run_id, event_id, 1)
        completion_payload = {
            "status": "completed",
            "manifold": manifold,
            "manifold_digest": manifold_digest,
            "requirements": {key: self._artifact_ref(item).to_dict() for key, item in inputs.items()},
            "source_state_ref": ArtifactRef(run_id, current.id, current.revision).to_dict(),
        }
        completion_ref = ArtifactRef(run_id, "completion-record", 1)
        state_payload = self._state_payload(
            state="completed",
            lifecycle_revision=int(current.payload.get("lifecycle_revision", 0)) + 1,
            obligations=(),
            legal_actions=("export_audit",),
            idempotency_key=event_key,
        )
        state_payload["completion_requirements"] = completion_payload["requirements"]
        state_payload["previous_state_ref"] = ArtifactRef(run_id, current.id, current.revision).to_dict()
        self._carry_correction_context(current, state_payload)
        state_payload["state_digest"] = _digest(
            {key: value for key, value in state_payload.items() if key != "state_digest"}
        )
        try:
            created = self.ledger.append_artifact_batch(
                run_id,
                (
                    (
                        event_id,
                        LIFECYCLE_EVENT_KIND,
                        event_payload,
                        (ArtifactRef(run_id, current.id, current.revision),),
                    ),
                    (
                        "completion-record",
                        COMPLETION_RECORD_KIND,
                        completion_payload,
                        (
                            ArtifactRef(run_id, current.id, current.revision),
                            event_ref,
                            *(ArtifactRef.from_dict(reference) for reference in manifold["closure_refs"]),
                            *(self._artifact_ref(item) for item in inputs.values()),
                        ),
                    ),
                    (
                        "run-state",
                        RESEARCH_RUN_STATE_KIND,
                        state_payload,
                        (ArtifactRef(run_id, current.id, current.revision), event_ref, completion_ref),
                    ),
                ),
                expected_revision=expected_revision,
            )
        except LedgerConflictError as error:
            raise CoordinatorConflictError("stale_revision") from error
        return created[-1]

    def ingest_pressure_signal(
        self,
        *,
        run_id: str,
        disputed_claim_id: str,
        signal: PressureSignal,
        source: str,
        timestamp: str,
        quality: str = "low",
        contradiction_id: str | None = None,
        validation_state: str | None = None,
        expected_revision: int | None = None,
    ) -> ArtifactRevision:
        """Record one pressure signal against a disputed claim without flipping anything silently.

        Pressure events never mutate the underlying contradiction packet's status.
        They append a new ``DISPUTE_PACKET_KIND`` ledger artifact carrying the
        updated pressure ledger, the latest independent-validation state, and
        the full audit trail.  ``provider_validation`` events additionally
        write a ``PROVIDER_VALIDATION_KIND`` audit artifact.
        """

        validate_identifier(run_id, "run_id")
        validate_identifier(disputed_claim_id, "disputed_claim_id")
        if not isinstance(signal, PressureSignal):
            raise CoordinatorConflictError(f"signal must be a PressureSignal; got {signal!r}")
        if not isinstance(source, str) or not source.strip():
            raise CoordinatorConflictError("pressure source is required")
        if not isinstance(timestamp, str) or not timestamp.strip():
            raise CoordinatorConflictError("pressure timestamp is required")
        if signal is PressureSignal.INDEPENDENT_VALIDATION and not isinstance(validation_state, str):
            raise DisputeDispositionError("provider_validation events require a validation_state")
        if validation_state is not None and validation_state not in {
            "none",
            "requested",
            "passed",
            "failed",
            "inconclusive",
        }:
            raise DisputeDispositionError(f"unknown validation_state: {validation_state!r}")

        artifacts = self.ledger.load_run(run_id).artifacts
        existing_packet = None
        if contradiction_id is not None:
            try:
                existing_packet = self.ledger.get_artifact(ArtifactRef(run_id, contradiction_id, 1))
            except RuntimeStoreError:
                existing_packet = None
        if existing_packet is None and contradiction_id is not None:
            existing_packet = next(
                (item for item in artifacts if item.kind == CONTRADICTION_PACKET_KIND and item.id == contradiction_id),
                None,
            )
        if contradiction_id is not None and existing_packet is None:
            raise CoordinatorConflictError(f"unknown contradiction_id: {contradiction_id}")

        dispute_artifacts = sorted(
            (item for item in artifacts if item.kind == DISPUTE_PACKET_KIND),
            key=lambda item: (item.round_id, item.id, item.revision),
        )
        latest_dispute = None
        for item in reversed(dispute_artifacts):
            if item.payload.get("disputed_claim_id") != disputed_claim_id:
                continue
            latest_dispute = item
            break

        previous_ledger: PressureLedger = ()
        previous_validation = "none"
        previous_signals: tuple[PressureSignal, ...] = ()
        previous_position = "requester disputes claim"
        agent_position = f"agent holds claim {disputed_claim_id} by evidence"
        audit_trail = DisputeAuditTrail()
        if latest_dispute is not None:
            decoded = dispute_packet_from_payload(latest_dispute.payload)
            previous_signals = decoded.pressure_signals
            previous_validation = decoded.independent_validation_state
            previous_position = decoded.requester_position
            previous_audit = decoded.audit_trail
            for raw in previous_audit.entries:
                audit_trail = DisputeAuditTrail(entries=(*audit_trail.entries, raw))
            for raw in latest_dispute.payload.get("pressure_ledger", ()):
                if not isinstance(raw, Mapping):
                    continue
                previous_ledger = append_signal(
                    previous_ledger,
                    signal=PressureSignal(str(raw.get("signal"))),
                    timestamp=str(raw.get("timestamp", "")),
                    source=str(raw.get("source", "")),
                    quality=str(raw.get("quality", "low")),
                )

        # The base for evidence-quality comparison comes from the contradiction packet.
        evidence_basis: dict[str, Any] = {}
        if existing_packet is not None:
            claim_a = existing_packet.payload.get("claim_a") if isinstance(existing_packet.payload, Mapping) else None
            if isinstance(claim_a, Mapping):
                evidence_basis["basis_refs"] = list(claim_a.get("basis_refs", ())) or [
                    f"contradiction:{contradiction_id}"
                ]
                evidence_basis["quality"] = claim_a.get("evidence_quality", "medium")
            else:
                evidence_basis["basis_refs"] = [f"contradiction:{contradiction_id}"]
                evidence_basis["quality"] = "medium"
        else:
            evidence_basis["basis_refs"] = [f"claim:{disputed_claim_id}"]
            evidence_basis["quality"] = "medium"

        new_ledger = append_signal(
            previous_ledger,
            signal=signal,
            timestamp=timestamp,
            source=source,
            quality=quality,
        )
        combined_signals: tuple[PressureSignal, ...] = tuple(dict.fromkeys(previous_signals + (signal,)))
        effective_validation = (
            validation_state
            if signal is PressureSignal.INDEPENDENT_VALIDATION and validation_state is not None
            else previous_validation
        )

        claim_state = {
            "disputed_claim_id": disputed_claim_id,
            "supported_by": evidence_basis,
            "disputed": True,
            "requester_position": previous_position,
            "agent_position": agent_position,
        }
        evaluated: DisputePacket = evaluate_dispute(
            claim_state=claim_state,
            pressure_signals=combined_signals,
            evidence_updates=(),
            audit_trail=audit_trail,
            independent_validation=effective_validation,
            timestamp=timestamp,
        )
        # Reconciliation: keep the prior audit trail without re-deriving.
        evaluated = DisputePacket(
            dispute_id=evaluated.dispute_id,
            disputed_claim_id=evaluated.disputed_claim_id,
            requester_position=evaluated.requester_position or previous_position,
            agent_position=evaluated.agent_position or agent_position,
            evidence_basis=evaluated.evidence_basis,
            pressure_signals=evaluated.pressure_signals,
            independent_validation_state=evaluated.independent_validation_state,
            recommended_verification_path=evaluated.recommended_verification_path,
            audit_trail=audit_trail,
            contradiction_id=contradiction_id,
        )

        dispute_id = f"dispute-{disputed_claim_id}"
        latest_dispute_id = latest_dispute.id if latest_dispute is not None else dispute_id
        ledger_id = f"{latest_dispute_id}-ledger"
        current = self._latest_state(run_id)
        current_ref = self._artifact_ref(current)
        expected = expected_revision if expected_revision is not None else self.ledger.get_revision(run_id)
        dispute_payload = {
            **evaluated.to_dict(),
            "pressure_ledger": [entry.to_dict() for entry in new_ledger],
            "disposition": evaluated.audit_trail.entries[-1].disposition.value
            if evaluated.audit_trail.entries
            else evaluated.independent_validation_state
            if evaluated.independent_validation_state in {"passed", "failed", "inconclusive"}
            else DisputeDisposition.AGENT_HOLDS.value,
        }
        entries: list[tuple[str, str, dict[str, Any], tuple[ArtifactRef, ...]]] = [
            (
                ledger_id,
                DISPUTE_PACKET_KIND,
                dispute_payload,
                (current_ref,),
            )
        ]
        parents: tuple[ArtifactRef, ...] = (current_ref,)
        if existing_packet is not None:
            parents = (*parents, self._artifact_ref(existing_packet))
        if signal is PressureSignal.INDEPENDENT_VALIDATION:
            sanitized_ts = "".join(
                character for character in timestamp.lower() if character.isalnum() or character == "-"
            )[:16]
            provider_id = "provider-validation-" + disputed_claim_id + "-" + sanitized_ts
            entries.append(
                (
                    provider_id,
                    PROVIDER_VALIDATION_KIND,
                    {
                        "disputed_claim_id": disputed_claim_id,
                        "validation_state": effective_validation,
                        "timestamp": timestamp,
                        "source": source,
                        "quality": quality,
                    },
                    parents,
                )
            )
        try:
            appended = self.ledger.append_artifact_batch(run_id, tuple(entries), expected_revision=expected)
        except LedgerConflictError as error:
            raise CoordinatorConflictError("stale_revision") from error
        # If the evaluator's audit_trail differs from the persisted trail, append a flip entry now.
        flip_entries = [entry for entry in evaluated.audit_trail.entries if entry not in audit_trail.entries]
        if flip_entries:
            flip_payload = {
                "disputed_claim_id": disputed_claim_id,
                "pressure_signals": [signal.value for signal in combined_signals],
                "entries": [entry.to_dict() for entry in flip_entries],
                "timestamp": timestamp,
                "contradiction_id": contradiction_id,
            }
            flip_id = f"dispute-audit-{disputed_claim_id}-{timestamp}"
            try:
                appended = self.ledger.append_artifact_batch(
                    run_id,
                    (
                        (
                            flip_id,
                            DISPUTE_PACKET_KIND,
                            flip_payload,
                            (current_ref, *appended),
                        ),
                    ),
                    expected_revision=self.ledger.get_revision(run_id),
                )
            except LedgerConflictError as error:
                raise CoordinatorConflictError("stale_revision") from error
        return appended[-1]

    def recover(self, run_id: str) -> dict[str, Any]:
        reconciled: list[str] = []
        quarantined_attempts: list[str] = []
        quarantined_refs = self._quarantined_refs(run_id)
        for item in self.ledger.load_run(run_id).artifacts:
            if item.kind != LEASE_KIND or item.payload.get("status") != "active":
                continue
            latest = max(
                (
                    candidate
                    for candidate in self.ledger.load_run(run_id).artifacts
                    if candidate.id == item.id and candidate.kind == LEASE_KIND
                ),
                key=lambda candidate: candidate.revision,
            )
            if latest != item:
                continue
            if self._artifact_ref(item) in quarantined_refs:
                quarantined_attempts.append(str(item.payload["attempt_id"]))
                continue
            payload = {**dict(item.payload), "status": "unknown", "recovery_reason": "process_restart"}
            try:
                self.ledger.append_artifact(
                    run_id,
                    item.id,
                    LEASE_KIND,
                    payload,
                    parent_refs=(ArtifactRef(run_id, item.id, item.revision),),
                    expected_revision=self.ledger.get_revision(run_id),
                )
            except LedgerConflictError as error:
                raise CoordinatorConflictError("stale_revision") from error
            reconciled.append(str(item.payload["attempt_id"]))
        for item in self.ledger.load_run(run_id).artifacts:
            if item.kind != LEASE_KIND or item.payload.get("status") != "quarantined":
                continue
            latest = max(
                (
                    candidate
                    for candidate in self.ledger.load_run(run_id).artifacts
                    if candidate.id == item.id and candidate.kind == LEASE_KIND
                ),
                key=lambda candidate: candidate.revision,
            )
            if latest == item and str(item.payload["attempt_id"]) not in quarantined_attempts:
                quarantined_attempts.append(str(item.payload["attempt_id"]))
        return {
            "run_id": run_id,
            "reconciled_attempts": sorted(reconciled),
            "quarantined_attempts": sorted(quarantined_attempts),
            "state_digest": self._latest_state(run_id).payload["state_digest"],
        }


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CoordinatorConflictError(f"{label} must be a non-empty string")
    return value


__all__ = [
    "COMPLETION_RECORD_KIND",
    "CoordinatorConflictError",
    "CoordinatorError",
    "CoordinatorEventConflictError",
    "CoordinatorResult",
    "CompletionBlockedError",
    "HOST_EVENT_KIND",
    "IllegalTransitionError",
    "LEASE_KIND",
    "LIFECYCLE_EVENT_KIND",
    "LIFECYCLE_STATES",
    "RESEARCH_RUN_STATE_KIND",
    "ResearchRunCoordinator",
]


def _state_regions(state: str) -> dict:
    """Project one canonical lifecycle state into the five orthogonal regions (#324).

    States without a canonical region projection fail closed.
    """

    base = {"revision": 0, "updated_at": ""}
    mapping = {
        "alignment": {
            "cognitive": {"value": "active", **base},
            "workflow": {"value": "alignment", **base},
            "authority": {"value": "awaiting_requester", **base},
            "epistemic": {"value": "exploratory", **base},
            "delivery": {"value": "not_started", **base},
        },
        "handoff_pending": {
            "cognitive": {"value": "active", **base},
            "workflow": {"value": "alignment", **base},
            "authority": {"value": "awaiting_requester", **base},
            "epistemic": {"value": "exploratory", **base},
            "delivery": {"value": "not_started", **base},
        },
        "autonomous_research": {
            "cognitive": {"value": "active", **base},
            "workflow": {"value": "autonomous_research", **base},
            "authority": {"value": "research_owner", **base},
            "epistemic": {"value": "depth", **base},
            "delivery": {"value": "not_started", **base},
        },
        "synthesis": {
            "cognitive": {"value": "active", **base},
            "workflow": {"value": "synthesis", **base},
            "authority": {"value": "research_owner", **base},
            "epistemic": {"value": "synthesis", **base},
            "delivery": {"value": "not_started", **base},
        },
        "readiness": {
            "cognitive": {"value": "active", **base},
            "workflow": {"value": "readiness", **base},
            "authority": {"value": "research_owner", **base},
            "epistemic": {"value": "verified", **base},
            "delivery": {"value": "not_started", **base},
        },
        "delivery_pending": {
            "cognitive": {"value": "active", **base},
            "workflow": {"value": "delivery_pending", **base},
            "authority": {"value": "research_owner", **base},
            "epistemic": {"value": "verified", **base},
            "delivery": {"value": "deliveries_compiled", **base},
        },
        "awaiting_acceptance": {
            "cognitive": {"value": "active", **base},
            "workflow": {"value": "awaiting_acceptance", **base},
            "authority": {"value": "awaiting_requester", **base},
            "epistemic": {"value": "verified", **base},
            "delivery": {"value": "delivered", **base},
        },
        "completed": {
            "cognitive": {"value": "settled", **base},
            "workflow": {"value": "completed", **base},
            "authority": {"value": "completed", **base},
            "epistemic": {"value": "settled", **base},
            "delivery": {"value": "completed", **base},
        },
        # Resumable holds project their predecessor stage: the lifecycle matrix
        # enters and exits both inside the autonomous-research stage, so the
        # stage regions carry over. paused keeps research_owner authority
        # (resume needs no requester decision); blocked holds behind a
        # not-yet-recorded method-or-authority decision, so the decision ball
        # sits outside the run -> awaiting_requester.
        "paused": {
            "cognitive": {"value": "active", **base},
            "workflow": {"value": "autonomous_research", **base},
            "authority": {"value": "research_owner", **base},
            "epistemic": {"value": "depth", **base},
            "delivery": {"value": "not_started", **base},
        },
        "blocked": {
            "cognitive": {"value": "active", **base},
            "workflow": {"value": "autonomous_research", **base},
            "authority": {"value": "awaiting_requester", **base},
            "epistemic": {"value": "depth", **base},
            "delivery": {"value": "not_started", **base},
        },
        # Terminal states (lifecycle-matrix-v1.json state_vocabulary.terminal)
        # accept only idempotent reads and audit export: every region is
        # concluded. The why (supersede / cancel / authority / fatal failure)
        # lives in the state payload and lineage, not in the region values.
        "superseded": {
            "cognitive": {"value": "settled", **base},
            "workflow": {"value": "completed", **base},
            "authority": {"value": "completed", **base},
            "epistemic": {"value": "settled", **base},
            "delivery": {"value": "completed", **base},
        },
        "authority_blocked": {
            "cognitive": {"value": "settled", **base},
            "workflow": {"value": "completed", **base},
            "authority": {"value": "completed", **base},
            "epistemic": {"value": "settled", **base},
            "delivery": {"value": "completed", **base},
        },
        "failed": {
            "cognitive": {"value": "settled", **base},
            "workflow": {"value": "completed", **base},
            "authority": {"value": "completed", **base},
            "epistemic": {"value": "settled", **base},
            "delivery": {"value": "completed", **base},
        },
    }
    try:
        return mapping[state]
    except KeyError as error:
        raise IllegalTransitionError("illegal_transition") from error
