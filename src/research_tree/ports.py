"""Stable extension ports; concrete product behavior arrives in later issues."""

from __future__ import annotations

from typing import Any, Mapping, Protocol


class IntakePort(Protocol):
    def ingest(self, context: Mapping[str, Any]) -> Mapping[str, Any]: ...


class IntentPort(Protocol):
    def model(self, context: Mapping[str, Any]) -> Mapping[str, Any]: ...


class IntentAnalysisPort(Protocol):
    """Optional semantic adapter; compilers validate its structured output."""

    def analyze(self, context: Mapping[str, Any]) -> Mapping[str, Any]: ...


class StrategyPort(Protocol):
    def plan(self, intent_model: Mapping[str, Any]) -> Mapping[str, Any]: ...


class ResearchPort(Protocol):
    def investigate(self, work_item: Mapping[str, Any]) -> Mapping[str, Any]: ...


class ConvergencePort(Protocol):
    def decide(self, findings: Mapping[str, Any]) -> Mapping[str, Any]: ...


class DeliveryPort(Protocol):
    def render(self, decisions: Mapping[str, Any]) -> Mapping[str, Any]: ...


class VerificationPort(Protocol):
    def verify(self, package: Mapping[str, Any]) -> Mapping[str, Any]: ...


class SourceAcquisitionPort(Protocol):
    """Obtain a selected source without defining a mandatory research path."""

    def acquire(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...


class PrimarySourceValidationPort(Protocol):
    """Check whether a selected source is primary for the claimed evidence."""

    def validate_primary_source(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...


class EvidenceReviewPort(Protocol):
    """Review a source's applicability to one bounded technical decision."""

    def review(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...


class ProvenanceIntegrityPort(Protocol):
    """Verify recorded version and extraction provenance for selected evidence."""

    def verify_integrity(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...
