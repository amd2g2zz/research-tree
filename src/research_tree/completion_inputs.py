"""Typed writers for canonical completion inputs.

The generic ledger append surface remains available for non-authoritative
artifacts.  Only this module can ask the ledger to create a completion-input
registration alongside a validated artifact revision.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

from .domain import ArtifactRef, ArtifactRevision, canonical_json_bytes
from .run_ledger import LedgerIntegrityError, RunLedger


class CompletionInputError(LedgerIntegrityError):
    """Raised when a proposed canonical completion input is not admissible."""


class CompletionInputRegistrar:
    """Write and register one typed completion input in one ledger transaction."""

    def __init__(self, ledger: RunLedger) -> None:
        if not isinstance(ledger, RunLedger):
            raise CompletionInputError("completion inputs require a RunLedger")
        self.ledger = ledger

    def registered_inputs(self, round_id: str) -> tuple[ArtifactRevision, ...]:
        return self.ledger.list_completion_inputs(round_id)

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


__all__ = ["CompletionInputError", "CompletionInputRegistrar"]
