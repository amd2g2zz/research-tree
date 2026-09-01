"""Typed writers for canonical completion inputs.

The generic ledger append surface remains available for non-authoritative
artifacts.  Only this module can ask the ledger to create a completion-input
registration alongside a validated artifact revision.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

from .acceptance import DeliveryAcceptance, delivery_pair_digest
from .domain import (
    ArtifactRef,
    ArtifactRevision,
    DataIntegrityError,
    canonical_json_bytes,
    thaw_json,
    validate_identifier,
)
from .run_ledger import LedgerIntegrityError, RunLedger


class CompletionInputError(LedgerIntegrityError):
    """Raised when a proposed canonical completion input is not admissible."""


GOAL_SATISFACTION_ROLE = "goal_satisfaction"
GOAL_SATISFACTION_KIND = "goal-satisfaction"
GOAL_SATISFACTION_VERDICTS = ("satisfied", "partial", "unmet", "waived")
# Ledger artifact kinds a goal_satisfaction verdict may cite as evidence. The
# PRD also lists "experiment result"; no such artifact kind exists in the
# runtime, so the set covers the three existing evidence classes.
GOAL_SATISFACTION_EVIDENCE_KINDS = frozenset(
    {"finding-pack", "slot-closure-assessment", "goal-contribution-assessment"}
)


def validate_goal_satisfaction_payload(payload: Any) -> dict[str, Any]:
    """Validate one per-oracle goal_satisfaction payload and return its normalized fields.

    Every field violation raises ``CompletionInputError`` naming the field, so a
    rejected registration always says which key was inadmissible.
    """

    required = {"schema", "oracle_id", "verdict", "evidence_refs", "waiver_reason"}
    if not isinstance(payload, Mapping):
        raise CompletionInputError("goal_satisfaction payload must be an object")
    if set(payload) != required:
        raise CompletionInputError("goal_satisfaction payload fields do not match schema")
    if payload["schema"] != 1:
        raise CompletionInputError("goal_satisfaction payload schema must be 1")
    oracle_id = payload["oracle_id"]
    if not isinstance(oracle_id, str) or not oracle_id.strip():
        raise CompletionInputError("goal_satisfaction oracle_id must be a non-empty string")
    verdict = payload["verdict"]
    if verdict not in GOAL_SATISFACTION_VERDICTS:
        raise CompletionInputError("goal_satisfaction verdict must be one of: satisfied, partial, unmet, waived")
    refs_value = payload["evidence_refs"]
    if not isinstance(refs_value, (list, tuple)) or isinstance(refs_value, (str, bytes)):
        raise CompletionInputError("goal_satisfaction evidence_refs must be a sequence of artifact references")
    evidence_refs: list[ArtifactRef] = []
    for value in refs_value:
        try:
            evidence_refs.append(ArtifactRef.from_dict(value))
        except (DataIntegrityError, TypeError, ValueError) as error:
            raise CompletionInputError("goal_satisfaction evidence_refs entries must be artifact references") from error
    waiver_reason = payload["waiver_reason"]
    if waiver_reason is not None and (not isinstance(waiver_reason, str) or not waiver_reason.strip()):
        raise CompletionInputError("goal_satisfaction waiver_reason must be a non-empty string or null")
    if verdict == "waived":
        if waiver_reason is None:
            raise CompletionInputError("waived verdict requires a non-empty waiver_reason")
    elif waiver_reason is not None:
        raise CompletionInputError(f"{verdict} verdict requires waiver_reason: null")
    if verdict in {"satisfied", "partial"} and not evidence_refs:
        raise CompletionInputError(f"{verdict} verdict requires non-empty evidence_refs")
    return {
        "oracle_id": oracle_id,
        "verdict": verdict,
        "evidence_refs": tuple(evidence_refs),
        "waiver_reason": waiver_reason,
    }


class CompletionInputRegistrar:
    """Write and register one typed completion input in one ledger transaction."""

    def __init__(self, ledger: RunLedger) -> None:
        if not isinstance(ledger, RunLedger):
            raise CompletionInputError("completion inputs require a RunLedger")
        self.ledger = ledger

    def registered_inputs(self, round_id: str) -> tuple[ArtifactRevision, ...]:
        return self.ledger.list_completion_inputs(round_id)

    def write_delivery_pair(
        self,
        *,
        round_id: str,
        technical_package_id: str,
        human_report_id: str,
        technical_payload: Mapping[str, Any],
        human_payload: Mapping[str, Any],
        technical_parent_refs: Sequence[ArtifactRef],
        human_parent_refs: Sequence[ArtifactRef],
        expected_revision: int,
    ) -> tuple[ArtifactRevision, ArtifactRevision]:
        """Atomically register one canonical technical/human delivery pair."""

        from .delivery import HUMAN_RESEARCH_REPORT_KIND, TECHNICAL_RESEARCH_PACKAGE_KIND

        round_id = validate_identifier(round_id, "round_id")
        technical_package_id = validate_identifier(technical_package_id, "technical_package_id")
        human_report_id = validate_identifier(human_report_id, "human_report_id")
        if technical_package_id == human_report_id:
            raise CompletionInputError("delivery pair artifact ids must be distinct")
        _delivery_payload(technical_payload, TECHNICAL_RESEARCH_PACKAGE_KIND)
        _delivery_payload(human_payload, HUMAN_RESEARCH_REPORT_KIND)
        technical_parents = _refs(technical_parent_refs)
        human_parents = _refs(human_parent_refs)
        snapshot = self.ledger.load_run(round_id)
        technical_ref = ArtifactRef(round_id, technical_package_id, _next_revision(snapshot, technical_package_id))
        expected_human_ref = ArtifactRef(round_id, human_report_id, _next_revision(snapshot, human_report_id))
        human_package_ref = human_payload.get("technical_package_ref")
        if not isinstance(human_package_ref, Mapping) or ArtifactRef.from_dict(human_package_ref) != technical_ref:
            raise CompletionInputError("human delivery must bind the exact technical package revision")
        if technical_ref not in human_parents:
            raise CompletionInputError("human delivery parent lineage must include the exact technical package")
        pair_digest = delivery_pair_digest(
            round_id, _revision_token(technical_ref), _revision_token(expected_human_ref)
        )
        appended = self.ledger.append_completion_input_batch(
            round_id,
            (
                (
                    technical_package_id,
                    "technical_delivery",
                    TECHNICAL_RESEARCH_PACKAGE_KIND,
                    dict(technical_payload),
                    technical_parents,
                    "canonical-delivery-compiler-v1",
                    {"pair_digest": pair_digest, "surface": "technical"},
                ),
                (
                    human_report_id,
                    "human_delivery",
                    HUMAN_RESEARCH_REPORT_KIND,
                    dict(human_payload),
                    human_parents,
                    "canonical-delivery-compiler-v1",
                    {"pair_digest": pair_digest, "surface": "human"},
                ),
            ),
            expected_revision=expected_revision,
        )
        if len(appended) != 2:
            raise CompletionInputError("canonical delivery registration must append exactly two surfaces")
        return appended[0], appended[1]

    def write_delivery_acceptance(
        self,
        *,
        round_id: str,
        technical_package: ArtifactRevision,
        human_research_report: ArtifactRevision,
        acceptance: DeliveryAcceptance | Mapping[str, Any],
        expected_revision: int,
    ) -> ArtifactRevision:
        """Register a human acceptance bound to one current delivery pair."""

        from .acceptance import CANONICAL_HUMAN_KIND, CANONICAL_TECHNICAL_KIND

        round_id = validate_identifier(round_id, "round_id")
        if not isinstance(technical_package, ArtifactRevision) or not isinstance(
            human_research_report, ArtifactRevision
        ):
            raise CompletionInputError("acceptance requires ArtifactRevision delivery surfaces")
        if isinstance(acceptance, Mapping):
            acceptance = _acceptance_from_mapping(acceptance)
        if not isinstance(acceptance, DeliveryAcceptance):
            raise CompletionInputError("acceptance must be a DeliveryAcceptance")
        technical_ref = ArtifactRef(technical_package.round_id, technical_package.id, technical_package.revision)
        human_ref = ArtifactRef(
            human_research_report.round_id, human_research_report.id, human_research_report.revision
        )
        if (
            acceptance.run_id != round_id
            or technical_package.round_id != round_id
            or human_research_report.round_id != round_id
        ):
            raise CompletionInputError("acceptance delivery lineage belongs to another run")
        if technical_package.kind != CANONICAL_TECHNICAL_KIND or human_research_report.kind != CANONICAL_HUMAN_KIND:
            raise CompletionInputError("acceptance requires canonical delivery kinds")
        if technical_ref == human_ref or technical_ref not in human_research_report.parent_refs:
            raise CompletionInputError("acceptance delivery pair lineage is not exact")
        expected_technical_revision = _delivery_revision_value(technical_package, "technical_revision", technical_ref)
        expected_human_revision = _delivery_revision_value(human_research_report, "human_revision", human_ref)
        if (
            acceptance.technical_revision != expected_technical_revision
            or acceptance.human_revision != expected_human_revision
        ):
            raise CompletionInputError("acceptance does not bind the exact delivery revisions")
        if not (acceptance.actor == "human" or acceptance.actor.startswith("human-")):
            raise CompletionInputError("delivery acceptance actor must be human")
        expected_display_digest = delivery_pair_digest(
            round_id, acceptance.technical_revision, acceptance.human_revision
        )
        if acceptance.displayed_digest != expected_display_digest:
            raise CompletionInputError("acceptance displayed digest is stale")
        expected_manifest_digest = delivery_manifest_digest(technical_package, human_research_report)
        if acceptance.manifest_digest != expected_manifest_digest:
            raise CompletionInputError("acceptance manifest digest does not match the exact pair")
        return self._write(
            round_id=round_id,
            artifact_id=acceptance.acceptance_id,
            role="acceptance",
            kind="delivery-acceptance",
            payload=acceptance.to_dict(),
            parent_refs=(technical_ref, human_ref),
            issuer="human-delivery-acceptance-v1",
            issuer_evidence={
                "actor": acceptance.actor,
                "pair_digest": acceptance.displayed_digest,
                "manifest_digest": acceptance.manifest_digest,
            },
            expected_revision=expected_revision,
        )

    write_acceptance = write_delivery_acceptance

    def write_closure(
        self,
        *,
        round_id: str,
        assessment_id: str,
        payload: Mapping[str, Any],
        parent_refs: Sequence[ArtifactRef],
        core_evaluator_id: str,
        expected_revision: int,
    ) -> ArtifactRevision:
        from .closure import ASSESSMENT_KIND, SlotClosureAssessment

        assessment = SlotClosureAssessment.from_dict(payload)
        parents = _refs(parent_refs)
        if (
            assessment.status != "passed"
            or assessment.evaluator_id != core_evaluator_id
            or assessment.assessment_id != assessment_id
            or tuple(assessment.parent_refs) != parents
        ):
            raise CompletionInputError("closure assessment issuer or lineage is not canonical")
        return self._write(
            round_id=round_id,
            artifact_id=assessment_id,
            role="closure",
            kind=ASSESSMENT_KIND,
            payload=payload,
            parent_refs=parents,
            issuer=assessment.evaluator_id,
            issuer_evidence={"closure_token": assessment.closure_token, "token_digest": assessment.token_digest},
            expected_revision=expected_revision,
        )

    def write_insight(
        self,
        *,
        round_id: str,
        insight_id: str,
        payload: Mapping[str, Any],
        parent_refs: Sequence[ArtifactRef],
        expected_revision: int,
    ) -> ArtifactRevision:
        from .insights import validate_insight_digest

        validate_insight_digest(payload)
        parents = _refs(parent_refs)
        expected_parent_ids = {f"finding:{reference.artifact_id}" for reference in parents}
        actual_parent_ids = set(payload["parent_refs"])
        if expected_parent_ids != actual_parent_ids:
            raise CompletionInputError("insight digest parent lineage is not exact")
        return self._write(
            round_id=round_id,
            artifact_id=insight_id,
            role="insight",
            kind="insight-digest",
            payload=payload,
            parent_refs=parents,
            issuer=str(payload["producer_version"]),
            issuer_evidence={"digest_id": payload["digest_id"]},
            expected_revision=expected_revision,
        )

    def write_readiness(
        self,
        *,
        round_id: str,
        readiness_id: str,
        payload: Mapping[str, Any],
        parent_refs: Sequence[ArtifactRef],
        expected_revision: int,
    ) -> ArtifactRevision:
        from .readiness import READINESS_RECORD_KIND, validate_readiness_record_payload

        validate_readiness_record_payload(payload)
        parents = _refs(parent_refs)
        expected = {
            ArtifactRef.from_dict(payload["technical_package_ref"]),
            *(ArtifactRef.from_dict(item) for item in payload["source_refs"]),
        }
        if set(parents) != expected:
            raise CompletionInputError("readiness record parent lineage is not exact")
        return self._write(
            round_id=round_id,
            artifact_id=readiness_id,
            role="readiness",
            kind=READINESS_RECORD_KIND,
            payload=payload,
            parent_refs=parents,
            issuer="canonical-readiness-verifier-v1",
            issuer_evidence={"payload_digest": _digest(payload)},
            expected_revision=expected_revision,
        )

    def write_goal_satisfaction(
        self,
        *,
        round_id: str,
        registration_id: str,
        oracle_id: str,
        verdict: str,
        evidence_refs: Sequence[ArtifactRef] = (),
        waiver_reason: str | None = None,
        expected_revision: int,
    ) -> ArtifactRevision:
        """Register one per-oracle goal_satisfaction completion input (issuer: coordinator).

        The payload's ``evidence_refs`` are bound to the registration's exact
        parent lineage, so a satisfied/partial verdict can never cite evidence
        the ledger does not hold.
        """

        round_id = validate_identifier(round_id, "round_id")
        registration_id = validate_identifier(registration_id, "registration_id")
        payload = {
            "schema": 1,
            "oracle_id": oracle_id,
            "verdict": verdict,
            "evidence_refs": [ref.to_dict() for ref in evidence_refs],
            "waiver_reason": waiver_reason,
        }
        validated = validate_goal_satisfaction_payload(payload)
        parents = _refs(validated["evidence_refs"])
        return self._write(
            round_id=round_id,
            artifact_id=registration_id,
            role=GOAL_SATISFACTION_ROLE,
            kind=GOAL_SATISFACTION_KIND,
            payload=payload,
            parent_refs=parents,
            issuer="coordinator",
            issuer_evidence={"oracle_id": validated["oracle_id"], "verdict": validated["verdict"]},
            expected_revision=expected_revision,
        )

    def write_alignment_verification(
        self,
        *,
        round_id: str,
        verification_id: str,
        payload: Mapping[str, Any],
        expected_revision: int,
    ) -> ArtifactRevision:
        """Register one independent alignment verification (issue #462).

        The subagent-produced artifact binds its parent lineage to the exact
        projection revision the verifier read, so a display gate can bind the
        verification to the projection content through the authority
        fingerprint carried in the payload.
        """

        from .independent_review import (
            ALIGNMENT_VERIFICATION_KIND,
            ALIGNMENT_VERIFICATION_ROLE,
            INDEPENDENT_REVIEW_ISSUER,
            IndependentReviewError,
            validate_alignment_verification_payload,
        )

        round_id = validate_identifier(round_id, "round_id")
        verification_id = validate_identifier(verification_id, "verification_id")
        try:
            validated = validate_alignment_verification_payload(thaw_json(dict(payload)))
        except IndependentReviewError as error:
            raise CompletionInputError(str(error)) from error
        if validated["id"] != verification_id:
            raise CompletionInputError("alignment verification payload id does not match verification_id")
        if validated["round_id"] != round_id:
            raise CompletionInputError("alignment verification payload round_id does not match round_id")
        return self._write(
            round_id=round_id,
            artifact_id=verification_id,
            role=ALIGNMENT_VERIFICATION_ROLE,
            kind=ALIGNMENT_VERIFICATION_KIND,
            payload=thaw_json(dict(payload)),
            parent_refs=(validated["projection_ref"],),
            issuer=INDEPENDENT_REVIEW_ISSUER,
            issuer_evidence={
                "verifier_identity": validated["verifier_identity"],
                "session_context": validated["session_context"],
                "authority_fingerprint": validated["authority_fingerprint"],
            },
            expected_revision=expected_revision,
        )

    def write_delivery_review(
        self,
        *,
        round_id: str,
        review_id: str,
        payload: Mapping[str, Any],
        expected_revision: int,
    ) -> ArtifactRevision:
        """Register one independent delivery review (issue #462).

        The subagent-produced artifact binds its parent lineage to the exact
        evidence custody references (finding packs) the verifier read, so the
        delivery gate can re-verify custody at completion time.
        """

        from .independent_review import (
            DELIVERY_REVIEW_KIND,
            DELIVERY_REVIEW_ROLE,
            INDEPENDENT_REVIEW_ISSUER,
            IndependentReviewError,
            validate_delivery_review_payload,
        )

        round_id = validate_identifier(round_id, "round_id")
        review_id = validate_identifier(review_id, "review_id")
        try:
            validated = validate_delivery_review_payload(thaw_json(dict(payload)))
        except IndependentReviewError as error:
            raise CompletionInputError(str(error)) from error
        if validated["id"] != review_id:
            raise CompletionInputError("delivery review payload id does not match review_id")
        if validated["round_id"] != round_id:
            raise CompletionInputError("delivery review payload round_id does not match round_id")
        parents = _refs(validated["evidence_custody"])
        return self._write(
            round_id=round_id,
            artifact_id=review_id,
            role=DELIVERY_REVIEW_ROLE,
            kind=DELIVERY_REVIEW_KIND,
            payload=thaw_json(dict(payload)),
            parent_refs=parents,
            issuer=INDEPENDENT_REVIEW_ISSUER,
            issuer_evidence={
                "verifier_identity": validated["verifier_identity"],
                "session_context": validated["session_context"],
                "verdict": validated["verdict"],
            },
            expected_revision=expected_revision,
        )

    def write_evaluation(
        self,
        *,
        round_id: str,
        evaluation_id: str,
        payload: Mapping[str, Any],
        parent_refs: Sequence[ArtifactRef],
        expected_revision: int,
    ) -> ArtifactRevision:
        from .evaluation import BLUEPRINT_EVALUATION_KIND, validate_blueprint_evaluation_payload

        validate_blueprint_evaluation_payload(payload)
        parents = _refs(parent_refs)
        expected = {
            ArtifactRef.from_dict(payload["technical_package_ref"]),
            ArtifactRef.from_dict(payload["readiness_record_ref"]),
        }
        if set(parents) != expected:
            raise CompletionInputError("evaluation parent lineage is not exact")
        return self._write(
            round_id=round_id,
            artifact_id=evaluation_id,
            role="evaluation",
            kind=BLUEPRINT_EVALUATION_KIND,
            payload=payload,
            parent_refs=parents,
            issuer="independent-evaluation-suite-v1",
            issuer_evidence={"case_id": payload["case"]["id"], "payload_digest": _digest(payload)},
            expected_revision=expected_revision,
        )

    def _write(
        self,
        *,
        round_id: str,
        artifact_id: str,
        role: str,
        kind: str,
        payload: Mapping[str, Any],
        parent_refs: tuple[ArtifactRef, ...],
        issuer: str,
        issuer_evidence: Mapping[str, Any],
        expected_revision: int,
    ) -> ArtifactRevision:
        if not isinstance(issuer, str) or not issuer.strip():
            raise CompletionInputError("completion input issuer must be non-empty")
        return self.ledger.append_completion_input(
            round_id,
            artifact_id,
            role,
            kind,
            dict(payload),
            parent_refs=parent_refs,
            issuer=issuer,
            issuer_evidence=dict(issuer_evidence),
            expected_revision=expected_revision,
        )


def _refs(values: Sequence[ArtifactRef]) -> tuple[ArtifactRef, ...]:
    result = tuple(values)
    if len(set(result)) != len(result) or any(not isinstance(value, ArtifactRef) for value in result):
        raise CompletionInputError("completion input parents must be distinct ArtifactRef values")
    return result


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def delivery_manifest_digest(technical: ArtifactRevision, human: ArtifactRevision) -> str:
    """Return the immutable manifest digest used by the registration boundary."""

    technical_manifest = (
        thaw_json(technical.payload.get("manifest"))
        if isinstance(technical.payload, Mapping) and technical.payload.get("manifest") is not None
        else None
    )
    human_manifest = (
        thaw_json(human.payload.get("manifest"))
        if isinstance(human.payload, Mapping) and human.payload.get("manifest") is not None
        else None
    )
    if technical_manifest is not None or human_manifest is not None:
        if (
            technical_manifest is None
            or human_manifest is None
            or canonical_json_bytes(technical_manifest) != canonical_json_bytes(human_manifest)
        ):
            raise CompletionInputError("delivery manifests must be identical")
        return _digest(technical_manifest)
    return _digest(
        {
            "technical": {
                "ref": ArtifactRef(technical.round_id, technical.id, technical.revision).to_dict(),
                "hash": technical.content_hash,
            },
            "human": {
                "ref": ArtifactRef(human.round_id, human.id, human.revision).to_dict(),
                "hash": human.content_hash,
            },
        }
    )


def _delivery_payload(payload: Mapping[str, Any], kind: str) -> None:
    if not isinstance(payload, Mapping) or not isinstance(payload.get("document"), Mapping):
        raise CompletionInputError(f"{kind} payload document is malformed")
    if not isinstance(payload.get("markdown"), str) or not payload["markdown"].strip():
        raise CompletionInputError(f"{kind} payload markdown is malformed")
    if kind == "human-research-report":
        reference = payload.get("technical_package_ref")
        if not isinstance(reference, Mapping):
            raise CompletionInputError("human-research-report payload lacks technical_package_ref")


def _next_revision(snapshot, artifact_id: str) -> int:
    revisions = [item.revision for item in snapshot.artifacts if item.id == artifact_id]
    return max(revisions, default=0) + 1


def _revision_token(reference: ArtifactRef) -> str:
    return f"{reference.artifact_id}@{reference.revision}"


def _delivery_revision_value(artifact: ArtifactRevision, field: str, reference: ArtifactRef) -> str:
    payload = artifact.payload
    manifest = payload.get("manifest") if isinstance(payload, Mapping) else None
    value = manifest.get(field) if isinstance(manifest, Mapping) else None
    if isinstance(value, str) and value.strip():
        return value
    return _revision_token(reference)


def _acceptance_from_mapping(value: Mapping[str, Any]) -> DeliveryAcceptance:
    required = {
        "acceptance_id",
        "run_id",
        "technical_revision",
        "human_revision",
        "displayed_digest",
        "manifest_digest",
        "feedback",
    }
    if not required <= set(value):
        raise CompletionInputError("acceptance payload is incomplete")
    return DeliveryAcceptance.create(
        str(value["acceptance_id"]),
        str(value["run_id"]),
        str(value["technical_revision"]),
        str(value["human_revision"]),
        str(value["displayed_digest"]),
        str(value["manifest_digest"]),
        value["feedback"],
        decision=str(value.get("decision", "accepted")),
        actor=str(value.get("actor", "human")),
    )


__all__ = [
    "CompletionInputError",
    "CompletionInputRegistrar",
    "GOAL_SATISFACTION_EVIDENCE_KINDS",
    "GOAL_SATISFACTION_KIND",
    "GOAL_SATISFACTION_ROLE",
    "GOAL_SATISFACTION_VERDICTS",
    "delivery_manifest_digest",
    "validate_goal_satisfaction_payload",
]
