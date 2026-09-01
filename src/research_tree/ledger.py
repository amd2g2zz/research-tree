"""Persist atomic research findings and converge them into decision records."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .claims import Claim, ClaimAdmissionEvaluator, ClaimGrounding, ClaimState, ClaimValidationError
from .contradictions import unresolved_claim_ids
from .decision_map import BLUEPRINT_TARGET_KIND
from .domain import (
    ArtifactRef,
    ArtifactRevision,
    InvalidIdentifierError,
    RuntimeStoreError,
    validate_identifier,
)
from .evidence import EvidenceAnchor, EvidenceResolver, EvidenceValidationError
from .run_ledger import RunLedger
from .work_items import WORK_ITEM_KIND

FINDING_PACK_KIND = "finding-pack"
DECISION_LEDGER_KIND = "decision-ledger-entry"
ANCHOR_KINDS = {"source", "repository", "input", "experiment", "finding"}
OBSERVATION_ANCHOR_KINDS = ANCHOR_KINDS - {"finding"}
CONFIDENCES = {"low", "medium", "high"}
OPTION_EFFECTS = {"supports", "contradicts", "limits"}
DECISION_STATUSES = {"selected", "conditional", "deferred", "blocked"}
ALTERNATIVE_DISPOSITIONS = {"rejected", "deferred", "unresolved"}
VALIDATION_KINDS = {"test", "spike", "metric", "review"}
CONTINUATION_KINDS = {"deep_dive", "adversarial", "validation", "method_switch"}
VALIDATION_RESULTS = {"passed", "failed", "inconclusive"}


class FindingPackError(RuntimeStoreError):
    """Base error for invalid research observations."""


class InvalidFindingPackError(FindingPackError):
    """Raised before an unanchored worker report can be persisted."""


class DecisionLedgerError(RuntimeStoreError):
    """Base error for invalid decision convergence."""


class InvalidDecisionLedgerError(DecisionLedgerError):
    """Raised before an incomplete technical decision can be persisted."""


class CanonicalFindingPackCompiler:
    """Compile strict Finding Packs into the canonical RunLedger."""

    def __init__(self, ledger: RunLedger, evidence_resolver: EvidenceResolver) -> None:
        if not isinstance(ledger, RunLedger):
            raise InvalidFindingPackError("canonical Finding Pack compiler requires a RunLedger")
        if not isinstance(evidence_resolver, EvidenceResolver) or evidence_resolver.ledger is not ledger:
            raise InvalidFindingPackError(
                "canonical Finding Pack compiler requires a matching ledger-backed EvidenceResolver"
            )
        self._ledger = ledger
        self._evidence_resolver = evidence_resolver

    def compile(
        self,
        *,
        round_id: str,
        finding_id: str,
        work_item: ArtifactRevision,
        observations: Sequence[Mapping[str, Any]],
        option_effects: Sequence[Mapping[str, Any]],
        implementation_implications: Sequence[str],
        remaining_uncertainties: Sequence[str],
        expected_revision: int,
        claims: Sequence[Claim] = (),
        claim_groundings: Sequence[ClaimGrounding] = (),
        research_node_id: str | None = None,
        research_continuations: Sequence[Mapping[str, Any]] = (),
        validation_result: Mapping[str, Any] | None = None,
        search_comparison: Mapping[str, Any] | None = None,
        comparison_status: str | None = None,
    ) -> ArtifactRevision:
        try:
            snapshot = self._ledger.load_run(round_id)
            validate_identifier(finding_id, "finding_id")
            _ensure_id_compatibility(snapshot.artifacts, finding_id, FINDING_PACK_KIND, InvalidFindingPackError)
            work = _resolve_exact(
                snapshot.artifacts,
                work_item,
                WORK_ITEM_KIND,
                "work_item",
                InvalidFindingPackError,
            )
            if work.round_id != round_id:
                raise InvalidFindingPackError("work_item must belong to Finding Pack round")
            target = _work_target(snapshot.artifacts, work, InvalidFindingPackError)
            slot = _target_slot(target, work.payload.get("decision_slot_id"), InvalidFindingPackError)
            options = _string_sequence(
                slot.get("alternatives"),
                "slot alternatives",
                error_type=InvalidFindingPackError,
            )
            normalized_observations = _normalize_observations(
                observations,
                slot,
                strict_evidence=True,
            )
            _validate_resolvable_observations(normalized_observations, self._evidence_resolver)
            normalized_claims, normalized_groundings, claim_assessments = _normalize_claim_admission(
                claims,
                claim_groundings,
                normalized_observations,
                self._evidence_resolver,
            )
            normalized_effects = _normalize_option_effects(option_effects, options)
            _validate_effect_claims(normalized_effects, claim_assessments, InvalidFindingPackError)
            payload = {
                "id": finding_id,
                "round_id": round_id,
                "work_item_id": work.id,
                "blueprint_target_id": target.id,
                "decision_slot_id": slot["id"],
                "observations": normalized_observations,
                "option_effects": normalized_effects,
                "claims": normalized_claims,
                "claim_groundings": normalized_groundings,
                "claim_assessments": claim_assessments,
                "implementation_implications": list(
                    _string_sequence(
                        implementation_implications,
                        "implementation_implications",
                        error_type=InvalidFindingPackError,
                    )
                ),
                "remaining_uncertainties": list(
                    _string_sequence(
                        remaining_uncertainties,
                        "remaining_uncertainties",
                        allow_empty=True,
                        error_type=InvalidFindingPackError,
                    )
                ),
                "research_node_id": (
                    None
                    if research_node_id is None
                    else _nonempty_string(
                        research_node_id,
                        "research_node_id",
                        InvalidFindingPackError,
                    )
                ),
                "research_continuations": _normalize_research_continuations(research_continuations),
                "validation_result": _normalize_validation_result(validation_result),
                "evidence_mode": "strict",
            }
            normalized_comparison = _normalize_search_comparison(search_comparison)
            if normalized_comparison is not None:
                payload["search_comparison"] = normalized_comparison
                payload["comparison_status"] = "measured"
            elif comparison_status is not None:
                if comparison_status != "skipped":
                    raise InvalidFindingPackError("comparison_status must be 'skipped' when no comparison is declared")
                payload["comparison_status"] = "skipped"
        except (InvalidIdentifierError, TypeError, ValueError) as error:
            raise InvalidFindingPackError(str(error)) from error

        work_ref = ArtifactRef(round_id, work.id, work.revision)
        target_ref = ArtifactRef(round_id, target.id, target.revision)
        evidence_refs = _unique_artifact_refs(
            (*_strict_evidence_refs(normalized_observations), *_claim_evidence_refs(claim_groundings))
        )
        finding = self._ledger.append_artifact(
            round_id,
            finding_id,
            FINDING_PACK_KIND,
            payload,
            parent_refs=(work_ref, target_ref, *evidence_refs),
            expected_revision=expected_revision,
        )
        if any(item.kind == "research-run-state" for item in self._ledger.load_run(round_id).artifacts):
            from .coordinator import ResearchRunCoordinator

            ResearchRunCoordinator(self._ledger).detect_and_apply_contradictions(
                run_id=round_id,
                blueprint_target_id=target.id,
                decision_slot_id=slot["id"],
                expected_revision=self._ledger.get_revision(round_id),
            )
        from .coordinator import ResearchRunCoordinator

        ResearchRunCoordinator(self._ledger).assess_finding_pack_contribution(
            round_id,
            finding,
            expected_revision=self._ledger.get_revision(round_id),
        )
        return finding


class CanonicalDecisionLedgerCompiler:
    """Converge strict canonical Finding Packs in the same RunLedger."""

    def __init__(self, ledger: RunLedger, evidence_resolver: EvidenceResolver) -> None:
        if not isinstance(ledger, RunLedger):
            raise InvalidDecisionLedgerError("canonical Decision Ledger compiler requires a RunLedger")
        if not isinstance(evidence_resolver, EvidenceResolver) or evidence_resolver.ledger is not ledger:
            raise InvalidDecisionLedgerError(
                "canonical Decision Ledger compiler requires a matching ledger-backed EvidenceResolver"
            )
        self._ledger = ledger
        self._evidence_resolver = evidence_resolver

    def converge(
        self,
        *,
        round_id: str,
        decision_id: str,
        blueprint_target: ArtifactRevision,
        decision_slot_id: str,
        finding_packs: Sequence[ArtifactRevision],
        status: str,
        selected_option: str | None,
        alternatives: Sequence[Mapping[str, Any]],
        anchors: Sequence[Mapping[str, Any]],
        design_consequence: str,
        repository_touchpoints: Sequence[Mapping[str, Any]],
        validation: Mapping[str, Any],
        change_tasks: Sequence[Mapping[str, Any]],
        assumptions: Sequence[str],
        fallback: str,
        reversal_condition: str,
        revision_reason: str,
        expected_revision: int,
    ) -> ArtifactRevision:
        try:
            snapshot = self._ledger.load_run(round_id)
            validate_identifier(decision_id, "decision_id")
            _ensure_id_compatibility(
                snapshot.artifacts,
                decision_id,
                DECISION_LEDGER_KIND,
                InvalidDecisionLedgerError,
            )
            target = _resolve_exact(
                snapshot.artifacts,
                blueprint_target,
                BLUEPRINT_TARGET_KIND,
                "blueprint_target",
                InvalidDecisionLedgerError,
            )
            if target.round_id != round_id:
                raise InvalidDecisionLedgerError("blueprint_target must belong to decision round")
            slot = _target_slot(target, decision_slot_id, InvalidDecisionLedgerError)
            slot_options = _string_sequence(slot.get("alternatives"), "slot alternatives")
            normalized_status = _enum(status, "status", DECISION_STATUSES, InvalidDecisionLedgerError)
            findings = _resolve_findings(
                snapshot.artifacts,
                finding_packs,
                round_id,
                target,
                slot["id"],
            )
            evidence_refs = (
                _strict_finding_evidence_refs(findings, self._evidence_resolver)
                if normalized_status in {"selected", "conditional"} or findings
                else ()
            )
            selected = _normalize_selected_option(
                selected_option,
                normalized_status,
                slot_options,
            )
            conflict_candidates = tuple(
                artifact
                for artifact in snapshot.artifacts
                if artifact.kind == FINDING_PACK_KIND
                and artifact.payload.get("blueprint_target_id") == target.id
                and artifact.payload.get("decision_slot_id") == slot["id"]
            )
            _validate_finding_claim_authority(
                tuple({(item.id, item.revision): item for item in (*findings, *conflict_candidates)}.values()),
                self._evidence_resolver,
                selected,
            )
            normalized_alternatives = _normalize_alternatives(
                alternatives,
                slot_options,
                selected,
            )
            normalized_anchors = _normalize_decision_anchors(anchors, findings)
            normalized_touchpoints = _normalize_touchpoints(repository_touchpoints, slot)
            normalized_validation = _normalize_validation(validation)
            normalized_tasks = _normalize_change_tasks(change_tasks, slot)
            payload = {
                "id": decision_id,
                "round_id": round_id,
                "blueprint_target_id": target.id,
                "decision_slot_id": slot["id"],
                "status": normalized_status,
                "selected_option": selected,
                "alternatives": normalized_alternatives,
                "anchors": normalized_anchors,
                "design_consequence": _nonempty_string(
                    design_consequence,
                    "design_consequence",
                    InvalidDecisionLedgerError,
                ),
                "repository_touchpoints": normalized_touchpoints,
                "validation": normalized_validation,
                "change_tasks": normalized_tasks,
                "assumptions": list(_string_sequence(assumptions, "assumptions", allow_empty=True)),
                "fallback": _nonempty_string(fallback, "fallback", InvalidDecisionLedgerError),
                "reversal_condition": _nonempty_string(
                    reversal_condition,
                    "reversal_condition",
                    InvalidDecisionLedgerError,
                ),
                "revision_reason": _nonempty_string(
                    revision_reason,
                    "revision_reason",
                    InvalidDecisionLedgerError,
                ),
            }
            _validate_decision_trace(slot, findings, payload, InvalidDecisionLedgerError)
            previous = _latest_artifact(snapshot.artifacts, decision_id, DECISION_LEDGER_KIND)
        except (InvalidIdentifierError, TypeError, ValueError) as error:
            raise InvalidDecisionLedgerError(str(error)) from error

        target_ref = ArtifactRef(round_id, target.id, target.revision)
        finding_refs = tuple(ArtifactRef(round_id, finding.id, finding.revision) for finding in findings)
        parent_refs = (() if previous is None else (ArtifactRef(round_id, previous.id, previous.revision),)) + (
            target_ref,
            *finding_refs,
            *evidence_refs,
        )
        return self._ledger.append_artifact(
            round_id,
            decision_id,
            DECISION_LEDGER_KIND,
            payload,
            parent_refs=_unique_artifact_refs(parent_refs),
            expected_revision=expected_revision,
        )


def _ensure_id_compatibility(
    artifacts: Sequence[ArtifactRevision],
    artifact_id: str,
    expected_kind: str,
    error_type: type[RuntimeStoreError],
) -> None:
    foreign = {artifact.kind for artifact in artifacts if artifact.id == artifact_id and artifact.kind != expected_kind}
    if foreign:
        raise error_type(f"artifact id {artifact_id!r} is already used by kinds: {sorted(foreign)}")


def _resolve_exact(
    artifacts: Sequence[ArtifactRevision],
    artifact: ArtifactRevision,
    expected_kind: str,
    label: str,
    error_type: type[RuntimeStoreError],
) -> ArtifactRevision:
    if not isinstance(artifact, ArtifactRevision):
        raise error_type(f"{label} must be an ArtifactRevision")
    for stored in artifacts:
        if stored.id == artifact.id and stored.revision == artifact.revision:
            if stored != artifact:
                raise error_type(f"{label} does not match its stored revision")
            if stored.kind != expected_kind:
                raise error_type(f"{label} must be a {expected_kind} artifact")
            return stored
    raise error_type(f"{label} has not been persisted in the active run ledger")


def _work_target(
    artifacts: Sequence[ArtifactRevision],
    work: ArtifactRevision,
    error_type: type[RuntimeStoreError],
) -> ArtifactRevision:
    expected_id = work.payload.get("blueprint_target_id")
    if not isinstance(expected_id, str):
        raise error_type("work_item has no blueprint_target_id")
    by_ref = {(artifact.id, artifact.revision): artifact for artifact in artifacts}
    for reference in work.parent_refs:
        if reference.artifact_id != expected_id:
            continue
        target = by_ref.get((reference.artifact_id, reference.revision))
        if target is not None and target.kind == BLUEPRINT_TARGET_KIND:
            return target
    raise error_type("work_item has no exact Blueprint Target parent reference")


def _target_slot(
    target: ArtifactRevision,
    slot_id_value: Any,
    error_type: type[RuntimeStoreError],
) -> Mapping[str, Any]:
    slot_id = _identifier(slot_id_value, "decision_slot_id", error_type)
    slots = _mapping_sequence(target.payload.get("slots"), "blueprint_target slots", error_type)
    for slot in slots:
        if slot.get("id") == slot_id:
            return slot
    raise error_type(f"Decision Slot is absent from Blueprint Target: {slot_id}")


def _normalize_observations(
    value: Any,
    slot: Mapping[str, Any],
    *,
    strict_evidence: bool,
) -> list[dict[str, Any]]:
    observations = _mapping_sequence(value, "observations", InvalidFindingPackError)
    if not observations:
        raise InvalidFindingPackError("Finding Pack requires at least one atomic observation")
    normalized: list[dict[str, Any]] = []
    for index, observation in enumerate(observations):
        label = f"observations[{index}]"
        expected_observation_keys = {"claim", "anchor", "applicability", "confidence", "limitation"}
        _require_exact_keys(
            observation,
            expected_observation_keys | ({"claim_id"} if "claim_id" in observation else set()),
            label,
            InvalidFindingPackError,
        )
        raw_anchor = observation["anchor"]
        if isinstance(raw_anchor, Mapping) and "artifact_digest" in raw_anchor:
            try:
                typed = EvidenceAnchor.from_dict(raw_anchor)
            except (TypeError, ValueError) as error:
                raise InvalidFindingPackError(f"{label}.anchor is invalid: {error}") from error
            if strict_evidence and not typed.is_strict:
                raise InvalidFindingPackError(f"{label}.anchor must be an exact canonical EvidenceAnchor")
            anchor = typed.to_dict()
        else:
            if strict_evidence:
                raise InvalidFindingPackError(f"{label}.anchor must be a canonical EvidenceAnchor")
            anchor = _normalize_anchor(
                raw_anchor,
                label,
                OBSERVATION_ANCHOR_KINDS,
                InvalidFindingPackError,
            )
        if anchor.get("kind") == "repository":
            _validate_repository_anchor(anchor["ref"], slot, InvalidFindingPackError)
        normalized.append(
            {
                "claim_id": _identifier(
                    observation.get("claim_id", f"observation-{index}"),
                    f"{label}.claim_id",
                    InvalidFindingPackError,
                ),
                "claim": _nonempty_string(observation["claim"], f"{label}.claim", InvalidFindingPackError),
                "anchor": anchor,
                "applicability": _nonempty_string(
                    observation["applicability"],
                    f"{label}.applicability",
                    InvalidFindingPackError,
                ),
                "confidence": _enum(
                    observation["confidence"],
                    f"{label}.confidence",
                    CONFIDENCES,
                    InvalidFindingPackError,
                ),
                "limitation": _nonempty_string(
                    observation["limitation"],
                    f"{label}.limitation",
                    InvalidFindingPackError,
                ),
            }
        )
    return normalized


def _validate_resolvable_observations(
    observations: Sequence[Mapping[str, Any]],
    resolver: EvidenceResolver,
) -> None:
    for index, observation in enumerate(observations):
        anchor = observation["anchor"]
        if not isinstance(anchor, Mapping) or "artifact_digest" not in anchor:
            raise InvalidFindingPackError(f"observations[{index}].anchor must be an EvidenceAnchor")
        try:
            typed = EvidenceAnchor.from_dict(anchor)
            resolver.resolve(typed)
        except (KeyError, TypeError, EvidenceValidationError) as error:
            raise InvalidFindingPackError(f"observations[{index}].anchor is not resolvable: {error}") from error


def _strict_evidence_refs(observations: Sequence[Mapping[str, Any]]) -> tuple[ArtifactRef, ...]:
    references: list[ArtifactRef] = []
    for index, observation in enumerate(observations):
        try:
            anchor = EvidenceAnchor.from_dict(observation["anchor"])
        except (KeyError, TypeError, ValueError) as error:
            raise InvalidFindingPackError(f"observations[{index}].anchor is not canonical evidence: {error}") from error
        if anchor.artifact_ref is None:
            raise InvalidFindingPackError(f"observations[{index}].anchor is missing its exact evidence reference")
        if anchor.artifact_ref not in references:
            references.append(anchor.artifact_ref)
    return tuple(references)


def _strict_finding_evidence_refs(
    findings: Sequence[ArtifactRevision], resolver: EvidenceResolver
) -> tuple[ArtifactRef, ...]:
    if not findings:
        raise InvalidDecisionLedgerError("selected or conditional decision requires at least one strict Finding Pack")
    references: list[ArtifactRef] = []
    for finding in findings:
        if finding.payload.get("evidence_mode") != "strict":
            raise InvalidDecisionLedgerError(f"Finding Pack {finding.id} is not backed by strict evidence")
        try:
            finding_refs = _strict_evidence_refs(finding.payload.get("observations", ()))
        except InvalidFindingPackError as error:
            raise InvalidDecisionLedgerError(
                f"Finding Pack {finding.id} has invalid strict evidence: {error}"
            ) from error
        if not finding_refs:
            raise InvalidDecisionLedgerError(f"Finding Pack {finding.id} requires at least one strict observation")
        for reference in finding_refs:
            if reference not in finding.parent_refs:
                raise InvalidDecisionLedgerError(
                    f"Finding Pack {finding.id} lacks parent lineage for {reference.artifact_id}"
                )
            if reference not in references:
                references.append(reference)
        for observation in finding.payload.get("observations", ()):
            try:
                resolver.resolve(EvidenceAnchor.from_dict(observation["anchor"]))
            except (KeyError, TypeError, ValueError, EvidenceValidationError) as error:
                raise InvalidDecisionLedgerError(
                    f"Finding Pack {finding.id} evidence is not resolvable: {error}"
                ) from error
    return tuple(references)


def _normalize_claim_admission(
    claims: Sequence[Claim],
    groundings: Sequence[ClaimGrounding],
    observations: Sequence[Mapping[str, Any]],
    resolver: EvidenceResolver,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    normalized_claims = tuple(claims)
    normalized_groundings = tuple(groundings)
    if any(not isinstance(claim, Claim) for claim in normalized_claims):
        raise InvalidFindingPackError("claims must contain Claim values")
    if any(not isinstance(grounding, ClaimGrounding) for grounding in normalized_groundings):
        raise InvalidFindingPackError("claim_groundings must contain ClaimGrounding values")
    if not normalized_claims and not normalized_groundings:
        return [], [], []
    claim_ids = {claim.claim_id for claim in normalized_claims}
    if len(claim_ids) != len(normalized_claims):
        raise InvalidFindingPackError("claims must not contain duplicate claim_id values")
    observation_claim_ids = {str(observation["claim_id"]) for observation in observations}
    if observation_claim_ids != claim_ids:
        raise InvalidFindingPackError("every Finding observation must bind exactly one declared claim")
    if any(grounding.claim_id not in claim_ids for grounding in normalized_groundings):
        raise InvalidFindingPackError("claim grounding refers to an undeclared claim")
    evaluator = ClaimAdmissionEvaluator(resolver)
    try:
        assessments = [
            evaluator.assess(
                claim,
                tuple(grounding for grounding in normalized_groundings if grounding.claim_id == claim.claim_id),
            )
            for claim in normalized_claims
        ]
    except ClaimValidationError as error:
        raise InvalidFindingPackError(str(error)) from error
    return (
        [_claim_to_dict(claim) for claim in normalized_claims],
        [_grounding_to_dict(grounding) for grounding in normalized_groundings],
        [_assessment_to_dict(assessment) for assessment in assessments],
    )


def _validate_effect_claims(
    effects: Sequence[Mapping[str, Any]],
    assessments: Sequence[Mapping[str, Any]],
    error_type: type[RuntimeStoreError],
) -> None:
    if not assessments:
        return
    admitted = {item.get("claim_id") for item in assessments if item.get("state") == ClaimState.CORROBORATED.value}
    known = {item.get("claim_id") for item in assessments}
    for effect in effects:
        claim_ids = effect.get("claim_ids")
        if not claim_ids:
            raise error_type("every option effect requires at least one claim_id")
        if any(claim_id not in known for claim_id in claim_ids):
            raise error_type("option effect refers to an undeclared claim")
        if effect.get("effect") == "supports" and any(claim_id not in admitted for claim_id in claim_ids):
            raise error_type("supporting option effect requires corroborated claims")


def _claim_to_dict(claim: Claim) -> dict[str, Any]:
    return {
        "claim_id": claim.claim_id,
        "subject": claim.subject,
        "predicate": claim.predicate,
        "value": claim.value,
        "polarity": claim.polarity,
        "scope": claim.scope,
        "version": claim.version,
        "time_range": claim.time_range,
        "conditions": list(claim.conditions),
        "platform": claim.platform,
        "modality": claim.modality,
    }


def _claim_from_dict(value: Mapping[str, Any]) -> Claim:
    required = {
        "claim_id",
        "subject",
        "predicate",
        "value",
        "polarity",
        "scope",
        "version",
        "time_range",
        "conditions",
    }
    optional = {"platform", "modality"}
    if not isinstance(value, Mapping) or not required <= set(value) or set(value) - required - optional:
        raise InvalidDecisionLedgerError("claim has unsupported fields")
    conditions = value["conditions"]
    if isinstance(conditions, (str, bytes)) or not isinstance(conditions, Sequence):
        raise InvalidDecisionLedgerError("claim.conditions must be a sequence")
    return Claim(
        claim_id=value["claim_id"],
        subject=value["subject"],
        predicate=value["predicate"],
        value=value["value"],
        polarity=value["polarity"],
        scope=value["scope"],
        version=value["version"],
        time_range=value["time_range"],
        conditions=tuple(conditions),
        platform=value.get("platform", "unspecified"),
        modality=value.get("modality", "unspecified"),
    )


def _grounding_to_dict(grounding: ClaimGrounding) -> dict[str, Any]:
    return {"grounding_id": grounding.grounding_id, "claim_id": grounding.claim_id, "anchor": dict(grounding.anchor)}


def _grounding_from_dict(value: Mapping[str, Any]) -> ClaimGrounding:
    _require_exact_keys(value, {"grounding_id", "claim_id", "anchor"}, "claim_grounding", InvalidDecisionLedgerError)
    return ClaimGrounding(grounding_id=value["grounding_id"], claim_id=value["claim_id"], anchor=value["anchor"])


def _assessment_to_dict(assessment: Any) -> dict[str, Any]:
    return {
        "claim_id": assessment.claim_id,
        "state": assessment.state.value,
        "provenance_clusters": list(assessment.provenance_clusters),
        "grounding_ids": list(assessment.grounding_ids),
        "grounding_refs": [reference.to_dict() for reference in assessment.grounding_refs],
        "rejection_reasons": list(assessment.rejection_reasons),
    }


def _claim_evidence_refs(groundings: Sequence[ClaimGrounding]) -> tuple[ArtifactRef, ...]:
    references: list[ArtifactRef] = []
    for grounding in groundings:
        try:
            reference = EvidenceAnchor.from_dict(grounding.anchor).artifact_ref
        except (TypeError, ValueError) as error:
            raise InvalidFindingPackError(f"claim grounding is not canonical evidence: {error}") from error
        if reference not in references:
            references.append(reference)
    return tuple(references)


def _validate_finding_claim_authority(
    findings: Sequence[ArtifactRevision],
    resolver: EvidenceResolver,
    selected_option: str | None,
) -> None:
    if selected_option is None:
        return
    parsed_claims: list[Claim] = []
    parsed_by_finding: dict[ArtifactRef, tuple[Claim, ...]] = {}
    for finding in findings:
        try:
            values = tuple(_claim_from_dict(value) for value in finding.payload.get("claims", ()))
        except (ClaimValidationError, KeyError, TypeError, ValueError) as error:
            raise InvalidDecisionLedgerError(
                f"Finding Pack {finding.id} has invalid claim admission: {error}"
            ) from error
        parsed_claims.extend(values)
        parsed_by_finding[ArtifactRef(finding.round_id, finding.id, finding.revision)] = values
    contested = unresolved_claim_ids(parsed_claims)
    for finding in findings:
        try:
            claims = tuple(_claim_from_dict(value) for value in finding.payload["claims"])
            groundings = tuple(_grounding_from_dict(value) for value in finding.payload["claim_groundings"])
            assessments = {
                claim.claim_id: ClaimAdmissionEvaluator(resolver).assess(
                    claim,
                    tuple(grounding for grounding in groundings if grounding.claim_id == claim.claim_id),
                )
                for claim in claims
            }
            for effect in finding.payload.get("option_effects", ()):
                if effect.get("option") != selected_option or effect.get("effect") != "supports":
                    continue
                claim_ids = effect.get("claim_ids")
                if not claim_ids:
                    raise InvalidDecisionLedgerError("supporting option effect has no claim admission")
                if any(claim_id in contested for claim_id in claim_ids):
                    raise InvalidDecisionLedgerError("selected option relies on an unresolved canonical contradiction")
                if any(
                    assessments.get(claim_id) is None or not assessments[claim_id].decision_authority
                    for claim_id in claim_ids
                ):
                    raise InvalidDecisionLedgerError("selected option relies on a non-corroborated claim")
        except (ClaimValidationError, KeyError, TypeError, ValueError) as error:
            raise InvalidDecisionLedgerError(
                f"Finding Pack {finding.id} has invalid claim admission: {error}"
            ) from error


def _unique_artifact_refs(references: Sequence[ArtifactRef]) -> tuple[ArtifactRef, ...]:
    unique: list[ArtifactRef] = []
    for reference in references:
        if reference not in unique:
            unique.append(reference)
    return tuple(unique)


def _normalize_option_effects(value: Any, options: tuple[str, ...]) -> list[dict[str, Any]]:
    effects = _mapping_sequence(value, "option_effects", InvalidFindingPackError)
    if not effects:
        raise InvalidFindingPackError("Finding Pack requires at least one option effect")
    normalized: list[dict[str, Any]] = []
    for index, effect in enumerate(effects):
        label = f"option_effects[{index}]"
        _require_exact_keys(
            effect,
            {"option", "effect"} | ({"claim_ids"} if "claim_ids" in effect else set()),
            label,
            InvalidFindingPackError,
        )
        option = _nonempty_string(effect["option"], f"{label}.option", InvalidFindingPackError)
        if option not in options:
            raise InvalidFindingPackError(f"{label}.option is absent from the Decision Slot")
        normalized.append(
            {
                "option": option,
                "effect": _enum(effect["effect"], f"{label}.effect", OPTION_EFFECTS, InvalidFindingPackError),
                "claim_ids": list(
                    _string_sequence(effect["claim_ids"], f"{label}.claim_ids", error_type=InvalidFindingPackError)
                )
                if "claim_ids" in effect
                else [],
            }
        )
    return normalized


def _normalize_search_comparison(
    value: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Validate the batch cross-comparison carrier for a Finding Pack payload."""

    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise InvalidFindingPackError("search_comparison must be a mapping")
    allowed = {"comparison_id", "provider_fanout", "duplicates", "captures", "coverage_met", "contradictions"}
    unexpected = set(value) - allowed
    if unexpected:
        raise InvalidFindingPackError(f"search_comparison has unsupported keys: {sorted(unexpected)}")
    counts: dict[str, int] = {}
    for name in ("provider_fanout", "duplicates", "captures"):
        raw = value.get(name, 0)
        if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
            raise InvalidFindingPackError(f"search_comparison.{name} must be a nonnegative integer")
        counts[name] = raw
    coverage = value.get("coverage_met", 0)
    if coverage not in (0, 1, True, False):
        raise InvalidFindingPackError("search_comparison.coverage_met must be 0 or 1")
    raw_contradictions = value.get("contradictions", ())
    if isinstance(raw_contradictions, (str, bytes)) or not isinstance(raw_contradictions, Sequence):
        raise InvalidFindingPackError("search_comparison.contradictions must be a sequence of strings")
    contradictions: list[str] = []
    for item in raw_contradictions:
        if not isinstance(item, str) or not item.strip():
            raise InvalidFindingPackError("search_comparison.contradictions must be non-empty strings")
        contradictions.append(item.strip())
    comparison: dict[str, Any] = {
        **counts,
        "coverage_met": int(bool(coverage)),
        "contradictions": contradictions,
    }
    comparison_id = value.get("comparison_id")
    if comparison_id is not None:
        if not isinstance(comparison_id, str) or not comparison_id.strip():
            raise InvalidFindingPackError("search_comparison.comparison_id must be a non-empty string")
        comparison["comparison_id"] = comparison_id.strip()
    return comparison


def _normalize_research_continuations(value: Any) -> list[dict[str, Any]]:
    continuations = _mapping_sequence(
        value,
        "research_continuations",
        InvalidFindingPackError,
    )
    normalized: list[dict[str, Any]] = []
    for index, continuation in enumerate(continuations):
        label = f"research_continuations[{index}]"
        _require_exact_keys(
            continuation,
            {
                "kind",
                "question",
                "trigger",
                "evidence_needed",
                "oracle",
                "estimated_cost",
            },
            label,
            InvalidFindingPackError,
        )
        cost = continuation["estimated_cost"]
        if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost <= 0:
            raise InvalidFindingPackError(f"{label}.estimated_cost must be positive")
        normalized.append(
            {
                "kind": _enum(
                    continuation["kind"],
                    f"{label}.kind",
                    CONTINUATION_KINDS,
                    InvalidFindingPackError,
                ),
                "question": _nonempty_string(
                    continuation["question"],
                    f"{label}.question",
                    InvalidFindingPackError,
                ),
                "trigger": _nonempty_string(
                    continuation["trigger"],
                    f"{label}.trigger",
                    InvalidFindingPackError,
                ),
                "evidence_needed": _nonempty_string(
                    continuation["evidence_needed"],
                    f"{label}.evidence_needed",
                    InvalidFindingPackError,
                ),
                "oracle": _nonempty_string(
                    continuation["oracle"],
                    f"{label}.oracle",
                    InvalidFindingPackError,
                ),
                "estimated_cost": float(cost),
            }
        )
    return normalized


def _normalize_validation_result(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise InvalidFindingPackError("validation_result must be a mapping or null")
    _require_exact_keys(
        value,
        {"status", "oracle", "evidence_ref"},
        "validation_result",
        InvalidFindingPackError,
    )
    return {
        "status": _enum(
            value["status"],
            "validation_result.status",
            VALIDATION_RESULTS,
            InvalidFindingPackError,
        ),
        "oracle": _nonempty_string(
            value["oracle"],
            "validation_result.oracle",
            InvalidFindingPackError,
        ),
        "evidence_ref": _nonempty_string(
            value["evidence_ref"],
            "validation_result.evidence_ref",
            InvalidFindingPackError,
        ),
    }


def _resolve_findings(
    artifacts: Sequence[ArtifactRevision],
    values: Any,
    round_id: str,
    target: ArtifactRevision,
    slot_id: str,
) -> tuple[ArtifactRevision, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise InvalidDecisionLedgerError("finding_packs must be a sequence")
    findings: list[ArtifactRevision] = []
    seen_ids: set[str] = set()
    target_ref = ArtifactRef(round_id, target.id, target.revision)
    for index, finding in enumerate(values):
        stored = _resolve_exact(
            artifacts,
            finding,
            FINDING_PACK_KIND,
            f"finding_packs[{index}]",
            InvalidDecisionLedgerError,
        )
        if stored.round_id != round_id:
            raise InvalidDecisionLedgerError("Finding Pack must belong to decision round")
        if stored.id in seen_ids:
            raise InvalidDecisionLedgerError("finding_packs cannot include two revisions of one id")
        seen_ids.add(stored.id)
        if (
            stored.payload.get("blueprint_target_id") != target.id
            or stored.payload.get("decision_slot_id") != slot_id
            or target_ref not in stored.parent_refs
        ):
            raise InvalidDecisionLedgerError("Finding Pack must belong to the exact Blueprint Target and Decision Slot")
        findings.append(stored)
    return tuple(findings)


def _normalize_selected_option(
    value: Any,
    status: str,
    options: tuple[str, ...],
) -> str | None:
    if status in {"selected", "conditional"}:
        selected = _nonempty_string(value, "selected_option", InvalidDecisionLedgerError)
        if selected not in options:
            raise InvalidDecisionLedgerError("selected_option is absent from the Decision Slot")
        return selected
    if value is not None:
        raise InvalidDecisionLedgerError("deferred or blocked decision must not select an option")
    return None


def _normalize_alternatives(
    value: Any,
    options: tuple[str, ...],
    selected: str | None,
) -> list[dict[str, str]]:
    alternatives = _mapping_sequence(value, "alternatives", InvalidDecisionLedgerError)
    if not alternatives:
        raise InvalidDecisionLedgerError("Decision Ledger entry requires at least one alternative")
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, alternative in enumerate(alternatives):
        label = f"alternatives[{index}]"
        _require_exact_keys(
            alternative,
            {"option", "disposition", "reason"},
            label,
            InvalidDecisionLedgerError,
        )
        option = _nonempty_string(alternative["option"], f"{label}.option", InvalidDecisionLedgerError)
        if option not in options or option == selected or option in seen:
            raise InvalidDecisionLedgerError(f"{label}.option must be a distinct unselected slot option")
        seen.add(option)
        normalized.append(
            {
                "option": option,
                "disposition": _enum(
                    alternative["disposition"],
                    f"{label}.disposition",
                    ALTERNATIVE_DISPOSITIONS,
                    InvalidDecisionLedgerError,
                ),
                "reason": _nonempty_string(alternative["reason"], f"{label}.reason", InvalidDecisionLedgerError),
            }
        )
    return normalized


def _normalize_decision_anchors(
    value: Any,
    findings: Sequence[ArtifactRevision],
) -> list[dict[str, str]]:
    anchors = _mapping_sequence(value, "anchors", InvalidDecisionLedgerError)
    normalized: list[dict[str, str]] = []
    finding_ids = {finding.id for finding in findings}
    for index, anchor_value in enumerate(anchors):
        anchor = _normalize_anchor(
            anchor_value,
            f"anchors[{index}]",
            ANCHOR_KINDS,
            InvalidDecisionLedgerError,
        )
        if anchor["kind"] == "finding" and anchor["ref"] not in finding_ids:
            raise InvalidDecisionLedgerError("finding anchor must refer to a supplied Finding Pack")
        normalized.append(anchor)
    return normalized


def _normalize_touchpoints(value: Any, slot: Mapping[str, Any]) -> list[dict[str, str | None]]:
    allowed = {
        (item.get("path"), item.get("symbol"))
        for item in _mapping_sequence(
            slot.get("repository_touchpoints"),
            "slot repository_touchpoints",
            InvalidDecisionLedgerError,
        )
    }
    points = _mapping_sequence(value, "repository_touchpoints", InvalidDecisionLedgerError)
    normalized: list[dict[str, str | None]] = []
    for index, point in enumerate(points):
        label = f"repository_touchpoints[{index}]"
        _require_exact_keys(point, {"path", "symbol"}, label, InvalidDecisionLedgerError)
        path = _nonempty_string(point["path"], f"{label}.path", InvalidDecisionLedgerError)
        symbol_raw = point["symbol"]
        if symbol_raw is not None and not isinstance(symbol_raw, str):
            raise InvalidDecisionLedgerError(f"{label}.symbol must be a string or null")
        symbol = (
            None
            if symbol_raw is None
            else _nonempty_string(
                symbol_raw,
                f"{label}.symbol",
                InvalidDecisionLedgerError,
            )
        )
        if allowed and (path, symbol) not in allowed:
            raise InvalidDecisionLedgerError(f"{label} is absent from the Decision Slot")
        normalized.append({"path": path, "symbol": symbol})
    if allowed and not normalized:
        raise InvalidDecisionLedgerError("repository-backed Decision Slot requires a touchpoint")
    return normalized


def _normalize_validation(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise InvalidDecisionLedgerError("validation must be a mapping")
    _require_exact_keys(value, {"kind", "oracle"}, "validation", InvalidDecisionLedgerError)
    return {
        "kind": _enum(value["kind"], "validation.kind", VALIDATION_KINDS, InvalidDecisionLedgerError),
        "oracle": _nonempty_string(value["oracle"], "validation.oracle", InvalidDecisionLedgerError),
    }


def _normalize_change_tasks(value: Any, slot: Mapping[str, Any]) -> list[dict[str, Any]]:
    tasks = _mapping_sequence(value, "change_tasks", InvalidDecisionLedgerError)
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, task in enumerate(tasks):
        label = f"change_tasks[{index}]"
        _require_exact_keys(
            task,
            {"id", "description", "acceptance_oracle", "repository_touchpoints"},
            label,
            InvalidDecisionLedgerError,
        )
        task_id = _identifier(task["id"], f"{label}.id", InvalidDecisionLedgerError)
        if task_id in seen:
            raise InvalidDecisionLedgerError(f"duplicate change task id: {task_id}")
        seen.add(task_id)
        normalized.append(
            {
                "id": task_id,
                "description": _nonempty_string(
                    task["description"], f"{label}.description", InvalidDecisionLedgerError
                ),
                "acceptance_oracle": _nonempty_string(
                    task["acceptance_oracle"],
                    f"{label}.acceptance_oracle",
                    InvalidDecisionLedgerError,
                ),
                "repository_touchpoints": _normalize_touchpoints(
                    task["repository_touchpoints"],
                    slot,
                ),
            }
        )
    return normalized


def _validate_decision_trace(
    slot: Mapping[str, Any],
    findings: Sequence[ArtifactRevision],
    payload: Mapping[str, Any],
    error_type: type[RuntimeStoreError],
) -> None:
    if payload["status"] not in {"selected", "conditional"}:
        return
    finding_anchors = {anchor["ref"] for anchor in payload["anchors"] if anchor["kind"] == "finding"}
    if not findings or not finding_anchors:
        raise error_type("selected or conditional decision requires a supplied Finding Pack anchor")
    selected_option = payload["selected_option"]
    supported_options = {
        effect["option"]
        for finding in findings
        for effect in finding.payload.get("option_effects", ())
        if (
            isinstance(effect, Mapping) and effect.get("effect") == "supports" and isinstance(effect.get("option"), str)
        )
    }
    if selected_option not in supported_options:
        raise error_type("selected or conditional decision requires a Finding Pack support effect for selected_option")
    if slot.get("priority") != "P0":
        return
    if not payload["change_tasks"]:
        raise error_type("P0 selected or conditional decision requires at least one change task")


def _latest_artifact(artifacts: Sequence[ArtifactRevision], artifact_id: str, kind: str) -> ArtifactRevision | None:
    matches = [artifact for artifact in artifacts if artifact.id == artifact_id and artifact.kind == kind]
    return max(matches, key=lambda artifact: artifact.revision, default=None)


def _normalize_anchor(
    value: Any,
    label: str,
    allowed_kinds: set[str],
    error_type: type[RuntimeStoreError],
) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise error_type(f"{label}.anchor must be a mapping")
    _require_exact_keys(value, {"kind", "ref"}, f"{label}.anchor", error_type)
    return {
        "kind": _enum(value["kind"], f"{label}.anchor.kind", allowed_kinds, error_type),
        "ref": _nonempty_string(value["ref"], f"{label}.anchor.ref", error_type),
    }


def _validate_repository_anchor(
    value: str,
    slot: Mapping[str, Any],
    error_type: type[RuntimeStoreError],
) -> None:
    allowed = {
        f"{item.get('path')}:{item.get('symbol')}"
        for item in _mapping_sequence(
            slot.get("repository_touchpoints"),
            "slot repository_touchpoints",
            error_type,
        )
        if item.get("symbol") is not None
    }
    allowed.update(
        str(item.get("path"))
        for item in _mapping_sequence(
            slot.get("repository_touchpoints"),
            "slot repository_touchpoints",
            error_type,
        )
    )
    if value not in allowed:
        raise error_type("repository observation anchor is absent from the Decision Slot")


def _mapping_sequence(
    value: Any,
    label: str,
    error_type: type[RuntimeStoreError],
) -> list[Mapping[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise error_type(f"{label} must be a sequence of mappings")
    result: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise error_type(f"{label}[{index}] must be a mapping")
        result.append(item)
    return result


def _string_sequence(
    value: Any,
    label: str,
    *,
    allow_empty: bool = False,
    error_type: type[RuntimeStoreError] = InvalidDecisionLedgerError,
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise error_type(f"{label} must be a sequence of strings")
    result = tuple(_nonempty_string(item, label, error_type) for item in value)
    if not result and not allow_empty:
        raise error_type(f"{label} must not be empty")
    return result


def _identifier(value: Any, label: str, error_type: type[RuntimeStoreError]) -> str:
    try:
        return validate_identifier(value, label)
    except InvalidIdentifierError as error:
        raise error_type(str(error)) from error


def _enum(
    value: Any,
    label: str,
    allowed: set[str],
    error_type: type[RuntimeStoreError],
) -> str:
    normalized = _nonempty_string(value, label, error_type)
    if normalized not in allowed:
        raise error_type(f"{label} is unsupported: {normalized}")
    return normalized


def _nonempty_string(value: Any, label: str, error_type: type[RuntimeStoreError]) -> str:
    if not isinstance(value, str) or not value.strip():
        raise error_type(f"{label} must be a nonempty string")
    return value


def _require_exact_keys(
    value: Mapping[str, Any],
    expected: set[str],
    label: str,
    error_type: type[RuntimeStoreError],
) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise error_type(f"{label} has unexpected keys; missing={missing}, extra={extra}")
