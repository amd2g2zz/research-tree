"""Persistence and evaluator authority for OracleRun slot closure."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .content_store import ContentAddressedStore, ContentStoreError
from .domain import (
    ArtifactRef,
    ArtifactRevision,
    RuntimeStoreError,
    canonical_json_bytes,
    thaw_json,
    validate_identifier,
)
from .evidence import EVIDENCE_ARTIFACT_KIND, EvidenceAnchor, EvidenceArtifact, EvidenceResolver
from .oracles import (
    ORACLE_ATTEMPT_KIND,
    ORACLE_RUN_KIND,
    ORACLE_SPEC_KIND,
    InvalidOracleError,
    OracleAttempt,
    OracleRun,
    OracleSpec,
    validate_oracle_run_lineage,
)
from .run_ledger import RunLedger
from .source_capture import ACQUISITION_RECEIPT_KIND, SOURCE_CAPTURE_KIND, AcquisitionReceipt, SourceCapture


ASSESSMENT_KIND = "slot-closure-assessment"
FINDING_PACK_KIND = "finding-pack"


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
        if not isinstance(self.successor_kinds, tuple) or any(
            not isinstance(value, str) or not value.strip() for value in self.successor_kinds
        ):
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


# fmt: off
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

# fmt: on
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

    def _current_artifact(self, reference: ArtifactRef, kind: str) -> ArtifactRevision:
        try:
            artifact = self.ledger.get_artifact(reference)
        except RuntimeStoreError as error:
            raise ClosureAssessmentError(f"unresolved {kind} reference") from error
        if artifact.kind != kind or not self.ledger.is_latest_artifact(reference):
            raise ClosureAssessmentError(f"{kind} reference is stale or mismatched")
        return artifact

    def _current_by_id(self, round_id: str, artifact_id: str, kind: str) -> tuple[ArtifactRef, ArtifactRevision]:
        candidates = [
            artifact
            for artifact in self.ledger.list_artifacts(round_id)
            if artifact.id == artifact_id
            and artifact.kind == kind
            and self.ledger.is_latest_artifact(_artifact_ref(artifact))
        ]
        if len(candidates) != 1:
            raise ClosureAssessmentError(f"{kind} identity is unresolved or ambiguous")
        artifact = candidates[0]
        return _artifact_ref(artifact), artifact

    def _require_bound_content(
        self,
        reference: ArtifactRef,
        *,
        digest: str,
        media_type: str,
        size_bytes: int,
        label: str,
    ) -> None:
        try:
            content = self.ledger.get_bound_content(reference)
        except RuntimeStoreError as error:
            raise ClosureAssessmentError(f"{label} has no durable content binding") from error
        if (
            content.availability != "available"
            or content.digest != digest
            or content.media_type != media_type
            or content.byte_size != size_bytes
        ):
            raise ClosureAssessmentError(f"{label} content binding does not match its canonical payload")
        try:
            data = self.ledger.resolve_content(reference, ContentAddressedStore(self.ledger.workspace))
        except (RuntimeStoreError, ContentStoreError, OSError) as error:
            raise ClosureAssessmentError(f"{label} content bytes are unavailable or corrupt") from error
        if len(data) != size_bytes or hashlib.sha256(data).hexdigest() != digest:
            raise ClosureAssessmentError(f"{label} content bytes do not match its canonical payload")

    def _validated_oracle_runs(
        self,
        oracle_runs: Sequence[ArtifactRevision],
    ) -> tuple[OracleRun, ...] | None:
        validated: list[OracleRun] = []
        try:
            for revision in oracle_runs:
                reference = _artifact_ref(revision)
                run = OracleRun.from_revision(reference, revision)
                spec = self.ledger.get_artifact(run.oracle_spec_ref)
                attempt = self.ledger.get_artifact(run.attempt_ref)
                inputs = tuple(self.ledger.get_artifact(item) for item in run.input_refs)
                results = tuple(self.ledger.get_artifact(item) for item in run.result_artifact_refs)
                events = tuple(self.ledger.get_artifact(item) for item in run.tool_event_refs)
                validated.append(
                    validate_oracle_run_lineage(
                        revision,
                        spec,
                        attempt,
                        input_revisions=inputs,
                        result_revisions=results,
                        tool_event_revisions=events,
                    )
                )
        except (RuntimeStoreError, InvalidOracleError, TypeError, ValueError):
            return None
        return tuple(validated)

    def _parent_of_kind(
        self,
        artifact: ArtifactRevision,
        kind: str,
        label: str,
        round_id: str,
    ) -> tuple[ArtifactRef, ArtifactRevision]:
        parents: list[tuple[ArtifactRef, ArtifactRevision]] = []
        for reference in artifact.parent_refs:
            try:
                parent = self.ledger.get_artifact(reference)
            except RuntimeStoreError as error:
                raise ClosureAssessmentError(f"{label} has an unresolved parent") from error
            if parent.kind == kind:
                if reference.round_id != round_id:
                    raise ClosureAssessmentError(f"{label} parent belongs to another run")
                parents.append((reference, self._current_artifact(reference, kind)))
        if len(parents) != 1:
            raise ClosureAssessmentError(f"{label} must bind exactly one {kind}")
        return parents[0]

    def _capture_origin_is_bound(
        self,
        capture_ref: ArtifactRef,
        capture: SourceCapture,
        round_id: str,
    ) -> None:
        if capture_ref.round_id != round_id or capture.run_id != round_id:
            raise ClosureAssessmentError("source capture belongs to another run")
        self._require_bound_content(
            capture_ref,
            digest=capture.content_digest,
            media_type=capture.media_type,
            size_bytes=capture.size_bytes,
            label="source capture",
        )
        visited = {capture.capture_id}
        origin = capture
        while origin.origin_capture_id is not None:
            origin_id = origin.origin_capture_id
            if origin_id in visited:
                raise ClosureAssessmentError("source capture origin lineage contains a cycle")
            visited.add(origin_id)
            origin_ref, origin_artifact = self._current_by_id(capture_ref.round_id, origin_id, SOURCE_CAPTURE_KIND)
            try:
                origin = SourceCapture.from_dict(origin_artifact.payload)
            except (TypeError, ValueError) as error:
                raise ClosureAssessmentError("source capture origin is not canonical") from error
            if origin.capture_id != origin_id or origin.run_id != capture_ref.round_id or origin.status != "committed":
                raise ClosureAssessmentError("source capture origin identity is not committed")
            self._require_bound_content(
                origin_ref,
                digest=origin.content_digest,
                media_type=origin.media_type,
                size_bytes=origin.size_bytes,
                label="source capture origin",
            )

    def _finding_evidence_is_bound(self, finding: ArtifactRevision, round_id: str) -> bool:
        try:
            if finding.round_id != round_id:
                raise ClosureAssessmentError("finding pack belongs to another run")
            if finding.payload.get("evidence_mode") != "strict":
                raise ClosureAssessmentError("finding pack is not backed by strict evidence")
            observations = finding.payload.get("observations")
            if isinstance(observations, (str, bytes)) or not isinstance(observations, Sequence):
                raise ClosureAssessmentError("finding pack observations are not a sequence")
            resolver = EvidenceResolver.from_ledger(
                self.ledger,
                ContentAddressedStore(self.ledger.workspace),
                workspace=self.ledger.workspace,
            )
            references: set[ArtifactRef] = set()
            for observation in observations:
                if not isinstance(observation, Mapping):
                    raise ClosureAssessmentError("finding observation is not a mapping")
                anchor = EvidenceAnchor.from_dict(observation.get("anchor"))
                if anchor.artifact_ref is None or anchor.artifact_ref not in finding.parent_refs:
                    raise ClosureAssessmentError("finding observation has no direct evidence parent")
                if anchor.artifact_ref.round_id != round_id:
                    raise ClosureAssessmentError("finding evidence belongs to another run")
                evidence_revision = self._current_artifact(anchor.artifact_ref, EVIDENCE_ARTIFACT_KIND)
                evidence = EvidenceArtifact.from_revision(anchor.artifact_ref, evidence_revision)
                if evidence.run_id != round_id:
                    raise ClosureAssessmentError("evidence artifact belongs to another run")
                if evidence.evidence_class == "legacy_unspecified":
                    raise ClosureAssessmentError("finding anchor does not identify authoritative evidence")
                if (
                    anchor.artifact_digest != evidence.content_digest
                    or anchor.artifact_revision != evidence.revision
                    or anchor.extractor_version != evidence.extractor_version
                    or evidence.status != "active"
                ):
                    raise ClosureAssessmentError("finding anchor does not match active canonical evidence")
                resolver.resolve(anchor)
                self._require_bound_content(
                    anchor.artifact_ref,
                    digest=evidence.content_digest,
                    media_type=evidence.media_type,
                    size_bytes=evidence.size_bytes,
                    label="evidence artifact",
                )
                receipt_ref, receipt_revision = self._parent_of_kind(
                    evidence_revision,
                    ACQUISITION_RECEIPT_KIND,
                    "evidence artifact",
                    round_id,
                )
                receipt = AcquisitionReceipt.from_dict(receipt_revision.payload)
                capture_ref, capture_revision = self._parent_of_kind(
                    receipt_revision,
                    SOURCE_CAPTURE_KIND,
                    "acquisition receipt",
                    round_id,
                )
                capture = SourceCapture.from_dict(capture_revision.payload)
                if (
                    receipt.receipt_id != receipt_ref.artifact_id
                    or receipt.status != "succeeded"
                    or capture.capture_id != capture_ref.artifact_id
                    or capture.run_id != capture_ref.round_id
                    or capture.status != "committed"
                    or capture.capture_id != receipt.capture_id
                    or capture.attempt_id != receipt.attempt_id
                    or capture.method_id != receipt.method_id
                    or capture.provider_id != receipt.provider_id
                    or evidence.acquisition_method != capture.method_id
                ):
                    raise ClosureAssessmentError("evidence receipt and source capture are not exact")
                self._capture_origin_is_bound(capture_ref, capture, round_id)
                references.add(anchor.artifact_ref)
            return bool(references)
        except (RuntimeStoreError, TypeError, ValueError, ClosureAssessmentError):
            return False

    def _decision_findings(
        self,
        decision: ArtifactRevision,
        target_ref: ArtifactRef,
        slot_id: str,
    ) -> tuple[ArtifactRevision, ...]:
        findings: list[ArtifactRevision] = []
        for reference in decision.parent_refs:
            try:
                parent = self.ledger.get_artifact(reference)
            except RuntimeStoreError as error:
                raise ClosureAssessmentError("decision has an unresolved Finding parent") from error
            if parent.kind != FINDING_PACK_KIND:
                continue
            current = self._current_artifact(reference, FINDING_PACK_KIND)
            if (
                target_ref not in current.parent_refs
                or current.payload.get("blueprint_target_id") != target_ref.artifact_id
                or current.payload.get("decision_slot_id") != slot_id
            ):
                raise ClosureAssessmentError("decision Finding parent is not bound to the exact target and slot")
            findings.append(current)
        return tuple(sorted(findings, key=lambda item: (item.id, item.revision)))

    @staticmethod
    def _require_complete_findings(
        supplied: Sequence[ArtifactRevision],
        decision_findings: Sequence[ArtifactRevision],
    ) -> None:
        supplied_refs = tuple(_artifact_ref(item) for item in supplied)
        decision_refs = {_artifact_ref(item) for item in decision_findings}
        if len(set(supplied_refs)) != len(supplied_refs) or set(supplied_refs) != decision_refs:
            raise ClosureAssessmentError("findings must equal the complete decision Finding set")

    def assess(
        self,
        *,
        round_id: str,
        assessment_id: str,
        slot_id: str,
        blueprint_target: ArtifactRevision,
        decision: ArtifactRevision,
        findings: Sequence[ArtifactRevision],
        oracle_runs: Sequence[ArtifactRevision],
        evaluator_id: str,
        provenance_groups: Sequence[str],
        counterevidence_disposition: str,
        active_contradiction: bool,
        expected_revision: int,
    ) -> ArtifactRevision:
        if evaluator_id != self.core_evaluator_id:
            raise ClosureAssessmentError("only the core evaluator may issue closure")
        validate_identifier(assessment_id, "assessment_id")
        _text(slot_id, "slot_id")
        target_ref = self._resolve(blueprint_target, "blueprint-target", round_id)
        decision_ref = self._resolve(decision, "decision-ledger-entry", round_id)
        if target_ref not in decision.parent_refs or decision.payload.get("decision_slot_id") != slot_id:
            raise ClosureAssessmentError("decision is not bound to the exact target and slot")
        finding_values = tuple(findings)
        finding_refs = tuple(self._resolve(item, FINDING_PACK_KIND, round_id) for item in finding_values)
        self._require_complete_findings(finding_values, self._decision_findings(decision, target_ref, slot_id))
        oracle_values = tuple(oracle_runs)
        run_refs = tuple(self._resolve(item, ORACLE_RUN_KIND, round_id) for item in oracle_values)
        validated_oracle_runs = self._validated_oracle_runs(oracle_values)
        if not isinstance(provenance_groups, Sequence) or any(
            not isinstance(group, str) or not group.strip() for group in provenance_groups
        ):
            raise ClosureAssessmentError("provenance_groups must contain non-empty strings")
        disposition = _text(counterevidence_disposition, "counterevidence_disposition")
        checks = {
            "slot_lineage": True,
            "evidence": bool(finding_refs)
            and all(self._finding_evidence_is_bound(item, round_id) for item in finding_values),
            "provenance_independence": len(set(provenance_groups)) >= 2,
            "counterevidence": bool(disposition),
            "no_active_contradiction": not active_contradiction,
            "oracle": validated_oracle_runs is not None
            and any(item.verdict == "passed" for item in validated_oracle_runs),
            "fallback": bool(str(decision.payload.get("fallback", "")).strip()),
            "reversal_condition": bool(str(decision.payload.get("reversal_condition", "")).strip()),
        }
        successors: list[str] = []
        if not checks["oracle"]:
            successors.append("validation")
        if validated_oracle_runs is not None and any(
            item.verdict in {"failed", "blocked"} for item in validated_oracle_runs
        ):
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

    def _append_assessment(
        self,
        round_id: str,
        assessment_id: str,
        payload: Mapping[str, Any],
        parents: tuple[ArtifactRef, ...],
        expected_revision: int,
    ) -> ArtifactRevision:
        for existing in self.ledger.load_run(round_id).artifacts:
            if (
                existing.id == assessment_id
                and existing.kind == ASSESSMENT_KIND
                and existing.parent_refs == parents
                and _same_payload(existing, payload)
            ):
                return existing
        return self.ledger.append_artifact(
            round_id,
            assessment_id,
            ASSESSMENT_KIND,
            dict(payload),
            parent_refs=parents,
            expected_revision=expected_revision,
        )


__all__ = ["ASSESSMENT_KIND", "ClosureAssessmentError", "OracleService", "SlotClosureAssessor", "SlotClosureAssessment"]
