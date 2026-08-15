"""Compile traceable intent artifacts without pretending to infer by keyword."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .domain import (
    ArtifactRef,
    ArtifactRevision,
    InvalidIdentifierError,
    RuntimeStoreError,
    validate_identifier,
)
from .intake import INPUT_LEDGER_ARTIFACT_KIND
from .run_ledger import RunLedger


INTENT_MODEL_KIND = "intent-model"
WORKING_BRIEF_KIND = "working-brief"

SIGNAL_KINDS = {
    "stated_goal",
    "constraint",
    "preference",
    "repository_fact",
    "context",
    "other",
}
HYPOTHESIS_STATUSES = {"leading", "viable", "rejected", "needs_user_input"}
CONFIDENCES = {"low", "medium", "high"}
VALIDATION_PATHS = {
    "alignment_research",
    "repository_inspection",
    "experiment",
    "user_question",
    "none",
}
DECISION_DRIVER_DIMENSIONS = {"technical", "user", "delivery", "commercial", "risk", "other"}
TRIGGER_KINDS = {"initial_request", "feedback", "new_material", "new_repository"}
WORKING_BRIEF_INPUT_ROLES = {
    "primary",
    "constraint",
    "context",
    "counterexample",
    "baseline",
    "out_of_scope",
}
CONFLICT_STATUSES = {"open", "scoped", "resolved"}
PRIOR_MATERIAL_DISPOSITIONS = {"reuse", "revalidate", "downgrade", "ignore", "overturn"}


class IntentError(RuntimeStoreError):
    """Base error for invalid intent-understanding artifacts."""


class InvalidIntentModelError(IntentError):
    """Raised when an Intent Model would lose traceability or ambiguity."""


class InvalidWorkingBriefError(IntentError):
    """Raised when a Working Brief cannot be traced to its selected inputs."""


@dataclass(frozen=True, slots=True)
class QuestionRecommendation:
    """One optional, nonblocking clarification a caller may choose to show."""

    hypothesis_ids: tuple[str, ...]
    question: str
    reason: str


class CanonicalIntentModelCompiler:
    """Validate and persist an Intent Model directly in the canonical ledger."""

    def __init__(self, ledger: RunLedger) -> None:
        if not isinstance(ledger, RunLedger):
            raise InvalidIntentModelError("canonical Intent Model compiler requires a RunLedger")
        self._ledger = ledger

    def compile(
        self,
        *,
        round_id: str,
        intent_id: str,
        context_bundle_ids: Sequence[str],
        input_ids: Sequence[str],
        analysis: Mapping[str, Any],
        expected_revision: int,
    ) -> ArtifactRevision:
        try:
            snapshot = self._ledger.load_run(round_id)
            validate_identifier(intent_id, "intent_id")
            normalized_input_ids = _identifier_tuple(input_ids, "input_ids", error_type=InvalidIntentModelError)
            normalized_bundle_ids = _identifier_tuple(
                context_bundle_ids,
                "context_bundle_ids",
                error_type=InvalidIntentModelError,
                allow_empty=True,
            )
            input_artifacts = _resolve_ledger_input_artifacts(
                snapshot.artifacts,
                normalized_input_ids,
                expect_bundle=False,
                error_type=InvalidIntentModelError,
            )
            bundle_artifacts = _resolve_ledger_input_artifacts(
                snapshot.artifacts,
                normalized_bundle_ids,
                expect_bundle=True,
                error_type=InvalidIntentModelError,
            )
            payload = _normalize_intent_analysis(
                intent_id=intent_id,
                round_id=round_id,
                context_bundle_ids=normalized_bundle_ids,
                input_ids=normalized_input_ids,
                analysis=analysis,
            )
        except (InvalidIdentifierError, TypeError, ValueError) as error:
            raise InvalidIntentModelError(str(error)) from error

        parent_refs = tuple(
            ArtifactRef(round_id, artifact.id, artifact.revision)
            for artifact in (*bundle_artifacts, *input_artifacts)
        )
        return self._ledger.append_artifact(
            round_id,
            intent_id,
            INTENT_MODEL_KIND,
            _json_ready(payload),
            parent_refs=parent_refs,
            expected_revision=expected_revision,
        )


class CanonicalWorkingBriefCompiler:
    """Compile a lineage-bound Working Brief in the canonical ledger."""

    def __init__(self, ledger: RunLedger) -> None:
        if not isinstance(ledger, RunLedger):
            raise InvalidWorkingBriefError("canonical Working Brief compiler requires a RunLedger")
        self._ledger = ledger

    def compile(
        self,
        *,
        round_id: str,
        brief_id: str,
        intent_model: ArtifactRevision,
        triggers: Sequence[Mapping[str, Any]],
        context_bundle_ids: Sequence[str],
        selected_input_ids: Sequence[str],
        input_roles: Mapping[str, str],
        material_conflicts: Sequence[Mapping[str, Any]],
        working_interpretation: str,
        technical_outcome: str,
        expected_revision: int,
        assumptions: Sequence[str] = (),
        prior_material_disposition: Mapping[str, str] | None = None,
        delivery_targets: Mapping[str, bool] | None = None,
    ) -> ArtifactRevision:
        try:
            snapshot = self._ledger.load_run(round_id)
            validate_identifier(brief_id, "brief_id")
            stored_model = _resolve_ledger_exact_artifact(snapshot.artifacts, intent_model)
            if stored_model.kind != INTENT_MODEL_KIND or stored_model.round_id != round_id:
                raise InvalidWorkingBriefError("intent_model must be an intent-model artifact in the Working Brief run")
            input_ids = _identifier_tuple(selected_input_ids, "selected_input_ids", error_type=InvalidWorkingBriefError)
            bundle_ids = _identifier_tuple(
                context_bundle_ids, "context_bundle_ids", error_type=InvalidWorkingBriefError, allow_empty=True
            )
            input_artifacts = _resolve_ledger_input_artifacts(
                snapshot.artifacts, input_ids, expect_bundle=False, error_type=InvalidWorkingBriefError
            )
            bundle_artifacts = _resolve_ledger_input_artifacts(
                snapshot.artifacts, bundle_ids, expect_bundle=True, error_type=InvalidWorkingBriefError
            )
            _ensure_brief_context_is_modeled(stored_model, input_ids, bundle_ids, input_artifacts, bundle_artifacts)
            hypotheses = _mapping_sequence(
                stored_model.payload.get("hypotheses"), "intent_model hypotheses", error_type=InvalidWorkingBriefError
            )
            leading_ids = tuple(item["id"] for item in hypotheses if item.get("status") == "leading" and isinstance(item.get("id"), str))
            viable_ids = tuple(
                item["id"]
                for item in hypotheses
                if item.get("status") in {"viable", "needs_user_input"} and isinstance(item.get("id"), str)
            )
            if len(leading_ids) != 1:
                raise InvalidWorkingBriefError("intent_model must contain exactly one leading hypothesis")
            payload = {
                "id": brief_id,
                "round_id": round_id,
                "triggers": _normalize_triggers(triggers, input_ids),
                "context_bundle_ids": bundle_ids,
                "selected_input_ids": input_ids,
                "intent_model_id": stored_model.id,
                "intent_hypothesis_ids": leading_ids,
                "viable_intent_hypothesis_ids": viable_ids,
                "input_roles": _normalize_input_roles(input_roles, input_ids),
                "working_interpretation": _nonempty_string(working_interpretation, "working_interpretation", error_type=InvalidWorkingBriefError),
                "material_conflicts": _normalize_conflicts(material_conflicts, input_ids),
                "technical_outcome": _nonempty_string(technical_outcome, "technical_outcome", error_type=InvalidWorkingBriefError),
                "non_goals": stored_model.payload.get("non_goals", ()),
                "retained_hard_constraints": stored_model.payload.get("hard_constraints", ()),
                "assumptions": _string_tuple(assumptions, "assumptions", error_type=InvalidWorkingBriefError),
                "prior_material_disposition": _normalize_disposition(prior_material_disposition),
                "delivery_targets": _normalize_delivery_targets(delivery_targets),
            }
        except (InvalidIdentifierError, TypeError, ValueError) as error:
            raise InvalidWorkingBriefError(str(error)) from error
        parent_refs = (
            ArtifactRef(round_id, stored_model.id, stored_model.revision),
            *(ArtifactRef(round_id, item.id, item.revision) for item in (*bundle_artifacts, *input_artifacts)),
        )
        return self._ledger.append_artifact(
            round_id, brief_id, WORKING_BRIEF_KIND, _json_ready(payload), parent_refs=parent_refs, expected_revision=expected_revision
        )


class QuestionPolicy:
    """Recommend at most one clarification, without pausing the research round."""

    def recommend(self, intent_model: ArtifactRevision) -> QuestionRecommendation | None:
        if intent_model.kind != INTENT_MODEL_KIND:
            raise InvalidIntentModelError("QuestionPolicy requires an intent-model artifact")
        hypothesis_statuses = {
            hypothesis["id"]: hypothesis["status"]
            for hypothesis in _mapping_sequence(
                intent_model.payload.get("hypotheses"),
                "intent_model hypotheses",
                error_type=InvalidIntentModelError,
            )
            if isinstance(hypothesis.get("id"), str) and isinstance(hypothesis.get("status"), str)
        }
        unresolved = _mapping_sequence(
            intent_model.payload.get("unresolved_interpretations"),
            "unresolved_interpretations",
            error_type=InvalidIntentModelError,
        )
        for candidate in unresolved:
            ids = _identifier_tuple(
                candidate.get("hypothesis_ids"),
                "unresolved_interpretation hypothesis_ids",
                error_type=InvalidIntentModelError,
            )
            _ensure_active_question_alternatives(
                ids,
                hypothesis_statuses,
                "unresolved_interpretation",
                InvalidIntentModelError,
            )
            if (
                candidate.get("consequential") is True
                and candidate.get("non_recoverable") is True
                and candidate.get("rankable") is False
            ):
                return QuestionRecommendation(
                    hypothesis_ids=ids,
                    question=_nonempty_string(
                        candidate.get("question"),
                        "unresolved_interpretation question",
                        error_type=InvalidIntentModelError,
                    ),
                    reason=(
                        "The choice changes the technical path, cannot be safely deferred, "
                        "and available evidence cannot rank the alternatives."
                    ),
                )
        return None


def _normalize_intent_analysis(
    *,
    intent_id: str,
    round_id: str,
    context_bundle_ids: tuple[str, ...],
    input_ids: tuple[str, ...],
    analysis: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(analysis, Mapping):
        raise InvalidIntentModelError("analysis must be a mapping")
    required = {
        "signals",
        "hypotheses",
        "desired_outcomes",
        "success_signals",
        "decision_drivers",
        "hard_constraints",
        "non_goals",
        "unresolved_interpretations",
    }
    _require_exact_keys(analysis, required, "analysis", InvalidIntentModelError)
    signals = _normalize_signals(analysis["signals"], input_ids)
    hypotheses = _normalize_hypotheses(analysis["hypotheses"], input_ids)
    return {
        "id": intent_id,
        "round_id": round_id,
        "context_bundle_ids": context_bundle_ids,
        "input_ids": input_ids,
        "signals": signals,
        "hypotheses": hypotheses,
        "desired_outcomes": _string_tuple(
            analysis["desired_outcomes"], "desired_outcomes", error_type=InvalidIntentModelError
        ),
        "success_signals": _string_tuple(
            analysis["success_signals"], "success_signals", error_type=InvalidIntentModelError
        ),
        "decision_drivers": _normalize_decision_drivers(
            analysis["decision_drivers"], input_ids
        ),
        "hard_constraints": _string_tuple(
            analysis["hard_constraints"], "hard_constraints", error_type=InvalidIntentModelError
        ),
        "non_goals": _string_tuple(
            analysis["non_goals"], "non_goals", error_type=InvalidIntentModelError
        ),
        "unresolved_interpretations": _normalize_unresolved(
            analysis["unresolved_interpretations"], hypotheses
        ),
    }


def _normalize_signals(
    value: Any,
    input_ids: tuple[str, ...],
) -> list[dict[str, str]]:
    signals = _mapping_sequence(value, "signals", error_type=InvalidIntentModelError)
    if not signals:
        raise InvalidIntentModelError("analysis must contain at least one signal")
    normalized: list[dict[str, str]] = []
    for index, signal in enumerate(signals):
        _require_exact_keys(
            signal,
            {"input_id", "observation", "kind", "authority_boundary"},
            f"signals[{index}]",
            InvalidIntentModelError,
        )
        input_id = _identifier(
            signal["input_id"], f"signals[{index}].input_id", InvalidIntentModelError
        )
        if input_id not in input_ids:
            raise InvalidIntentModelError(
                f"signals[{index}].input_id must be one of the selected input_ids"
            )
        kind = _nonempty_string(
            signal["kind"], f"signals[{index}].kind", error_type=InvalidIntentModelError
        )
        if kind not in SIGNAL_KINDS:
            raise InvalidIntentModelError(f"signals[{index}].kind is unsupported: {kind}")
        normalized.append(
            {
                "input_id": input_id,
                "observation": _nonempty_string(
                    signal["observation"],
                    f"signals[{index}].observation",
                    error_type=InvalidIntentModelError,
                ),
                "kind": kind,
                "authority_boundary": _nonempty_string(
                    signal["authority_boundary"],
                    f"signals[{index}].authority_boundary",
                    error_type=InvalidIntentModelError,
                ),
            }
        )
    return normalized


def _normalize_hypotheses(value: Any, input_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    hypotheses = _mapping_sequence(value, "hypotheses", error_type=InvalidIntentModelError)
    if not hypotheses:
        raise InvalidIntentModelError("analysis must contain at least one hypothesis")
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    leading_count = 0
    for index, hypothesis in enumerate(hypotheses):
        _require_exact_keys(
            hypothesis,
            {
                "id",
                "interpretation",
                "status",
                "signal_refs",
                "confidence",
                "decision_consequence",
                "validation",
            },
            f"hypotheses[{index}]",
            InvalidIntentModelError,
        )
        hypothesis_id = _identifier(
            hypothesis["id"], f"hypotheses[{index}].id", InvalidIntentModelError
        )
        if hypothesis_id in seen_ids:
            raise InvalidIntentModelError(f"duplicate hypothesis id: {hypothesis_id}")
        seen_ids.add(hypothesis_id)
        signal_refs = _identifier_tuple(
            hypothesis["signal_refs"],
            f"hypotheses[{index}].signal_refs",
            error_type=InvalidIntentModelError,
        )
        unknown_refs = set(signal_refs) - set(input_ids)
        if unknown_refs:
            raise InvalidIntentModelError(
                f"hypotheses[{index}].signal_refs contain unknown inputs: {sorted(unknown_refs)}"
            )
        status = _nonempty_string(
            hypothesis["status"], f"hypotheses[{index}].status", error_type=InvalidIntentModelError
        )
        if status not in HYPOTHESIS_STATUSES:
            raise InvalidIntentModelError(f"hypotheses[{index}].status is unsupported: {status}")
        if status == "leading":
            leading_count += 1
        confidence = _nonempty_string(
            hypothesis["confidence"],
            f"hypotheses[{index}].confidence",
            error_type=InvalidIntentModelError,
        )
        if confidence not in CONFIDENCES:
            raise InvalidIntentModelError(
                f"hypotheses[{index}].confidence is unsupported: {confidence}"
            )
        validation = _nonempty_string(
            hypothesis["validation"],
            f"hypotheses[{index}].validation",
            error_type=InvalidIntentModelError,
        )
        if validation not in VALIDATION_PATHS:
            raise InvalidIntentModelError(
                f"hypotheses[{index}].validation is unsupported: {validation}"
            )
        normalized.append(
            {
                "id": hypothesis_id,
                "interpretation": _nonempty_string(
                    hypothesis["interpretation"],
                    f"hypotheses[{index}].interpretation",
                    error_type=InvalidIntentModelError,
                ),
                "status": status,
                "signal_refs": signal_refs,
                "confidence": confidence,
                "decision_consequence": _nonempty_string(
                    hypothesis["decision_consequence"],
                    f"hypotheses[{index}].decision_consequence",
                    error_type=InvalidIntentModelError,
                ),
                "validation": validation,
            }
        )
    if leading_count != 1:
        raise InvalidIntentModelError("analysis must contain exactly one leading hypothesis")
    return normalized


def _normalize_decision_drivers(value: Any, input_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    drivers = _mapping_sequence(value, "decision_drivers", error_type=InvalidIntentModelError)
    normalized: list[dict[str, Any]] = []
    for index, driver in enumerate(drivers):
        _require_exact_keys(
            driver,
            {"dimension", "statement", "signal_refs"},
            f"decision_drivers[{index}]",
            InvalidIntentModelError,
        )
        dimension = _nonempty_string(
            driver["dimension"],
            f"decision_drivers[{index}].dimension",
            error_type=InvalidIntentModelError,
        )
        if dimension not in DECISION_DRIVER_DIMENSIONS:
            raise InvalidIntentModelError(
                f"decision_drivers[{index}].dimension is unsupported: {dimension}"
            )
        signal_refs = _identifier_tuple(
            driver["signal_refs"],
            f"decision_drivers[{index}].signal_refs",
            error_type=InvalidIntentModelError,
            allow_empty=True,
        )
        unknown_refs = set(signal_refs) - set(input_ids)
        if unknown_refs:
            raise InvalidIntentModelError(
                f"decision_drivers[{index}].signal_refs contain unknown inputs: {sorted(unknown_refs)}"
            )
        normalized.append(
            {
                "dimension": dimension,
                "statement": _nonempty_string(
                    driver["statement"],
                    f"decision_drivers[{index}].statement",
                    error_type=InvalidIntentModelError,
                ),
                "signal_refs": signal_refs,
            }
        )
    return normalized


def _normalize_unresolved(value: Any, hypotheses: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    unresolved = _mapping_sequence(
        value, "unresolved_interpretations", error_type=InvalidIntentModelError
    )
    hypothesis_statuses = {
        hypothesis["id"]: hypothesis["status"]
        for hypothesis in hypotheses
        if isinstance(hypothesis.get("id"), str) and isinstance(hypothesis.get("status"), str)
    }
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(unresolved):
        _require_exact_keys(
            item,
            {"hypothesis_ids", "question", "consequential", "non_recoverable", "rankable"},
            f"unresolved_interpretations[{index}]",
            InvalidIntentModelError,
        )
        ids = _identifier_tuple(
            item["hypothesis_ids"],
            f"unresolved_interpretations[{index}].hypothesis_ids",
            error_type=InvalidIntentModelError,
        )
        _ensure_active_question_alternatives(
            ids,
            hypothesis_statuses,
            f"unresolved_interpretations[{index}]",
            InvalidIntentModelError,
        )
        booleans: dict[str, bool] = {}
        for field in ("consequential", "non_recoverable", "rankable"):
            if not isinstance(item[field], bool):
                raise InvalidIntentModelError(
                    f"unresolved_interpretations[{index}].{field} must be a bool"
                )
            booleans[field] = item[field]
        normalized.append(
            {
                "hypothesis_ids": ids,
                "question": _nonempty_string(
                    item["question"],
                    f"unresolved_interpretations[{index}].question",
                    error_type=InvalidIntentModelError,
                ),
                **booleans,
            }
        )
    return normalized


def _normalize_triggers(value: Any, selected_input_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    triggers = _mapping_sequence(value, "triggers", error_type=InvalidWorkingBriefError)
    if not triggers:
        raise InvalidWorkingBriefError("Working Brief requires at least one trigger")
    normalized: list[dict[str, Any]] = []
    for index, trigger in enumerate(triggers):
        _require_exact_keys(
            trigger,
            {"kind", "text", "input_ids"},
            f"triggers[{index}]",
            InvalidWorkingBriefError,
        )
        kind = _nonempty_string(
            trigger["kind"], f"triggers[{index}].kind", error_type=InvalidWorkingBriefError
        )
        if kind not in TRIGGER_KINDS:
            raise InvalidWorkingBriefError(f"triggers[{index}].kind is unsupported: {kind}")
        trigger_ids = _identifier_tuple(
            trigger["input_ids"],
            f"triggers[{index}].input_ids",
            error_type=InvalidWorkingBriefError,
        )
        if not set(trigger_ids) <= set(selected_input_ids):
            raise InvalidWorkingBriefError(
                f"triggers[{index}].input_ids must be selected Working Brief inputs"
            )
        normalized.append(
            {
                "kind": kind,
                "text": _nonempty_string(
                    trigger["text"], f"triggers[{index}].text", error_type=InvalidWorkingBriefError
                ),
                "input_ids": trigger_ids,
            }
        )
    return normalized


def _normalize_input_roles(
    value: Mapping[str, str], selected_input_ids: tuple[str, ...]
) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise InvalidWorkingBriefError("input_roles must be a mapping")
    if set(value) != set(selected_input_ids):
        raise InvalidWorkingBriefError("input_roles must cover exactly the selected_input_ids")
    normalized: dict[str, str] = {}
    for input_id in selected_input_ids:
        role = _nonempty_string(
            value[input_id], f"input_roles[{input_id}]", error_type=InvalidWorkingBriefError
        )
        if role not in WORKING_BRIEF_INPUT_ROLES:
            raise InvalidWorkingBriefError(f"input_roles[{input_id}] is unsupported: {role}")
        normalized[input_id] = role
    return normalized


def _normalize_conflicts(
    value: Any, selected_input_ids: tuple[str, ...]
) -> list[dict[str, Any]]:
    conflicts = _mapping_sequence(value, "material_conflicts", error_type=InvalidWorkingBriefError)
    normalized: list[dict[str, Any]] = []
    for index, conflict in enumerate(conflicts):
        _require_exact_keys(
            conflict,
            {"input_ids", "status", "note"},
            f"material_conflicts[{index}]",
            InvalidWorkingBriefError,
        )
        ids = _identifier_tuple(
            conflict["input_ids"],
            f"material_conflicts[{index}].input_ids",
            error_type=InvalidWorkingBriefError,
        )
        if len(ids) < 2:
            raise InvalidWorkingBriefError(
                f"material_conflicts[{index}] must cite at least two inputs"
            )
        if not set(ids) <= set(selected_input_ids):
            raise InvalidWorkingBriefError(
                f"material_conflicts[{index}].input_ids must be selected inputs"
            )
        status = _nonempty_string(
            conflict["status"],
            f"material_conflicts[{index}].status",
            error_type=InvalidWorkingBriefError,
        )
        if status not in CONFLICT_STATUSES:
            raise InvalidWorkingBriefError(
                f"material_conflicts[{index}].status is unsupported: {status}"
            )
        normalized.append(
            {
                "input_ids": ids,
                "status": status,
                "note": _nonempty_string(
                    conflict["note"],
                    f"material_conflicts[{index}].note",
                    error_type=InvalidWorkingBriefError,
                ),
            }
        )
    return normalized


def _normalize_disposition(value: Mapping[str, str] | None) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise InvalidWorkingBriefError("prior_material_disposition must be a mapping")
    normalized: dict[str, str] = {}
    for artifact_id, disposition in value.items():
        normalized_id = _identifier(
            artifact_id, "prior_material_disposition artifact id", InvalidWorkingBriefError
        )
        normalized_value = _nonempty_string(
            disposition,
            f"prior_material_disposition[{normalized_id}]",
            error_type=InvalidWorkingBriefError,
        )
        if normalized_value not in PRIOR_MATERIAL_DISPOSITIONS:
            raise InvalidWorkingBriefError(
                f"prior_material_disposition[{normalized_id}] is unsupported: {normalized_value}"
            )
        normalized[normalized_id] = normalized_value
    return normalized


def _normalize_delivery_targets(value: Mapping[str, bool] | None) -> dict[str, bool]:
    defaults = {
        "technical_research_package": True,
        "human_brief": True,
        "openspec": False,
    }
    if value is None:
        return defaults
    if not isinstance(value, Mapping):
        raise InvalidWorkingBriefError("delivery_targets must be a mapping")
    _require_exact_keys(value, set(defaults), "delivery_targets", InvalidWorkingBriefError)
    if any(not isinstance(enabled, bool) for enabled in value.values()):
        raise InvalidWorkingBriefError("delivery_targets values must be bools")
    return {key: value[key] for key in defaults}


def _resolve_ledger_input_artifacts(
    artifacts: Sequence[ArtifactRevision],
    input_ids: tuple[str, ...],
    *,
    expect_bundle: bool,
    error_type: type[IntentError],
) -> tuple[ArtifactRevision, ...]:
    resolved: list[ArtifactRevision] = []
    for input_id in input_ids:
        matches = [
            artifact
            for artifact in artifacts
            if artifact.id == input_id and artifact.kind == INPUT_LEDGER_ARTIFACT_KIND
        ]
        artifact = max(matches, key=lambda item: item.revision, default=None)
        if artifact is None:
            raise error_type(f"selected input does not resolve to an Input Ledger entry: {input_id}")
        is_bundle = artifact.payload.get("kind") == "context_bundle"
        if is_bundle != expect_bundle:
            expected = "a Context Bundle" if expect_bundle else "a non-bundle input"
            raise error_type(f"selected input {input_id} must resolve to {expected}")
        resolved.append(artifact)
    return tuple(resolved)


def _resolve_ledger_exact_artifact(
    artifacts: Sequence[ArtifactRevision], artifact: ArtifactRevision
) -> ArtifactRevision:
    if not isinstance(artifact, ArtifactRevision):
        raise InvalidWorkingBriefError("intent_model must be an ArtifactRevision")
    for stored in artifacts:
        if stored.id == artifact.id and stored.revision == artifact.revision:
            if stored != artifact:
                raise InvalidWorkingBriefError("intent_model does not match its stored revision")
            return stored
    raise InvalidWorkingBriefError("intent_model has not been persisted in this RunLedger")


def _ensure_brief_context_is_modeled(
    intent_model: ArtifactRevision,
    selected_input_ids: tuple[str, ...],
    context_bundle_ids: tuple[str, ...],
    input_artifacts: tuple[ArtifactRevision, ...],
    bundle_artifacts: tuple[ArtifactRevision, ...],
) -> None:
    """Prevent a brief from mixing a model with material it did not interpret."""

    modeled_input_ids = _identifier_tuple(
        intent_model.payload.get("input_ids"),
        "intent_model input_ids",
        error_type=InvalidWorkingBriefError,
    )
    modeled_bundle_ids = _identifier_tuple(
        intent_model.payload.get("context_bundle_ids"),
        "intent_model context_bundle_ids",
        error_type=InvalidWorkingBriefError,
        allow_empty=True,
    )
    unmodeled_inputs = set(selected_input_ids) - set(modeled_input_ids)
    if unmodeled_inputs:
        raise InvalidWorkingBriefError(
            "Working Brief cannot select inputs absent from the Intent Model: "
            f"{sorted(unmodeled_inputs)}"
        )
    unmodeled_bundles = set(context_bundle_ids) - set(modeled_bundle_ids)
    if unmodeled_bundles:
        raise InvalidWorkingBriefError(
            "Working Brief cannot select Context Bundles absent from the Intent Model: "
            f"{sorted(unmodeled_bundles)}"
        )
    modeled_refs = set(intent_model.parent_refs)
    selected_artifacts = (*bundle_artifacts, *input_artifacts)
    changed_refs = [
        artifact.id
        for artifact in selected_artifacts
        if ArtifactRef(artifact.round_id, artifact.id, artifact.revision) not in modeled_refs
    ]
    if changed_refs:
        raise InvalidWorkingBriefError(
            "Working Brief inputs have changed since the Intent Model; compile a new Intent Model: "
            f"{sorted(changed_refs)}"
        )


def _ensure_active_question_alternatives(
    hypothesis_ids: tuple[str, ...],
    hypothesis_statuses: Mapping[str, str],
    label: str,
    error_type: type[IntentError],
) -> None:
    if len(hypothesis_ids) < 2:
        raise error_type(f"{label} must compare at least two hypotheses")
    if not set(hypothesis_ids) <= set(hypothesis_statuses):
        raise error_type(f"{label} references an unknown hypothesis")
    statuses = {hypothesis_statuses[hypothesis_id] for hypothesis_id in hypothesis_ids}
    if not statuses <= {"leading", "viable", "needs_user_input"}:
        raise error_type(f"{label} cannot include a rejected hypothesis")
    if not statuses & {"viable", "needs_user_input"}:
        raise error_type(f"{label} must include a viable alternative")


def _mapping_sequence(value: Any, label: str, *, error_type: type[IntentError]) -> list[Mapping[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise error_type(f"{label} must be a sequence of mappings")
    normalized: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise error_type(f"{label}[{index}] must be a mapping")
        normalized.append(item)
    return normalized


def _identifier_tuple(
    value: Any,
    label: str,
    *,
    error_type: type[IntentError],
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise error_type(f"{label} must be a sequence of identifiers")
    result = tuple(_identifier(item, label, error_type) for item in value)
    if not result and not allow_empty:
        raise error_type(f"{label} must not be empty")
    if len(set(result)) != len(result):
        raise error_type(f"{label} must not contain duplicate identifiers")
    return result


def _string_tuple(
    value: Any,
    label: str,
    *,
    error_type: type[IntentError],
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise error_type(f"{label} must be a sequence of strings")
    return tuple(_nonempty_string(item, label, error_type=error_type) for item in value)


def _identifier(value: Any, label: str, error_type: type[IntentError]) -> str:
    try:
        return validate_identifier(value, label)
    except InvalidIdentifierError as error:
        raise error_type(str(error)) from error


def _nonempty_string(value: Any, label: str, *, error_type: type[IntentError]) -> str:
    if not isinstance(value, str) or not value.strip():
        raise error_type(f"{label} must be a nonempty string")
    return value


def _require_exact_keys(
    value: Mapping[str, Any],
    expected: set[str],
    label: str,
    error_type: type[IntentError],
) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise error_type(f"{label} has unexpected keys; missing={missing}, extra={extra}")


def _json_ready(value: Any) -> Any:
    """Translate validation-friendly tuples into the store's JSON input shape."""

    if isinstance(value, Mapping):
        return {key: _json_ready(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_json_ready(child) for child in value]
    if isinstance(value, list):
        return [_json_ready(child) for child in value]
    return value
