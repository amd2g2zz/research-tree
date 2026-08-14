"""Typed admission for canonical completion inputs."""

from __future__ import annotations

from typing import Callable, Mapping

from .closure import ASSESSMENT_KIND, SlotClosureAssessor
from .domain import ArtifactRef, ArtifactRevision, RuntimeStoreError, thaw_json, validate_identifier
from .evaluation import BLUEPRINT_EVALUATION_KIND, validate_blueprint_evaluation_payload
from .insights import validate_insight_digest
from .readiness import READINESS_RECORD_KIND, validate_readiness_record_payload
from .run_ledger import RunLedger


CANONICAL_COMPLETION_INPUT_KIND = "canonical-completion-input"
CANONICAL_COMPLETION_INPUT_ISSUER_KIND = "canonical-completion-input-issuer"


class CompletionInputRegistrationError(RuntimeStoreError):
    """Raised when an artifact cannot enter canonical completion registration."""


_ROLE_KINDS = {
    "closure": ASSESSMENT_KIND,
    "insight": "insight-digest",
    "readiness": READINESS_RECORD_KIND,
    "evaluation": BLUEPRINT_EVALUATION_KIND,
}


class CanonicalCompletionInputRegistrar:
    """Validate and register exact role artifacts through the reserved ledger path."""

    def __init__(self, ledger: RunLedger, *, closure_assessor: SlotClosureAssessor | None = None) -> None:
        if not isinstance(ledger, RunLedger):
            raise CompletionInputRegistrationError("registrar requires a RunLedger")
        self.ledger = ledger
        self.closure_assessor = closure_assessor

    def register(
        self,
        *,
        run_id: str,
        role: str,
        input_artifact: ArtifactRevision,
        issuer_id: str,
        registration_id: str,
        expected_revision: int,
    ) -> ArtifactRevision:
        run_id = validate_identifier(run_id, "run_id")
        role = _role(role)
        issuer_id = validate_identifier(issuer_id, "issuer_id")
        registration_id = validate_identifier(registration_id, "registration_id")
        input_ref = _exact_current_input(self.ledger, run_id, role, input_artifact)
        _validate_role(role, input_artifact, self.closure_assessor)
        payload = {
            "schema_version": 1,
            "role": role,
            "input_ref": input_ref.to_dict(),
            "issuer_id": issuer_id,
        }
        existing = _existing_registration(self.ledger, run_id, registration_id, payload)
        if existing is not None:
            return existing
        issuer, registration = self.ledger.append_canonical_completion_registration(
            run_id,
            issuer_id=issuer_id,
            issuer_payload={
                "schema_version": 1,
                "role": role,
                "input_ref": input_ref.to_dict(),
                "issuer_id": issuer_id,
            },
            registration_id=registration_id,
            registration_payload=payload,
            input_ref=input_ref,
            expected_revision=expected_revision,
        )
        if (
            issuer.kind != CANONICAL_COMPLETION_INPUT_ISSUER_KIND
            or registration.kind != CANONICAL_COMPLETION_INPUT_KIND
        ):
            raise CompletionInputRegistrationError("ledger returned invalid completion registration")
        return registration


def _role(value: str) -> str:
    if not isinstance(value, str) or value not in _ROLE_KINDS:
        raise CompletionInputRegistrationError("unsupported completion input role")
    return value


def _exact_current_input(
    ledger: RunLedger,
    run_id: str,
    role: str,
    artifact: ArtifactRevision,
) -> ArtifactRef:
    if not isinstance(artifact, ArtifactRevision) or artifact.round_id != run_id:
        raise CompletionInputRegistrationError("completion input must belong to the target run")
    if artifact.kind != _ROLE_KINDS[role]:
        raise CompletionInputRegistrationError("completion input kind does not match its role")
    reference = ArtifactRef(run_id, artifact.id, artifact.revision)
    if ledger.get_artifact(reference) != artifact or not ledger.is_latest_artifact(reference):
        raise CompletionInputRegistrationError("completion input must be an exact current ledger artifact")
    return reference


def _validate_role(
    role: str,
    artifact: ArtifactRevision,
    closure_assessor: SlotClosureAssessor | None,
) -> None:
    try:
        if role == "closure":
            if closure_assessor is None or not closure_assessor.is_current(artifact):
                raise CompletionInputRegistrationError("closure input is not current")
            return
        payload = thaw_json(artifact.payload)
        validators: Mapping[str, Callable[[Mapping[str, object]], None]] = {
            "insight": validate_insight_digest,
            "readiness": validate_readiness_record_payload,
            "evaluation": validate_blueprint_evaluation_payload,
        }
        validators[role](payload)
    except (KeyError, RuntimeStoreError, TypeError, ValueError) as error:
        if isinstance(error, CompletionInputRegistrationError):
            raise
        raise CompletionInputRegistrationError("invalid completion input") from error


def _existing_registration(
    ledger: RunLedger,
    run_id: str,
    registration_id: str,
    payload: Mapping[str, object],
) -> ArtifactRevision | None:
    for item in ledger.load_run(run_id).artifacts:
        if item.id != registration_id or item.kind != CANONICAL_COMPLETION_INPUT_KIND:
            continue
        if thaw_json(item.payload) == dict(payload):
            return item
        raise CompletionInputRegistrationError("registration id is already bound to different input")
    return None


__all__ = [
    "CANONICAL_COMPLETION_INPUT_KIND",
    "CANONICAL_COMPLETION_INPUT_ISSUER_KIND",
    "CanonicalCompletionInputRegistrar",
    "CompletionInputRegistrationError",
]
