"""Run optional, strategy-selected assurance checks for one technical decision."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping, Sequence

from .decision_map import BLUEPRINT_TARGET_KIND
from .domain import (
    ArtifactRef,
    ArtifactRevision,
    InvalidIdentifierError,
    RuntimeStoreError,
    thaw_json,
    validate_identifier,
)
from .feedback import RESEARCH_STRATEGY_KIND, validate_research_strategy_payload
from .ledger import DECISION_LEDGER_KIND, FINDING_PACK_KIND, DecisionLedgerCompiler
from .ports import (
    EvidenceReviewPort,
    PrimarySourceValidationPort,
    ProvenanceIntegrityPort,
    SourceAcquisitionPort,
)
from .storage import RunStore


ASSURANCE_ADAPTER_SELECTION_KIND = "assurance-adapter-selection"
ASSURANCE_EVIDENCE_KIND = "assurance-evidence"
ASSURANCE_FOLLOW_UP_KIND = "assurance-follow-up"
ASSURANCE_RESOLUTION_KIND = "assurance-resolution"

ADAPTER_KINDS = (
    "source_acquisition",
    "primary_source_validation",
    "evidence_review",
    "provenance_integrity",
)
EVIDENCE_STANDARDS = {"ordinary", "primary_source", "high_assurance"}
RISK_TIERS = {"low", "medium", "high"}
DECISION_VALUES = {"low", "medium", "high"}
FAILURE_MODES = {"follow_up", "block"}
RESULT_STATUSES = {"passed", "failed"}
REVIEW_STATUSES = {*RESULT_STATUSES, "not_requested"}

_ADAPTER_METHODS = {
    "source_acquisition": "acquire",
    "primary_source_validation": "validate_primary_source",
    "evidence_review": "review",
    "provenance_integrity": "verify_integrity",
}


class AssuranceError(RuntimeStoreError):
    """Base error for strategy-selected assurance behavior."""


class InvalidAssuranceError(AssuranceError):
    """Raised before assurance data can escape a bounded decision context."""


@dataclass(frozen=True, slots=True)
class AssuranceAdapterSet:
    """Optional concrete adapters for the four independently selected checks."""

    source_acquisition: SourceAcquisitionPort | None = None
    primary_source_validation: PrimarySourceValidationPort | None = None
    evidence_review: EvidenceReviewPort | None = None
    provenance_integrity: ProvenanceIntegrityPort | None = None


@dataclass(frozen=True, slots=True)
class AssuranceRunArtifacts:
    """Immutable output of one assurance run and its decision-local outcome."""

    evidence: ArtifactRevision
    resolution: ArtifactRevision
    follow_up: ArtifactRevision | None = None
    blocked_decision: ArtifactRevision | None = None


class AssuranceStrategySelector:
    """Persist a decision-local adapter selection derived from one strategy."""

    def __init__(self, store: RunStore) -> None:
        self._store = store

    def select(
        self,
        *,
        round_id: str,
        selection_id: str,
        strategy: ArtifactRevision,
        blueprint_target: ArtifactRevision,
        policies: Sequence[Mapping[str, Any]],
    ) -> ArtifactRevision:
        """Select zero or more assurance profiles without changing the strategy artifact."""

        try:
            snapshot = self._store.load_round(round_id)
            validate_identifier(selection_id, "selection_id")
            _ensure_new_id(snapshot.artifacts, selection_id, "selection_id")
            stored_strategy = _resolve_exact(
                snapshot.artifacts,
                strategy,
                RESEARCH_STRATEGY_KIND,
                "strategy",
            )
            stored_target = _resolve_exact(
                snapshot.artifacts,
                blueprint_target,
                BLUEPRINT_TARGET_KIND,
                "blueprint_target",
            )
            _ensure_same_round(round_id, stored_strategy, "strategy")
            _ensure_same_round(round_id, stored_target, "blueprint_target")
            _validate_strategy_target_lineage(stored_strategy, stored_target)
            normalized_policies = _normalize_policies(policies, stored_target)
            payload = {
                "id": selection_id,
                "round_id": round_id,
                "strategy_ref": _ref_dict(stored_strategy),
                "blueprint_target_ref": _ref_dict(stored_target),
                "decisions": normalized_policies,
            }
            validate_assurance_selection_payload(payload)
        except (InvalidIdentifierError, TypeError, ValueError) as error:
            raise InvalidAssuranceError(str(error)) from error

        return self._store.append_artifact(
            round_id,
            selection_id,
            ASSURANCE_ADAPTER_SELECTION_KIND,
            payload,
            parent_refs=(
                ArtifactRef(stored_strategy.round_id, stored_strategy.id, stored_strategy.revision),
                ArtifactRef(stored_target.round_id, stored_target.id, stored_target.revision),
            ),
        )


class AssuranceAdapterRunner:
    """Invoke only the adapters selected for one persisted Decision Ledger revision."""

    def __init__(self, store: RunStore) -> None:
        self._store = store

    def run(
        self,
        *,
        round_id: str,
        evidence_id: str,
        selection: ArtifactRevision,
        decision: ArtifactRevision,
        source: Mapping[str, Any],
        adapters: AssuranceAdapterSet,
    ) -> AssuranceRunArtifacts:
        """Persist bounded provenance and resolve a failed review locally to its decision."""

        try:
            snapshot = self._store.load_round(round_id)
            validate_identifier(evidence_id, "evidence_id")
            _ensure_new_id(snapshot.artifacts, evidence_id, "evidence_id")
            stored_selection = _resolve_exact(
                snapshot.artifacts,
                selection,
                ASSURANCE_ADAPTER_SELECTION_KIND,
                "selection",
            )
            stored_decision = _resolve_exact(
                snapshot.artifacts,
                decision,
                DECISION_LEDGER_KIND,
                "decision",
            )
            _ensure_same_round(round_id, stored_selection, "selection")
            _ensure_same_round(round_id, stored_decision, "decision")
            strategy, target = _selection_sources(snapshot.artifacts, stored_selection)
            _validate_decision_for_target(stored_decision, target)
            _ensure_latest_decision(snapshot.artifacts, stored_decision)
            selected_policy = _policy_for_decision(stored_selection, stored_decision)
            source_record = _normalize_source(source)
            if not isinstance(adapters, AssuranceAdapterSet):
                raise InvalidAssuranceError("adapters must be an AssuranceAdapterSet")
            selected_kinds = (
                () if selected_policy is None else tuple(selected_policy["adapters"])
            )
            adapter_values = _selected_adapters(adapters, selected_kinds)
            resolution_id = _derived_id(evidence_id, "resolution")
            _ensure_new_id(snapshot.artifacts, resolution_id, "resolution_id")
            follow_up_id = (
                None
                if selected_policy is None or selected_policy["failure_mode"] != "follow_up"
                else _derived_id(evidence_id, "follow-up")
            )
            if follow_up_id is not None:
                _ensure_new_id(snapshot.artifacts, follow_up_id, "follow_up_id")
        except (InvalidIdentifierError, TypeError, ValueError) as error:
            raise InvalidAssuranceError(str(error)) from error

        results: list[dict[str, str]] = []
        source_state = dict(source_record)
        decision_view = {
            "id": stored_decision.id,
            "revision": stored_decision.revision,
            "decision_slot_id": stored_decision.payload["decision_slot_id"],
            "status": stored_decision.payload["status"],
        }
        selection_view = {
            "id": stored_selection.id,
            "revision": stored_selection.revision,
            "strategy_id": strategy.id,
            "blueprint_target_id": target.id,
        }
        for adapter_kind, adapter in adapter_values:
            request = {
                "round_id": round_id,
                "selection": selection_view,
                "decision": decision_view,
                "source": dict(source_state),
                "policy": None if selected_policy is None else dict(selected_policy),
            }
            result, updates = _invoke_adapter(adapter_kind, adapter, request)
            source_state.update(updates)
            results.append(
                {
                    "adapter_kind": adapter_kind,
                    "status": result["status"],
                    "summary": result["summary"],
                }
            )

        review_result = _adapter_summary(results, "evidence_review")
        integrity_result = _adapter_summary(results, "provenance_integrity")
        evidence_status = "failed" if any(item["status"] == "failed" for item in results) else "passed"
        evidence_payload = {
            "id": evidence_id,
            "round_id": round_id,
            "selection_ref": _ref_dict(stored_selection),
            "strategy_ref": _ref_dict(strategy),
            "blueprint_target_ref": _ref_dict(target),
            "decision_ref": _ref_dict(stored_decision),
            "decision_slot_id": stored_decision.payload["decision_slot_id"],
            "source": source_state,
            "adapter_results": results,
            "review_result": review_result,
            "integrity_result": integrity_result,
            "status": evidence_status,
        }
        validate_assurance_evidence_payload(evidence_payload)
        evidence = self._store.append_artifact(
            round_id,
            evidence_id,
            ASSURANCE_EVIDENCE_KIND,
            evidence_payload,
            parent_refs=(
                ArtifactRef(
                    stored_selection.round_id,
                    stored_selection.id,
                    stored_selection.revision,
                ),
                ArtifactRef(strategy.round_id, strategy.id, strategy.revision),
                ArtifactRef(target.round_id, target.id, target.revision),
                ArtifactRef(stored_decision.round_id, stored_decision.id, stored_decision.revision),
            ),
        )

        follow_up: ArtifactRevision | None = None
        blocked_decision: ArtifactRevision | None = None
        outcome = "passed"
        if evidence_status == "failed":
            if selected_policy is None:
                raise InvalidAssuranceError("an unselected decision cannot produce a failed assurance result")
            if selected_policy["failure_mode"] == "follow_up":
                if follow_up_id is None:
                    raise InvalidAssuranceError("follow-up id was not prepared")
                follow_up = self._append_follow_up(
                    round_id=round_id,
                    follow_up_id=follow_up_id,
                    evidence=evidence,
                    decision=stored_decision,
                    selection=stored_selection,
                    failed_results=results,
                )
                outcome = "follow_up"
            else:
                blocked_decision = _append_blocked_decision(
                    self._store,
                    snapshot.artifacts,
                    stored_decision,
                    target,
                    evidence,
                )
                outcome = "blocked"

        resolution_decision = stored_decision if blocked_decision is None else blocked_decision
        resolution_payload = {
            "id": resolution_id,
            "round_id": round_id,
            "status": outcome,
            "assurance_evidence_ref": _ref_dict(evidence),
            "decision_ref": _ref_dict(resolution_decision),
            "follow_up_ref": None if follow_up is None else _ref_dict(follow_up),
        }
        validate_assurance_resolution_payload(resolution_payload)
        resolution_refs = [
            ArtifactRef(evidence.round_id, evidence.id, evidence.revision),
            ArtifactRef(
                resolution_decision.round_id,
                resolution_decision.id,
                resolution_decision.revision,
            ),
        ]
        if follow_up is not None:
            resolution_refs.append(ArtifactRef(follow_up.round_id, follow_up.id, follow_up.revision))
        resolution = self._store.append_artifact(
            round_id,
            resolution_id,
            ASSURANCE_RESOLUTION_KIND,
            resolution_payload,
            parent_refs=tuple(resolution_refs),
        )
        return AssuranceRunArtifacts(
            evidence=evidence,
            resolution=resolution,
            follow_up=follow_up,
            blocked_decision=blocked_decision,
        )

    def _append_follow_up(
        self,
        *,
        round_id: str,
        follow_up_id: str,
        evidence: ArtifactRevision,
        decision: ArtifactRevision,
        selection: ArtifactRevision,
        failed_results: Sequence[Mapping[str, str]],
    ) -> ArtifactRevision:
        failed_kinds = [item["adapter_kind"] for item in failed_results if item["status"] == "failed"]
        payload = {
            "id": follow_up_id,
            "round_id": round_id,
            "assurance_evidence_ref": _ref_dict(evidence),
            "decision_ref": _ref_dict(decision),
            "decision_slot_id": decision.payload["decision_slot_id"],
            "kind": "evaluation",
            "scope": (
                "Resolve failed " + ", ".join(failed_kinds) + " assurance evidence for this Decision Slot."
            ),
            "reason": "A strategy-selected assurance check failed without changing the requester target.",
        }
        validate_assurance_follow_up_payload(payload)
        return self._store.append_artifact(
            round_id,
            follow_up_id,
            ASSURANCE_FOLLOW_UP_KIND,
            payload,
            parent_refs=(
                ArtifactRef(evidence.round_id, evidence.id, evidence.revision),
                ArtifactRef(decision.round_id, decision.id, decision.revision),
                ArtifactRef(selection.round_id, selection.id, selection.revision),
            ),
        )


def validate_assurance_selection_payload(payload: Mapping[str, Any]) -> None:
    """Validate the persisted strategy-to-decision adapter selection contract."""

    data = _mapping(payload, "assurance selection payload")
    _require_exact_keys(
        data,
        {"id", "round_id", "strategy_ref", "blueprint_target_ref", "decisions"},
        "assurance selection payload",
    )
    _identifier(data["id"], "assurance selection id")
    _identifier(data["round_id"], "assurance selection round_id")
    _validate_ref(data["strategy_ref"], "assurance selection strategy_ref")
    _validate_ref(data["blueprint_target_ref"], "assurance selection blueprint_target_ref")
    decisions = _mappings(data["decisions"], "assurance selection decisions")
    seen_slots: set[str] = set()
    for index, decision in enumerate(decisions):
        label = f"assurance selection decisions[{index}]"
        _require_exact_keys(
            decision,
            {
                "decision_slot_id",
                "risk_tier",
                "evidence_standard",
                "decision_value",
                "adapters",
                "failure_mode",
                "selection_reason",
            },
            label,
        )
        slot_id = _identifier(decision["decision_slot_id"], f"{label}.decision_slot_id")
        if slot_id in seen_slots:
            raise InvalidAssuranceError(f"{label}.decision_slot_id is duplicated")
        seen_slots.add(slot_id)
        risk_tier = _enum(decision["risk_tier"], f"{label}.risk_tier", RISK_TIERS)
        standard = _enum(
            decision["evidence_standard"],
            f"{label}.evidence_standard",
            EVIDENCE_STANDARDS,
        )
        decision_value = _enum(
            decision["decision_value"],
            f"{label}.decision_value",
            DECISION_VALUES,
        )
        adapters = _enum_sequence(decision["adapters"], f"{label}.adapters", set(ADAPTER_KINDS))
        if adapters != _adapters_for_policy(standard, risk_tier, decision_value):
            raise InvalidAssuranceError(
                f"{label}.adapters does not match the selected evidence_standard"
            )
        _enum(decision["failure_mode"], f"{label}.failure_mode", FAILURE_MODES)
        _nonempty(decision["selection_reason"], f"{label}.selection_reason")


def validate_assurance_evidence_payload(payload: Mapping[str, Any]) -> None:
    """Validate standalone provenance without treating it as a mutable Finding Pack."""

    data = _mapping(payload, "assurance evidence payload")
    _require_exact_keys(
        data,
        {
            "id",
            "round_id",
            "selection_ref",
            "strategy_ref",
            "blueprint_target_ref",
            "decision_ref",
            "decision_slot_id",
            "source",
            "adapter_results",
            "review_result",
            "integrity_result",
            "status",
        },
        "assurance evidence payload",
    )
    _identifier(data["id"], "assurance evidence id")
    _identifier(data["round_id"], "assurance evidence round_id")
    for field in ("selection_ref", "strategy_ref", "blueprint_target_ref", "decision_ref"):
        _validate_ref(data[field], f"assurance evidence {field}")
    _identifier(data["decision_slot_id"], "assurance evidence decision_slot_id")
    source = _mapping(data["source"], "assurance evidence source")
    _require_exact_keys(
        source,
        {"locator", "version", "extraction_boundary", "applicability"},
        "assurance evidence source",
    )
    for field in ("locator", "version", "extraction_boundary", "applicability"):
        _nonempty(source[field], f"assurance evidence source.{field}")
    results = _mappings(data["adapter_results"], "assurance evidence adapter_results")
    seen_kinds: set[str] = set()
    by_kind: dict[str, Mapping[str, Any]] = {}
    for index, result in enumerate(results):
        label = f"assurance evidence adapter_results[{index}]"
        _require_exact_keys(result, {"adapter_kind", "status", "summary"}, label)
        kind = _enum(result["adapter_kind"], f"{label}.adapter_kind", set(ADAPTER_KINDS))
        if kind in seen_kinds:
            raise InvalidAssuranceError(f"{label}.adapter_kind is duplicated")
        seen_kinds.add(kind)
        _enum(result["status"], f"{label}.status", RESULT_STATUSES)
        _nonempty(result["summary"], f"{label}.summary")
        by_kind[kind] = result
    for field, kind in (
        ("review_result", "evidence_review"),
        ("integrity_result", "provenance_integrity"),
    ):
        summary = _mapping(data[field], f"assurance evidence {field}")
        _require_exact_keys(summary, {"status", "summary"}, f"assurance evidence {field}")
        status = _enum(summary["status"], f"assurance evidence {field}.status", REVIEW_STATUSES)
        _nonempty(summary["summary"], f"assurance evidence {field}.summary")
        expected = by_kind.get(kind)
        if expected is None:
            if status != "not_requested":
                raise InvalidAssuranceError(
                    f"assurance evidence {field} must be not_requested without {kind}"
                )
        elif summary != {"status": expected["status"], "summary": expected["summary"]}:
            raise InvalidAssuranceError(
                f"assurance evidence {field} must match its selected adapter result"
            )
    status = _enum(data["status"], "assurance evidence status", RESULT_STATUSES)
    has_failure = any(result["status"] == "failed" for result in results)
    if (status == "failed") != has_failure:
        raise InvalidAssuranceError("assurance evidence status must match its adapter results")


def validate_assurance_follow_up_payload(payload: Mapping[str, Any]) -> None:
    """Validate one bounded assurance remediation recommendation."""

    data = _mapping(payload, "assurance follow-up payload")
    _require_exact_keys(
        data,
        {
            "id",
            "round_id",
            "assurance_evidence_ref",
            "decision_ref",
            "decision_slot_id",
            "kind",
            "scope",
            "reason",
        },
        "assurance follow-up payload",
    )
    _identifier(data["id"], "assurance follow-up id")
    _identifier(data["round_id"], "assurance follow-up round_id")
    _validate_ref(data["assurance_evidence_ref"], "assurance follow-up assurance_evidence_ref")
    _validate_ref(data["decision_ref"], "assurance follow-up decision_ref")
    _identifier(data["decision_slot_id"], "assurance follow-up decision_slot_id")
    if data["kind"] != "evaluation":
        raise InvalidAssuranceError("assurance follow-up kind must be evaluation")
    _nonempty(data["scope"], "assurance follow-up scope")
    _nonempty(data["reason"], "assurance follow-up reason")


def validate_assurance_resolution_payload(payload: Mapping[str, Any]) -> None:
    """Validate the link from a failed check to its local remediation or block."""

    data = _mapping(payload, "assurance resolution payload")
    _require_exact_keys(
        data,
        {
            "id",
            "round_id",
            "status",
            "assurance_evidence_ref",
            "decision_ref",
            "follow_up_ref",
        },
        "assurance resolution payload",
    )
    _identifier(data["id"], "assurance resolution id")
    _identifier(data["round_id"], "assurance resolution round_id")
    status = _enum(data["status"], "assurance resolution status", {"passed", "follow_up", "blocked"})
    _validate_ref(data["assurance_evidence_ref"], "assurance resolution assurance_evidence_ref")
    _validate_ref(data["decision_ref"], "assurance resolution decision_ref")
    follow_up = data["follow_up_ref"]
    if status == "follow_up":
        if follow_up is None:
            raise InvalidAssuranceError("follow-up resolution requires follow_up_ref")
        _validate_ref(follow_up, "assurance resolution follow_up_ref")
    elif follow_up is not None:
        raise InvalidAssuranceError("only a follow_up resolution may include follow_up_ref")


def _normalize_policies(
    value: Any,
    target: ArtifactRevision,
) -> list[dict[str, Any]]:
    policies = _mappings(value, "policies")
    slots = _target_slots(target)
    normalized: list[dict[str, Any]] = []
    seen_slots: set[str] = set()
    for index, policy in enumerate(policies):
        label = f"policies[{index}]"
        _require_exact_keys(
            policy,
            {
                "decision_slot_id",
                "risk_tier",
                "evidence_standard",
                "decision_value",
                "failure_mode",
                "selection_reason",
            },
            label,
        )
        slot_id = _identifier(policy["decision_slot_id"], f"{label}.decision_slot_id")
        if slot_id not in slots:
            raise InvalidAssuranceError(f"{label}.decision_slot_id is absent from the Blueprint Target")
        if slot_id in seen_slots:
            raise InvalidAssuranceError(f"{label}.decision_slot_id is duplicated")
        seen_slots.add(slot_id)
        standard = _enum(
            policy["evidence_standard"],
            f"{label}.evidence_standard",
            EVIDENCE_STANDARDS,
        )
        risk_tier = _enum(policy["risk_tier"], f"{label}.risk_tier", RISK_TIERS)
        decision_value = _enum(
            policy["decision_value"],
            f"{label}.decision_value",
            DECISION_VALUES,
        )
        normalized.append(
            {
                "decision_slot_id": slot_id,
                "risk_tier": risk_tier,
                "evidence_standard": standard,
                "decision_value": decision_value,
                "adapters": list(_adapters_for_policy(standard, risk_tier, decision_value)),
                "failure_mode": _enum(
                    policy["failure_mode"],
                    f"{label}.failure_mode",
                    FAILURE_MODES,
                ),
                "selection_reason": _nonempty(
                    policy["selection_reason"],
                    f"{label}.selection_reason",
                ),
            }
        )
    return sorted(normalized, key=lambda policy: policy["decision_slot_id"])


def _adapters_for_policy(
    evidence_standard: str,
    risk_tier: str,
    decision_value: str,
) -> tuple[str, ...]:
    """Apply the strategy's explicit evidence standard proportionately to value and risk."""

    if evidence_standard == "ordinary":
        return ()
    if evidence_standard == "primary_source":
        adapters = ("source_acquisition", "primary_source_validation")
        if risk_tier == "high" or decision_value == "high":
            return (*adapters, "evidence_review")
        return adapters
    return ADAPTER_KINDS


def _selection_sources(
    artifacts: Sequence[ArtifactRevision],
    selection: ArtifactRevision,
) -> tuple[ArtifactRevision, ArtifactRevision]:
    try:
        validate_assurance_selection_payload(selection.payload)
    except RuntimeStoreError as error:
        raise InvalidAssuranceError(str(error)) from error
    strategy_ref = _artifact_ref(selection.payload["strategy_ref"], "selection strategy_ref")
    target_ref = _artifact_ref(selection.payload["blueprint_target_ref"], "selection blueprint_target_ref")
    if strategy_ref not in selection.parent_refs or target_ref not in selection.parent_refs:
        raise InvalidAssuranceError("assurance selection lacks exact strategy or Blueprint Target parents")
    strategy = _resolve_ref(artifacts, strategy_ref, RESEARCH_STRATEGY_KIND, "selection strategy")
    target = _resolve_ref(artifacts, target_ref, BLUEPRINT_TARGET_KIND, "selection Blueprint Target")
    _validate_strategy_target_lineage(strategy, target)
    return strategy, target


def _validate_strategy_target_lineage(
    strategy: ArtifactRevision,
    target: ArtifactRevision,
) -> None:
    try:
        validate_research_strategy_payload(strategy.payload)
    except RuntimeStoreError as error:
        raise InvalidAssuranceError(f"invalid persisted Research Strategy: {error}") from error
    brief_id = strategy.payload.get("working_brief_id")
    model_id = strategy.payload.get("intent_model_id")
    if brief_id != target.payload.get("brief_id") or model_id != target.payload.get("intent_model_id"):
        raise InvalidAssuranceError(
            "Research Strategy and Blueprint Target must share the exact Working Brief and Intent Model"
        )
    strategy_refs = set(strategy.parent_refs)
    target_refs = set(target.parent_refs)
    shared_brief = [
        ref
        for ref in strategy_refs & target_refs
        if ref.artifact_id == brief_id and ref.round_id == strategy.round_id
    ]
    shared_model = [
        ref
        for ref in strategy_refs & target_refs
        if ref.artifact_id == model_id and ref.round_id == strategy.round_id
    ]
    if len(shared_brief) != 1 or len(shared_model) != 1:
        raise InvalidAssuranceError(
            "Research Strategy and Blueprint Target must retain exact Brief and Intent Model parent refs"
        )


def _validate_decision_for_target(
    decision: ArtifactRevision,
    target: ArtifactRevision,
) -> None:
    if decision.payload.get("blueprint_target_id") != target.id:
        raise InvalidAssuranceError("decision does not belong to the selected Blueprint Target")
    target_ref = ArtifactRef(target.round_id, target.id, target.revision)
    if target_ref not in decision.parent_refs:
        raise InvalidAssuranceError("decision lacks the exact selected Blueprint Target parent ref")
    slot_id = _identifier(decision.payload.get("decision_slot_id"), "decision decision_slot_id")
    if slot_id not in _target_slots(target):
        raise InvalidAssuranceError("decision slot is absent from the selected Blueprint Target")
    if decision.payload.get("status") not in {"selected", "conditional"}:
        raise InvalidAssuranceError("assurance can only review a selected or conditional decision")


def _ensure_latest_decision(
    artifacts: Sequence[ArtifactRevision], decision: ArtifactRevision
) -> None:
    latest = max(
        (
            item
            for item in artifacts
            if item.id == decision.id and item.kind == DECISION_LEDGER_KIND
        ),
        key=lambda item: item.revision,
    )
    if latest != decision:
        raise InvalidAssuranceError("decision must be its latest persisted revision")


def _policy_for_decision(
    selection: ArtifactRevision,
    decision: ArtifactRevision,
) -> Mapping[str, Any] | None:
    slot_id = decision.payload["decision_slot_id"]
    policies = _mappings(selection.payload["decisions"], "assurance selection decisions")
    if not policies:
        return None
    policy = next((item for item in policies if item.get("decision_slot_id") == slot_id), None)
    if policy is None:
        raise InvalidAssuranceError("Decision Slot has no strategy-selected assurance policy")
    return policy


def _selected_adapters(
    adapters: AssuranceAdapterSet,
    selected_kinds: Sequence[str],
) -> tuple[tuple[str, Any], ...]:
    values = {
        "source_acquisition": adapters.source_acquisition,
        "primary_source_validation": adapters.primary_source_validation,
        "evidence_review": adapters.evidence_review,
        "provenance_integrity": adapters.provenance_integrity,
    }
    selected: list[tuple[str, Any]] = []
    for kind in selected_kinds:
        adapter = values[kind]
        method = _ADAPTER_METHODS[kind]
        if adapter is None or not callable(getattr(adapter, method, None)):
            raise InvalidAssuranceError(f"selected adapter {kind} is unavailable")
        selected.append((kind, adapter))
    return tuple(selected)


def _invoke_adapter(
    kind: str,
    adapter: Any,
    request: Mapping[str, Any],
) -> tuple[dict[str, str], dict[str, str]]:
    method = getattr(adapter, _ADAPTER_METHODS[kind])
    try:
        raw_result = method(request)
    except Exception as error:
        return (
            {
                "status": "failed",
                "summary": f"{kind} raised {error.__class__.__name__}.",
            },
            {},
        )
    return _normalize_adapter_result(raw_result, kind)


def _normalize_adapter_result(value: Any, label: str) -> tuple[dict[str, str], dict[str, str]]:
    result = _mapping(value, f"{label} adapter result")
    allowed = {"status", "summary", "source_version", "extraction_boundary", "applicability"}
    required = {"status", "summary"}
    missing = required - set(result)
    extra = set(result) - allowed
    if missing or extra:
        raise InvalidAssuranceError(
            f"{label} adapter result has unexpected keys; missing={sorted(missing)}, extra={sorted(extra)}"
        )
    normalized = {
        "status": _enum(result["status"], f"{label} adapter result.status", RESULT_STATUSES),
        "summary": _nonempty(result["summary"], f"{label} adapter result.summary"),
    }
    updates: dict[str, str] = {}
    for result_key, source_key in (
        ("source_version", "version"),
        ("extraction_boundary", "extraction_boundary"),
        ("applicability", "applicability"),
    ):
        if result_key in result and result[result_key] is not None:
            updates[source_key] = _nonempty(result[result_key], f"{label} adapter result.{result_key}")
    return normalized, updates


def _adapter_summary(results: Sequence[Mapping[str, str]], kind: str) -> dict[str, str]:
    result = next((item for item in results if item["adapter_kind"] == kind), None)
    if result is None:
        return {
            "status": "not_requested",
            "summary": f"No {kind} adapter was selected.",
        }
    return {"status": result["status"], "summary": result["summary"]}


def _append_blocked_decision(
    store: RunStore,
    artifacts: Sequence[ArtifactRevision],
    decision: ArtifactRevision,
    target: ArtifactRevision,
    evidence: ArtifactRevision,
) -> ArtifactRevision:
    payload = thaw_json(decision.payload)
    if not isinstance(payload, dict):
        raise InvalidAssuranceError("stored decision payload is malformed")
    alternatives = payload.get("alternatives")
    if not isinstance(alternatives, list):
        raise InvalidAssuranceError("stored decision alternatives are malformed")
    selected_option = payload.get("selected_option")
    if isinstance(selected_option, str) and selected_option not in {
        item.get("option") for item in alternatives if isinstance(item, Mapping)
    }:
        alternatives.append(
            {
                "option": selected_option,
                "disposition": "unresolved",
                "reason": "A strategy-selected high-assurance check failed.",
            }
        )
    finding_packs = _decision_finding_packs(artifacts, decision)
    reversal = _nonempty(payload.get("reversal_condition"), "stored decision reversal_condition")
    reason = _nonempty(payload.get("revision_reason"), "stored decision revision_reason")
    return DecisionLedgerCompiler(store).converge(
        round_id=decision.round_id,
        decision_id=decision.id,
        blueprint_target=target,
        decision_slot_id=_identifier(payload.get("decision_slot_id"), "stored decision decision_slot_id"),
        finding_packs=finding_packs,
        status="blocked",
        selected_option=None,
        alternatives=alternatives,
        anchors=_mappings(payload.get("anchors"), "stored decision anchors"),
        design_consequence=_nonempty(
            payload.get("design_consequence"), "stored decision design_consequence"
        ),
        repository_touchpoints=_mappings(
            payload.get("repository_touchpoints"), "stored decision repository_touchpoints"
        ),
        validation=_mapping(payload.get("validation"), "stored decision validation"),
        change_tasks=_mappings(payload.get("change_tasks"), "stored decision change_tasks"),
        assumptions=_strings(payload.get("assumptions"), "stored decision assumptions"),
        fallback=_nonempty(payload.get("fallback"), "stored decision fallback"),
        reversal_condition=(
            f"{reversal} Reconsider after assurance evidence {evidence.id}@{evidence.revision} is corrected."
        ),
        revision_reason=(
            f"{reason} Blocked after assurance evidence {evidence.id}@{evidence.revision} failed."
        ),
    )


def _decision_finding_packs(
    artifacts: Sequence[ArtifactRevision], decision: ArtifactRevision
) -> tuple[ArtifactRevision, ...]:
    by_ref = {(item.round_id, item.id, item.revision): item for item in artifacts}
    findings: list[ArtifactRevision] = []
    for reference in decision.parent_refs:
        item = by_ref.get((reference.round_id, reference.artifact_id, reference.revision))
        if item is not None and item.kind == FINDING_PACK_KIND:
            findings.append(item)
    return tuple(findings)


def _normalize_source(value: Any) -> dict[str, str]:
    source = _mapping(value, "source")
    _require_exact_keys(
        source,
        {"locator", "version", "extraction_boundary", "applicability"},
        "source",
    )
    return {
        field: _nonempty(source[field], f"source.{field}")
        for field in ("locator", "version", "extraction_boundary", "applicability")
    }


def _resolve_exact(
    artifacts: Sequence[ArtifactRevision],
    value: ArtifactRevision,
    expected_kind: str,
    label: str,
) -> ArtifactRevision:
    if not isinstance(value, ArtifactRevision):
        raise InvalidAssuranceError(f"{label} must be an ArtifactRevision")
    for item in artifacts:
        if item.id == value.id and item.revision == value.revision:
            if item != value:
                raise InvalidAssuranceError(f"{label} does not match its stored revision")
            if item.kind != expected_kind:
                raise InvalidAssuranceError(f"{label} must be a {expected_kind} artifact")
            return item
    raise InvalidAssuranceError(f"{label} has not been persisted in this RunStore")


def _resolve_ref(
    artifacts: Sequence[ArtifactRevision],
    reference: ArtifactRef,
    expected_kind: str,
    label: str,
) -> ArtifactRevision:
    for item in artifacts:
        if (
            item.round_id == reference.round_id
            and item.id == reference.artifact_id
            and item.revision == reference.revision
        ):
            if item.kind != expected_kind:
                raise InvalidAssuranceError(f"{label} must be a {expected_kind} artifact")
            return item
    raise InvalidAssuranceError(f"{label} exact parent reference cannot be resolved")


def _ensure_new_id(artifacts: Sequence[ArtifactRevision], artifact_id: str, label: str) -> None:
    occupied = {item.kind for item in artifacts if item.id == artifact_id}
    if occupied:
        raise InvalidAssuranceError(f"{label} is already used by artifact kinds: {sorted(occupied)}")


def _ensure_same_round(round_id: str, artifact: ArtifactRevision, label: str) -> None:
    if artifact.round_id != round_id:
        raise InvalidAssuranceError(f"{label} must belong to assurance round")


def _target_slots(target: ArtifactRevision) -> dict[str, Mapping[str, Any]]:
    slots = _mappings(target.payload.get("slots"), "Blueprint Target slots")
    result: dict[str, Mapping[str, Any]] = {}
    for index, slot in enumerate(slots):
        slot_id = _identifier(slot.get("id"), f"Blueprint Target slots[{index}].id")
        if slot_id in result:
            raise InvalidAssuranceError(f"Blueprint Target repeats Decision Slot {slot_id}")
        result[slot_id] = slot
    return result


def _derived_id(source_id: str, suffix: str) -> str:
    candidate = f"{source_id}-{suffix}"
    if len(candidate) <= 64:
        return candidate
    digest = sha256(candidate.encode("utf-8")).hexdigest()[:16]
    prefix = source_id[: 64 - len(suffix) - len(digest) - 2].rstrip("-")
    return f"{prefix}-{suffix}-{digest}"


def _ref_dict(artifact: ArtifactRevision) -> dict[str, Any]:
    return ArtifactRef(artifact.round_id, artifact.id, artifact.revision).to_dict()


def _artifact_ref(value: Any, label: str) -> ArtifactRef:
    data = _mapping(value, label)
    _require_exact_keys(data, {"round_id", "artifact_id", "revision"}, label)
    return ArtifactRef(
        _identifier(data["round_id"], f"{label}.round_id"),
        _identifier(data["artifact_id"], f"{label}.artifact_id"),
        _positive_int(data["revision"], f"{label}.revision"),
    )


def _validate_ref(value: Any, label: str) -> None:
    _artifact_ref(value, label)


def _mappings(value: Any, label: str) -> list[Mapping[str, Any]]:
    plain = thaw_json(value)
    if isinstance(plain, (str, bytes)) or not isinstance(plain, Sequence):
        raise InvalidAssuranceError(f"{label} must be a sequence of mappings")
    result: list[Mapping[str, Any]] = []
    for index, item in enumerate(plain):
        if not isinstance(item, Mapping):
            raise InvalidAssuranceError(f"{label}[{index}] must be a mapping")
        result.append(item)
    return result


def _strings(value: Any, label: str) -> tuple[str, ...]:
    plain = thaw_json(value)
    if isinstance(plain, (str, bytes)) or not isinstance(plain, Sequence):
        raise InvalidAssuranceError(f"{label} must be a sequence of strings")
    return tuple(_nonempty(item, label) for item in plain)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    plain = thaw_json(value)
    if not isinstance(plain, Mapping):
        raise InvalidAssuranceError(f"{label} must be a mapping")
    return plain


def _enum_sequence(value: Any, label: str, allowed: set[str]) -> tuple[str, ...]:
    plain = thaw_json(value)
    if isinstance(plain, (str, bytes)) or not isinstance(plain, Sequence):
        raise InvalidAssuranceError(f"{label} must be a sequence")
    result = tuple(_enum(item, label, allowed) for item in plain)
    if len(set(result)) != len(result):
        raise InvalidAssuranceError(f"{label} must not contain duplicate values")
    return result


def _identifier(value: Any, label: str) -> str:
    try:
        return validate_identifier(value, label)
    except InvalidIdentifierError as error:
        raise InvalidAssuranceError(str(error)) from error


def _enum(value: Any, label: str, allowed: set[str]) -> str:
    result = _nonempty(value, label)
    if result not in allowed:
        raise InvalidAssuranceError(f"{label} is unsupported: {result}")
    return result


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidAssuranceError(f"{label} must be a nonempty string")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidAssuranceError(f"{label} must be a positive integer")
    return value


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise InvalidAssuranceError(
            f"{label} has unexpected keys; missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
