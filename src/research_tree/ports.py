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
