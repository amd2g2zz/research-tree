"""Compile structured research decisions into agent and requester deliveries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .decision_map import BLUEPRINT_TARGET_KIND
from .domain import (
    ArtifactRef,
    ArtifactRevision,
    InvalidIdentifierError,
    RuntimeStoreError,
    thaw_json,
    validate_identifier,
)
from .intake import INPUT_LEDGER_ARTIFACT_KIND
from .intent import INTENT_MODEL_KIND, WORKING_BRIEF_KIND
from .ledger import (
    ALTERNATIVE_DISPOSITIONS,
    ANCHOR_KINDS,
    DECISION_LEDGER_KIND,
    DECISION_STATUSES,
    FINDING_PACK_KIND,
    OPTION_EFFECTS,
    VALIDATION_KINDS,
)
from .storage import RunStore


TECHNICAL_RESEARCH_PACKAGE_KIND = "technical-research-package"
HUMAN_BRIEF_KIND = "human-brief"
READINESS_GATES = (
    "intent_alignment",
    "decision_closure",
    "traceability",
    "repository_fit",
    "implementation_readiness",
    "operational_quality",
)
READINESS_STATES = {
    "intent_alignment": {"pass", "fail", "deferred"},
    "decision_closure": {"pass", "fail", "deferred"},
    "traceability": {"pass", "fail"},
    "repository_fit": {"pass", "fail", "not_applicable"},
    "implementation_readiness": {"pass", "fail", "deferred"},
    "operational_quality": {"pass", "fail", "deferred"},
}
DESIGN_GROUPS = (
    "architecture",
    "interface",
    "state",
    "security",
    "operations",
    "migration",
    "validation",
    "other",
)


class DeliveryError(RuntimeStoreError):
    """Base error for structured delivery compilation."""


class InvalidDeliveryError(DeliveryError):
    """Raised before an untraceable or incomplete delivery is appended."""


@dataclass(frozen=True, slots=True)
class DeliveryArtifacts:
    """The two immutable outputs compiled from one structured snapshot."""

    technical_package: ArtifactRevision
    human_brief: ArtifactRevision


class DeliveryCompiler:
    """Compile canonical documents without accepting worker report prose."""

    def __init__(self, store: RunStore) -> None:
        self._store = store

    def compile(
        self,
        *,
        round_id: str,
        technical_package_id: str,
        human_brief_id: str,
        working_brief: ArtifactRevision,
        blueprint_target: ArtifactRevision,
        decision_entries: Sequence[ArtifactRevision],
        readiness: Mapping[str, Any],
    ) -> DeliveryArtifacts:
        """Append a technical package and a separate concise human brief.

        Both payloads and their validation are completed before either artifact
        is appended. The method deliberately has no worker-prose, arbitrary
        architecture-text, or OpenSpec input path.
        """

        try:
            snapshot = self._store.load_round(round_id)
            validate_identifier(technical_package_id, "technical_package_id")
            validate_identifier(human_brief_id, "human_brief_id")
            if technical_package_id == human_brief_id:
                raise InvalidDeliveryError(
                    "technical_package_id and human_brief_id must be distinct"
                )
            _ensure_id_compatibility(
                snapshot.artifacts, technical_package_id, TECHNICAL_RESEARCH_PACKAGE_KIND
            )
            _ensure_id_compatibility(snapshot.artifacts, human_brief_id, HUMAN_BRIEF_KIND)
            brief = _resolve_exact(
                snapshot.artifacts, working_brief, WORKING_BRIEF_KIND, "working_brief"
            )
            target = _resolve_exact(
                snapshot.artifacts,
                blueprint_target,
                BLUEPRINT_TARGET_KIND,
                "blueprint_target",
            )
            if brief.round_id != round_id or target.round_id != round_id:
                raise InvalidDeliveryError(
                    "working_brief and blueprint_target must belong to delivery round"
                )
            model = _resolve_brief_model(snapshot.artifacts, brief)
            _ensure_target_lineage(target, brief, model)
            inputs = _resolve_brief_inputs(snapshot.artifacts, brief)
            decisions, findings = _resolve_decisions(
                snapshot.artifacts, round_id, target, decision_entries
            )
            normalized_readiness = _normalize_readiness(readiness)
            previous_package = _latest_artifact(
                snapshot.artifacts,
                technical_package_id,
                TECHNICAL_RESEARCH_PACKAGE_KIND,
            )
            previous_human = _latest_artifact(
                snapshot.artifacts,
                human_brief_id,
                HUMAN_BRIEF_KIND,
            )
            next_package_ref = ArtifactRef(
                round_id,
                technical_package_id,
                _next_revision(snapshot.artifacts, technical_package_id),
            )
            document = _technical_document(
                round_id,
                brief,
                model,
                target,
                inputs,
                decisions,
                findings,
                normalized_readiness,
            )
            _ensure_readiness_matches_closure(
                _mapping_sequence(
                    document["blueprint_closure"], "technical package blueprint_closure", allow_empty=True
                ),
                normalized_readiness,
            )
            technical_payload = {
                "document": document,
                "markdown": _render_technical_markdown(round_id, document),
            }
            human_document = _human_document(
                brief,
                document,
                normalized_readiness,
            )
            human_payload = {
                "technical_package_ref": next_package_ref.to_dict(),
                "document": human_document,
                "markdown": _render_human_markdown(round_id, next_package_ref, human_document),
            }
            validate_technical_package_payload(technical_payload)
            validate_human_brief_payload(human_payload)
        except (InvalidIdentifierError, TypeError, ValueError) as error:
            raise InvalidDeliveryError(str(error)) from error

        source_refs = (
            (ArtifactRef(round_id, brief.id, brief.revision),)
            + (ArtifactRef(round_id, model.id, model.revision),)
            + (ArtifactRef(round_id, target.id, target.revision),)
            + tuple(ArtifactRef(round_id, item.id, item.revision) for item in inputs)
            + tuple(ArtifactRef(round_id, item.id, item.revision) for item in decisions)
            + tuple(ArtifactRef(round_id, item.id, item.revision) for item in findings)
        )
        package_refs = _unique_refs(
            (() if previous_package is None else (ArtifactRef(round_id, previous_package.id, previous_package.revision),))
            + source_refs
        )
        human_refs = _unique_refs(
            (() if previous_human is None else (ArtifactRef(round_id, previous_human.id, previous_human.revision),))
            + (next_package_ref,)
            + source_refs
        )
        technical_package = self._store.append_artifact(
            round_id,
            technical_package_id,
            TECHNICAL_RESEARCH_PACKAGE_KIND,
            technical_payload,
            parent_refs=package_refs,
        )
        if technical_package.revision != next_package_ref.revision:
            raise InvalidDeliveryError("technical package revision changed during delivery compilation")
        human_brief = self._store.append_artifact(
            round_id,
            human_brief_id,
            HUMAN_BRIEF_KIND,
            human_payload,
            parent_refs=human_refs,
        )
        return DeliveryArtifacts(technical_package=technical_package, human_brief=human_brief)


def validate_technical_package_payload(payload: Mapping[str, Any]) -> None:
    """Validate the canonical document needed by an implementation agent."""

    _require_exact_keys(payload, {"document", "markdown"}, "technical package payload")
    document = _mapping_value(payload["document"], "technical package document")
    _validate_technical_document(document)
    _nonempty_string(payload["markdown"], "technical package markdown")


def validate_human_brief_payload(payload: Mapping[str, Any]) -> None:
    """Validate the smaller requester-facing document before append."""

    _require_exact_keys(
        payload, {"technical_package_ref", "document", "markdown"}, "human brief payload"
    )
    ref = _mapping_value(payload["technical_package_ref"], "human brief technical_package_ref")
    _validate_artifact_ref(ref, "technical_package_ref")
    document = _mapping_value(payload["document"], "human brief document")
    _validate_human_document(document)
    _nonempty_string(payload["markdown"], "human brief markdown")


def _validate_technical_document(document: Mapping[str, Any]) -> None:
    _require_exact_keys(
        document,
        {
            "round_and_scope",
            "intent_basis",
            "technical_baseline",
            "blueprint_closure",
            "research_findings",
            "decision_records",
            "recommended_design",
            "implementation_plan",
            "rollout_and_observability",
            "operational_handoff",
            "risks_and_validation",
            "readiness_record",
            "traceability",
        },
        "technical package document",
    )
    _validate_round_and_scope(document["round_and_scope"])
    _validate_intent_basis(document["intent_basis"])
    _validate_technical_baseline(document["technical_baseline"])
    closure = _validate_blueprint_closure(document["blueprint_closure"])
    _validate_finding_records(document["research_findings"])
    _validate_decision_records(document["decision_records"])
    _validate_recommended_design(document["recommended_design"])
    _validate_implementation_plan(document["implementation_plan"])
    _validate_operational_contract(document["rollout_and_observability"])
    _validate_operational_handoff(document["operational_handoff"])
    _validate_risks_and_validation(document["risks_and_validation"])
    readiness = _normalize_readiness(
        _mapping_value(document["readiness_record"], "technical package readiness_record")
    )
    _ensure_readiness_matches_closure(closure, readiness)
    _validate_traceability(document["traceability"])


def _validate_human_document(document: Mapping[str, Any]) -> None:
    _require_exact_keys(
        document,
        {
            "what_was_understood",
            "recommended_direction",
            "important_choices",
            "near_term_result",
            "implementation_readiness",
            "unclosed_blueprint_items",
            "readiness_findings",
            "next_work_item_ids",
            "risks_and_uncertainty",
        },
        "human brief document",
    )
    understood = _mapping_value(document["what_was_understood"], "human what_was_understood")
    _require_exact_keys(
        understood,
        {"working_interpretation", "leading_interpretation", "material_alternatives"},
        "human what_was_understood",
    )
    _nonempty_string(understood["working_interpretation"], "human working_interpretation")
    if understood["leading_interpretation"] != "":
        _nonempty_string(understood["leading_interpretation"], "human leading_interpretation")
    for index, item in enumerate(
        _mapping_sequence(
            understood["material_alternatives"], "human material_alternatives", allow_empty=True
        )
    ):
        label = f"human material_alternatives[{index}]"
        _require_exact_keys(item, {"id", "interpretation", "status"}, label)
        _identifier(item["id"], f"{label}.id")
        _nonempty_string(item["interpretation"], f"{label}.interpretation")
        _nonempty_string(item["status"], f"{label}.status")

    direction = _mapping_value(document["recommended_direction"], "human recommended_direction")
    _require_exact_keys(
        direction, {"technical_outcome", "selected_directions"}, "human recommended_direction"
    )
    _nonempty_string(direction["technical_outcome"], "human technical_outcome")
    for index, item in enumerate(
        _mapping_sequence(direction["selected_directions"], "human selected_directions", allow_empty=True)
    ):
        label = f"human selected_directions[{index}]"
        _require_exact_keys(item, {"decision_slot_id", "selected_option", "status"}, label)
        _identifier(item["decision_slot_id"], f"{label}.decision_slot_id")
        _nonempty_string(item["selected_option"], f"{label}.selected_option")
        _enum_value(item["status"], f"{label}.status", DECISION_STATUSES)

    for index, choice in enumerate(
        _mapping_sequence(document["important_choices"], "human important_choices", allow_empty=True)
    ):
        label = f"human important_choices[{index}]"
        _require_exact_keys(choice, {"decision_slot_id", "status", "selected_option", "trade_off"}, label)
        _identifier(choice["decision_slot_id"], f"{label}.decision_slot_id")
        _enum_value(choice["status"], f"{label}.status", DECISION_STATUSES)
        if choice["selected_option"] is not None:
            _nonempty_string(choice["selected_option"], f"{label}.selected_option")
        _nonempty_string(choice["trade_off"], f"{label}.trade_off")

    near_term = _mapping_value(document["near_term_result"], "human near_term_result")
    _require_exact_keys(near_term, {"status", "milestone", "validation"}, "human near_term_result")
    _enum_value(
        near_term["status"],
        "human near_term_result.status",
        {"planned", "blocked_by_unclosed_decisions"},
    )
    _nonempty_string(near_term["milestone"], "human near_term_result.milestone")
    _nonempty_string(near_term["validation"], "human near_term_result.validation")

    implementation_readiness = _mapping_value(
        document["implementation_readiness"], "human implementation_readiness"
    )
    _require_exact_keys(
        implementation_readiness,
        {"risk_tier", "gates", "closure"},
        "human implementation_readiness",
    )
    _validate_readiness_gates(
        implementation_readiness["risk_tier"],
        implementation_readiness["gates"],
        "human implementation_readiness",
    )
    _validate_blueprint_closure(implementation_readiness["closure"])
    _validate_human_unclosed_items(document["unclosed_blueprint_items"])
    _validate_readiness_findings(document["readiness_findings"], "human readiness_findings")
    _identifier_sequence(
        document["next_work_item_ids"], "human next_work_item_ids", allow_empty=True
    )
    for index, risk in enumerate(
        _mapping_sequence(document["risks_and_uncertainty"], "human risks_and_uncertainty", allow_empty=True)
    ):
        label = f"human risks_and_uncertainty[{index}]"
        _require_exact_keys(risk, {"statement", "response"}, label)
        _nonempty_string(risk["statement"], f"{label}.statement")
        _nonempty_string(risk["response"], f"{label}.response")


def _validate_round_and_scope(value: Any) -> None:
    scope = _mapping_value(value, "technical package round_and_scope")
    _require_exact_keys(
        scope,
        {
            "round_id",
            "working_interpretation",
            "technical_outcome",
            "triggers",
            "selected_input_ids",
            "input_roles",
            "material_conflicts",
            "non_goals",
            "hard_constraints",
            "assumptions",
        },
        "technical package round_and_scope",
    )
    _identifier(scope["round_id"], "technical package round_and_scope.round_id")
    _nonempty_string(
        scope["working_interpretation"], "technical package round_and_scope.working_interpretation"
    )
    _nonempty_string(scope["technical_outcome"], "technical package round_and_scope.technical_outcome")
    _validate_json_sequence(scope["triggers"], "technical package round_and_scope.triggers")
    selected_inputs = _identifier_sequence(
        scope["selected_input_ids"], "technical package round_and_scope.selected_input_ids", allow_empty=True
    )
    roles = _mapping_value(scope["input_roles"], "technical package round_and_scope.input_roles")
    if set(roles) != set(selected_inputs):
        raise InvalidDeliveryError("technical package round_and_scope.input_roles must cover selected_input_ids")
    for input_id, role in roles.items():
        _identifier(input_id, "technical package round_and_scope.input_roles key")
        _nonempty_string(role, "technical package round_and_scope.input_roles value")
    _validate_json_sequence(scope["material_conflicts"], "technical package round_and_scope.material_conflicts")
    for field in ("non_goals", "hard_constraints", "assumptions"):
        _string_sequence(scope[field], f"technical package round_and_scope.{field}", allow_empty=True)


def _validate_intent_basis(value: Any) -> None:
    basis = _mapping_value(value, "technical package intent_basis")
    _require_exact_keys(basis, {"signals", "hypotheses", "decision_drivers"}, "technical package intent_basis")
    _validate_json_sequence(basis["signals"], "technical package intent_basis.signals")
    for index, hypothesis in enumerate(
        _mapping_sequence(basis["hypotheses"], "technical package intent_basis.hypotheses")
    ):
        label = f"technical package intent_basis.hypotheses[{index}]"
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
            label,
        )
        _identifier(hypothesis["id"], f"{label}.id")
        for field in ("interpretation", "status", "confidence", "decision_consequence", "validation"):
            _nonempty_string(hypothesis[field], f"{label}.{field}")
        _string_sequence(hypothesis["signal_refs"], f"{label}.signal_refs", allow_empty=True)
    _validate_json_sequence(basis["decision_drivers"], "technical package intent_basis.decision_drivers")


def _validate_technical_baseline(value: Any) -> None:
    baseline = _mapping_value(value, "technical package technical_baseline")
    _require_exact_keys(baseline, {"state", "repositories"}, "technical package technical_baseline")
    state = _enum_value(
        baseline["state"], "technical package technical_baseline.state", {"repository_backed", "greenfield"}
    )
    repositories = _mapping_sequence(
        baseline["repositories"], "technical package technical_baseline.repositories", allow_empty=True
    )
    if state == "repository_backed" and not repositories:
        raise InvalidDeliveryError("repository_backed technical baseline requires a repository")
    if state == "greenfield" and repositories:
        raise InvalidDeliveryError("greenfield technical baseline cannot contain repositories")
    for index, repository in enumerate(repositories):
        label = f"technical package technical_baseline.repositories[{index}]"
        _require_exact_keys(repository, {"input_id", "revision", "anchors", "facts", "unreadable"}, label)
        _identifier(repository["input_id"], f"{label}.input_id")
        _validate_json_value(repository["revision"], f"{label}.revision")
        for point_index, point in enumerate(
            _mapping_sequence(repository["anchors"], f"{label}.anchors", allow_empty=True)
        ):
            _validate_touchpoint_template(point, f"{label}.anchors[{point_index}]")
        _validate_json_sequence(repository["facts"], f"{label}.facts")
        _validate_json_sequence(repository["unreadable"], f"{label}.unreadable")


def _validate_blueprint_closure(value: Any) -> list[Mapping[str, Any]]:
    closure = _mapping_sequence(value, "technical package blueprint_closure", allow_empty=True)
    seen: set[str] = set()
    for index, item in enumerate(closure):
        label = f"technical package blueprint_closure[{index}]"
        _require_exact_keys(
            item,
            {
                "decision_slot_id",
                "priority",
                "question",
                "intent_hypothesis_ids",
                "status",
                "selected_option",
                "closure_or_fallback",
                "next_action",
            },
            label,
        )
        slot_id = _identifier(item["decision_slot_id"], f"{label}.decision_slot_id")
        if slot_id in seen:
            raise InvalidDeliveryError(f"technical package blueprint_closure repeats Decision Slot {slot_id}")
        seen.add(slot_id)
        _enum_value(item["priority"], f"{label}.priority", {"P0", "P1", "P2"})
        _nonempty_string(item["question"], f"{label}.question")
        _identifier_sequence(item["intent_hypothesis_ids"], f"{label}.intent_hypothesis_ids", allow_empty=True)
        status = _enum_value(
            item["status"], f"{label}.status", {"missing", *DECISION_STATUSES}
        )
        if status in {"selected", "conditional"}:
            _nonempty_string(item["selected_option"], f"{label}.selected_option")
        elif item["selected_option"] is not None:
            raise InvalidDeliveryError(f"{label}.selected_option must be null when status is {status}")
        _nonempty_string(item["closure_or_fallback"], f"{label}.closure_or_fallback")
        _nonempty_string(item["next_action"], f"{label}.next_action")
    return closure


def _validate_finding_records(value: Any) -> None:
    for index, finding in enumerate(
        _mapping_sequence(value, "technical package research_findings", allow_empty=True)
    ):
        label = f"technical package research_findings[{index}]"
        _require_exact_keys(
            finding,
            {
                "finding_id",
                "revision",
                "decision_slot_id",
                "observations",
                "option_effects",
                "implementation_implications",
                "remaining_uncertainties",
            },
            label,
        )
        _identifier(finding["finding_id"], f"{label}.finding_id")
        _positive_int(finding["revision"], f"{label}.revision")
        _identifier(finding["decision_slot_id"], f"{label}.decision_slot_id")
        for observation_index, observation in enumerate(
            _mapping_sequence(finding["observations"], f"{label}.observations", allow_empty=True)
        ):
            observation_label = f"{label}.observations[{observation_index}]"
            _require_exact_keys(
                observation,
                {"claim", "anchor", "applicability", "confidence", "limitation"},
                observation_label,
            )
            for field in ("claim", "applicability", "limitation"):
                _nonempty_string(observation[field], f"{observation_label}.{field}")
            _validate_anchor_template(
                observation["anchor"], f"{observation_label}.anchor", ANCHOR_KINDS - {"finding"}
            )
            _enum_value(observation["confidence"], f"{observation_label}.confidence", {"low", "medium", "high"})
        for effect_index, effect in enumerate(
            _mapping_sequence(finding["option_effects"], f"{label}.option_effects", allow_empty=True)
        ):
            effect_label = f"{label}.option_effects[{effect_index}]"
            _require_exact_keys(effect, {"option", "effect"}, effect_label)
            _nonempty_string(effect["option"], f"{effect_label}.option")
            _enum_value(effect["effect"], f"{effect_label}.effect", OPTION_EFFECTS)
        _string_sequence(
            finding["implementation_implications"], f"{label}.implementation_implications", allow_empty=True
        )
        _string_sequence(
            finding["remaining_uncertainties"], f"{label}.remaining_uncertainties", allow_empty=True
        )


def _validate_decision_records(value: Any) -> None:
    for index, record in enumerate(
        _mapping_sequence(value, "technical package decision_records", allow_empty=True)
    ):
        label = f"technical package decision_records[{index}]"
        _require_exact_keys(
            record,
            {
                "decision_id",
                "revision",
                "decision_slot_id",
                "priority",
                "kind",
                "intent_hypothesis_ids",
                "dependencies",
                "status",
                "selected_option",
                "alternatives",
                "anchors",
                "design_consequence",
                "repository_touchpoints",
                "validation",
                "change_tasks",
                "assumptions",
                "fallback",
                "reversal_condition",
            },
            label,
        )
        _identifier(record["decision_id"], f"{label}.decision_id")
        _positive_int(record["revision"], f"{label}.revision")
        _identifier(record["decision_slot_id"], f"{label}.decision_slot_id")
        priority = _enum_value(record["priority"], f"{label}.priority", {"P0", "P1", "P2"})
        _nonempty_string(record["kind"], f"{label}.kind")
        _identifier_sequence(record["intent_hypothesis_ids"], f"{label}.intent_hypothesis_ids", allow_empty=True)
        _identifier_sequence(record["dependencies"], f"{label}.dependencies", allow_empty=True)
        status = _enum_value(record["status"], f"{label}.status", DECISION_STATUSES)
        selected = record["selected_option"]
        if status in {"selected", "conditional"}:
            selected = _nonempty_string(selected, f"{label}.selected_option")
        elif selected is not None:
            raise InvalidDeliveryError(f"{label}.selected_option must be null when status is {status}")
        _validate_decision_alternatives(
            record["alternatives"], None, selected, f"{label}.alternatives"
        )
        anchors = _mapping_sequence(record["anchors"], f"{label}.anchors", allow_empty=True)
        if priority == "P0" and not anchors:
            raise InvalidDeliveryError(f"{label}.anchors must not be empty for P0")
        for anchor_index, anchor in enumerate(anchors):
            _validate_anchor_template(anchor, f"{label}.anchors[{anchor_index}]", ANCHOR_KINDS)
        _nonempty_string(record["design_consequence"], f"{label}.design_consequence")
        for point_index, point in enumerate(
            _mapping_sequence(record["repository_touchpoints"], f"{label}.repository_touchpoints", allow_empty=True)
        ):
            _validate_touchpoint_template(point, f"{label}.repository_touchpoints[{point_index}]")
        _validate_validation(record["validation"], f"{label}.validation")
        _validate_change_task_templates(record["change_tasks"], f"{label}.change_tasks")
        _string_sequence(record["assumptions"], f"{label}.assumptions", allow_empty=True)
        _nonempty_string(record["fallback"], f"{label}.fallback")
        _nonempty_string(record["reversal_condition"], f"{label}.reversal_condition")


def _validate_recommended_design(value: Any) -> None:
    design = _mapping_value(value, "technical package recommended_design")
    _require_exact_keys(design, set(DESIGN_GROUPS), "technical package recommended_design")
    for group in DESIGN_GROUPS:
        for index, entry in enumerate(
            _mapping_sequence(design[group], f"technical package recommended_design.{group}", allow_empty=True)
        ):
            label = f"technical package recommended_design.{group}[{index}]"
            _require_exact_keys(
                entry,
                {"decision_slot_id", "selected_option", "status", "design_consequence"},
                label,
            )
            _identifier(entry["decision_slot_id"], f"{label}.decision_slot_id")
            if entry["selected_option"] is not None:
                _nonempty_string(entry["selected_option"], f"{label}.selected_option")
            _enum_value(entry["status"], f"{label}.status", DECISION_STATUSES)
            _nonempty_string(entry["design_consequence"], f"{label}.design_consequence")


def _validate_implementation_plan(value: Any) -> None:
    seen_orders: set[int] = set()
    for index, item in enumerate(
        _mapping_sequence(value, "technical package implementation_plan", allow_empty=True)
    ):
        label = f"technical package implementation_plan[{index}]"
        _require_exact_keys(
            item,
            {
                "order",
                "decision_slot_id",
                "decision_id",
                "change_task_id",
                "description",
                "repository_touchpoints",
                "depends_on",
                "validation",
                "rollback",
            },
            label,
        )
        order = _positive_int(item["order"], f"{label}.order")
        if order in seen_orders:
            raise InvalidDeliveryError(f"technical package implementation_plan repeats order {order}")
        seen_orders.add(order)
        for field in ("decision_slot_id", "decision_id", "change_task_id"):
            _identifier(item[field], f"{label}.{field}")
        _nonempty_string(item["description"], f"{label}.description")
        for point_index, point in enumerate(
            _mapping_sequence(item["repository_touchpoints"], f"{label}.repository_touchpoints", allow_empty=True)
        ):
            _validate_touchpoint_template(point, f"{label}.repository_touchpoints[{point_index}]")
        _identifier_sequence(item["depends_on"], f"{label}.depends_on", allow_empty=True)
        _validate_validation(item["validation"], f"{label}.validation")
        _nonempty_string(item["rollback"], f"{label}.rollback")
    if seen_orders and seen_orders != set(range(1, len(seen_orders) + 1)):
        raise InvalidDeliveryError("technical package implementation_plan.order must be contiguous from one")


def _validate_operational_contract(value: Any) -> None:
    contract = _mapping_value(value, "technical package rollout_and_observability")
    _require_exact_keys(contract, {"rollout", "observability"}, "technical package rollout_and_observability")
    for name in ("rollout", "observability"):
        surface = _mapping_value(contract[name], f"technical package {name}")
        _require_exact_keys(surface, {"status", "items", "next_action"}, f"technical package {name}")
        status = _enum_value(surface["status"], f"technical package {name}.status", {"documented", "unknown"})
        items = _mapping_sequence(surface["items"], f"technical package {name}.items", allow_empty=True)
        if status == "documented" and not items:
            raise InvalidDeliveryError(f"technical package {name}.documented requires an item")
        for index, item in enumerate(items):
            label = f"technical package {name}.items[{index}]"
            _require_exact_keys(
                item,
                {
                    "decision_slot_id",
                    "status",
                    "selected_option",
                    "validation",
                    "fallback",
                    "change_task_ids",
                    "next_action",
                },
                label,
            )
            _identifier(item["decision_slot_id"], f"{label}.decision_slot_id")
            item_status = _enum_value(
                item["status"], f"{label}.status", {"missing", *DECISION_STATUSES}
            )
            if item_status in {"selected", "conditional"}:
                _nonempty_string(item["selected_option"], f"{label}.selected_option")
            elif item["selected_option"] is not None:
                raise InvalidDeliveryError(f"{label}.selected_option must be null when status is {item_status}")
            _validate_validation(item["validation"], f"{label}.validation")
            _nonempty_string(item["fallback"], f"{label}.fallback")
            _identifier_sequence(item["change_task_ids"], f"{label}.change_task_ids", allow_empty=True)
            _nonempty_string(item["next_action"], f"{label}.next_action")
        _nonempty_string(surface["next_action"], f"technical package {name}.next_action")


def _validate_operational_handoff(value: Any) -> None:
    handoff = _mapping_value(value, "technical package operational_handoff")
    _require_exact_keys(handoff, {"observability", "rollout", "rollback"}, "technical package operational_handoff")
    observability = _mapping_value(handoff["observability"], "technical package operational_handoff.observability")
    _require_exact_keys(
        observability,
        {"status", "items", "next_action"},
        "technical package operational_handoff.observability",
    )
    _enum_value(
        observability["status"],
        "technical package operational_handoff.observability.status",
        {"missing", "selected", "conditional", "deferred", "blocked", "unknown"},
    )
    for index, item in enumerate(
        _mapping_sequence(
            observability["items"], "technical package operational_handoff.observability.items", allow_empty=True
        )
    ):
        _validate_operational_item(item, f"technical package operational_handoff.observability.items[{index}]")
    _nonempty_string(
        observability["next_action"], "technical package operational_handoff.observability.next_action"
    )

    rollout = _mapping_value(handoff["rollout"], "technical package operational_handoff.rollout")
    _require_exact_keys(
        rollout,
        {"status", "items", "next_action"},
        "technical package operational_handoff.rollout",
    )
    _enum_value(
        rollout["status"],
        "technical package operational_handoff.rollout.status",
        {"derived_from_ordered_change_tasks", "unknown"},
    )
    for index, item in enumerate(
        _mapping_sequence(rollout["items"], "technical package operational_handoff.rollout.items", allow_empty=True)
    ):
        label = f"technical package operational_handoff.rollout.items[{index}]"
        _require_exact_keys(
            item,
            {"order", "decision_slot_id", "change_task_id", "description", "validation", "repository_touchpoints"},
            label,
        )
        _positive_int(item["order"], f"{label}.order")
        _identifier(item["decision_slot_id"], f"{label}.decision_slot_id")
        _identifier(item["change_task_id"], f"{label}.change_task_id")
        _nonempty_string(item["description"], f"{label}.description")
        _validate_validation(item["validation"], f"{label}.validation")
        for point_index, point in enumerate(
            _mapping_sequence(item["repository_touchpoints"], f"{label}.repository_touchpoints", allow_empty=True)
        ):
            _validate_touchpoint_template(point, f"{label}.repository_touchpoints[{point_index}]")
    _nonempty_string(rollout["next_action"], "technical package operational_handoff.rollout.next_action")

    for index, item in enumerate(
        _mapping_sequence(handoff["rollback"], "technical package operational_handoff.rollback", allow_empty=True)
    ):
        label = f"technical package operational_handoff.rollback[{index}]"
        _require_exact_keys(
            item,
            {"order", "decision_slot_id", "change_task_id", "fallback", "validation"},
            label,
        )
        _positive_int(item["order"], f"{label}.order")
        _identifier(item["decision_slot_id"], f"{label}.decision_slot_id")
        _identifier(item["change_task_id"], f"{label}.change_task_id")
        _nonempty_string(item["fallback"], f"{label}.fallback")
        _validate_validation(item["validation"], f"{label}.validation")


def _validate_operational_item(value: Any, label: str) -> None:
    item = _mapping_value(value, label)
    _require_exact_keys(
        item,
        {
            "decision_slot_id",
            "status",
            "selected_option",
            "validation",
            "fallback",
            "change_task_ids",
            "next_action",
        },
        label,
    )
    _identifier(item["decision_slot_id"], f"{label}.decision_slot_id")
    status = _enum_value(item["status"], f"{label}.status", {"missing", *DECISION_STATUSES})
    if status in {"selected", "conditional"}:
        _nonempty_string(item["selected_option"], f"{label}.selected_option")
    elif item["selected_option"] is not None:
        raise InvalidDeliveryError(f"{label}.selected_option must be null when status is {status}")
    _validate_validation(item["validation"], f"{label}.validation")
    _nonempty_string(item["fallback"], f"{label}.fallback")
    _identifier_sequence(item["change_task_ids"], f"{label}.change_task_ids", allow_empty=True)
    _nonempty_string(item["next_action"], f"{label}.next_action")


def _validate_risks_and_validation(value: Any) -> None:
    for index, risk in enumerate(
        _mapping_sequence(value, "technical package risks_and_validation", allow_empty=True)
    ):
        label = f"technical package risks_and_validation[{index}]"
        _require_exact_keys(risk, {"kind", "decision_slot_id", "statement", "validation", "response"}, label)
        _enum_value(risk["kind"], f"{label}.kind", {"decision_status", "assumption", "uncertainty"})
        _identifier(risk["decision_slot_id"], f"{label}.decision_slot_id")
        for field in ("statement", "validation", "response"):
            _nonempty_string(risk[field], f"{label}.{field}")


def _validate_traceability(value: Any) -> None:
    traceability = _mapping_value(value, "technical package traceability")
    _require_exact_keys(
        traceability,
        {
            "working_brief",
            "intent_model",
            "blueprint_target",
            "input_refs",
            "decision_refs",
            "finding_refs",
        },
        "technical package traceability",
    )
    for field in ("working_brief", "intent_model", "blueprint_target"):
        _validate_artifact_ref(traceability[field], f"technical package traceability.{field}")
    for field in ("input_refs", "decision_refs", "finding_refs"):
        for index, ref in enumerate(
            _mapping_sequence(traceability[field], f"technical package traceability.{field}", allow_empty=True)
        ):
            _validate_artifact_ref(ref, f"technical package traceability.{field}[{index}]")


def _validate_human_unclosed_items(value: Any) -> None:
    for index, item in enumerate(
        _mapping_sequence(value, "human unclosed_blueprint_items", allow_empty=True)
    ):
        label = f"human unclosed_blueprint_items[{index}]"
        _require_exact_keys(
            item,
            {
                "decision_slot_id",
                "priority",
                "question",
                "status",
                "closure_or_fallback",
                "next_action",
            },
            label,
        )
        _identifier(item["decision_slot_id"], f"{label}.decision_slot_id")
        _enum_value(item["priority"], f"{label}.priority", {"P0", "P1", "P2"})
        _nonempty_string(item["question"], f"{label}.question")
        _enum_value(item["status"], f"{label}.status", {"missing", "conditional", "deferred", "blocked"})
        _nonempty_string(item["closure_or_fallback"], f"{label}.closure_or_fallback")
        _nonempty_string(item["next_action"], f"{label}.next_action")


def _validate_readiness_findings(value: Any, label: str) -> None:
    for index, finding in enumerate(_mapping_sequence(value, label, allow_empty=True)):
        item_label = f"{label}[{index}]"
        _require_exact_keys(finding, {"gate", "summary"}, item_label)
        gate = _nonempty_string(finding["gate"], f"{item_label}.gate")
        if gate not in READINESS_GATES:
            raise InvalidDeliveryError(f"{item_label}.gate is unsupported: {gate}")
        _nonempty_string(finding["summary"], f"{item_label}.summary")


def _validate_readiness_gates(risk_tier: Any, gates_value: Any, label: str) -> None:
    tier = _enum_value(risk_tier, f"{label}.risk_tier", {"default", "medium", "high"})
    if tier not in {"default", "medium", "high"}:
        raise InvalidDeliveryError(f"{label}.risk_tier is unsupported")
    gates = _mapping_value(gates_value, f"{label}.gates")
    _require_exact_keys(gates, set(READINESS_GATES), f"{label}.gates")
    for gate in READINESS_GATES:
        _enum_value(gates[gate], f"{label}.gates.{gate}", READINESS_STATES[gate])


def _validate_change_task_templates(value: Any, label: str) -> None:
    seen: set[str] = set()
    for index, task in enumerate(_mapping_sequence(value, label, allow_empty=True)):
        item_label = f"{label}[{index}]"
        _require_exact_keys(
            task,
            {"id", "description", "acceptance_oracle", "repository_touchpoints"},
            item_label,
        )
        task_id = _identifier(task["id"], f"{item_label}.id")
        if task_id in seen:
            raise InvalidDeliveryError(f"{label} repeats change task id {task_id}")
        seen.add(task_id)
        _nonempty_string(task["description"], f"{item_label}.description")
        _nonempty_string(task["acceptance_oracle"], f"{item_label}.acceptance_oracle")
        for point_index, point in enumerate(
            _mapping_sequence(task["repository_touchpoints"], f"{item_label}.repository_touchpoints", allow_empty=True)
        ):
            _validate_touchpoint_template(point, f"{item_label}.repository_touchpoints[{point_index}]")


def _validate_anchor_template(value: Any, label: str, allowed_kinds: set[str]) -> None:
    anchor = _mapping_value(value, label)
    _require_exact_keys(anchor, {"kind", "ref"}, label)
    _enum_value(anchor["kind"], f"{label}.kind", allowed_kinds)
    _nonempty_string(anchor["ref"], f"{label}.ref")


def _validate_touchpoint_template(value: Any, label: str) -> None:
    touchpoint = _mapping_value(value, label)
    _require_exact_keys(touchpoint, {"path", "symbol"}, label)
    _nonempty_string(touchpoint["path"], f"{label}.path")
    if touchpoint["symbol"] is not None:
        _nonempty_string(touchpoint["symbol"], f"{label}.symbol")


def _validate_artifact_ref(value: Any, label: str) -> None:
    ref = _mapping_value(value, label)
    _require_exact_keys(ref, {"round_id", "artifact_id", "revision"}, label)
    _identifier(ref["round_id"], f"{label}.round_id")
    _identifier(ref["artifact_id"], f"{label}.artifact_id")
    _positive_int(ref["revision"], f"{label}.revision")


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidDeliveryError(f"{label} must be a positive integer")
    return value


def _validate_json_sequence(value: Any, label: str) -> None:
    plain = thaw_json(value)
    if isinstance(plain, (str, bytes)) or not isinstance(plain, Sequence):
        raise InvalidDeliveryError(f"{label} must be a JSON sequence")
    for index, item in enumerate(plain):
        _validate_json_value(item, f"{label}[{index}]")


def _validate_json_value(value: Any, label: str) -> None:
    plain = thaw_json(value)
    if plain is None or isinstance(plain, (str, bool, int, float)):
        return
    if isinstance(plain, Mapping):
        for key, item in plain.items():
            if not isinstance(key, str) or not key:
                raise InvalidDeliveryError(f"{label} has a non-string JSON key")
            _validate_json_value(item, f"{label}.{key}")
        return
    if isinstance(plain, Sequence) and not isinstance(plain, (str, bytes)):
        for index, item in enumerate(plain):
            _validate_json_value(item, f"{label}[{index}]")
        return
    raise InvalidDeliveryError(f"{label} is not JSON-compatible")


def _technical_document(
    round_id: str,
    brief: ArtifactRevision,
    model: ArtifactRevision,
    target: ArtifactRevision,
    inputs: Sequence[ArtifactRevision],
    decisions: Sequence[ArtifactRevision],
    findings: Sequence[ArtifactRevision],
    readiness: Mapping[str, Any],
) -> dict[str, Any]:
    slots = _target_slots(target)
    records = _decision_records(slots, decisions)
    closure = _blueprint_closure(slots, records)
    implementation_plan = _implementation_plan(slots, records)
    rollout_and_observability = _rollout_and_observability(slots, records)
    return {
        "round_and_scope": _round_and_scope(round_id, brief),
        "intent_basis": _intent_basis(model, brief),
        "technical_baseline": _technical_baseline(inputs),
        "blueprint_closure": closure,
        "research_findings": _finding_records(findings),
        "decision_records": records,
        "recommended_design": _recommended_design(records),
        "implementation_plan": implementation_plan,
        "rollout_and_observability": rollout_and_observability,
        "operational_handoff": _operational_handoff(
            rollout_and_observability,
            implementation_plan,
        ),
        "risks_and_validation": _risks_and_validation(records, findings),
        "readiness_record": dict(readiness),
        "traceability": {
            "working_brief": _ref_dict(brief),
            "intent_model": _ref_dict(model),
            "blueprint_target": _ref_dict(target),
            "input_refs": [_ref_dict(item) for item in inputs],
            "decision_refs": [_ref_dict(item) for item in decisions],
            "finding_refs": [_ref_dict(item) for item in findings],
        },
    }


def _human_document(
    brief: ArtifactRevision,
    technical_document: Mapping[str, Any],
    readiness: Mapping[str, Any],
) -> dict[str, Any]:
    intent_basis = _mapping_value(technical_document["intent_basis"], "intent_basis")
    hypotheses = _mapping_sequence(intent_basis["hypotheses"], "intent hypotheses", allow_empty=True)
    records = _mapping_sequence(
        technical_document["decision_records"], "decision_records", allow_empty=True
    )
    plan = _mapping_sequence(
        technical_document["implementation_plan"], "implementation_plan", allow_empty=True
    )
    risks = _mapping_sequence(
        technical_document["risks_and_validation"], "risks_and_validation", allow_empty=True
    )
    closure = _mapping_sequence(
        technical_document["blueprint_closure"], "blueprint_closure", allow_empty=True
    )
    unclosed = [
        {
            "decision_slot_id": item["decision_slot_id"],
            "priority": item["priority"],
            "question": item["question"],
            "status": item["status"],
            "closure_or_fallback": item["closure_or_fallback"],
            "next_action": item["next_action"],
        }
        for item in closure
        if item["status"] in {"missing", "conditional", "deferred", "blocked"}
    ]
    priority_order = {"P0": 0, "P1": 1, "P2": 2}
    unclosed.sort(
        key=lambda item: (priority_order[item["priority"]], item["decision_slot_id"])
    )
    readiness_findings = _mapping_sequence(
        readiness["findings"], "readiness findings", allow_empty=True
    )
    choices = [
        {
            "decision_slot_id": item["decision_slot_id"],
            "status": item["status"],
            "selected_option": item["selected_option"],
            "trade_off": item["reversal_condition"],
        }
        for item in records
    ]
    leading = next((item for item in hypotheses if item.get("status") == "leading"), None)
    return {
        "what_was_understood": {
            "working_interpretation": _string_value(
                brief.payload.get("working_interpretation"), "working_brief working_interpretation"
            ),
            "leading_interpretation": "" if leading is None else leading["interpretation"],
            "material_alternatives": [
                {
                    "id": item["id"],
                    "interpretation": item["interpretation"],
                    "status": item["status"],
                }
                for item in hypotheses
                if item.get("status") in {"viable", "needs_user_input"}
            ],
        },
        "recommended_direction": {
            "technical_outcome": _string_value(
                brief.payload.get("technical_outcome"), "working_brief technical_outcome"
            ),
            "selected_directions": [
                {
                    "decision_slot_id": item["decision_slot_id"],
                    "selected_option": item["selected_option"],
                    "status": item["status"],
                }
                for item in records
                if item["selected_option"] is not None
            ],
        },
        "important_choices": choices,
        "near_term_result": (
            {
                "status": "planned",
                "milestone": plan[0]["description"],
                "validation": plan[0]["validation"]["oracle"],
            }
            if plan
            else {
                "status": "blocked_by_unclosed_decisions",
                "milestone": "No implementation task is ready from the supplied decisions.",
                "validation": "Close the visible Decision Slot or retain its fallback.",
            }
        ),
        "implementation_readiness": {
            "risk_tier": readiness["risk_tier"],
            "gates": dict(_mapping_value(readiness["gates"], "readiness gates")),
            "closure": closure,
        },
        "unclosed_blueprint_items": unclosed,
        "readiness_findings": [
            {"gate": item["gate"], "summary": item["summary"]}
            for item in readiness_findings
        ],
        "next_work_item_ids": list(
            _identifier_sequence(
                readiness["next_work_item_ids"], "readiness next_work_item_ids", allow_empty=True
            )
        ),
        "risks_and_uncertainty": [
            {
                "statement": item["statement"],
                "response": item["response"],
            }
            for item in risks
        ],
    }


def _resolve_exact(
    artifacts: Sequence[ArtifactRevision],
    artifact: ArtifactRevision,
    expected_kind: str,
    label: str,
) -> ArtifactRevision:
    if not isinstance(artifact, ArtifactRevision):
        raise InvalidDeliveryError(f"{label} must be an ArtifactRevision")
    for stored in artifacts:
        if stored.id == artifact.id and stored.revision == artifact.revision:
            if stored != artifact:
                raise InvalidDeliveryError(f"{label} does not match its stored revision")
            if stored.kind != expected_kind:
                raise InvalidDeliveryError(f"{label} must be a {expected_kind} artifact")
            return stored
    raise InvalidDeliveryError(f"{label} has not been persisted in this RunStore")


def _resolve_brief_model(
    artifacts: Sequence[ArtifactRevision], brief: ArtifactRevision
) -> ArtifactRevision:
    model_id = _identifier(brief.payload.get("intent_model_id"), "working_brief intent_model_id")
    by_ref = {(artifact.id, artifact.revision): artifact for artifact in artifacts}
    for ref in brief.parent_refs:
        model = by_ref.get((ref.artifact_id, ref.revision))
        if ref.artifact_id == model_id and model is not None and model.kind == INTENT_MODEL_KIND:
            return model
    raise InvalidDeliveryError("working_brief has no exact Intent Model parent reference")


def _ensure_target_lineage(
    target: ArtifactRevision, brief: ArtifactRevision, model: ArtifactRevision
) -> None:
    if target.payload.get("brief_id") != brief.id or target.payload.get("intent_model_id") != model.id:
        raise InvalidDeliveryError("Blueprint Target does not belong to supplied Brief and Intent Model")
    refs = set(target.parent_refs)
    if ArtifactRef(brief.round_id, brief.id, brief.revision) not in refs:
        raise InvalidDeliveryError("Blueprint Target lacks exact Working Brief parent reference")
    if ArtifactRef(model.round_id, model.id, model.revision) not in refs:
        raise InvalidDeliveryError("Blueprint Target lacks exact Intent Model parent reference")


def _resolve_brief_inputs(
    artifacts: Sequence[ArtifactRevision], brief: ArtifactRevision
) -> tuple[ArtifactRevision, ...]:
    ids = set(
        _identifier_sequence(
            brief.payload.get("selected_input_ids"),
            "working_brief selected_input_ids",
            allow_empty=True,
        )
        + _identifier_sequence(
            brief.payload.get("context_bundle_ids"),
            "working_brief context_bundle_ids",
            allow_empty=True,
        )
    )
    by_ref = {(artifact.id, artifact.revision): artifact for artifact in artifacts}
    result: list[ArtifactRevision] = []
    for ref in brief.parent_refs:
        artifact = by_ref.get((ref.artifact_id, ref.revision))
        if ref.artifact_id in ids and artifact is not None and artifact.kind == INPUT_LEDGER_ARTIFACT_KIND:
            result.append(artifact)
    if {item.id for item in result} != ids:
        raise InvalidDeliveryError("working_brief has incomplete exact Input Ledger lineage")
    return tuple(result)


def _resolve_decisions(
    artifacts: Sequence[ArtifactRevision],
    round_id: str,
    target: ArtifactRevision,
    values: Sequence[ArtifactRevision],
) -> tuple[tuple[ArtifactRevision, ...], tuple[ArtifactRevision, ...]]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise InvalidDeliveryError("decision_entries must be a sequence")
    slots = _target_slots(target)
    target_ref = ArtifactRef(round_id, target.id, target.revision)
    by_ref = {(artifact.id, artifact.revision): artifact for artifact in artifacts}
    decisions: list[ArtifactRevision] = []
    findings: list[ArtifactRevision] = []
    seen_ids: set[str] = set()
    seen_slots: set[str] = set()
    seen_findings: set[tuple[str, int]] = set()
    for index, supplied in enumerate(values):
        decision = _resolve_exact(
            artifacts, supplied, DECISION_LEDGER_KIND, f"decision_entries[{index}]"
        )
        if decision.round_id != round_id:
            raise InvalidDeliveryError("Decision Ledger entry must belong to delivery round")
        if _latest_artifact(artifacts, decision.id, DECISION_LEDGER_KIND) != decision:
            raise InvalidDeliveryError(f"Decision Ledger revision is stale: {decision.id}")
        slot_id = _identifier(decision.payload.get("decision_slot_id"), "Decision Ledger decision_slot_id")
        if slot_id not in slots:
            raise InvalidDeliveryError("Decision Ledger entry references an absent Decision Slot")
        if decision.id in seen_ids or slot_id in seen_slots:
            raise InvalidDeliveryError("delivery cannot include ambiguous Decision Ledger entries")
        if target_ref not in decision.parent_refs or decision.payload.get("blueprint_target_id") != target.id:
            raise InvalidDeliveryError(
                "Decision Ledger entry must belong to the exact Blueprint Target revision"
            )
        linked_findings: list[ArtifactRevision] = []
        for ref in decision.parent_refs:
            finding = by_ref.get((ref.artifact_id, ref.revision))
            if finding is not None and finding.kind == FINDING_PACK_KIND:
                linked_findings.append(finding)
        _validate_implementation_decision(slots[slot_id], decision, linked_findings)
        seen_ids.add(decision.id)
        seen_slots.add(slot_id)
        decisions.append(decision)
        for finding in linked_findings:
            key = (finding.id, finding.revision)
            if key not in seen_findings:
                seen_findings.add(key)
                findings.append(finding)
    return tuple(decisions), tuple(findings)


def _validate_implementation_decision(
    slot: Mapping[str, Any],
    decision: ArtifactRevision,
    findings: Sequence[ArtifactRevision],
) -> None:
    """Revalidate direct storage writes against the Decision Ledger contract.

    ``RunStore`` intentionally stores generic immutable JSON and therefore
    cannot know the semantic invariants of a Decision Ledger. Delivery is the
    last safe boundary before an implementation agent can act on a record, so
    it repeats the relevant schema and slot-conformance checks here.
    """

    data = _mapping_value(decision.payload, f"Decision Ledger {decision.id}")
    _require_exact_keys(
        data,
        {
            "id",
            "round_id",
            "blueprint_target_id",
            "decision_slot_id",
            "status",
            "selected_option",
            "alternatives",
            "anchors",
            "design_consequence",
            "repository_touchpoints",
            "validation",
            "change_tasks",
            "assumptions",
            "fallback",
            "reversal_condition",
            "revision_reason",
        },
        f"Decision Ledger {decision.id}",
    )
    slot_id = _identifier(slot.get("id"), "Decision Slot id")
    if _identifier(data["id"], f"Decision Ledger {decision.id}.id") != decision.id:
        raise InvalidDeliveryError(f"Decision Ledger {decision.id}.id does not match artifact id")
    if _identifier(data["round_id"], f"Decision Ledger {decision.id}.round_id") != decision.round_id:
        raise InvalidDeliveryError(f"Decision Ledger {decision.id}.round_id does not match artifact round")
    if _identifier(data["decision_slot_id"], f"Decision Ledger {decision.id}.decision_slot_id") != slot_id:
        raise InvalidDeliveryError(f"Decision Ledger {decision.id} does not match its Decision Slot")
    _identifier(data["blueprint_target_id"], f"Decision Ledger {decision.id}.blueprint_target_id")
    status = _enum_value(
        data["status"], f"Decision Ledger {decision.id}.status", DECISION_STATUSES
    )
    options = _string_sequence(slot.get("alternatives"), f"slot {slot_id} alternatives")
    selected_option = data["selected_option"]
    if status in {"selected", "conditional"}:
        selected_option = _nonempty_string(
            selected_option, f"Decision Ledger {decision.id}.selected_option"
        )
        if selected_option not in options:
            raise InvalidDeliveryError(
                f"Decision Ledger {decision.id}.selected_option is absent from its Decision Slot"
            )
    elif selected_option is not None:
        raise InvalidDeliveryError(
            f"Decision Ledger {decision.id} {status} status must not select an option"
        )
    _nonempty_string(data.get("design_consequence"), f"Decision Ledger {decision.id}.design_consequence")
    _nonempty_string(data.get("fallback"), f"Decision Ledger {decision.id}.fallback")
    _nonempty_string(
        data.get("reversal_condition"), f"Decision Ledger {decision.id}.reversal_condition"
    )
    _nonempty_string(data.get("revision_reason"), f"Decision Ledger {decision.id}.revision_reason")
    _validate_validation(
        data["validation"], f"Decision Ledger {decision.id}.validation"
    )
    _validate_decision_alternatives(
        data["alternatives"],
        options,
        selected_option,
        f"Decision Ledger {decision.id}.alternatives",
    )
    anchors = _validate_decision_anchors(
        data["anchors"],
        findings,
        f"Decision Ledger {decision.id}.anchors",
    )
    _validate_constrained_touchpoints(
        data["repository_touchpoints"],
        slot,
        f"Decision Ledger {decision.id}.repository_touchpoints",
    )
    tasks = _validate_change_tasks(
        data["change_tasks"], slot, f"Decision Ledger {decision.id}.change_tasks"
    )
    _string_sequence(
        data["assumptions"], f"Decision Ledger {decision.id}.assumptions", allow_empty=True
    )
    if slot.get("priority") != "P0":
        return
    if not _identifier_sequence(slot.get("intent_hypothesis_ids"), f"slot {slot_id} hypotheses", allow_empty=True):
        raise InvalidDeliveryError(f"P0 Decision Slot {slot_id} lacks intent hypotheses")
    if not anchors:
        raise InvalidDeliveryError(f"P0 Decision Ledger {decision.id} requires an anchor")
    if status not in {"selected", "conditional"}:
        return
    if not findings:
        raise InvalidDeliveryError(f"P0 Decision Ledger {decision.id} requires a linked Finding Pack")
    finding_ids = {item.id for item in findings}
    finding_anchors = {anchor["ref"] for anchor in anchors if anchor["kind"] == "finding"}
    if not finding_anchors or not finding_anchors <= finding_ids:
        raise InvalidDeliveryError(
            f"P0 Decision Ledger {decision.id} requires a linked Finding Pack anchor"
        )
    effects: set[str] = set()
    for finding in findings:
        finding_payload = _mapping_value(finding.payload, f"Finding Pack {finding.id}")
        if (
            finding_payload.get("blueprint_target_id") != data["blueprint_target_id"]
            or finding_payload.get("decision_slot_id") != slot_id
        ):
            raise InvalidDeliveryError(
                f"Finding Pack {finding.id} is not scoped to Decision Slot {slot_id}"
            )
        for index, effect in enumerate(
            _mapping_sequence(
                finding_payload.get("option_effects"),
                f"Finding Pack {finding.id}.option_effects",
                allow_empty=True,
            )
        ):
            _require_exact_keys(
                effect,
                {"option", "effect"},
                f"Finding Pack {finding.id}.option_effects[{index}]",
            )
            option = _nonempty_string(
                effect["option"], f"Finding Pack {finding.id}.option_effects[{index}].option"
            )
            _enum_value(
                effect["effect"], f"Finding Pack {finding.id}.option_effects[{index}].effect", OPTION_EFFECTS
            )
            effects.add(option)
    if selected_option not in effects:
        raise InvalidDeliveryError(
            f"P0 Decision Ledger {decision.id} lacks a Finding Pack effect for its selected_option"
        )
    if not tasks:
        raise InvalidDeliveryError(f"P0 Decision Ledger {decision.id} requires a change task")


def _enum_value(value: Any, label: str, allowed: set[str]) -> str:
    candidate = _nonempty_string(value, label)
    if candidate not in allowed:
        raise InvalidDeliveryError(f"{label} is unsupported: {candidate}")
    return candidate


def _validate_validation(value: Any, label: str) -> dict[str, str]:
    validation = _mapping_value(value, label)
    _require_exact_keys(validation, {"kind", "oracle"}, label)
    return {
        "kind": _enum_value(validation["kind"], f"{label}.kind", VALIDATION_KINDS),
        "oracle": _nonempty_string(validation["oracle"], f"{label}.oracle"),
    }


def _validate_decision_alternatives(
    value: Any,
    slot_options: Sequence[str] | None,
    selected_option: str | None,
    label: str,
) -> list[dict[str, str]]:
    alternatives = _mapping_sequence(value, label)
    if not alternatives:
        raise InvalidDeliveryError(f"{label} must contain at least one alternative")
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, alternative in enumerate(alternatives):
        item_label = f"{label}[{index}]"
        _require_exact_keys(alternative, {"option", "disposition", "reason"}, item_label)
        option = _nonempty_string(alternative["option"], f"{item_label}.option")
        if (
            (slot_options is not None and option not in slot_options)
            or option == selected_option
            or option in seen
        ):
            raise InvalidDeliveryError(
                f"{item_label}.option must be a distinct unselected Decision Slot option"
            )
        seen.add(option)
        normalized.append(
            {
                "option": option,
                "disposition": _enum_value(
                    alternative["disposition"],
                    f"{item_label}.disposition",
                    ALTERNATIVE_DISPOSITIONS,
                ),
                "reason": _nonempty_string(alternative["reason"], f"{item_label}.reason"),
            }
        )
    return normalized


def _validate_decision_anchors(
    value: Any,
    findings: Sequence[ArtifactRevision],
    label: str,
) -> list[dict[str, str]]:
    anchors = _mapping_sequence(value, label, allow_empty=True)
    finding_ids = {finding.id for finding in findings}
    normalized: list[dict[str, str]] = []
    for index, anchor in enumerate(anchors):
        item_label = f"{label}[{index}]"
        _require_exact_keys(anchor, {"kind", "ref"}, item_label)
        kind = _enum_value(anchor["kind"], f"{item_label}.kind", ANCHOR_KINDS)
        reference = _nonempty_string(anchor["ref"], f"{item_label}.ref")
        if kind == "finding" and reference not in finding_ids:
            raise InvalidDeliveryError(
                f"{item_label}.ref must name a Finding Pack linked from this Decision Ledger"
            )
        normalized.append({"kind": kind, "ref": reference})
    return normalized


def _slot_touchpoints(slot: Mapping[str, Any], label: str) -> set[tuple[str, str | None]]:
    result: set[tuple[str, str | None]] = set()
    for index, point in enumerate(
        _mapping_sequence(slot.get("repository_touchpoints"), f"{label} repository_touchpoints", allow_empty=True)
    ):
        point_label = f"{label} repository_touchpoints[{index}]"
        _require_exact_keys(point, {"path", "symbol"}, point_label)
        path = _nonempty_string(point["path"], f"{point_label}.path")
        symbol_raw = point["symbol"]
        if symbol_raw is not None and not isinstance(symbol_raw, str):
            raise InvalidDeliveryError(f"{point_label}.symbol must be a string or null")
        symbol = None if symbol_raw is None else _nonempty_string(
            symbol_raw, f"{point_label}.symbol"
        )
        result.add((path, symbol))
    return result


def _validate_constrained_touchpoints(
    value: Any,
    slot: Mapping[str, Any],
    label: str,
) -> list[dict[str, str | None]]:
    points = _mapping_sequence(value, label, allow_empty=True)
    allowed = _slot_touchpoints(slot, f"slot {_identifier(slot.get('id'), 'Decision Slot id')}")
    greenfield = _string_sequence(
        slot.get("greenfield_assumptions"),
        f"slot {_identifier(slot.get('id'), 'Decision Slot id')} greenfield_assumptions",
        allow_empty=True,
    )
    normalized: list[dict[str, str | None]] = []
    for index, point in enumerate(points):
        item_label = f"{label}[{index}]"
        _require_exact_keys(point, {"path", "symbol"}, item_label)
        path = _nonempty_string(point["path"], f"{item_label}.path")
        symbol_raw = point["symbol"]
        if symbol_raw is not None and not isinstance(symbol_raw, str):
            raise InvalidDeliveryError(f"{item_label}.symbol must be a string or null")
        symbol = None if symbol_raw is None else _nonempty_string(
            symbol_raw, f"{item_label}.symbol"
        )
        if allowed and (path, symbol) not in allowed:
            raise InvalidDeliveryError(f"{item_label} is not constrained by its Decision Slot")
        if not allowed and not greenfield:
            raise InvalidDeliveryError(
                f"{item_label} requires an explicit greenfield assumption when no repository touchpoint exists"
            )
        normalized.append({"path": path, "symbol": symbol})
    if allowed and not normalized:
        raise InvalidDeliveryError(f"{label} requires at least one Decision Slot touchpoint")
    if not allowed and not greenfield:
        raise InvalidDeliveryError(
            f"{label} requires a Decision Slot touchpoint or an explicit greenfield assumption"
        )
    return normalized


def _validate_change_tasks(
    value: Any,
    slot: Mapping[str, Any],
    label: str,
) -> list[dict[str, Any]]:
    tasks = _mapping_sequence(value, label, allow_empty=True)
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, task in enumerate(tasks):
        item_label = f"{label}[{index}]"
        _require_exact_keys(
            task,
            {"id", "description", "acceptance_oracle", "repository_touchpoints"},
            item_label,
        )
        task_id = _identifier(task["id"], f"{item_label}.id")
        if task_id in seen:
            raise InvalidDeliveryError(f"{label} contains duplicate change task id: {task_id}")
        seen.add(task_id)
        normalized.append(
            {
                "id": task_id,
                "description": _nonempty_string(task["description"], f"{item_label}.description"),
                "acceptance_oracle": _nonempty_string(
                    task["acceptance_oracle"], f"{item_label}.acceptance_oracle"
                ),
                "repository_touchpoints": _validate_constrained_touchpoints(
                    task["repository_touchpoints"], slot, f"{item_label}.repository_touchpoints"
                ),
            }
        )
    return normalized


def _normalize_readiness(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidDeliveryError("readiness must be a mapping")
    _require_exact_keys(value, {"risk_tier", "gates", "findings", "next_work_item_ids"}, "readiness")
    tier = _nonempty_string(value["risk_tier"], "readiness.risk_tier")
    if tier not in {"default", "medium", "high"}:
        raise InvalidDeliveryError("readiness.risk_tier is unsupported")
    gates = _mapping_value(value["gates"], "readiness.gates")
    _require_exact_keys(gates, set(READINESS_GATES), "readiness.gates")
    normalized_gates: dict[str, str] = {}
    for gate in READINESS_GATES:
        state = _nonempty_string(gates[gate], f"readiness.gates.{gate}")
        if state not in READINESS_STATES[gate]:
            raise InvalidDeliveryError(f"readiness.gates.{gate} is unsupported: {state}")
        normalized_gates[gate] = state
    findings = _mapping_sequence(value["findings"], "readiness.findings", allow_empty=True)
    normalized_findings = []
    for index, finding in enumerate(findings):
        _require_exact_keys(finding, {"gate", "summary"}, f"readiness.findings[{index}]")
        gate = _nonempty_string(finding["gate"], f"readiness.findings[{index}].gate")
        if gate not in READINESS_GATES:
            raise InvalidDeliveryError(f"readiness.findings[{index}].gate is unsupported")
        normalized_findings.append(
            {"gate": gate, "summary": _nonempty_string(finding["summary"], "readiness finding summary")}
        )
    next_ids = _identifier_sequence(
        value["next_work_item_ids"], "readiness.next_work_item_ids", allow_empty=True
    )
    return {
        "risk_tier": tier,
        "gates": normalized_gates,
        "findings": normalized_findings,
        "next_work_item_ids": list(next_ids),
    }


def _ensure_readiness_matches_closure(
    closure: Sequence[Mapping[str, Any]], readiness: Mapping[str, Any]
) -> None:
    unclosed = [
        item
        for item in closure
        if item.get("status") in {"missing", "conditional", "deferred", "blocked"}
    ]
    gates = _mapping_value(readiness.get("gates"), "readiness gates")
    if unclosed and gates.get("decision_closure") == "pass":
        slots = ", ".join(
            _cell(item.get("decision_slot_id")) for item in unclosed
        )
        raise InvalidDeliveryError(
            "readiness.gates.decision_closure cannot be pass while Blueprint Closure is unclosed: "
            f"{slots}"
        )


def _target_slots(target: ArtifactRevision) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for index, slot in enumerate(_mapping_sequence(target.payload.get("slots"), "Blueprint Target slots")):
        slot_id = _identifier(slot.get("id"), f"Blueprint Target slots[{index}].id")
        if slot_id in result:
            raise InvalidDeliveryError(f"Blueprint Target repeats Decision Slot {slot_id}")
        result[slot_id] = slot
    return result


def _decision_records(
    slots: Mapping[str, Mapping[str, Any]], decisions: Sequence[ArtifactRevision]
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for decision in decisions:
        data = _mapping_value(decision.payload, f"Decision Ledger {decision.id}")
        slot_id = _identifier(data.get("decision_slot_id"), "Decision Ledger decision_slot_id")
        slot = slots[slot_id]
        records.append(
            {
                "decision_id": decision.id,
                "revision": decision.revision,
                "decision_slot_id": slot_id,
                "priority": _nonempty_string(slot.get("priority"), f"slot {slot_id}.priority"),
                "kind": _nonempty_string(slot.get("kind"), f"slot {slot_id}.kind"),
                "intent_hypothesis_ids": list(
                    _identifier_sequence(slot.get("intent_hypothesis_ids"), f"slot {slot_id} hypotheses")
                ),
                "dependencies": list(
                    _identifier_sequence(slot.get("depends_on"), f"slot {slot_id} depends_on", allow_empty=True)
                ),
                "status": _nonempty_string(data.get("status"), f"Decision Ledger {decision.id}.status"),
                "selected_option": data.get("selected_option"),
                "alternatives": _json_list(data.get("alternatives")),
                "anchors": _json_list(data.get("anchors")),
                "design_consequence": _nonempty_string(
                    data.get("design_consequence"), f"Decision Ledger {decision.id}.design_consequence"
                ),
                "repository_touchpoints": _json_list(data.get("repository_touchpoints")),
                "validation": _json_mapping(data.get("validation")),
                "change_tasks": _json_list(data.get("change_tasks")),
                "assumptions": _json_list(data.get("assumptions")),
                "fallback": _nonempty_string(data.get("fallback"), f"Decision Ledger {decision.id}.fallback"),
                "reversal_condition": _nonempty_string(
                    data.get("reversal_condition"), f"Decision Ledger {decision.id}.reversal_condition"
                ),
            }
        )
    return records


def _blueprint_closure(
    slots: Mapping[str, Mapping[str, Any]], records: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    by_slot = {item["decision_slot_id"]: item for item in records}
    result: list[dict[str, Any]] = []
    for slot_id, slot in slots.items():
        record = by_slot.get(slot_id)
        result.append(
            {
                "decision_slot_id": slot_id,
                "priority": _nonempty_string(slot.get("priority"), f"slot {slot_id}.priority"),
                "question": _nonempty_string(slot.get("question"), f"slot {slot_id}.question"),
                "intent_hypothesis_ids": list(
                    _identifier_sequence(slot.get("intent_hypothesis_ids"), f"slot {slot_id} hypotheses")
                ),
                "status": "missing" if record is None else record["status"],
                "selected_option": None if record is None else record["selected_option"],
                "closure_or_fallback": (
                    _nonempty_string(slot.get("fallback"), f"slot {slot_id}.fallback")
                    if record is None
                    else record["fallback"]
                ),
                "next_action": (
                    "Create or converge a Decision Ledger entry for this slot."
                    if record is None
                    else _validation_next_action(record["validation"])
                ),
            }
        )
    return result


def _round_and_scope(round_id: str, brief: ArtifactRevision) -> dict[str, Any]:
    return {
        "round_id": round_id,
        "working_interpretation": _string_value(
            brief.payload.get("working_interpretation"), "working_brief working_interpretation"
        ),
        "technical_outcome": _string_value(
            brief.payload.get("technical_outcome"), "working_brief technical_outcome"
        ),
        "triggers": _json_list(brief.payload.get("triggers")),
        "selected_input_ids": _json_list(brief.payload.get("selected_input_ids")),
        "input_roles": _json_mapping(brief.payload.get("input_roles")),
        "material_conflicts": _json_list(brief.payload.get("material_conflicts")),
        "non_goals": _json_list(brief.payload.get("non_goals")),
        "hard_constraints": _json_list(brief.payload.get("retained_hard_constraints")),
        "assumptions": _json_list(brief.payload.get("assumptions")),
    }


def _intent_basis(model: ArtifactRevision, brief: ArtifactRevision) -> dict[str, Any]:
    visible = set(
        _identifier_sequence(
            brief.payload.get("intent_hypothesis_ids"),
            "working_brief intent_hypothesis_ids",
            allow_empty=True,
        )
        + _identifier_sequence(
            brief.payload.get("viable_intent_hypothesis_ids"),
            "working_brief viable_intent_hypothesis_ids",
            allow_empty=True,
        )
    )
    hypotheses: list[dict[str, Any]] = []
    for item in _mapping_sequence(model.payload.get("hypotheses"), "intent_model hypotheses"):
        hypothesis_id = _identifier(item.get("id"), "intent hypothesis id")
        if hypothesis_id not in visible:
            continue
        hypotheses.append(
            {
                "id": hypothesis_id,
                "interpretation": _nonempty_string(item.get("interpretation"), "intent interpretation"),
                "status": _nonempty_string(item.get("status"), "intent status"),
                "signal_refs": _json_list(item.get("signal_refs")),
                "confidence": _nonempty_string(item.get("confidence"), "intent confidence"),
                "decision_consequence": _nonempty_string(
                    item.get("decision_consequence"), "intent decision_consequence"
                ),
                "validation": _nonempty_string(item.get("validation"), "intent validation"),
            }
        )
    if not hypotheses:
        raise InvalidDeliveryError("Working Brief exposes no Intent Model hypothesis")
    return {
        "signals": _json_list(model.payload.get("signals")),
        "hypotheses": hypotheses,
        "decision_drivers": _json_list(model.payload.get("decision_drivers")),
    }


def _technical_baseline(inputs: Sequence[ArtifactRevision]) -> dict[str, Any]:
    repositories: list[dict[str, Any]] = []
    for item in inputs:
        if item.payload.get("kind") != "repository":
            continue
        baseline = _mapping_value(item.payload.get("repository_baseline"), "repository baseline")
        repositories.append(
            {
                "input_id": item.id,
                "revision": _json_mapping(baseline.get("revision")),
                "anchors": _json_list(baseline.get("anchors")),
                "facts": _json_list(baseline.get("facts")),
                "unreadable": _json_list(baseline.get("unreadable")),
            }
        )
    return {
        "state": "repository_backed" if repositories else "greenfield",
        "repositories": repositories,
    }


def _finding_records(findings: Sequence[ArtifactRevision]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for finding in findings:
        data = _mapping_value(finding.payload, f"Finding Pack {finding.id}")
        records.append(
            {
                "finding_id": finding.id,
                "revision": finding.revision,
                "decision_slot_id": _identifier(
                    data.get("decision_slot_id"), "Finding Pack decision_slot_id"
                ),
                "observations": _json_list(data.get("observations")),
                "option_effects": _json_list(data.get("option_effects")),
                "implementation_implications": _json_list(data.get("implementation_implications")),
                "remaining_uncertainties": _json_list(data.get("remaining_uncertainties")),
            }
        )
    return records


def _recommended_design(records: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {group: [] for group in DESIGN_GROUPS}
    for record in records:
        group = record["kind"] if record["kind"] in groups else "other"
        groups[group].append(
            {
                "decision_slot_id": record["decision_slot_id"],
                "selected_option": record["selected_option"],
                "status": record["status"],
                "design_consequence": record["design_consequence"],
            }
        )
    return groups


def _implementation_plan(
    slots: Mapping[str, Mapping[str, Any]], records: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    by_slot = {record["decision_slot_id"]: record for record in records}
    plan: list[dict[str, Any]] = []
    order = 1
    for slot_id in _stable_slot_order(slots):
        record = by_slot.get(slot_id)
        if record is None:
            continue
        for task in _mapping_sequence(record["change_tasks"], "decision change_tasks", allow_empty=True):
            plan.append(
                {
                    "order": order,
                    "decision_slot_id": slot_id,
                    "decision_id": record["decision_id"],
                    "change_task_id": _identifier(task.get("id"), "change task id"),
                    "description": _nonempty_string(task.get("description"), "change task description"),
                    "repository_touchpoints": _json_list(task.get("repository_touchpoints")),
                    "depends_on": list(record["dependencies"]),
                    "validation": _json_mapping(record["validation"]),
                    "rollback": record["fallback"],
                }
            )
            order += 1
    return plan


def _rollout_and_observability(
    slots: Mapping[str, Mapping[str, Any]], records: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Expose only operational facts recorded by typed Decision Slots.

    ``migration`` is the explicit rollout surface and ``operations`` is the
    explicit observability surface. No architecture decision is promoted into
    either section by inference; absence stays visible as ``unknown``.
    """

    by_slot = {record["decision_slot_id"]: record for record in records}
    return {
        "rollout": _operational_surface(
            slots,
            by_slot,
            slot_kind="migration",
            subject="rollout",
        ),
        "observability": _operational_surface(
            slots,
            by_slot,
            slot_kind="operations",
            subject="observability",
        ),
    }


def _operational_surface(
    slots: Mapping[str, Mapping[str, Any]],
    records: Mapping[str, Mapping[str, Any]],
    *,
    slot_kind: str,
    subject: str,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for slot_id in _stable_slot_order(slots):
        slot = slots[slot_id]
        if slot.get("kind") != slot_kind:
            continue
        record = records.get(slot_id)
        if record is None:
            items.append(
                {
                    "decision_slot_id": slot_id,
                    "status": "missing",
                    "selected_option": None,
                    "validation": _json_mapping(slot.get("validation")),
                    "fallback": _nonempty_string(
                        slot.get("fallback"), f"slot {slot_id}.fallback"
                    ),
                    "change_task_ids": [],
                    "next_action": "Create or converge a Decision Ledger entry for this slot.",
                }
            )
            continue
        items.append(
            {
                "decision_slot_id": slot_id,
                "status": record["status"],
                "selected_option": record["selected_option"],
                "validation": _json_mapping(record["validation"]),
                "fallback": record["fallback"],
                "change_task_ids": [
                    _identifier(task.get("id"), "change task id")
                    for task in _mapping_sequence(
                        record["change_tasks"], "operational change_tasks", allow_empty=True
                    )
                ],
                "next_action": _validation_next_action(record["validation"]),
            }
        )
    if not items:
        return {
            "status": "unknown",
            "items": [],
            "next_action": (
                f"Add an explicit {slot_kind} Decision Slot before defining {subject} steps."
            ),
        }
    if all(item["status"] == "selected" for item in items):
        return {
            "status": "documented",
            "items": items,
            "next_action": f"Run the validation recorded by the selected {slot_kind} Decision Slot.",
        }
    return {
        "status": "unknown",
        "items": items,
        "next_action": (
            f"Create or converge the visible {slot_kind} Decision Slot before defining {subject} behavior."
        ),
    }


def _operational_handoff(
    rollout_and_observability: Mapping[str, Any],
    implementation_plan: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a directly actionable operational view from recorded fields only."""

    observability = _mapping_value(
        rollout_and_observability["observability"], "observability surface"
    )
    observability_items = _mapping_sequence(
        observability["items"], "observability items", allow_empty=True
    )
    statuses = {item["status"] for item in observability_items}
    if "missing" in statuses:
        observability_status = "missing"
    elif "blocked" in statuses:
        observability_status = "blocked"
    elif "deferred" in statuses:
        observability_status = "deferred"
    elif "conditional" in statuses:
        observability_status = "conditional"
    elif statuses == {"selected"}:
        observability_status = "selected"
    else:
        observability_status = "unknown"

    rollout_items = [
        {
            "order": item["order"],
            "decision_slot_id": item["decision_slot_id"],
            "change_task_id": item["change_task_id"],
            "description": item["description"],
            "validation": _json_mapping(item["validation"]),
            "repository_touchpoints": _json_list(item["repository_touchpoints"]),
        }
        for item in implementation_plan
    ]
    rollback = [
        {
            "order": item["order"],
            "decision_slot_id": item["decision_slot_id"],
            "change_task_id": item["change_task_id"],
            "fallback": item["rollback"],
            "validation": _json_mapping(item["validation"]),
        }
        for item in implementation_plan
    ]
    return {
        "observability": {
            "status": observability_status,
            "items": [dict(item) for item in observability_items],
            "next_action": observability["next_action"],
        },
        "rollout": {
            "status": "derived_from_ordered_change_tasks" if rollout_items else "unknown",
            "items": rollout_items,
            "next_action": (
                "Run the validation for each ordered change task before rollout."
                if rollout_items
                else "No rollout task is recorded; add an explicit change task before rollout."
            ),
        },
        "rollback": rollback,
    }


def _stable_slot_order(slots: Mapping[str, Mapping[str, Any]]) -> list[str]:
    remaining = {
        slot_id: set(
            _identifier_sequence(slot.get("depends_on"), f"slot {slot_id} depends_on", allow_empty=True)
        )
        for slot_id, slot in slots.items()
    }
    for slot_id, dependencies in remaining.items():
        unknown = dependencies - set(remaining)
        if unknown:
            raise InvalidDeliveryError(f"slot {slot_id} depends on unknown slots: {sorted(unknown)}")
    ordered: list[str] = []
    while remaining:
        ready = sorted(slot_id for slot_id, dependencies in remaining.items() if not dependencies)
        if not ready:
            raise InvalidDeliveryError("Blueprint Target Decision Slot dependencies contain a cycle")
        ordered.extend(ready)
        for slot_id in ready:
            remaining.pop(slot_id)
        for dependencies in remaining.values():
            dependencies.difference_update(ready)
    return ordered


def _risks_and_validation(
    records: Sequence[Mapping[str, Any]], findings: Sequence[ArtifactRevision]
) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    for record in records:
        if record["status"] in {"conditional", "deferred", "blocked"}:
            risks.append(
                {
                    "kind": "decision_status",
                    "decision_slot_id": record["decision_slot_id"],
                    "statement": f"Decision remains {record['status']}.",
                    "validation": record["reversal_condition"],
                    "response": record["fallback"],
                }
            )
        for assumption in _string_sequence(record["assumptions"], "decision assumptions", allow_empty=True):
            risks.append(
                {
                    "kind": "assumption",
                    "decision_slot_id": record["decision_slot_id"],
                    "statement": assumption,
                    "validation": record["validation"]["oracle"],
                    "response": record["fallback"],
                }
            )
    for finding in findings:
        data = _mapping_value(finding.payload, f"Finding Pack {finding.id}")
        slot_id = _identifier(data.get("decision_slot_id"), "Finding Pack decision_slot_id")
        for uncertainty in _string_sequence(
            data.get("remaining_uncertainties"), "Finding Pack remaining_uncertainties", allow_empty=True
        ):
            risks.append(
                {
                    "kind": "uncertainty",
                    "decision_slot_id": slot_id,
                    "statement": uncertainty,
                    "validation": "Targeted follow-up Finding Pack or validation oracle.",
                    "response": "Keep the recorded fallback until the uncertainty closes.",
                }
            )
    return risks


def _render_technical_markdown(round_id: str, document: Mapping[str, Any]) -> str:
    scope = _mapping_value(document["round_and_scope"], "round_and_scope")
    lines = [f"# Technical Research Package: {round_id}", "", "## Round and Scope", ""]
    lines.extend(
        [
            f"- Working interpretation: {_cell(scope['working_interpretation'])}",
            f"- Technical outcome: {_cell(scope['technical_outcome'])}",
            f"- Hard constraints: {_joined(scope['hard_constraints'])}",
            f"- Non-goals: {_joined(scope['non_goals'])}",
            "",
            "## Intent Basis",
            "",
            "| Interpretation | Signals | Status/confidence | Design consequence | Validation |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    intent = _mapping_value(document["intent_basis"], "intent_basis")
    for hypothesis in _mapping_sequence(intent["hypotheses"], "intent hypotheses", allow_empty=True):
        lines.append(
            f"| {_cell(hypothesis['interpretation'])} | {_joined(hypothesis['signal_refs'])} | "
            f"{_cell(hypothesis['status'])}/{_cell(hypothesis['confidence'])} | "
            f"{_cell(hypothesis['decision_consequence'])} | {_cell(hypothesis['validation'])} |"
        )
    lines.extend(["", "## Current Technical Baseline", ""])
    baseline = _mapping_value(document["technical_baseline"], "technical_baseline")
    repositories = _mapping_sequence(baseline["repositories"], "repositories", allow_empty=True)
    if not repositories:
        lines.append("- No repository baseline was selected for this delivery.")
    for repository in repositories:
        lines.append(f"- Repository input `{_cell(repository['input_id'])}`")
        lines.append(f"  - Anchors: {_anchors(repository['anchors'])}")
        lines.append(f"  - Observed facts: {_observations(repository['facts'])}")
    lines.extend(["", "## Blueprint Closure", "", "| Priority | Decision slot | Status | Closure or fallback |", "| --- | --- | --- | --- |"])
    for closure in _mapping_sequence(document["blueprint_closure"], "blueprint_closure", allow_empty=True):
        lines.append(
            f"| {_cell(closure['priority'])} | {_cell(closure['decision_slot_id'])} | "
            f"{_cell(closure['status'])} | {_cell(closure['closure_or_fallback'])} |"
        )
    lines.extend(["", "## Research Strategy and Findings", "", "| Finding | Evidence | Technical implication |", "| --- | --- | --- |"])
    findings = _mapping_sequence(document["research_findings"], "research_findings", allow_empty=True)
    if not findings:
        lines.append("| No Finding Pack was supplied | - | No recommendation is inferred |")
    for finding in findings:
        implications = _joined(finding["implementation_implications"])
        for observation in _mapping_sequence(finding["observations"], "finding observations", allow_empty=True):
            anchor = _mapping_value(observation["anchor"], "observation anchor")
            lines.append(
                f"| {_cell(observation['claim'])} | {_cell(anchor['kind'])}:{_cell(anchor['ref'])} | "
                f"{_cell(implications)} |"
            )
    lines.extend(["", "## Recommended Design", ""])
    design = _mapping_value(document["recommended_design"], "recommended_design")
    for group in DESIGN_GROUPS:
        lines.extend([f"### {group.title()}", ""])
        entries = _mapping_sequence(design[group], f"recommended_design.{group}", allow_empty=True)
        if entries:
            lines.extend(
                f"- `{_cell(entry['decision_slot_id'])}`: {_cell(entry['selected_option'] or entry['status'])}. "
                f"{_cell(entry['design_consequence'])}"
                for entry in entries
            )
        else:
            lines.append("- No structured decision was supplied.")
        lines.append("")
    lines.extend(["## Decisions and Alternatives", "", "| Decision | Selected approach | Alternatives | Anchors | Reversal condition |", "| --- | --- | --- | --- | --- |"])
    for record in _mapping_sequence(document["decision_records"], "decision_records", allow_empty=True):
        lines.append(
            f"| {_cell(record['decision_slot_id'])} | {_cell(record['selected_option'] or record['status'])} | "
            f"{_alternatives(record['alternatives'])} | {_anchors(record['anchors'])} | "
            f"{_cell(record['reversal_condition'])} |"
        )
    lines.extend(["", "## Implementation Plan", "", "| Order | Work item | Repository touch points | Depends on | Validation | Rollback |", "| --- | --- | --- | --- | --- |"])
    plan = _mapping_sequence(document["implementation_plan"], "implementation_plan", allow_empty=True)
    if not plan:
        lines.append("| - | No task is emitted until a Decision Ledger entry provides one | - | - | - | - |")
    for item in plan:
        validation = _mapping_value(item["validation"], "implementation validation")
        lines.append(
            f"| {item['order']} | {_cell(item['description'])} | {_anchors(item['repository_touchpoints'])} | "
            f"{_joined(item['depends_on'])} | {_cell(validation['kind'])}: {_cell(validation['oracle'])} | "
            f"{_cell(item['rollback'])} |"
        )
    operational = _mapping_value(
        document["rollout_and_observability"], "rollout_and_observability"
    )
    lines.extend(["", "## Rollout and Observability", ""])
    for name in ("rollout", "observability"):
        surface = _mapping_value(operational[name], f"{name} surface")
        lines.extend([f"### {name.title()}", ""])
        lines.append(f"- Status: {_cell(surface['status'])}")
        items = _mapping_sequence(surface["items"], f"{name} items", allow_empty=True)
        if not items:
            lines.append("- No explicit Decision Slot supplied.")
        for item in items:
            validation = _mapping_value(item["validation"], f"{name} validation")
            lines.append(
                f"- `{_cell(item['decision_slot_id'])}`: {_cell(item['status'])}; "
                f"selected={_cell(item['selected_option'] or 'unresolved')}; "
                f"validation={_cell(validation['kind'])}: {_cell(validation['oracle'])}; "
                f"rollback/fallback={_cell(item['fallback'])}; next={_cell(item['next_action'])}"
            )
        lines.append(f"- Next action: {_cell(surface['next_action'])}")
        lines.append("")
    handoff = _mapping_value(document["operational_handoff"], "operational_handoff")
    handoff_observability = _mapping_value(
        handoff["observability"], "operational_handoff.observability"
    )
    handoff_rollout = _mapping_value(handoff["rollout"], "operational_handoff.rollout")
    lines.extend(["## Operational Handoff", ""])
    lines.append(f"- Observability status: {_cell(handoff_observability['status'])}")
    lines.append(f"- Observability next action: {_cell(handoff_observability['next_action'])}")
    lines.append(f"- Rollout status: {_cell(handoff_rollout['status'])}")
    for item in _mapping_sequence(
        handoff_rollout["items"], "operational_handoff rollout items", allow_empty=True
    ):
        validation = _mapping_value(item["validation"], "operational_handoff rollout validation")
        lines.append(
            f"- Rollout `{_cell(item['change_task_id'])}`: {_cell(item['description'])}; "
            f"validation={_cell(validation['kind'])}: {_cell(validation['oracle'])}"
        )
    lines.append(f"- Rollout next action: {_cell(handoff_rollout['next_action'])}")
    for item in _mapping_sequence(handoff["rollback"], "operational_handoff rollback", allow_empty=True):
        lines.append(
            f"- Rollback `{_cell(item['change_task_id'])}`: {_cell(item['fallback'])}"
        )
    lines.extend(["", "## Risks and Validation", "", "| Risk or assumption | Validation | Response |", "| --- | --- | --- |"])
    risks = _mapping_sequence(document["risks_and_validation"], "risks_and_validation", allow_empty=True)
    if not risks:
        lines.append("| No additional structured risk was supplied | - | - |")
    for risk in risks:
        lines.append(f"| {_cell(risk['statement'])} | {_cell(risk['validation'])} | {_cell(risk['response'])} |")
    lines.extend(["", "## Readiness Record", "", "| Gate | Result |", "| --- | --- |"])
    readiness = _mapping_value(document["readiness_record"], "readiness_record")
    gates = _mapping_value(readiness["gates"], "readiness gates")
    for gate in READINESS_GATES:
        lines.append(f"| {_cell(gate)} | {_cell(gates[gate])} |")
    lines.extend(["", "## Traceability", ""])
    traceability = _mapping_value(document["traceability"], "traceability")
    lines.append(f"- Working Brief: {_ref_label(traceability['working_brief'])}")
    lines.append(f"- Intent Model: {_ref_label(traceability['intent_model'])}")
    lines.append(f"- Blueprint Target: {_ref_label(traceability['blueprint_target'])}")
    lines.append(f"- Inputs: {_refs_label(traceability['input_refs'])}")
    lines.append(f"- Decisions: {_refs_label(traceability['decision_refs'])}")
    lines.append(f"- Findings: {_refs_label(traceability['finding_refs'])}")
    return "\n".join(lines) + "\n"


def _render_human_markdown(
    round_id: str, package_ref: ArtifactRef, document: Mapping[str, Any]
) -> str:
    understood = _mapping_value(document["what_was_understood"], "what_was_understood")
    direction = _mapping_value(document["recommended_direction"], "recommended_direction")
    near_term = _mapping_value(document["near_term_result"], "near_term_result")
    lines = [f"# Human Brief: {round_id}", "", "## What Was Understood", ""]
    lines.append(_cell(understood["working_interpretation"]))
    if understood["leading_interpretation"]:
        lines.append(f"Leading interpretation: {_cell(understood['leading_interpretation'])}")
    alternatives = _mapping_sequence(understood["material_alternatives"], "material alternatives", allow_empty=True)
    if alternatives:
        lines.append("Material alternatives remain visible:")
        lines.extend(f"- {_cell(item['interpretation'])} ({_cell(item['status'])})" for item in alternatives)
    lines.extend(["", "## Recommended Technical Direction", "", _cell(direction["technical_outcome"]), ""])
    for item in _mapping_sequence(direction["selected_directions"], "selected directions", allow_empty=True):
        lines.append(
            f"- `{_cell(item['decision_slot_id'])}`: {_cell(item['selected_option'])} ({_cell(item['status'])})"
        )
    lines.extend(["", "## Important Choices", "", "| Choice | Status | Main trade-off |", "| --- | --- | --- |"])
    for choice in _mapping_sequence(document["important_choices"], "important choices", allow_empty=True):
        lines.append(
            f"| {_cell(choice['decision_slot_id'])}: {_cell(choice['selected_option'] or 'unresolved')} | "
            f"{_cell(choice['status'])} | {_cell(choice['trade_off'])} |"
        )
    lines.extend(["", "## Near-Term Result", "", _cell(near_term["milestone"]), ""])
    lines.append(f"Validation: {_cell(near_term['validation'])}")
    lines.extend(["", "## Implementation Readiness", ""])
    readiness = _mapping_value(document["implementation_readiness"], "implementation_readiness")
    gates = _mapping_value(readiness["gates"], "human readiness gates")
    lines.extend(f"- {_cell(gate)}: {_cell(gates[gate])}" for gate in READINESS_GATES)
    lines.extend(
        [
            "",
            "## Unclosed Design Obligations",
            "",
            "| Priority | Decision slot | Status | Next action |",
            "| --- | --- | --- | --- |",
        ]
    )
    unclosed = _mapping_sequence(
        document["unclosed_blueprint_items"], "human unclosed_blueprint_items", allow_empty=True
    )
    if not unclosed:
        lines.append("| - | All visible Decision Slots are selected | selected | Continue with recorded validation |")
    for item in unclosed:
        lines.append(
            f"| {_cell(item['priority'])} | {_cell(item['decision_slot_id'])} | "
            f"{_cell(item['status'])} | {_cell(item['next_action'])} |"
        )
        lines.append(f"  - Fallback: {_cell(item['closure_or_fallback'])}")
    lines.extend(["", "## Readiness Findings", ""])
    readiness_findings = _mapping_sequence(
        document["readiness_findings"], "human readiness_findings", allow_empty=True
    )
    if not readiness_findings:
        lines.append("- No additional readiness finding was supplied.")
    for finding in readiness_findings:
        lines.append(f"- {_cell(finding['gate'])}: {_cell(finding['summary'])}")
    lines.extend(["", "## Next Research Work", ""])
    next_work_item_ids = _string_sequence(
        document["next_work_item_ids"], "human next_work_item_ids", allow_empty=True
    )
    if not next_work_item_ids:
        lines.append("- No additional work item was supplied.")
    lines.extend(f"- `{_cell(work_item_id)}`" for work_item_id in next_work_item_ids)
    lines.extend(["", "## Risks and Uncertainty", ""])
    risks = _mapping_sequence(document["risks_and_uncertainty"], "human risks", allow_empty=True)
    if not risks:
        lines.append("- No additional structured risk was supplied.")
    for risk in risks:
        lines.append(f"- {_cell(risk['statement'])} Response: {_cell(risk['response'])}")
    lines.extend(["", "## Technical Package", "", f"- {_ref_label(package_ref.to_dict())}"])
    return "\n".join(lines) + "\n"


def _validation_next_action(validation: Any) -> str:
    data = _mapping_value(validation, "validation")
    return f"Run {data['kind']} validation: {data['oracle']}"


def _ensure_id_compatibility(
    artifacts: Sequence[ArtifactRevision], artifact_id: str, expected_kind: str
) -> None:
    foreign = {
        artifact.kind
        for artifact in artifacts
        if artifact.id == artifact_id and artifact.kind != expected_kind
    }
    if foreign:
        raise InvalidDeliveryError(
            f"artifact id {artifact_id!r} is already used by kinds: {sorted(foreign)}"
        )


def _latest_artifact(
    artifacts: Sequence[ArtifactRevision], artifact_id: str, kind: str
) -> ArtifactRevision | None:
    matches = [artifact for artifact in artifacts if artifact.id == artifact_id and artifact.kind == kind]
    return max(matches, key=lambda artifact: artifact.revision, default=None)


def _next_revision(artifacts: Sequence[ArtifactRevision], artifact_id: str) -> int:
    return max((artifact.revision for artifact in artifacts if artifact.id == artifact_id), default=0) + 1


def _unique_refs(values: Sequence[ArtifactRef]) -> tuple[ArtifactRef, ...]:
    result: list[ArtifactRef] = []
    seen: set[tuple[str, str, int]] = set()
    for value in values:
        key = (value.round_id, value.artifact_id, value.revision)
        if key not in seen:
            seen.add(key)
            result.append(value)
    return tuple(result)


def _ref_dict(artifact: ArtifactRevision) -> dict[str, Any]:
    return ArtifactRef(artifact.round_id, artifact.id, artifact.revision).to_dict()


def _json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    plain = thaw_json(value)
    if isinstance(plain, list):
        return plain
    raise InvalidDeliveryError("expected a JSON list")


def _json_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    plain = thaw_json(value)
    if isinstance(plain, dict):
        return plain
    raise InvalidDeliveryError("expected a JSON mapping")


def _mapping_value(value: Any, label: str) -> Mapping[str, Any]:
    plain = thaw_json(value)
    if not isinstance(plain, Mapping):
        raise InvalidDeliveryError(f"{label} must be a mapping")
    return plain


def _mapping_sequence(value: Any, label: str, *, allow_empty: bool = False) -> list[Mapping[str, Any]]:
    plain = thaw_json(value)
    if isinstance(plain, (str, bytes)) or not isinstance(plain, Sequence):
        raise InvalidDeliveryError(f"{label} must be a sequence of mappings")
    result: list[Mapping[str, Any]] = []
    for index, item in enumerate(plain):
        if not isinstance(item, Mapping):
            raise InvalidDeliveryError(f"{label}[{index}] must be a mapping")
        result.append(item)
    if not result and not allow_empty:
        raise InvalidDeliveryError(f"{label} must not be empty")
    return result


def _identifier_sequence(value: Any, label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    values = _json_list(value)
    result = tuple(_identifier(item, label) for item in values)
    if not result and not allow_empty:
        raise InvalidDeliveryError(f"{label} must not be empty")
    if len(set(result)) != len(result):
        raise InvalidDeliveryError(f"{label} must not contain duplicate ids")
    return result


def _string_sequence(value: Any, label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    values = _json_list(value)
    result = tuple(_nonempty_string(item, label) for item in values)
    if not result and not allow_empty:
        raise InvalidDeliveryError(f"{label} must not be empty")
    return result


def _identifier(value: Any, label: str) -> str:
    try:
        return validate_identifier(value, label)
    except InvalidIdentifierError as error:
        raise InvalidDeliveryError(str(error)) from error


def _string_value(value: Any, label: str) -> str:
    return _nonempty_string(thaw_json(value), label)


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidDeliveryError(f"{label} must be a nonempty string")
    return value


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if not isinstance(value, Mapping):
        raise InvalidDeliveryError(f"{label} must be a mapping")
    actual = set(value)
    if actual != expected:
        raise InvalidDeliveryError(
            f"{label} has unexpected keys; missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _joined(value: Any) -> str:
    return ", ".join(_cell(item) for item in _json_list(value)) or "-"


def _anchors(value: Any) -> str:
    rendered: list[str] = []
    for item in _json_list(value):
        if isinstance(item, Mapping) and "path" in item:
            rendered.append(str(item["path"]) if item.get("symbol") is None else f"{item['path']}:{item['symbol']}")
        elif isinstance(item, Mapping) and "kind" in item and "ref" in item:
            rendered.append(f"{item['kind']}:{item['ref']}")
        else:
            rendered.append(str(item))
    return ", ".join(_cell(item) for item in rendered) or "-"


def _alternatives(value: Any) -> str:
    rendered = [
        f"{item.get('option')} ({item.get('disposition')})"
        for item in _json_list(value)
        if isinstance(item, Mapping)
    ]
    return ", ".join(_cell(item) for item in rendered) or "-"


def _observations(value: Any) -> str:
    rendered = [
        item.get("observation", "") for item in _json_list(value) if isinstance(item, Mapping)
    ]
    return "; ".join(_cell(item) for item in rendered) or "-"


def _ref_label(value: Any) -> str:
    ref = _mapping_value(value, "artifact reference")
    return f"{ref['round_id']}/{ref['artifact_id']}@{ref['revision']}"


def _refs_label(value: Any) -> str:
    return ", ".join(_ref_label(ref) for ref in _json_list(value)) or "-"
