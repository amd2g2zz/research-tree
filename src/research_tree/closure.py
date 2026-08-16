"""Persistence and evaluator authority for OracleRun slot closure."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .content_store import ContentAddressedStore, ContentStoreError
from .contradictions import claim_from_mapping, unresolved_claim_ids
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
ASSESSMENT_REVISION = 2
ASSESSOR_VERSION = "core-closure-v2"
ASSESSMENT_CHECK_NAMES = frozenset(
    {
        "slot_lineage",
        "evidence",
        "provenance_independence",
        "no_selected_option_contradiction",
        "oracle",
        "fallback",
        "reversal_condition",
    }
)


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


def _reference_sort_key(reference: ArtifactRef) -> tuple[str, str, int]:
    return reference.round_id, reference.artifact_id, reference.revision


def _same_payload(existing: ArtifactRevision, payload: Mapping[str, Any]) -> bool:
    return canonical_json_bytes(thaw_json(existing.payload)) == canonical_json_bytes(payload)


def _ref_dict(reference: ArtifactRef) -> dict[str, Any]:
    return reference.to_dict()


def _exact_mapping(value: Any, expected: frozenset[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ClosureAssessmentError(f"{label} has unsupported fields")
    return value


def _check_values(value: Any) -> dict[str, bool]:
    checks = _exact_mapping(value, ASSESSMENT_CHECK_NAMES, "assessment checks")
    if any(not isinstance(result, bool) for result in checks.values()):
        raise ClosureAssessmentError("assessment checks must be boolean")
    return {name: checks[name] for name in sorted(ASSESSMENT_CHECK_NAMES)}


def _reference_list(value: Any, label: str) -> tuple[ArtifactRef, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ClosureAssessmentError(f"{label} must be a reference sequence")
    return _refs(value, label)


def _sorted_reference_list(value: Any, label: str) -> tuple[ArtifactRef, ...]:
    references = _reference_list(value, label)
    if references != tuple(sorted(references, key=_reference_sort_key)):
        raise ClosureAssessmentError(f"{label} must be sorted")
    return references


def _boundary_values(value: Any, label: str) -> list[dict[str, str]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ClosureAssessmentError(f"{label} must be a sequence")
    boundaries: list[dict[str, str]] = []
    for index, item in enumerate(value):
        boundary = _exact_mapping(item, frozenset({"method_id", "provider_id"}), f"{label}[{index}]")
        boundaries.append(
            {
                "method_id": _text(boundary["method_id"], f"{label}[{index}].method_id"),
                "provider_id": _text(boundary["provider_id"], f"{label}[{index}].provider_id"),
            }
        )
    if boundaries != sorted(boundaries, key=lambda item: (item["method_id"], item["provider_id"])):
        raise ClosureAssessmentError(f"{label} must be sorted")
    if len({(item["method_id"], item["provider_id"]) for item in boundaries}) != len(boundaries):
        raise ClosureAssessmentError(f"{label} must not contain duplicates")
    return boundaries


def _text_values(value: Any, label: str) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ClosureAssessmentError(f"{label} must be a sequence")
    values = [_text(item, f"{label}[{index}]") for index, item in enumerate(value)]
    if values != sorted(values) or len(set(values)) != len(values):
        raise ClosureAssessmentError(f"{label} must be sorted and distinct")
    return values


def _finding_lineages(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ClosureAssessmentError("finding_lineages must be a sequence")
    lineages: list[dict[str, Any]] = []
    expected = frozenset(
        {
            "finding_ref",
            "evidence_refs",
            "receipt_refs",
            "capture_refs",
            "origin_refs",
            "origin_capture_ids",
            "provenance_groups",
            "method_provider_boundaries",
        }
    )
    for index, item in enumerate(value):
        lineage = _exact_mapping(item, expected, f"finding_lineages[{index}]")
        lineages.append(
            {
                "finding_ref": _ref(lineage["finding_ref"], f"finding_lineages[{index}].finding_ref").to_dict(),
                "evidence_refs": [
                    reference.to_dict()
                    for reference in _reference_list(
                        lineage["evidence_refs"], f"finding_lineages[{index}].evidence_refs"
                    )
                ],
                "receipt_refs": [
                    reference.to_dict()
                    for reference in _reference_list(lineage["receipt_refs"], f"finding_lineages[{index}].receipt_refs")
                ],
                "capture_refs": [
                    reference.to_dict()
                    for reference in _reference_list(lineage["capture_refs"], f"finding_lineages[{index}].capture_refs")
                ],
                "origin_refs": [
                    reference.to_dict()
                    for reference in _reference_list(lineage["origin_refs"], f"finding_lineages[{index}].origin_refs")
                ],
                "origin_capture_ids": _text_values(
                    lineage["origin_capture_ids"], f"finding_lineages[{index}].origin_capture_ids"
                ),
                "provenance_groups": _text_values(
                    lineage["provenance_groups"], f"finding_lineages[{index}].provenance_groups"
                ),
                "method_provider_boundaries": _boundary_values(
                    lineage["method_provider_boundaries"],
                    f"finding_lineages[{index}].method_provider_boundaries",
                ),
            }
        )
    if lineages != sorted(
        lineages,
        key=lambda item: (
            item["finding_ref"]["round_id"],
            item["finding_ref"]["artifact_id"],
            item["finding_ref"]["revision"],
        ),
    ):
        raise ClosureAssessmentError("finding_lineages must be sorted")
    return lineages


def _oracle_lineages(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ClosureAssessmentError("oracle_lineages must be a sequence")
    lineages: list[dict[str, Any]] = []
    expected = frozenset(
        {
            "oracle_run_ref",
            "oracle_spec_ref",
            "attempt_ref",
            "input_refs",
            "result_refs",
            "tool_event_refs",
            "evaluator",
        }
    )
    for index, item in enumerate(value):
        lineage = _exact_mapping(item, expected, f"oracle_lineages[{index}]")
        lineages.append(
            {
                "oracle_run_ref": _ref(lineage["oracle_run_ref"], f"oracle_lineages[{index}].oracle_run_ref").to_dict(),
                "oracle_spec_ref": _ref(
                    lineage["oracle_spec_ref"], f"oracle_lineages[{index}].oracle_spec_ref"
                ).to_dict(),
                "attempt_ref": _ref(lineage["attempt_ref"], f"oracle_lineages[{index}].attempt_ref").to_dict(),
                "input_refs": [
                    reference.to_dict()
                    for reference in _reference_list(lineage["input_refs"], f"oracle_lineages[{index}].input_refs")
                ],
                "result_refs": [
                    reference.to_dict()
                    for reference in _reference_list(lineage["result_refs"], f"oracle_lineages[{index}].result_refs")
                ],
                "tool_event_refs": [
                    reference.to_dict()
                    for reference in _reference_list(
                        lineage["tool_event_refs"], f"oracle_lineages[{index}].tool_event_refs"
                    )
                ],
                "evaluator": _text(lineage["evaluator"], f"oracle_lineages[{index}].evaluator"),
            }
        )
    if lineages != sorted(
        lineages,
        key=lambda item: (
            item["oracle_run_ref"]["round_id"],
            item["oracle_run_ref"]["artifact_id"],
            item["oracle_run_ref"]["revision"],
        ),
    ):
        raise ClosureAssessmentError("oracle_lineages must be sorted")
    return lineages


def _diagnostic_values(value: Any) -> dict[str, Any]:
    diagnostics = _exact_mapping(
        value,
        frozenset(
            {
                "method_provider_boundaries",
                "provenance_groups",
                "finding_lineages",
                "oracle_lineages",
                "selected_option_contradiction_refs",
            }
        ),
        "assessment diagnostics",
    )
    return {
        "method_provider_boundaries": _boundary_values(
            diagnostics["method_provider_boundaries"], "method_provider_boundaries"
        ),
        "provenance_groups": _text_values(diagnostics["provenance_groups"], "provenance_groups"),
        "finding_lineages": _finding_lineages(diagnostics["finding_lineages"]),
        "oracle_lineages": _oracle_lineages(diagnostics["oracle_lineages"]),
        "selected_option_contradiction_refs": [
            reference.to_dict()
            for reference in _reference_list(
                diagnostics["selected_option_contradiction_refs"],
                "selected_option_contradiction_refs",
            )
        ],
    }


@dataclass(frozen=True, slots=True)
class SlotClosureAssessment:
    """Typed view of one immutable assessment artifact."""

    assessment_id: str
    slot_id: str
    evaluator_id: str
    status: str
    checks: Mapping[str, bool]
    diagnostics: Mapping[str, Any]
    successor_kinds: tuple[str, ...]
    closure_token: str | None
    token_digest: str | None
    target_ref: ArtifactRef
    decision_ref: ArtifactRef
    finding_refs: tuple[ArtifactRef, ...]
    oracle_refs: tuple[ArtifactRef, ...]
    parent_refs: tuple[ArtifactRef, ...]

    def __post_init__(self) -> None:
        validate_identifier(self.assessment_id, "assessment_id")
        _text(self.slot_id, "slot_id")
        _text(self.evaluator_id, "evaluator_id")
        if self.status not in {"passed", "inconclusive"}:
            raise ClosureAssessmentError("assessment status is unsupported")
        checks = _check_values(self.checks)
        _diagnostic_values(self.diagnostics)
        if not isinstance(self.successor_kinds, tuple) or any(
            not isinstance(value, str) or not value.strip() for value in self.successor_kinds
        ):
            raise ClosureAssessmentError("successor_kinds must be a tuple of strings")
        if self.successor_kinds != tuple(sorted(set(self.successor_kinds))):
            raise ClosureAssessmentError("successor_kinds must be sorted and unique")
        if self.status != ("passed" if all(checks.values()) else "inconclusive"):
            raise ClosureAssessmentError("assessment status does not match its checks")
        if self.status == "passed":
            if not isinstance(self.token_digest, str) or len(self.token_digest) != 64:
                raise ClosureAssessmentError("passed assessment requires a token digest")
            if self.closure_token != f"closure-{self.token_digest}":
                raise ClosureAssessmentError("passed assessment requires an exact closure token")
        elif self.closure_token is not None or self.token_digest is not None:
            raise ClosureAssessmentError("inconclusive assessment must not issue a token")
        if not all(isinstance(reference, ArtifactRef) for reference in (self.target_ref, self.decision_ref)):
            raise ClosureAssessmentError("assessment target and decision refs must be exact")
        if not isinstance(self.finding_refs, tuple) or not isinstance(self.oracle_refs, tuple):
            raise ClosureAssessmentError("assessment refs must be tuples")
        if self.finding_refs != tuple(sorted(self.finding_refs, key=_reference_sort_key)) or self.oracle_refs != tuple(
            sorted(self.oracle_refs, key=_reference_sort_key)
        ):
            raise ClosureAssessmentError("assessment finding and oracle refs must be sorted")
        if not isinstance(self.parent_refs, tuple) or not all(isinstance(ref, ArtifactRef) for ref in self.parent_refs):
            raise ClosureAssessmentError("parent_refs must contain ArtifactRef values")
        expected_parents = (self.target_ref, self.decision_ref, *self.finding_refs, *self.oracle_refs)
        if len(set(expected_parents)) != len(expected_parents) or self.parent_refs != expected_parents:
            raise ClosureAssessmentError("assessment parent_refs must exactly match typed refs")

    def to_dict(self) -> dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "assessment_revision": ASSESSMENT_REVISION,
            "slot_id": self.slot_id,
            "evaluator_id": self.evaluator_id,
            "status": self.status,
            "checks": _check_values(self.checks),
            "diagnostics": _diagnostic_values(self.diagnostics),
            "successor_kinds": list(self.successor_kinds),
            "closure_token": self.closure_token,
            "token_digest": self.token_digest,
            "target_ref": self.target_ref.to_dict(),
            "decision_ref": self.decision_ref.to_dict(),
            "finding_refs": [reference.to_dict() for reference in self.finding_refs],
            "oracle_refs": [reference.to_dict() for reference in self.oracle_refs],
            "parent_refs": [ref.to_dict() for ref in self.parent_refs],
            "assessor_version": ASSESSOR_VERSION,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SlotClosureAssessment":
        if not isinstance(value, Mapping):
            raise ClosureAssessmentError("assessment payload must be a mapping")
        _exact_mapping(
            value,
            frozenset(
                {
                    "assessment_id",
                    "assessment_revision",
                    "slot_id",
                    "evaluator_id",
                    "status",
                    "checks",
                    "diagnostics",
                    "successor_kinds",
                    "closure_token",
                    "token_digest",
                    "target_ref",
                    "decision_ref",
                    "finding_refs",
                    "oracle_refs",
                    "parent_refs",
                    "assessor_version",
                }
            ),
            "assessment payload",
        )
        if value["assessment_revision"] != ASSESSMENT_REVISION:
            raise ClosureAssessmentError("assessment payload revision is unsupported")
        if value["assessor_version"] != ASSESSOR_VERSION:
            raise ClosureAssessmentError("assessment assessor version is unsupported")
        return cls(
            assessment_id=value["assessment_id"],
            slot_id=value["slot_id"],
            evaluator_id=value["evaluator_id"],
            status=value["status"],
            checks=_check_values(value["checks"]),
            diagnostics=_diagnostic_values(value["diagnostics"]),
            successor_kinds=tuple(value["successor_kinds"]),
            closure_token=value["closure_token"],
            token_digest=value["token_digest"],
            target_ref=_ref(value["target_ref"], "target_ref"),
            decision_ref=_ref(value["decision_ref"], "decision_ref"),
            finding_refs=_sorted_reference_list(value["finding_refs"], "finding_refs"),
            oracle_refs=_sorted_reference_list(value["oracle_refs"], "oracle_refs"),
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

    def _current_reference(self, reference: ArtifactRef, round_id: str) -> ArtifactRevision:
        if reference.round_id != round_id:
            raise ClosureAssessmentError("assessment lineage belongs to another run")
        try:
            artifact = self.ledger.get_artifact(reference)
        except RuntimeStoreError as error:
            raise ClosureAssessmentError("assessment lineage reference is unresolved") from error
        if not self.ledger.is_latest_artifact(reference):
            raise ClosureAssessmentError("assessment lineage reference is stale")
        return artifact

    @staticmethod
    def _decision_slot(target: ArtifactRevision, slot_id: str) -> Mapping[str, Any]:
        slots = target.payload.get("slots")
        if isinstance(slots, (str, bytes)) or not isinstance(slots, Sequence):
            raise ClosureAssessmentError("Blueprint Target has no canonical Decision Slots")
        matching_slot: Mapping[str, Any] | None = None
        seen_ids: set[str] = set()
        for index, candidate in enumerate(slots):
            if not isinstance(candidate, Mapping):
                raise ClosureAssessmentError(f"Blueprint Target slots[{index}] is malformed")
            candidate_id = candidate.get("id")
            try:
                candidate_id = validate_identifier(candidate_id, f"Blueprint Target slots[{index}].id")
            except (TypeError, ValueError, RuntimeStoreError) as error:
                raise ClosureAssessmentError(str(error)) from error
            if candidate_id in seen_ids:
                raise ClosureAssessmentError(f"Blueprint Target repeats Decision Slot {candidate_id}")
            seen_ids.add(candidate_id)
            if candidate_id == slot_id:
                matching_slot = candidate
        if matching_slot is None:
            raise ClosureAssessmentError("Decision Slot is absent from the exact Blueprint Target")
        alternatives = matching_slot.get("alternatives")
        if isinstance(alternatives, (str, bytes)) or not isinstance(alternatives, Sequence):
            raise ClosureAssessmentError("Decision Slot alternatives are malformed")
        option_values = tuple(_text(option, "Decision Slot alternative") for option in alternatives)
        if len(option_values) < 2 or len(set(option_values)) != len(option_values):
            raise ClosureAssessmentError("Decision Slot alternatives must be distinct and complete")
        return matching_slot

    def _validate_decision_slot_semantics(
        self,
        target: ArtifactRevision,
        decision: ArtifactRevision,
        slot_id: str,
    ) -> None:
        if decision.payload.get("blueprint_target_id") != target.id:
            raise ClosureAssessmentError("decision does not belong to the exact Blueprint Target")
        slot = self._decision_slot(target, slot_id)
        if decision.payload.get("status") not in {"selected", "conditional"}:
            raise ClosureAssessmentError("closure requires a selected or conditional Decision Ledger entry")
        selected_option = _text(decision.payload.get("selected_option"), "decision selected_option")
        if selected_option not in slot["alternatives"]:
            raise ClosureAssessmentError("decision selected_option is absent from the Decision Slot")

    @staticmethod
    def _sorted_revisions(values: Sequence[ArtifactRevision]) -> tuple[ArtifactRevision, ...]:
        return tuple(sorted(values, key=lambda value: (value.round_id, value.id, value.revision)))

    @staticmethod
    def _sorted_refs(values: set[ArtifactRef]) -> list[dict[str, Any]]:
        return [reference.to_dict() for reference in sorted(values, key=_reference_sort_key)]

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
        round_id: str,
    ) -> tuple[tuple[OracleRun, dict[str, Any]], ...] | None:
        validated: list[tuple[OracleRun, dict[str, Any]]] = []
        try:
            for revision in oracle_runs:
                reference = _artifact_ref(revision)
                current_run = self._current_artifact(reference, ORACLE_RUN_KIND)
                if current_run != revision or reference.round_id != round_id:
                    raise ClosureAssessmentError("OracleRun reference is stale or belongs to another run")
                run = OracleRun.from_revision(reference, revision)
                spec = self._current_artifact(run.oracle_spec_ref, ORACLE_SPEC_KIND)
                if run.oracle_spec_ref.round_id != round_id:
                    raise ClosureAssessmentError("OracleSpec belongs to another run")
                attempt = self._current_artifact(run.attempt_ref, ORACLE_ATTEMPT_KIND)
                if run.attempt_ref.round_id != round_id:
                    raise ClosureAssessmentError("OracleAttempt belongs to another run")
                inputs = tuple(self._current_reference(item, round_id) for item in run.input_refs)
                results = tuple(self._current_reference(item, round_id) for item in run.result_artifact_refs)
                events = tuple(self._current_reference(item, round_id) for item in run.tool_event_refs)
                canonical_run = validate_oracle_run_lineage(
                    revision,
                    spec,
                    attempt,
                    input_revisions=inputs,
                    result_revisions=results,
                    tool_event_revisions=events,
                )
                validated.append(
                    (
                        canonical_run,
                        {
                            "oracle_run_ref": reference.to_dict(),
                            "oracle_spec_ref": run.oracle_spec_ref.to_dict(),
                            "attempt_ref": run.attempt_ref.to_dict(),
                            "input_refs": [item.to_dict() for item in run.input_refs],
                            "result_refs": [item.to_dict() for item in run.result_artifact_refs],
                            "tool_event_refs": [item.to_dict() for item in run.tool_event_refs],
                            "evaluator": run.evaluator,
                        },
                    )
                )
        except (RuntimeStoreError, InvalidOracleError, TypeError, ValueError, ClosureAssessmentError):
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
    ) -> tuple[ArtifactRef, ...]:
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
        origin_refs: list[ArtifactRef] = []
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
            origin_refs.append(origin_ref)
        return tuple(origin_refs)

    def _finding_evidence_lineage(
        self,
        finding: ArtifactRevision,
        round_id: str,
    ) -> dict[str, Any] | None:
        try:
            if finding.round_id != round_id:
                raise ClosureAssessmentError("finding pack belongs to another run")
            current_finding = self._current_artifact(_artifact_ref(finding), FINDING_PACK_KIND)
            if current_finding != finding:
                raise ClosureAssessmentError("finding pack is stale")
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
            evidence_refs: set[ArtifactRef] = set()
            receipt_refs: set[ArtifactRef] = set()
            capture_refs: set[ArtifactRef] = set()
            origin_refs: set[ArtifactRef] = set()
            origin_capture_ids: set[str] = set()
            provenance_groups: set[str] = set()
            boundaries: set[tuple[str, str]] = set()
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
                receipt_refs.add(receipt_ref)
                receipt = AcquisitionReceipt.from_dict(receipt_revision.payload)
                capture_ref, capture_revision = self._parent_of_kind(
                    receipt_revision,
                    SOURCE_CAPTURE_KIND,
                    "acquisition receipt",
                    round_id,
                )
                capture_refs.add(capture_ref)
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
                origins = self._capture_origin_is_bound(capture_ref, capture, round_id)
                origin_refs.update(origins)
                origin_capture_ids.update(item.artifact_id for item in origins)
                if not origins:
                    origin_capture_ids.add(capture.capture_id)
                provenance_groups.add(capture.provenance_group)
                evidence_refs.add(anchor.artifact_ref)
                boundaries.add((capture.method_id, capture.provider_id))
            if not evidence_refs:
                raise ClosureAssessmentError("finding pack has no strict evidence references")
            return {
                "finding_ref": _artifact_ref(finding).to_dict(),
                "evidence_refs": self._sorted_refs(evidence_refs),
                "receipt_refs": self._sorted_refs(receipt_refs),
                "capture_refs": self._sorted_refs(capture_refs),
                "origin_refs": self._sorted_refs(origin_refs),
                "origin_capture_ids": sorted(origin_capture_ids),
                "provenance_groups": sorted(provenance_groups),
                "method_provider_boundaries": [
                    {"method_id": method_id, "provider_id": provider_id}
                    for method_id, provider_id in sorted(boundaries)
                ],
            }
        except (RuntimeStoreError, TypeError, ValueError, ClosureAssessmentError):
            return None

    def _finding_evidence_is_bound(self, finding: ArtifactRevision, round_id: str) -> bool:
        return self._finding_evidence_lineage(finding, round_id) is not None

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

    @staticmethod
    def _selected_option_contradictions(
        findings: Sequence[ArtifactRevision],
        selected_option: str,
    ) -> tuple[ArtifactRef, ...]:
        contradictions: list[ArtifactRef] = []
        for finding in findings:
            effects = finding.payload.get("option_effects")
            if isinstance(effects, (str, bytes)) or not isinstance(effects, Sequence):
                raise ClosureAssessmentError("finding option_effects must be a sequence")
            for effect in effects:
                if not isinstance(effect, Mapping):
                    raise ClosureAssessmentError("finding option effect must be a mapping")
                option = effect.get("option")
                disposition = effect.get("effect")
                if not isinstance(option, str) or not isinstance(disposition, str):
                    raise ClosureAssessmentError("finding option effect must use strings")
                if option == selected_option and disposition == "contradicts":
                    contradictions.append(_artifact_ref(finding))
                    break
        return tuple(sorted(contradictions, key=_reference_sort_key))

    def _canonical_claim_conflicts(
        self,
        *,
        round_id: str,
        blueprint_target: ArtifactRevision,
        slot_id: str,
    ) -> tuple[ArtifactRef, ...]:
        candidates = tuple(
            item
            for item in self.ledger.load_run(round_id).artifacts
            if item.kind == FINDING_PACK_KIND
            and item.payload.get("blueprint_target_id") == blueprint_target.id
            and item.payload.get("decision_slot_id") == slot_id
        )
        claims_by_finding: dict[ArtifactRef, tuple[Any, ...]] = {}
        all_claims: list[Any] = []
        for finding in candidates:
            try:
                claims = tuple(claim_from_mapping(item) for item in finding.payload.get("claims", ()))
            except (TypeError, ValueError) as error:
                raise ClosureAssessmentError(
                    f"Finding Pack {finding.id} has invalid canonical claims: {error}"
                ) from error
            reference = _artifact_ref(finding)
            claims_by_finding[reference] = claims
            all_claims.extend(claims)
        contested = unresolved_claim_ids(all_claims)
        return tuple(
            sorted(
                (
                    reference
                    for reference, claims in claims_by_finding.items()
                    if any(claim.claim_id in contested for claim in claims)
                ),
                key=_reference_sort_key,
            )
        )

    @staticmethod
    def _payload_with_token(base: Mapping[str, Any]) -> dict[str, Any]:
        status = base["status"]
        token_digest = hashlib.sha256(canonical_json_bytes(base)).hexdigest() if status == "passed" else None
        payload = {
            **base,
            "closure_token": f"closure-{token_digest}" if token_digest else None,
            "token_digest": token_digest,
        }
        return SlotClosureAssessment.from_dict(payload).to_dict()

    def _derive_payload(
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
    ) -> tuple[dict[str, Any], tuple[ArtifactRef, ...]]:
        if evaluator_id != self.core_evaluator_id:
            raise ClosureAssessmentError("only the core evaluator may issue closure")
        validate_identifier(assessment_id, "assessment_id")
        _text(slot_id, "slot_id")
        target_ref = self._resolve(blueprint_target, "blueprint-target", round_id)
        decision_ref = self._resolve(decision, "decision-ledger-entry", round_id)
        if target_ref not in decision.parent_refs or decision.payload.get("decision_slot_id") != slot_id:
            raise ClosureAssessmentError("decision is not bound to the exact target and slot")
        self._validate_decision_slot_semantics(blueprint_target, decision, slot_id)
        decision_findings = self._decision_findings(decision, target_ref, slot_id)
        finding_values = tuple(findings)
        self._require_complete_findings(finding_values, decision_findings)
        finding_values = self._sorted_revisions(decision_findings)
        finding_refs = tuple(self._resolve(item, FINDING_PACK_KIND, round_id) for item in finding_values)
        oracle_values = self._sorted_revisions(tuple(oracle_runs))
        run_refs = tuple(self._resolve(item, ORACLE_RUN_KIND, round_id) for item in oracle_values)
        if len(set(run_refs)) != len(run_refs):
            raise ClosureAssessmentError("oracle_runs must not contain duplicate references")
        validated_oracle_runs = self._validated_oracle_runs(oracle_values, round_id)
        finding_lineages = [self._finding_evidence_lineage(item, round_id) for item in finding_values]
        evidence = bool(finding_refs) and all(lineage is not None for lineage in finding_lineages)
        typed_lineages = [lineage for lineage in finding_lineages if lineage is not None]
        provenance_groups = {group for lineage in typed_lineages for group in lineage["provenance_groups"]}
        selected_option = _text(decision.payload.get("selected_option"), "decision selected_option")
        worker_contradiction_refs = self._selected_option_contradictions(finding_values, selected_option)
        canonical_contradiction_refs = self._canonical_claim_conflicts(
            round_id=round_id,
            blueprint_target=blueprint_target,
            slot_id=slot_id,
        )
        contradiction_refs = tuple(
            sorted(set(worker_contradiction_refs).union(canonical_contradiction_refs), key=_reference_sort_key)
        )
        passed_input_refs = {
            reference
            for run, _ in validated_oracle_runs or ()
            if run.verdict == "passed"
            for reference in run.input_refs
        }
        oracle = validated_oracle_runs is not None and any(run.verdict == "passed" for run, _ in validated_oracle_runs)
        checks = {
            "slot_lineage": True,
            "evidence": evidence,
            "provenance_independence": evidence and len(provenance_groups) >= 2,
            "no_selected_option_contradiction": not canonical_contradiction_refs
            and all(reference in passed_input_refs for reference in worker_contradiction_refs),
            "oracle": oracle,
            "fallback": bool(str(decision.payload.get("fallback", "")).strip()),
            "reversal_condition": bool(str(decision.payload.get("reversal_condition", "")).strip()),
        }
        successors: list[str] = []
        if not checks["oracle"]:
            successors.append("validation")
        if not checks["provenance_independence"] or (
            validated_oracle_runs is not None
            and any(run.verdict in {"failed", "blocked"} for run, _ in validated_oracle_runs)
        ):
            successors.append("method_switch")
        if not checks["no_selected_option_contradiction"]:
            successors.append("adversarial")
        if not checks["fallback"] or not checks["reversal_condition"]:
            successors.append("residual_risk")
        parent_refs = (target_ref, decision_ref, *finding_refs, *run_refs)
        diagnostics = {
            "method_provider_boundaries": [
                {"method_id": method_id, "provider_id": provider_id}
                for method_id, provider_id in sorted(
                    {
                        (item["method_id"], item["provider_id"])
                        for lineage in typed_lineages
                        for item in lineage["method_provider_boundaries"]
                    }
                )
            ],
            "provenance_groups": sorted(provenance_groups),
            "finding_lineages": typed_lineages,
            "oracle_lineages": [lineage for _, lineage in validated_oracle_runs or ()],
            "selected_option_contradiction_refs": [reference.to_dict() for reference in contradiction_refs],
        }
        base = {
            "assessment_id": assessment_id,
            "assessment_revision": ASSESSMENT_REVISION,
            "slot_id": slot_id,
            "evaluator_id": evaluator_id,
            "status": "passed" if all(checks.values()) else "inconclusive",
            "checks": {name: checks[name] for name in sorted(ASSESSMENT_CHECK_NAMES)},
            "diagnostics": diagnostics,
            "successor_kinds": sorted(set(successors)),
            "target_ref": target_ref.to_dict(),
            "decision_ref": decision_ref.to_dict(),
            "finding_refs": [reference.to_dict() for reference in finding_refs],
            "oracle_refs": [reference.to_dict() for reference in run_refs],
            "parent_refs": [reference.to_dict() for reference in parent_refs],
            "assessor_version": ASSESSOR_VERSION,
        }
        return self._payload_with_token(base), parent_refs

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
        expected_revision: int,
    ) -> ArtifactRevision:
        payload, parents = self._derive_payload(
            round_id=round_id,
            assessment_id=assessment_id,
            slot_id=slot_id,
            blueprint_target=blueprint_target,
            decision=decision,
            findings=findings,
            oracle_runs=oracle_runs,
            evaluator_id=evaluator_id,
        )
        return self._append_assessment(round_id, assessment_id, payload, parents, expected_revision)

    def is_current(self, assessment: ArtifactRevision) -> bool:
        """Return whether one passed current assessment replays exactly."""

        try:
            reference = _artifact_ref(assessment)
            if assessment.kind != ASSESSMENT_KIND or not self.ledger.is_latest_artifact(reference):
                return False
            stored = self.ledger.get_artifact(reference)
            if stored != assessment:
                return False
            model = SlotClosureAssessment.from_dict(assessment.payload)
            if (
                model.status != "passed"
                or model.assessment_id != assessment.id
                or model.evaluator_id != self.core_evaluator_id
                or model.target_ref.round_id != assessment.round_id
            ):
                return False
            target = self._current_artifact(model.target_ref, "blueprint-target")
            decision = self._current_artifact(model.decision_ref, "decision-ledger-entry")
            findings = tuple(self._current_artifact(item, FINDING_PACK_KIND) for item in model.finding_refs)
            oracle_runs = tuple(self._current_artifact(item, ORACLE_RUN_KIND) for item in model.oracle_refs)
            expected, parents = self._derive_payload(
                round_id=assessment.round_id,
                assessment_id=model.assessment_id,
                slot_id=model.slot_id,
                blueprint_target=target,
                decision=decision,
                findings=findings,
                oracle_runs=oracle_runs,
                evaluator_id=model.evaluator_id,
            )
            return parents == assessment.parent_refs and canonical_json_bytes(expected) == canonical_json_bytes(
                thaw_json(assessment.payload)
            )
        except (
            ClosureAssessmentError,
            InvalidOracleError,
            RuntimeStoreError,
            TypeError,
            ValueError,
            KeyError,
        ):
            return False

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
        if payload.get("status") != "passed":
            return self.ledger.append_artifact(
                round_id,
                assessment_id,
                ASSESSMENT_KIND,
                dict(payload),
                parent_refs=parents,
                expected_revision=expected_revision,
            )
        from .completion_inputs import CompletionInputRegistrar

        return CompletionInputRegistrar(self.ledger).write_closure(
            round_id=round_id,
            assessment_id=assessment_id,
            payload=payload,
            parent_refs=parents,
            core_evaluator_id=self.core_evaluator_id,
            expected_revision=expected_revision,
        )


__all__ = ["ASSESSMENT_KIND", "ClosureAssessmentError", "OracleService", "SlotClosureAssessor", "SlotClosureAssessment"]
