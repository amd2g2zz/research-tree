"""Durable source acquisition and bounded analysis checkpoint contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .content_store import ContentAddressedStore
from .domain import ArtifactRef, utc_now, validate_identifier, validate_timestamp
from .run_ledger import RunLedger

SOURCE_CAPTURE_KIND = "source-capture"
ACQUISITION_RECEIPT_KIND = "acquisition-receipt"
ANALYSIS_CHECKPOINT_KIND = "analysis-checkpoint"
SENSITIVE_KEYS = {
    "prompt",
    "system_prompt",
    "password",
    "token",
    "secret",
    "credential",
    "chain_of_thought",
    "private_reasoning",
}
SECRET_PATTERN = re.compile(r"(?:sk-[A-Za-z0-9]{12,}|(?:password|token|secret|api[_-]?key)\s*[:=]\s*\S+)", re.I)


class CaptureIncompleteError(ValueError):
    """An attempt cannot be completed because durable capture state is incomplete."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _digest(value: object, label: str) -> str:
    value = _text(value, label)
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _timestamp(value: object, label: str) -> str:
    return validate_timestamp(_text(value, label), label)


def _ref(value: object, label: str = "artifact_ref") -> ArtifactRef:
    if isinstance(value, ArtifactRef):
        return value
    if isinstance(value, Mapping):
        return ArtifactRef.from_dict(value)
    raise ValueError(f"{label} must be an ArtifactRef")


def _json(value: object, label: str) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Mapping):
        return {str(key): _json(child, f"{label}.{key}") for key, child in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json(child, label) for child in value]
    raise ValueError(f"{label} must be JSON-compatible")


def _redact_check(value: object, path: str = "checkpoint") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key).lower()
            if key_text in SENSITIVE_KEYS or any(
                term in key_text for term in ("prompt", "password", "secret", "credential", "reasoning")
            ):
                raise ValueError(f"redaction rejected sensitive field: {path}.{key}")
            _redact_check(child, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            _redact_check(child, f"{path}[{index}]")
    elif isinstance(value, str) and SECRET_PATTERN.search(value):
        raise ValueError(f"redaction rejected secret-like value at {path}")


@dataclass(frozen=True, slots=True)
class SourceCapture:
    capture_id: str
    run_id: str
    attempt_id: str
    locator: Mapping[str, str]
    content_digest: str
    media_type: str
    size_bytes: int
    captured_at: str
    method_id: str
    provider_id: str
    provenance_group: str
    status: str = "committed"
    selector: Mapping[str, object] = field(default_factory=dict)
    license_note: str | None = None
    access_note: str | None = None
    parser_version: str = "unparsed"
    origin_capture_id: str | None = None
    artifact_ref: ArtifactRef | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        for value, label in (
            (self.capture_id, "capture_id"),
            (self.run_id, "run_id"),
            (self.attempt_id, "attempt_id"),
            (self.method_id, "method_id"),
            (self.provider_id, "provider_id"),
            (self.provenance_group, "provenance_group"),
            (self.media_type, "media_type"),
            (self.parser_version, "parser_version"),
        ):
            validate_identifier(value, label) if label in {"capture_id", "run_id", "attempt_id"} else _text(
                value, label
            )
        if not isinstance(self.locator, Mapping) or not self.locator:
            raise ValueError("locator must be a non-empty mapping")
        for key, value in self.locator.items():
            _text(key, "locator key")
            _text(value, "locator value")
        _digest(self.content_digest, "content_digest")
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int) or self.size_bytes < 0:
            raise ValueError("size_bytes must be non-negative")
        _timestamp(self.captured_at, "captured_at")
        if self.status not in {"committed", "superseded", "quarantined", "unavailable"}:
            raise ValueError("invalid capture status")
        _json(self.selector, "selector")
        for value, label in (
            (self.license_note, "license_note"),
            (self.access_note, "access_note"),
            (self.origin_capture_id, "origin_capture_id"),
        ):
            if value is not None:
                _text(value, label)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "capture_id": self.capture_id,
            "run_id": self.run_id,
            "attempt_id": self.attempt_id,
            "locator": dict(self.locator),
            "content_digest": self.content_digest,
            "media_type": self.media_type,
            "size_bytes": self.size_bytes,
            "captured_at": self.captured_at,
            "method_id": self.method_id,
            "provider_id": self.provider_id,
            "provenance_group": self.provenance_group,
            "status": self.status,
            "selector": dict(self.selector),
            "license_note": self.license_note,
            "access_note": self.access_note,
            "parser_version": self.parser_version,
            "origin_capture_id": self.origin_capture_id,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SourceCapture":
        data = dict(value)
        if data.pop("schema_version", None) != 1:
            raise ValueError("unsupported source capture schema")
        data.pop("artifact_ref", None)
        return cls(**data)


@dataclass(frozen=True, slots=True)
class AcquisitionReceipt:
    receipt_id: str
    capture_id: str | None
    attempt_id: str
    method_id: str
    provider_id: str
    requested_at: str
    completed_at: str | None
    status: str
    failure_history: tuple[Mapping[str, str], ...] = ()
    selector: Mapping[str, object] = field(default_factory=dict)
    artifact_ref: ArtifactRef | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        for value, label in (
            (self.receipt_id, "receipt_id"),
            (self.attempt_id, "attempt_id"),
            (self.method_id, "method_id"),
            (self.provider_id, "provider_id"),
        ):
            validate_identifier(value, label)
        if self.capture_id is not None:
            validate_identifier(self.capture_id, "capture_id")
        _timestamp(self.requested_at, "requested_at")
        if self.completed_at is not None:
            _timestamp(self.completed_at, "completed_at")
        if self.status not in {"succeeded", "failed", "blocked", "unknown"}:
            raise ValueError("invalid acquisition status")
        if not isinstance(self.failure_history, tuple) or any(
            not isinstance(item, Mapping) for item in self.failure_history
        ):
            raise ValueError("failure_history must be a tuple of mappings")
        _json(self.selector, "selector")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "receipt_id": self.receipt_id,
            "capture_id": self.capture_id,
            "attempt_id": self.attempt_id,
            "method_id": self.method_id,
            "provider_id": self.provider_id,
            "requested_at": self.requested_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "failure_history": [dict(item) for item in self.failure_history],
            "selector": dict(self.selector),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AcquisitionReceipt":
        data = dict(value)
        if data.pop("schema_version", None) != 1:
            raise ValueError("unsupported acquisition receipt schema")
        data["failure_history"] = tuple(data.get("failure_history", ()))
        data.pop("artifact_ref", None)
        return cls(**data)


@dataclass(frozen=True, slots=True)
class AnalysisCheckpoint:
    checkpoint_id: str
    run_id: str
    attempt_id: str
    action_id: str
    scope: str
    source_capture_refs: tuple[ArtifactRef | str, ...]
    facts: tuple[Mapping[str, object], ...]
    hypotheses: tuple[Mapping[str, object], ...] = ()
    contradictions: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    method_outcomes: tuple[Mapping[str, object], ...] = ()
    next_actions: tuple[str, ...] = ()
    created_at: str = field(default_factory=utc_now)
    artifact_ref: ArtifactRef | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        for value, label in (
            (self.checkpoint_id, "checkpoint_id"),
            (self.run_id, "run_id"),
            (self.attempt_id, "attempt_id"),
            (self.action_id, "action_id"),
        ):
            validate_identifier(value, label)
        _text(self.scope, "scope")
        for sequence, label in (
            (self.source_capture_refs, "source_capture_refs"),
            (self.facts, "facts"),
            (self.hypotheses, "hypotheses"),
            (self.contradictions, "contradictions"),
            (self.open_questions, "open_questions"),
            (self.method_outcomes, "method_outcomes"),
            (self.next_actions, "next_actions"),
        ):
            if not isinstance(sequence, tuple):
                raise ValueError(f"{label} must be a tuple")
        _timestamp(self.created_at, "created_at")
        _redact_check(self.to_dict())
        if len(str(self.to_dict())) > 256_000 or len(self.facts) + len(self.hypotheses) > 256:
            raise ValueError("checkpoint exceeds bounded limits")

    def validate_capture_runs(self, run_id: str) -> None:
        for reference in self.source_capture_refs:
            if isinstance(reference, ArtifactRef) and reference.round_id != run_id:
                raise ValueError("checkpoint capture ref must belong to same run")
            if isinstance(reference, str) and not reference.startswith(f"{run_id}:"):
                raise ValueError("checkpoint capture ref must belong to same run")

    def to_dict(self) -> dict[str, Any]:
        def serial(value: object) -> object:
            return value.to_dict() if isinstance(value, ArtifactRef) else value

        return {
            "schema_version": 1,
            "checkpoint_id": self.checkpoint_id,
            "run_id": self.run_id,
            "attempt_id": self.attempt_id,
            "action_id": self.action_id,
            "scope": self.scope,
            "source_capture_refs": [serial(ref) for ref in self.source_capture_refs],
            "facts": [dict(item) for item in self.facts],
            "hypotheses": [dict(item) for item in self.hypotheses],
            "contradictions": list(self.contradictions),
            "open_questions": list(self.open_questions),
            "method_outcomes": [dict(item) for item in self.method_outcomes],
            "next_actions": list(self.next_actions),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AnalysisCheckpoint":
        data = dict(value)
        if data.pop("schema_version", None) != 1:
            raise ValueError("unsupported analysis checkpoint schema")
        data["source_capture_refs"] = tuple(data.get("source_capture_refs", ()))
        for key in ("facts", "hypotheses", "contradictions", "open_questions", "method_outcomes", "next_actions"):
            data[key] = tuple(data.get(key, ()))
        data.pop("artifact_ref", None)
        return cls(**data)


@dataclass(frozen=True, slots=True)
class ResumeBundle:
    capture: SourceCapture
    receipt: AcquisitionReceipt
    checkpoint: AnalysisCheckpoint


class DurableSourceCaptureService:
    """Persist and validate source lifecycle artifacts in a canonical ledger."""

    def __init__(self, ledger: RunLedger, store: ContentAddressedStore) -> None:
        self.ledger = ledger
        self.store = store

    def capture(
        self,
        *,
        run_id: str,
        capture_id: str,
        attempt_id: str,
        data: bytes,
        media_type: str,
        method_id: str,
        provider_id: str,
        expected_revision: int,
        locator: Mapping[str, str] | None = None,
        **metadata: Any,
    ) -> SourceCapture:
        content = self.store.ingest(data, media_type)
        record = SourceCapture(
            capture_id,
            run_id,
            attempt_id,
            locator or {"cas": content.locator},
            content.digest,
            content.media_type,
            content.byte_size,
            utc_now(),
            method_id,
            provider_id,
            metadata.pop("provenance_group", provider_id),
            metadata.pop("status", "committed"),
            **metadata,
        )
        artifact = self.ledger.append_artifact_with_content(
            run_id,
            capture_id,
            SOURCE_CAPTURE_KIND,
            record.to_dict(),
            content,
            self.store,
            expected_revision=expected_revision,
        )
        result = SourceCapture.from_dict(record.to_dict())
        object.__setattr__(result, "artifact_ref", ArtifactRef(run_id, artifact.id, artifact.revision))
        return result

    persist_capture = capture

    def receipt(
        self,
        *,
        run_id: str,
        receipt_id: str,
        capture: SourceCapture,
        attempt_id: str,
        method_id: str,
        provider_id: str,
        expected_revision: int,
        status: str = "succeeded",
        failure_history: Sequence[Mapping[str, str]] = (),
        **metadata: Any,
    ) -> AcquisitionReceipt:
        if capture.run_id != run_id or capture.attempt_id != attempt_id or capture.artifact_ref is None:
            raise CaptureIncompleteError("capture_incomplete: receipt capture identity is not committed")
        payload = AcquisitionReceipt(
            receipt_id,
            capture.capture_id,
            attempt_id,
            method_id,
            provider_id,
            metadata.pop("requested_at", utc_now()),
            metadata.pop("completed_at", utc_now()) if status == "succeeded" else None,
            status,
            tuple(failure_history),
            **metadata,
        )
        artifact = self.ledger.append_artifact(
            run_id,
            receipt_id,
            ACQUISITION_RECEIPT_KIND,
            payload.to_dict(),
            parent_refs=(capture.artifact_ref,),
            expected_revision=expected_revision,
        )
        result = AcquisitionReceipt.from_dict(payload.to_dict())
        object.__setattr__(result, "artifact_ref", ArtifactRef(run_id, artifact.id, artifact.revision))
        return result

    persist_receipt = receipt

    def checkpoint(
        self,
        *,
        run_id: str,
        checkpoint_id: str,
        attempt_id: str,
        action_id: str,
        source_capture_refs: Sequence[ArtifactRef | str],
        facts: Sequence[Mapping[str, object]],
        expected_revision: int,
        **metadata: Any,
    ) -> AnalysisCheckpoint:
        payload = AnalysisCheckpoint(
            checkpoint_id,
            run_id,
            attempt_id,
            action_id,
            metadata.pop("scope", "bounded analysis"),
            tuple(source_capture_refs),
            tuple(facts),
            tuple(metadata.pop("hypotheses", ())),
            tuple(metadata.pop("contradictions", ())),
            tuple(metadata.pop("open_questions", ())),
            tuple(metadata.pop("method_outcomes", ())),
            tuple(metadata.pop("next_actions", ())),
            metadata.pop("created_at", utc_now()),
        )
        payload.validate_capture_runs(run_id)
        parents = tuple(ref for ref in payload.source_capture_refs if isinstance(ref, ArtifactRef))
        for reference in parents:
            artifact = self.ledger.get_artifact(reference)
            if artifact.kind != SOURCE_CAPTURE_KIND or artifact.payload.get("status") != "committed":
                raise CaptureIncompleteError("capture_incomplete: checkpoint references unavailable capture")
        artifact = self.ledger.append_artifact(
            run_id,
            checkpoint_id,
            ANALYSIS_CHECKPOINT_KIND,
            payload.to_dict(),
            parent_refs=parents,
            expected_revision=expected_revision,
        )
        result = AnalysisCheckpoint.from_dict(payload.to_dict())
        object.__setattr__(result, "artifact_ref", ArtifactRef(run_id, artifact.id, artifact.revision))
        return result

    persist_checkpoint = checkpoint

    def validate_worker_finished(
        self, *, run_id: str, attempt_id: str, capture_refs: Sequence[ArtifactRef], checkpoint_ref: ArtifactRef | None
    ) -> dict[str, Any]:
        if checkpoint_ref is None:
            raise CaptureIncompleteError("capture_incomplete: checkpoint is required before worker_finished")
        if checkpoint_ref.round_id != run_id:
            raise CaptureIncompleteError("capture_incomplete: checkpoint belongs to another run")
        checkpoint = AnalysisCheckpoint.from_dict(self.ledger.get_artifact(checkpoint_ref).payload)
        if checkpoint.attempt_id != attempt_id:
            raise CaptureIncompleteError("capture_incomplete: checkpoint belongs to another attempt")
        for reference in capture_refs:
            if reference.round_id != run_id or self.ledger.get_artifact(reference).kind != SOURCE_CAPTURE_KIND:
                raise CaptureIncompleteError("capture_incomplete: capture reference is not committed in this run")
        return {
            "status": "accepted",
            "capture_refs": [ref.to_dict() for ref in capture_refs],
            "checkpoint_ref": checkpoint_ref.to_dict(),
        }

    def resume(self, run_id: str, attempt_id: str) -> ResumeBundle:
        artifacts = self.ledger.list_artifacts(run_id)
        captures = []
        receipts = []
        checkpoints = []
        for artifact in artifacts:
            reference = ArtifactRef(run_id, artifact.id, artifact.revision)
            if artifact.kind == SOURCE_CAPTURE_KIND and artifact.payload.get("attempt_id") == attempt_id:
                value = SourceCapture.from_dict(artifact.payload)
                object.__setattr__(value, "artifact_ref", reference)
                captures.append(value)
            elif artifact.kind == ACQUISITION_RECEIPT_KIND and artifact.payload.get("attempt_id") == attempt_id:
                value = AcquisitionReceipt.from_dict(artifact.payload)
                object.__setattr__(value, "artifact_ref", reference)
                receipts.append(value)
            elif artifact.kind == ANALYSIS_CHECKPOINT_KIND and artifact.payload.get("attempt_id") == attempt_id:
                value = AnalysisCheckpoint.from_dict(artifact.payload)
                object.__setattr__(value, "artifact_ref", reference)
                checkpoints.append(value)
        if not captures or not receipts or not checkpoints:
            raise CaptureIncompleteError("capture_incomplete: no complete resumable bundle")
        return ResumeBundle(captures[-1], receipts[-1], checkpoints[-1])


__all__ = [
    "ACQUISITION_RECEIPT_KIND",
    "ANALYSIS_CHECKPOINT_KIND",
    "CaptureIncompleteError",
    "DurableSourceCaptureService",
    "ResumeBundle",
    "SourceCapture",
]
