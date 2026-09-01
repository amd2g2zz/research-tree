"""Payload contracts for independent subagent review artifacts (issue #462).

Issue #292 gate 3 requires that a required review records distinct execution
identities, session/context lineage, evidence custody, oracle custody, and
authority; self-review cannot satisfy an independent gate. Two artifact kinds
carry that contract:

- ``alignment-verification`` (display gate): a fresh-context subagent reads the
  original conversation plus the projection draft and restates its independent
  understanding of the outcome, scope, authority, and every success oracle.
  The restatement binds to the projection content through the #450 authority
  fingerprint, so any authority-field change requires a new verification.
- ``delivery-review`` (delivery gate): a fresh subagent reads only the finding
  packs and the confirmed projection's oracles — never the main agent's
  summary — and records an independent per-oracle verdict with evidence
  custody, plus an overall verdict.

Both artifacts are produced host-side and persisted through the typed
completion-input channel (``CompletionInputRegistrar``). The identity fields
mirror the session identifiers the lifecycle hook already records host-side:
``verifier_identity`` is the subagent's session/execution identity and
``session_context`` is the session/context lineage the review is bound to
(the dispatching main session). An artifact without both identities is not
independent and its gate rejects fail-closed.

Issue #471 restates the independence threat model: the gates judge a review
against its registration's durable ``issuer`` principal — an HMAC of the
declared identity pair keyed with a secret per-run salt the ledger holds — so
the principal is tamper-evident, cannot be minted from public material by
out-of-process or cross-session adversaries, and never matches the
coordinator's own principal. This is channel separation and
coordinator-principal exclusion, NOT proof of subagent execution: a
same-process adversary with full ledger access can read the salt, which is
the tracked gate-3 boundary (unsupervised same-process authorization).
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any, Mapping, Sequence

from .completion_inputs import CompletionInputError
from .domain import ArtifactRef, canonical_json_bytes

ALIGNMENT_VERIFICATION_KIND = "alignment-verification"
DELIVERY_REVIEW_KIND = "delivery-review"
ALIGNMENT_VERIFICATION_ROLE = "alignment_verification"
DELIVERY_REVIEW_ROLE = "delivery_review"
INDEPENDENT_REVIEW_ISSUER = "independent-subagent-verifier-v1"
# Per-oracle and overall independent verdicts. ``unmet`` blocks the delivery
# gate; the verdict is an independent quality judgment and stays independent of
# the runtime's goal_satisfaction evidence-chain verdict (#443).
DELIVERY_REVIEW_VERDICTS = ("satisfied", "partial", "unmet")

_MAX_IDENTITY_LENGTH = 512


class IndependentReviewError(CompletionInputError):
    """Raised when an independent review payload is not admissible."""


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IndependentReviewError(f"{label} must be a non-empty string")
    return value


def verification_principal(salt: str, verifier_identity: str, session_context: str) -> str:
    """Derive the durable ledger principal a review's identity pair binds to (#471).

    The principal is an HMAC-SHA256 over the declared identity pair, keyed with
    a per-run secret salt the ledger generates at run creation and hands out
    only through the registrar/gate channel (:meth:`RunLedger.
    verification_principal`). Because the salt is secret, an out-of-process or
    cross-session adversary cannot mint a principal from public material.

    Threat model (restated per review A HIGH-2 / review B): this is
    **tamper-evidence + channel separation + coordinator-principal exclusion**,
    not proof of execution. The residual — a same-process adversary with full
    ledger access can read the salt and mint a matching principal — is the
    tracked gate-3 boundary (unsupervised same-process authorization); closing
    it requires a subagent execution record the registrar can attribute, which
    does not exist yet. Within the model, a principal cannot be swapped or
    re-used across identity pairs after the fact, and a registration is
    append-once.
    """

    material = {
        "issuer": INDEPENDENT_REVIEW_ISSUER,
        "session_context": session_context.strip(),
        "verifier_identity": verifier_identity.strip(),
    }
    digest = hmac.new(salt.encode("utf-8"), canonical_json_bytes(material), hashlib.sha256).hexdigest()
    return f"{INDEPENDENT_REVIEW_ISSUER}@{digest}"


def _identity_pair_wellformed(verifier_identity: Any, session_context: Any) -> bool:
    """Fail-closed checks shared by both identity predicates (#462 + #471)."""

    from .completion_inputs import COORDINATOR_ISSUER

    for value in (verifier_identity, session_context):
        if not isinstance(value, str) or not value.strip() or len(value) > _MAX_IDENTITY_LENGTH:
            return False
    if verifier_identity.strip() == session_context.strip():
        return False
    # The coordinator principal can never be an independent verifier identity:
    # a review declaring it (under any rename of the pair) is self-issuance.
    if verifier_identity.strip() == COORDINATOR_ISSUER or session_context.strip() == COORDINATOR_ISSUER:
        return False
    return True


def verify_identity_independent(verifier_identity: Any, session_context: Any) -> bool:
    """Return whether a review's identities are well-formed and self-distinct.

    #462 compatibility predicate (two arguments, no principal). It does NOT
    establish production independence — with #471 the production gates use
    :func:`verify_independent_review_principal`, which requires the durable
    write-time principal. Keeping this two-argument form preserves the #462
    caller contract unchanged.
    """

    return _identity_pair_wellformed(verifier_identity, session_context)


def verify_independent_review_principal(
    verifier_identity: Any,
    session_context: Any,
    *,
    issuer: Any,
    principal: Any,
) -> bool:
    """Return whether a review registration is structurally independent (#471).

    The production display/delivery predicate. ``issuer`` (the registration's
    durable ledger principal) and ``principal`` (the expected binding the gate
    recomputed through the ledger's secret run salt) are REQUIRED keywords: a
    call site that cannot supply them fails closed rather than open, so a gate
    lookup miss can never pass as independent.

    Independence holds only when the identity pair is well-formed and
    self-distinct, does not claim the coordinator principal, and the durable
    ``issuer`` equals the recomputed ``principal`` binding.
    """

    if not isinstance(issuer, str) or not issuer:
        return False
    if not isinstance(principal, str) or not principal:
        return False
    if not _identity_pair_wellformed(verifier_identity, session_context):
        return False
    return issuer == principal


def validate_alignment_verification_payload(payload: Any) -> dict[str, Any]:
    """Validate one alignment-verification payload and return its normalized fields.

    Every violation raises ``IndependentReviewError`` naming the field.
    """

    required = {
        "schema",
        "id",
        "round_id",
        "projection_ref",
        "authority_fingerprint",
        "verifier_identity",
        "session_context",
        "understood",
        "discrepancies",
    }
    if not isinstance(payload, Mapping):
        raise IndependentReviewError("alignment verification payload must be an object")
    if set(payload) != required:
        raise IndependentReviewError("alignment verification payload fields do not match schema")
    if payload["schema"] != 1:
        raise IndependentReviewError("alignment verification payload schema must be 1")
    artifact_id = _text(payload["id"], "alignment verification id")
    round_id = _text(payload["round_id"], "alignment verification round_id")
    try:
        projection_ref = ArtifactRef.from_dict(payload["projection_ref"])
    except (TypeError, ValueError) as error:
        raise IndependentReviewError("alignment verification projection_ref must be an artifact reference") from error
    fingerprint = payload["authority_fingerprint"]
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        raise IndependentReviewError("alignment verification authority_fingerprint must be a SHA-256 hex digest")
    verifier_identity = _text(payload["verifier_identity"], "alignment verification verifier_identity")
    session_context = _text(payload["session_context"], "alignment verification session_context")
    understood = payload["understood"]
    if not isinstance(understood, Mapping) or set(understood) != {"outcome", "scope", "authority", "success_oracles"}:
        raise IndependentReviewError(
            "alignment verification understood must restate outcome, scope, authority, and success_oracles"
        )
    for field in ("outcome", "scope", "authority"):
        _text(understood[field], f"alignment verification understood.{field}")
    oracles = understood["success_oracles"]
    if not isinstance(oracles, Sequence) or isinstance(oracles, (str, bytes)) or not oracles:
        raise IndependentReviewError("alignment verification understood.success_oracles must be a non-empty sequence")
    oracle_ids: list[str] = []
    for index, oracle in enumerate(oracles):
        if not isinstance(oracle, Mapping) or set(oracle) != {"id", "understanding"}:
            raise IndependentReviewError(
                f"alignment verification understood.success_oracles[{index}] must carry id and understanding"
            )
        oracle_id = _text(oracle["id"], f"alignment verification understood.success_oracles[{index}].id")
        _text(oracle["understanding"], f"alignment verification understood.success_oracles[{index}].understanding")
        if oracle_id in oracle_ids:
            raise IndependentReviewError(f"alignment verification understood.success_oracles duplicate id: {oracle_id}")
        oracle_ids.append(oracle_id)
    discrepancies = payload["discrepancies"]
    if not isinstance(discrepancies, Sequence) or isinstance(discrepancies, (str, bytes)):
        raise IndependentReviewError("alignment verification discrepancies must be a sequence")
    for index, entry in enumerate(discrepancies):
        _text(entry, f"alignment verification discrepancies[{index}]")
    return {
        "schema": 1,
        "id": artifact_id,
        "round_id": round_id,
        "projection_ref": projection_ref,
        "authority_fingerprint": fingerprint,
        "verifier_identity": verifier_identity,
        "session_context": session_context,
        "understood": {
            "outcome": understood["outcome"],
            "scope": understood["scope"],
            "authority": understood["authority"],
            "success_oracles": tuple(
                {"id": str(oracle["id"]), "understanding": str(oracle["understanding"])} for oracle in oracles
            ),
        },
        "discrepancies": tuple(discrepancies),
    }


def validate_delivery_review_payload(payload: Any) -> dict[str, Any]:
    """Validate one delivery-review payload and return its normalized fields.

    Every violation raises ``IndependentReviewError`` naming the field.
    """

    required = {
        "schema",
        "id",
        "round_id",
        "verifier_identity",
        "session_context",
        "per_oracle",
        "evidence_custody",
        "verdict",
    }
    if not isinstance(payload, Mapping):
        raise IndependentReviewError("delivery review payload must be an object")
    if set(payload) != required:
        raise IndependentReviewError("delivery review payload fields do not match schema")
    if payload["schema"] != 1:
        raise IndependentReviewError("delivery review payload schema must be 1")
    artifact_id = _text(payload["id"], "delivery review id")
    round_id = _text(payload["round_id"], "delivery review round_id")
    verifier_identity = _text(payload["verifier_identity"], "delivery review verifier_identity")
    session_context = _text(payload["session_context"], "delivery review session_context")
    per_oracle = payload["per_oracle"]
    if not isinstance(per_oracle, Mapping) or not per_oracle:
        raise IndependentReviewError("delivery review per_oracle must be a non-empty object")
    parsed_per_oracle: dict[str, dict[str, str]] = {}
    for oracle_id, judgment in per_oracle.items():
        if not isinstance(oracle_id, str) or not oracle_id.strip():
            raise IndependentReviewError("delivery review per_oracle keys must be non-empty oracle ids")
        if not isinstance(judgment, Mapping) or set(judgment) != {"verdict", "basis"}:
            raise IndependentReviewError(f"delivery review per_oracle[{oracle_id}] must carry verdict and basis")
        verdict = judgment["verdict"]
        if verdict not in DELIVERY_REVIEW_VERDICTS:
            raise IndependentReviewError(
                f"delivery review per_oracle[{oracle_id}].verdict must be one of: "
                + ", ".join(DELIVERY_REVIEW_VERDICTS)
            )
        basis = judgment["basis"]
        if not isinstance(basis, str) or not basis.strip():
            raise IndependentReviewError(f"delivery review per_oracle[{oracle_id}].basis must be a non-empty string")
        parsed_per_oracle[str(oracle_id)] = {"verdict": str(verdict), "basis": basis}
    custody_value = payload["evidence_custody"]
    if not isinstance(custody_value, Sequence) or isinstance(custody_value, (str, bytes)) or not custody_value:
        raise IndependentReviewError("delivery review evidence_custody must be a non-empty sequence")
    custody: list[ArtifactRef] = []
    for index, value in enumerate(custody_value):
        try:
            custody.append(ArtifactRef.from_dict(value))
        except (TypeError, ValueError) as error:
            raise IndependentReviewError(
                f"delivery review evidence_custody[{index}] must be an artifact reference"
            ) from error
    verdict = payload["verdict"]
    if verdict not in DELIVERY_REVIEW_VERDICTS:
        raise IndependentReviewError("delivery review verdict must be one of: " + ", ".join(DELIVERY_REVIEW_VERDICTS))
    return {
        "schema": 1,
        "id": artifact_id,
        "round_id": round_id,
        "verifier_identity": verifier_identity,
        "session_context": session_context,
        "per_oracle": parsed_per_oracle,
        "evidence_custody": tuple(custody),
        "verdict": str(verdict),
    }


__all__ = [
    "ALIGNMENT_VERIFICATION_KIND",
    "ALIGNMENT_VERIFICATION_ROLE",
    "DELIVERY_REVIEW_KIND",
    "DELIVERY_REVIEW_ROLE",
    "DELIVERY_REVIEW_VERDICTS",
    "INDEPENDENT_REVIEW_ISSUER",
    "IndependentReviewError",
    "validate_alignment_verification_payload",
    "validate_delivery_review_payload",
    "verification_principal",
    "verify_identity_independent",
    "verify_independent_review_principal",
]
