"""Persistence and evaluator authority for OracleRun slot closure."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .domain import ArtifactRef, ArtifactRevision, RuntimeStoreError, canonical_json_bytes, thaw_json, validate_identifier
from .oracles import (
    ORACLE_ATTEMPT_KIND,
    ORACLE_RUN_KIND,
    ORACLE_SPEC_KIND,
    InvalidOracleError,
    OracleAttempt,
    OracleRun,
    OracleSpec,
    validate_oracle_attempt_lineage,
    validate_oracle_run_lineage,
)
from .run_ledger import RunLedger


ASSESSMENT_KIND = "slot-closure-assessment"


class ClosureAssessmentError(InvalidOracleError):
    """Raised when an oracle or closure artifact cannot be authoritative."""


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ClosureAssessmentError(f"{label} must be a non-empty string")
    return value


def _ref(value: Mapping[str, Any], label: str) -> ArtifactRef:
    try:
        return ArtifactRef.from_dict(value)
    except (TypeError, ValueError, RuntimeStoreError) as error:
        raise ClosureAssessmentError(f"{label} is not an exact artifact reference") from error


def _refs(value: Sequence[Mapping[str, Any]], label: str) -> tuple[ArtifactRef, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ClosureAssessmentError(f"{label} must be a sequence")
    result = tuple(_ref(item, f"{label}[{index}]") for index, item in enumerate(value))
    if len(set(result)) != len(result):
        raise ClosureAssessmentError(f"{label} must not contain duplicate references")
    return result


def _artifact_ref(value: ArtifactRevision) -> ArtifactRef:
    return ArtifactRef(value.round_id, value.id, value.revision)


def _same_payload(existing: ArtifactRevision, payload: Mapping[str, Any]) -> bool:
    return canonical_json_bytes(thaw_json(existing.payload)) == canonical_json_bytes(payload)


@dataclass(frozen=True, slots=True)
class SlotClosureAssessment:
    """Typed view of one immutable assessment artifact."""

    assessment_id: str
    slot_id: str
    status: str
    checks: Mapping[str, bool]
    successor_kinds: tuple[str, ...]
    counterevidence_disposition: str
    closure_token: str | None
    parent_refs: tuple[ArtifactRef, ...]

    def __post_init__(self) -> None:
        validate_identifier(self.assessment_id, "assessment_id")
        _text(self.slot_id, "slot_id")
        if self.status not in {"passed", "inconclusive"}:
            raise ClosureAssessmentError("assessment status is unsupported")
        if not isinstance(self.checks, Mapping) or any(not isinstance(value, bool) for value in self.checks.values()):
            raise ClosureAssessmentError("checks must be a boolean mapping")
        if not isinstance(self.successor_kinds, tuple) or any(not isinstance(value, str) or not value.strip() for value in self.successor_kinds):
            raise ClosureAssessmentError("successor_kinds must be a tuple of strings")
        _text(self.counterevidence_disposition, "counterevidence_disposition")
        if self.status == "passed" and not self.closure_token:
            raise ClosureAssessmentError("passed assessment requires a closure token")
        if self.status != "passed" and self.closure_token is not None:
            raise ClosureAssessmentError("inconclusive assessment must not issue a token")
        if not isinstance(self.parent_refs, tuple) or not all(isinstance(ref, ArtifactRef) for ref in self.parent_refs):
            raise ClosureAssessmentError("parent_refs must contain ArtifactRef values")

    def to_dict(self) -> dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "slot_id": self.slot_id,
            "status": self.status,
            "checks": dict(self.checks),
            "successor_kinds": list(self.successor_kinds),
            "counterevidence_disposition": self.counterevidence_disposition,
            "closure_token": self.closure_token,
            "parent_refs": [ref.to_dict() for ref in self.parent_refs],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SlotClosureAssessment":
        if not isinstance(value, Mapping):
            raise ClosureAssessmentError("assessment payload must be a mapping")
        return cls(
            assessment_id=value["assessment_id"],
            slot_id=value["slot_id"],
            status=value["status"],
            checks=value["checks"],
            successor_kinds=tuple(value["successor_kinds"]),
            counterevidence_disposition=value["counterevidence_disposition"],
            closure_token=value["closure_token"],
            parent_refs=_refs(value["parent_refs"], "parent_refs"),
        )


class OracleService:
    """Persist OracleSpec, OracleAttempt, and OracleRun without lifecycle authority."""

    def __init__(self, ledger: RunLedger) -> None:
        if not isinstance(ledger, RunLedger):
            raise ClosureAssessmentError("OracleService requires a RunLedger")
        self.ledger = ledger

    def _artifact(self, reference: ArtifactRef, kind: str) -> ArtifactRevision:
        try:
            artifact = self.ledger.get_artifact(reference)
        except RuntimeStoreError as error:
            raise ClosureAssessmentError(f"unresolved {kind} reference: {reference}") from error
        if artifact.kind != kind:
            raise ClosureAssessmentError(f"reference must identify a {kind} artifact")
        return artifact

    def _append(self, round_id: str, artifact_id: str, kind: str, payload: Mapping[str, Any], parents: tuple[ArtifactRef, ...], expected_revision: int) -> ArtifactRevision:
        for existing in self.ledger.load_run(round_id).artifacts:
            if existing.id == artifact_id and existing.kind == kind and existing.parent_refs == parents and _same_payload(existing, payload):
                return existing
        return self.ledger.append_artifact(round_id, artifact_id, kind, dict(payload), parent_refs=parents, expected_revision=expected_revision)

    def create_spec(self, *, round_id: str, spec_id: str, spec: OracleSpec, expected_revision: int) -> ArtifactRevision:
        validate_identifier(spec_id, "spec_id")
        if not isinstance(spec, OracleSpec) or spec.oracle_spec_id != spec_id:
            raise ClosureAssessmentError("spec_id must match OracleSpec.oracle_spec_id")
        return self._append(round_id, spec_id, ORACLE_SPEC_KIND, spec.to_dict(), (), expected_revision)

    def start_attempt(self, *, round_id: str, attempt_id: str, spec: ArtifactRevision, input_refs: Sequence[ArtifactRef], method: str, environment_digest: str, expected_revision: int, toolchain_digest: str | None = None) -> ArtifactRevision:
        if spec.kind != ORACLE_SPEC_KIND or spec.round_id != round_id:
            raise ClosureAssessmentError("attempt requires a current OracleSpec")
        spec_ref = _artifact_ref(self._artifact(_artifact_ref(spec), ORACLE_SPEC_KIND))
        attempt = OracleAttempt(attempt_id, spec_ref, tuple(input_refs), method, environment_digest, toolchain_digest)
        for reference in attempt.input_refs:
            try:
                self.ledger.get_artifact(reference)
            except RuntimeStoreError as error:
                raise ClosureAssessmentError(f"unresolved input reference: {reference}") from error
        return self._append(round_id, attempt_id, ORACLE_ATTEMPT_KIND, attempt.to_dict(), (spec_ref, *attempt.input_refs), expected_revision)

    def record_run(self, *, round_id: str, run: OracleRun, expected_revision: int) -> ArtifactRevision:
        if not isinstance(run, OracleRun):
            raise ClosureAssessmentError("run must be an OracleRun")
        spec = self._artifact(run.oracle_spec_ref, ORACLE_SPEC_KIND)
        attempt = self._artifact(run.attempt_ref, ORACLE_ATTEMPT_KIND)
        inputs = tuple(self.ledger.get_artifact(ref) for ref in run.input_refs)
        results = tuple(self.ledger.get_artifact(ref) for ref in run.result_artifact_refs)
        events = tuple(self.ledger.get_artifact(ref) for ref in run.tool_event_refs)
        validate_oracle_run_lineage(
            ArtifactRevision.create(artifact_id=run.oracle_run_id, round_id=round_id, revision=1, kind=ORACLE_RUN_KIND, payload=run.to_dict(), parent_refs=(run.oracle_spec_ref, run.attempt_ref, *run.input_refs, *run.tool_event_refs, *run.result_artifact_refs)),
            spec,
            attempt,
            input_revisions=inputs,
            result_revisions=results,
            tool_event_revisions=events,
        )
        parents = (run.oracle_spec_ref, run.attempt_ref, *run.input_refs, *run.tool_event_refs, *run.result_artifact_refs)
        return self._append(round_id, run.oracle_run_id, ORACLE_RUN_KIND, run.to_dict(), parents, expected_revision)


class SlotClosureAssessor:
    """The only component allowed to issue an evaluator-owned closure token."""

    def __init__(self, ledger: RunLedger, *, core_evaluator_id: str) -> None:
        if not isinstance(ledger, RunLedger):
            raise ClosureAssessmentError("SlotClosureAssessor requires a RunLedger")
        self.ledger = ledger
        self.core_evaluator_id = _text(core_evaluator_id, "core_evaluator_id")

    def _resolve(self, value: ArtifactRevision, kind: str, round_id: str) -> ArtifactRef:
        if not isinstance(value, ArtifactRevision) or value.kind != kind or value.round_id != round_id:
            raise ClosureAssessmentError(f"assessment requires a {kind} from its round")
        ref = _artifact_ref(value)
        try:
            stored = self.ledger.get_artifact(ref)
        except RuntimeStoreError as error:
            raise ClosureAssessmentError(f"unresolved {kind} reference") from error
        if stored != value or not self.ledger.is_latest_artifact(ref):
            raise ClosureAssessmentError(f"{kind} revision is stale")
        return ref

    def assess(self, *, round_id: str, assessment_id: str, slot_id: str, blueprint_target: ArtifactRevision, decision: ArtifactRevision, findings: Sequence[ArtifactRevision], oracle_runs: Sequence[ArtifactRevision], evaluator_id: str, provenance_groups: Sequence[str], counterevidence_disposition: str, active_contradiction: bool, expected_revision: int) -> ArtifactRevision:
        if evaluator_id != self.core_evaluator_id:
            raise ClosureAssessmentError("only the core evaluator may issue closure")
        validate_identifier(assessment_id, "assessment_id")
        _text(slot_id, "slot_id")
        target_ref = self._resolve(blueprint_target, "blueprint-target", round_id)
        decision_ref = self._resolve(decision, "decision-ledger-entry", round_id)
        if target_ref not in decision.parent_refs or decision.payload.get("decision_slot_id") != slot_id:
            raise ClosureAssessmentError("decision is not bound to the exact target and slot")
        finding_refs = tuple(self._resolve(item, "finding-pack", round_id) for item in findings)
        if any(ref not in decision.parent_refs for ref in finding_refs):
            raise ClosureAssessmentError("finding is not bound to the exact decision")
        run_refs = tuple(self._resolve(item, ORACLE_RUN_KIND, round_id) for item in oracle_runs)
        if not isinstance(provenance_groups, Sequence) or any(not isinstance(group, str) or not group.strip() for group in provenance_groups):
            raise ClosureAssessmentError("provenance_groups must contain non-empty strings")
        disposition = _text(counterevidence_disposition, "counterevidence_disposition")
        checks = {
            "slot_lineage": True,
            "evidence": bool(finding_refs),
            "provenance_independence": len(set(provenance_groups)) >= 2,
            "counterevidence": bool(disposition),
            "no_active_contradiction": not active_contradiction,
            "oracle": any(item.payload.get("verdict") == "passed" for item in oracle_runs),
            "fallback": bool(str(decision.payload.get("fallback", "")).strip()),
            "reversal_condition": bool(str(decision.payload.get("reversal_condition", "")).strip()),
        }
        successors: list[str] = []
        if not checks["oracle"]:
            successors.append("validation")
        if any(item.payload.get("verdict") in {"failed", "blocked"} for item in oracle_runs):
            successors.append("method_switch")
        if not checks["no_active_contradiction"]:
            successors.append("adversarial")
        if not checks["fallback"] or not checks["reversal_condition"]:
            successors.append("residual_risk")
        base = {
            "assessment_id": assessment_id,
            "slot_id": slot_id,
            "status": "passed" if all(checks.values()) else "inconclusive",
            "checks": checks,
            "successor_kinds": sorted(set(successors)),
            "counterevidence_disposition": disposition,
            "parent_refs": [ref.to_dict() for ref in (target_ref, decision_ref, *finding_refs, *run_refs)],
        }
        token_digest = hashlib.sha256(canonical_json_bytes(base)).hexdigest() if base["status"] == "passed" else None
        token = "closure-" + token_digest if token_digest else None
        payload = {
            **base,
            "closure_token": token,
            "token_digest": token_digest,
            "assessment_revision": 1,
            "required_evidence_results": [{"check": name, "passed": result} for name, result in checks.items()],
            "independence_groups": list(provenance_groups),
            "counterevidence_search": {"status": disposition},
            "contradiction_disposition": {"status": "active" if active_contradiction else "none"},
            "oracle_refs": [ref.to_dict() for ref in run_refs],
            "fallback": str(decision.payload.get("fallback", "")),
            "reversal_condition": str(decision.payload.get("reversal_condition", "")),
            "assessor_version": "core-closure-v1",
        }
        parents = (target_ref, decision_ref, *finding_refs, *run_refs)
        return self._append_assessment(round_id, assessment_id, payload, parents, expected_revision)

    def _append_assessment(self, round_id: str, assessment_id: str, payload: Mapping[str, Any], parents: tuple[ArtifactRef, ...], expected_revision: int) -> ArtifactRevision:
        for existing in self.ledger.load_run(round_id).artifacts:
            if existing.id == assessment_id and existing.kind == ASSESSMENT_KIND and existing.parent_refs == parents and _same_payload(existing, payload):
                return existing
        return self.ledger.append_artifact(round_id, assessment_id, ASSESSMENT_KIND, dict(payload), parent_refs=parents, expected_revision=expected_revision)


__all__ = ["ASSESSMENT_KIND", "ClosureAssessmentError", "OracleService", "SlotClosureAssessor", "SlotClosureAssessment"]
