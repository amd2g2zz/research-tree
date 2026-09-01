"""Immutable, host-neutral strategy projection for the handoff boundary."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping, Sequence

from .domain import ArtifactRef, ArtifactRevision, DataIntegrityError, canonical_json_bytes, thaw_json

STRATEGY_PROJECTION_KIND = "strategy-projection"
STRATEGY_PROJECTION_SCHEMA_VERSION = 1
_STATUSES = frozenset({"draft", "displayed", "confirmed", "superseded"})
# Issue #471: marker artifact kind that explicitly invalidates a confirmed
# projection's authorization once a post-confirm revision supersedes it. The
# marker is append-only evidence: the superseded projection artifact itself is
# immutable, and re-display of a successor requires the full independent gate.
STRATEGY_PROJECTION_INVALIDATION_KIND = "strategy-projection-invalidation"
STRATEGY_PROJECTION_INVALIDATION_SCHEMA_VERSION = 1
# Coordinator's lifecycle-event artifacts (coordinator.LIFECYCLE_EVENT_KIND) carry the
# authoritative confirmation record; importing it here would create a cycle.
_LIFECYCLE_EVENT_KIND = "lifecycle-event"
_HANDOFF_CONFIRMED_EVENT = "handoff_confirmed"
_STAGE_BY_STATE = {
    "alignment": 1,
    "handoff_pending": 2,
    "autonomous_research": 3,
    "synthesis": 3,
    "readiness": 3,
    "delivery_pending": 3,
    "delivery_ready": 4,
    "awaiting_acceptance": 4,
    "completed": 4,
}


class StrategyProjectionError(DataIntegrityError):
    """Raised when a projection is incomplete, stale, or malformed."""


def macro_stage(state: str, *, prior_stage: int | None = None) -> int:
    """Map canonical lifecycle states to requester-visible macro stages."""

    if state in _STAGE_BY_STATE:
        return _STAGE_BY_STATE[state]
    if state in {"paused", "blocked"}:
        if prior_stage not in {1, 2, 3, 4}:
            raise StrategyProjectionError("prior_stage is required for paused or blocked state")
        return prior_stage
    if state in {"superseded", "authority_blocked", "failed"} and prior_stage in {1, 2, 3, 4}:
        return prior_stage
    raise StrategyProjectionError(f"unknown lifecycle state: {state}")


def _json_value(value: Any, label: str) -> Any:
    if isinstance(value, ArtifactRef):
        return value.to_dict()
    if isinstance(value, Mapping):
        return {str(key): _json_value(child, f"{label}.{key}") for key, child in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_value(child, label) for child in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise StrategyProjectionError(f"{label} must be JSON-compatible")


@dataclass(frozen=True, slots=True)
class StrategyProjection:
    projection_id: str
    run_id: str
    decision_frame_ref: ArtifactRef
    alignment_handoff_ref: ArtifactRef
    target_ref: ArtifactRef
    current_understanding: str
    assumptions: tuple[Any, ...]
    decision_targets: tuple[Any, ...]
    tracks: tuple[Any, ...]
    method_hypotheses: tuple[Any, ...]
    depth: str
    evidence_expectations: tuple[Any, ...]
    autonomy_envelope: Mapping[str, Any]
    replanning_policy: Mapping[str, Any]
    success_oracles: tuple[Any, ...]
    delivery_contract: Mapping[str, Any]
    stop_rule: str
    preference_influences: tuple[Any, ...]
    revision: int
    status: str
    display_digest: str
    content_hash: str

    @classmethod
    def create(cls, **values: Any) -> "StrategyProjection":
        values = dict(values)
        required = {
            "projection_id",
            "run_id",
            "decision_frame_ref",
            "alignment_handoff_ref",
            "target_ref",
            "current_understanding",
            "assumptions",
            "decision_targets",
            "tracks",
            "method_hypotheses",
            "depth",
            "evidence_expectations",
            "autonomy_envelope",
            "replanning_policy",
            "success_oracles",
            "delivery_contract",
            "stop_rule",
            "preference_influences",
            "revision",
            "status",
        }
        missing = sorted(required - set(values))
        if missing:
            raise StrategyProjectionError("missing fields: " + ", ".join(missing))
        refs = (values["decision_frame_ref"], values["alignment_handoff_ref"], values["target_ref"])
        if not all(isinstance(ref, ArtifactRef) for ref in refs):
            raise StrategyProjectionError("parent refs must be ArtifactRef values")
        run_id = values["run_id"]
        if not isinstance(run_id, str) or not run_id:
            raise StrategyProjectionError("run_id must be non-empty")
        if any(ref.round_id != run_id for ref in refs):
            raise StrategyProjectionError("all parent refs must share run_id")
        if not isinstance(values["current_understanding"], str) or not values["current_understanding"].strip():
            raise StrategyProjectionError("current_understanding must be non-empty")
        if not isinstance(values["stop_rule"], str) or not values["stop_rule"].strip():
            raise StrategyProjectionError("stop_rule must be non-empty")
        revision = values["revision"]
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise StrategyProjectionError("revision must be positive")
        status = values["status"]
        if status not in _STATUSES:
            raise StrategyProjectionError("status must be draft, displayed, confirmed, or superseded")
        if values["depth"] not in {"bounded", "deep", "recursive"}:
            raise StrategyProjectionError("depth must be bounded, deep, or recursive")
        for key in (
            "assumptions",
            "decision_targets",
            "tracks",
            "method_hypotheses",
            "evidence_expectations",
            "success_oracles",
            "preference_influences",
        ):
            if not isinstance(values[key], Sequence) or isinstance(values[key], (str, bytes)):
                raise StrategyProjectionError(f"{key} must contain at least one item")
            if key != "preference_influences" and not values[key]:
                raise StrategyProjectionError(f"{key} must contain at least one item")
        for influence in values["preference_influences"]:
            if not isinstance(influence, Mapping) or set(influence) != {
                "profile_revision",
                "observation_id",
                "key",
                "selected_value",
                "precedence",
                "reversal_condition",
            }:
                raise StrategyProjectionError("preference influence fields do not match schema")
            if (
                isinstance(influence["profile_revision"], bool)
                or not isinstance(influence["profile_revision"], int)
                or influence["profile_revision"] < 1
            ):
                raise StrategyProjectionError("preference influence profile_revision must be positive")
            if influence["precedence"] not in {"profile", "current-explicit"}:
                raise StrategyProjectionError("preference influence precedence is invalid")
            for key in ("observation_id", "key", "selected_value", "reversal_condition"):
                if not isinstance(influence[key], str) or not influence[key].strip():
                    raise StrategyProjectionError(f"preference influence {key} must be non-empty")
        for key in ("autonomy_envelope", "replanning_policy", "delivery_contract"):
            if not isinstance(values[key], Mapping) or not values[key]:
                raise StrategyProjectionError(f"{key} must be a non-empty object")
        normalized: dict[str, Any] = {}
        for key in required:
            normalized[key] = _json_value(values[key], key)
        normalized["decision_frame_ref"] = refs[0]
        normalized["alignment_handoff_ref"] = refs[1]
        normalized["target_ref"] = refs[2]
        normalized["assumptions"] = tuple(normalized["assumptions"])
        normalized["decision_targets"] = tuple(normalized["decision_targets"])
        normalized["tracks"] = tuple(normalized["tracks"])
        normalized["method_hypotheses"] = tuple(normalized["method_hypotheses"])
        normalized["evidence_expectations"] = tuple(normalized["evidence_expectations"])
        normalized["success_oracles"] = tuple(normalized["success_oracles"])
        normalized["preference_influences"] = tuple(normalized["preference_influences"])
        display_payload = cls._display_payload_from(normalized)
        display_digest = sha256(canonical_json_bytes(display_payload)).hexdigest()
        content_hash = sha256(canonical_json_bytes({**display_payload, "display_digest": display_digest})).hexdigest()
        return cls(**normalized, display_digest=display_digest, content_hash=content_hash)

    @staticmethod
    def _display_payload_from(values: Mapping[str, Any]) -> dict[str, Any]:
        payload = {
            "schema_version": STRATEGY_PROJECTION_SCHEMA_VERSION,
            "kind": STRATEGY_PROJECTION_KIND,
            **{
                key: _json_value(values[key], key)
                for key in (
                    "projection_id",
                    "run_id",
                    "decision_frame_ref",
                    "alignment_handoff_ref",
                    "target_ref",
                    "current_understanding",
                    "assumptions",
                    "decision_targets",
                    "tracks",
                    "method_hypotheses",
                    "depth",
                    "evidence_expectations",
                    "autonomy_envelope",
                    "replanning_policy",
                    "success_oracles",
                    "delivery_contract",
                    "stop_rule",
                    "preference_influences",
                    "revision",
                    "status",
                )
            },
        }
        return payload

    @property
    def kind(self) -> str:
        return STRATEGY_PROJECTION_KIND

    @property
    def id(self) -> str:
        return self.projection_id

    @property
    def display_payload(self) -> dict[str, Any]:
        return self._display_payload_from(self._values())

    def _values(self) -> dict[str, Any]:
        return {
            key: _json_value(getattr(self, key), key)
            for key in self.__dataclass_fields__
            if key not in {"display_digest", "content_hash"}
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.display_payload,
            "display_payload": self.display_payload,
            "display_digest": self.display_digest,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "StrategyProjection":
        if not isinstance(value, Mapping):
            raise StrategyProjectionError("projection must be an object")
        value = thaw_json(value)
        expected_keys = {
            "schema_version",
            "kind",
            "projection_id",
            "run_id",
            "decision_frame_ref",
            "alignment_handoff_ref",
            "target_ref",
            "current_understanding",
            "assumptions",
            "decision_targets",
            "tracks",
            "method_hypotheses",
            "depth",
            "evidence_expectations",
            "autonomy_envelope",
            "replanning_policy",
            "success_oracles",
            "delivery_contract",
            "stop_rule",
            "preference_influences",
            "revision",
            "status",
            "display_payload",
            "display_digest",
            "content_hash",
        }
        if set(value) != expected_keys:
            raise StrategyProjectionError("projection fields do not match schema")
        if value.get("schema_version") != STRATEGY_PROJECTION_SCHEMA_VERSION:
            raise StrategyProjectionError("schema_version must be 1")
        expected_display_keys = expected_keys - {"display_payload", "display_digest", "content_hash"}
        display_payload = value.get("display_payload")
        if not isinstance(display_payload, Mapping) or set(display_payload) != expected_display_keys:
            raise StrategyProjectionError("display_payload mismatch")
        try:
            refs = {
                name: ArtifactRef.from_dict(value[name])
                for name in ("decision_frame_ref", "alignment_handoff_ref", "target_ref")
            }
            item = cls.create(
                **{
                    key: thaw_json(value[key])
                    for key in (
                        "projection_id",
                        "run_id",
                        "current_understanding",
                        "assumptions",
                        "decision_targets",
                        "tracks",
                        "method_hypotheses",
                        "depth",
                        "evidence_expectations",
                        "autonomy_envelope",
                        "replanning_policy",
                        "success_oracles",
                        "delivery_contract",
                        "stop_rule",
                        "preference_influences",
                        "revision",
                        "status",
                    )
                },
                **refs,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise StrategyProjectionError("invalid projection fields") from error
        if display_payload != item.display_payload:
            raise StrategyProjectionError("display_payload mismatch")
        if value.get("display_digest") != item.display_digest or value.get("content_hash") != item.content_hash:
            raise StrategyProjectionError("projection digest mismatch")
        return item


def latest_confirmed(artifacts: Sequence[ArtifactRevision]) -> ArtifactRevision | None:
    """Return the projection revision the run lifecycle has authoritatively confirmed.

    Confirmation is the run's ``handoff_confirmed`` ``lifecycle-event`` artifact that
    names the exact projection reference and displayed digest the human authorized,
    ordered by ``(created_at, revision)``. The answer is the fail-closed ``None`` when
    the tail of the confirmation record cannot be trusted:

    - A ``handoff_confirmed`` event that cannot be resolved to the projection revision
      it names (unparseable reference, unknown projection revision, digest mismatch) and
      that is not older than the last resolvable confirmation poisons the tail: the
      query returns ``None`` rather than silently re-arming the older confirmation.
    - A confirmed revision that has been superseded by a later revision of the same
      projection is no longer authoritative; the fail-closed answer is ``None`` until
      the newer revision is itself confirmed.

    Projections that are merely draft or displayed are never returned.
    """

    projections = {
        (artifact.id, artifact.revision): artifact
        for artifact in artifacts
        if artifact.kind == STRATEGY_PROJECTION_KIND
    }
    events = []
    for artifact in artifacts:
        if artifact.kind != _LIFECYCLE_EVENT_KIND or artifact.payload.get("event") != _HANDOFF_CONFIRMED_EVENT:
            continue
        events.append(((artifact.created_at, artifact.revision), _resolved_confirmation(artifact, projections)))
    resolvable = [(key, projection) for key, projection in events if projection is not None]
    if not resolvable:
        return None
    last_key, last_projection = max(resolvable, key=lambda item: item[0])
    if any(key >= last_key for key, projection in events if projection is None):
        return None
    if _latest_revision_by_id(projections).get(last_projection.id) != last_projection.revision:
        return None
    return last_projection


def _resolved_confirmation(
    artifact: ArtifactRevision, projections: Mapping[tuple[str, int], ArtifactRevision]
) -> ArtifactRevision | None:
    """Resolve a handoff_confirmed event to the projection revision it authorizes.

    Returns ``None`` for an event that cannot be resolved: an unparseable
    ``projection_ref``, a projection revision absent from the artifacts, or a
    displayed-digest mismatch.
    """

    payload = artifact.payload.get("payload")
    projection_value = payload.get("projection_ref") if isinstance(payload, Mapping) else None
    digest = payload.get("display_digest") if isinstance(payload, Mapping) else None
    try:
        reference = ArtifactRef.from_dict(projection_value)
    except (TypeError, ValueError, DataIntegrityError):
        return None
    projection = projections.get((reference.artifact_id, reference.revision))
    if projection is None or projection.payload.get("display_digest") != digest:
        return None
    return projection


def _latest_revision_by_id(projections: Mapping[tuple[str, int], ArtifactRevision]) -> dict[str, int]:
    latest: dict[str, int] = {}
    for artifact_id, revision in projections:
        current = latest.get(artifact_id)
        if current is None or revision > current:
            latest[artifact_id] = revision
    return latest


def validate_strategy_projection_invalidation(payload: Any) -> dict[str, Any]:
    """Validate one strategy-projection-invalidation marker payload (#471).

    Every violation raises ``StrategyProjectionError`` naming the field, so a
    malformed marker can never silently pass as invalidation evidence.
    """

    required = {
        "schema",
        "id",
        "run_id",
        "superseded_projection_ref",
        "superseded_display_digest",
        "superseded_authority_fingerprint",
        "reason",
    }
    if not isinstance(payload, Mapping):
        raise StrategyProjectionError("projection invalidation payload must be an object")
    if set(payload) != required:
        raise StrategyProjectionError("projection invalidation payload fields do not match schema")
    if payload["schema"] != STRATEGY_PROJECTION_INVALIDATION_SCHEMA_VERSION:
        raise StrategyProjectionError("projection invalidation schema must be 1")
    for field in ("id", "run_id", "superseded_display_digest", "superseded_authority_fingerprint", "reason"):
        value = payload[field]
        if not isinstance(value, str) or not value.strip():
            raise StrategyProjectionError(f"projection invalidation {field} must be a non-empty string")
    if len(payload["superseded_display_digest"]) != 64 or len(payload["superseded_authority_fingerprint"]) != 64:
        raise StrategyProjectionError("projection invalidation digests must be SHA-256 hex digests")
    try:
        superseded = ArtifactRef.from_dict(payload["superseded_projection_ref"])
    except (TypeError, ValueError, DataIntegrityError) as error:
        raise StrategyProjectionError(
            "projection invalidation superseded_projection_ref must be an artifact reference"
        ) from error
    return {"superseded_projection_ref": superseded}


def has_confirmation_history(artifacts: Sequence[ArtifactRevision], projection_id: str) -> bool:
    """Return whether any ``handoff_confirmed`` event ever named this projection id.

    Issue #471 (review A/B HIGH-1): post-confirm supersede semantics must key
    on the projection's own confirmation history, not on the
    ``latest_confirmed`` snapshot — the snapshot is permanently ``None`` once a
    later revision supersedes a confirmation, which let a second post-confirm
    ``revise_strategy`` fall back to the legacy displayed branch. Once a
    projection id has been confirmed, EVERY subsequent revision — including
    revisions after a later re-confirmation — is post-confirm and must be
    written as a draft behind an invalidation marker; a re-confirmed revision
    reached that state only by passing the full display gate itself.
    """

    for artifact in artifacts:
        if artifact.kind != _LIFECYCLE_EVENT_KIND or artifact.payload.get("event") != _HANDOFF_CONFIRMED_EVENT:
            continue
        payload = artifact.payload.get("payload")
        reference_value = payload.get("projection_ref") if isinstance(payload, Mapping) else None
        try:
            reference = ArtifactRef.from_dict(reference_value)
        except (TypeError, ValueError, DataIntegrityError):
            continue
        if reference.artifact_id == projection_id:
            return True
    return False


AUTHORITY_FIELD_LABELS = (
    "outcome",
    "scope",
    "authority",
    "success_oracles",
    "delivery_contract",
)


def authority_fingerprint(projection: StrategyProjection) -> str:
    """Fingerprint the authority-bearing fields of a projection.

    Issue #292 gate 1: handoff confirmation was digest-bound but compilation
    never re-materialized each authority-bearing field, so a stale
    reconnaissance-only scope/authority could survive a user's broader
    authorization. The fingerprint covers the primary decision outcome, the
    autonomy scope, the authority boundary, the success oracles, and the
    delivery contract, each labeled and hashed independently so any single
    field drift changes the value.
    """

    scope = projection.autonomy_envelope.get("allowed") if isinstance(projection.autonomy_envelope, Mapping) else None
    authority = (
        projection.autonomy_envelope.get("authority") if isinstance(projection.autonomy_envelope, Mapping) else None
    )
    material = {
        "outcome": sha256(canonical_json_bytes(projection.current_understanding)).hexdigest(),
        "scope": sha256(canonical_json_bytes(scope)).hexdigest(),
        "authority": sha256(canonical_json_bytes(authority)).hexdigest(),
        "success_oracles": sha256(canonical_json_bytes(projection.success_oracles)).hexdigest(),
        "delivery_contract": sha256(canonical_json_bytes(projection.delivery_contract)).hexdigest(),
        "decision_targets": sha256(canonical_json_bytes(tuple(projection.decision_targets))).hexdigest(),
    }
    return sha256(canonical_json_bytes(material)).hexdigest()


def validate_falsifiability(projection: StrategyProjection) -> None:
    """Reject projections whose success oracles are not evidence-bound.

    Every success oracle must reference at least one evidence standard, and every
    decision target oracle reference must resolve inside ``success_oracles``. String
    oracles carry no evidence standards, so a projection prepared for this review
    uses ``{"id", "evidence_standard_ids"}`` oracle entries and ``{"id", "oracle_ids"}``
    decision-target entries.
    """

    oracle_ids: set[str] = set()
    for index, oracle in enumerate(projection.success_oracles):
        if not isinstance(oracle, Mapping):
            raise StrategyProjectionError(
                f"success_oracles[{index}] must be a mapping with id and evidence_standard_ids"
            )
        oracle_id = oracle.get("id")
        if not isinstance(oracle_id, str) or not oracle_id.strip():
            raise StrategyProjectionError(f"success_oracles[{index}] must carry an id")
        standards = oracle.get("evidence_standard_ids")
        if (
            not isinstance(standards, Sequence)
            or isinstance(standards, (str, bytes))
            or not standards
            or not all(isinstance(value, str) and value.strip() for value in standards)
        ):
            raise StrategyProjectionError(
                f"success_oracles[{index}] requires non-empty evidence_standard_ids: {oracle_id}"
            )
        oracle_ids.add(oracle_id)
    for index, target in enumerate(projection.decision_targets):
        if not isinstance(target, Mapping):
            continue
        target_id = target.get("id")
        if not isinstance(target_id, str) or not target_id.strip():
            raise StrategyProjectionError(f"decision_targets[{index}] must carry an id")
        references = target.get("oracle_ids")
        if references is None:
            continue
        if not isinstance(references, Sequence) or isinstance(references, (str, bytes)):
            raise StrategyProjectionError(f"decision_targets[{index}] oracle_ids must be a sequence")
        for reference in references:
            if reference not in oracle_ids:
                raise StrategyProjectionError(
                    f"decision_targets[{index}] oracle_ids entry not in success_oracles: {reference}"
                )
