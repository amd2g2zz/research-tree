"""Create feedback-driven successor rounds without rewriting predecessor state."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import tempfile
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .domain import (
    ArtifactRef,
    ArtifactRevision,
    InvalidIdentifierError,
    RoundNotFoundError,
    RoundRecord,
    RuntimeStoreError,
    thaw_json,
    validate_identifier,
)
from .intake import INPUT_LEDGER_ARTIFACT_KIND, InputIntakeService
from .intent import IntentModelCompiler, WorkingBriefCompiler
from .ledger import DECISION_LEDGER_KIND, FINDING_PACK_KIND
from .storage import RunStore
from .work_items import WORK_ITEM_KIND


FEEDBACK_LINEAGE_KIND = "feedback-lineage"
RESEARCH_STRATEGY_KIND = "research-strategy"
ROUND_SUPERSESSION_KIND = "round-supersession"
SAME_ROUND_REPLAN_KIND = "same-round-replan"
CORRECTION_EVENT_KIND = "correction-event"
STALE_STATE_QUARANTINE_KIND = "stale-state-quarantine"

CORRECTION_KINDS = frozenset({"correction", "reopen"})
CORRECTION_RELATIONS = frozenset({"supersedes", "reopens"})
CORRECTION_ACTORS = frozenset({"human", "operator"})
CORRECTION_AFFECTED_ROLES = (
    "intent_model",
    "working_brief",
    "decision_map",
    "strategy",
    "handoff",
)
CORRECTION_ACTION_ROLES = ("decision_map", "strategy", "handoff")
CORRECTION_ROLE_KINDS = {
    "intent_model": "intent-model",
    "working_brief": "working-brief",
    "decision_map": "blueprint-target",
    "strategy": RESEARCH_STRATEGY_KIND,
    "handoff": "alignment-handoff",
}

TARGET_CHANGE_DIMENSIONS = frozenset({"target", "priority", "success_definition"})
CANDIDATE_DISPOSITIONS = frozenset({"reuse", "revalidate", "downgrade", "ignore", "overturn"})
CARRIED_INPUT_DISPOSITIONS = frozenset({"reuse", "revalidate", "downgrade"})
REQUIRED_CANDIDATE_KINDS = frozenset({INPUT_LEDGER_ARTIFACT_KIND, FINDING_PACK_KIND, DECISION_LEDGER_KIND})
ACTIVE_WORK_STATUSES = frozenset({"planned", "ready", "running"})


class FeedbackError(RuntimeStoreError):
    """Base error for feedback lineage and successor-round violations."""


class InvalidFeedbackError(FeedbackError):
    """Raised before feedback can silently alter the wrong research round."""


@dataclass(frozen=True, slots=True)
class CorrectionBinding:
    """An exact artifact revision and digest affected by a correction."""

    role: str
    artifact_ref: ArtifactRef
    digest: str

    def __post_init__(self) -> None:
        if self.role not in CORRECTION_ROLE_KINDS:
            raise InvalidFeedbackError(f"unsupported correction binding role: {self.role}")
        if not isinstance(self.artifact_ref, ArtifactRef):
            raise InvalidFeedbackError("correction binding requires an exact artifact reference")
        if (
            not isinstance(self.digest, str)
            or len(self.digest) != 64
            or any(character not in "0123456789abcdef" for character in self.digest)
        ):
            raise InvalidFeedbackError("correction binding digest must be 64 lowercase hex characters")

    @classmethod
    def from_artifact(cls, role: str, artifact: ArtifactRevision) -> "CorrectionBinding":
        if not isinstance(artifact, ArtifactRevision):
            raise InvalidFeedbackError("correction binding source must be an artifact revision")
        return cls(
            role=role,
            artifact_ref=ArtifactRef(artifact.round_id, artifact.id, artifact.revision),
            digest=artifact.content_hash,
        )

    @classmethod
    def from_value(cls, role: str, value: "CorrectionBinding | Mapping[str, Any]") -> "CorrectionBinding":
        if isinstance(value, cls):
            if value.role != role:
                raise InvalidFeedbackError("correction binding role does not match its mapping key")
            return value
        if not isinstance(value, Mapping):
            raise InvalidFeedbackError("correction binding must be an object")
        _require_exact_keys(value, {"artifact_ref", "digest"}, f"affected.{role}")
        return cls(
            role=role,
            artifact_ref=_validate_ref(value["artifact_ref"], f"affected.{role}.artifact_ref"),
            digest=str(value["digest"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"artifact_ref": self.artifact_ref.to_dict(), "digest": self.digest}


@dataclass(frozen=True, slots=True)
class CorrectionEvent:
    """One requester correction that invalidates exact predecessor state."""

    event_id: str
    run_id: str
    kind: str
    actor: str
    reason: str
    relation: str
    task_id: str
    domain_id: str
    successor_task_id: str
    successor_domain_id: str
    affected: Mapping[str, CorrectionBinding]

    def __post_init__(self) -> None:
        try:
            validate_identifier(self.event_id, "event_id")
            validate_identifier(self.run_id, "run_id")
            validate_identifier(self.task_id, "task_id")
            validate_identifier(self.domain_id, "domain_id")
            validate_identifier(self.successor_task_id, "successor_task_id")
            validate_identifier(self.successor_domain_id, "successor_domain_id")
        except (InvalidIdentifierError, TypeError, ValueError) as error:
            raise InvalidFeedbackError(str(error)) from error
        if self.kind not in CORRECTION_KINDS:
            raise InvalidFeedbackError("correction kind must be correction or reopen")
        if self.actor not in CORRECTION_ACTORS:
            raise InvalidFeedbackError("material correction actor must be human or operator")
        if self.relation not in CORRECTION_RELATIONS:
            raise InvalidFeedbackError("correction relation must be supersedes or reopens")
        if self.kind == "correction" and self.relation != "supersedes":
            raise InvalidFeedbackError("correction events require a supersedes relation")
        if self.kind == "reopen" and self.relation != "reopens":
            raise InvalidFeedbackError("reopen events require a reopens relation")
        _nonempty_string(self.reason, "reason")
        if set(self.affected) != set(CORRECTION_AFFECTED_ROLES):
            raise InvalidFeedbackError(
                "correction affected roles must be exactly " + ", ".join(CORRECTION_AFFECTED_ROLES)
            )
        normalized = {
            role: CorrectionBinding.from_value(role, self.affected[role]) for role in CORRECTION_AFFECTED_ROLES
        }
        if any(binding.artifact_ref.round_id != self.run_id for binding in normalized.values()):
            raise InvalidFeedbackError("all affected correction bindings must belong to the run")
        object.__setattr__(self, "affected", MappingProxyType(normalized))

    @classmethod
    def create(cls, **values: Any) -> "CorrectionEvent":
        return cls(**values)

    @classmethod
    def from_value(cls, value: "CorrectionEvent | Mapping[str, Any]") -> "CorrectionEvent":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise InvalidFeedbackError("correction event must be an object")
        expected = {
            "event_id",
            "run_id",
            "kind",
            "actor",
            "reason",
            "relation",
            "task_id",
            "domain_id",
            "successor_task_id",
            "successor_domain_id",
            "affected",
        }
        _require_exact_keys(value, expected, "correction event")
        affected = value["affected"]
        if not isinstance(affected, Mapping):
            raise InvalidFeedbackError("correction affected bindings must be an object")
        return cls(
            event_id=str(value["event_id"]),
            run_id=str(value["run_id"]),
            kind=str(value["kind"]),
            actor=str(value["actor"]),
            reason=str(value["reason"]),
            relation=str(value["relation"]),
            task_id=str(value["task_id"]),
            domain_id=str(value["domain_id"]),
            successor_task_id=str(value["successor_task_id"]),
            successor_domain_id=str(value["successor_domain_id"]),
            affected={
                str(role): CorrectionBinding.from_value(str(role), binding) for role, binding in affected.items()
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "kind": self.kind,
            "actor": self.actor,
            "reason": self.reason,
            "relation": self.relation,
            "task_id": self.task_id,
            "domain_id": self.domain_id,
            "successor_task_id": self.successor_task_id,
            "successor_domain_id": self.successor_domain_id,
            "affected": {role: self.affected[role].to_dict() for role in CORRECTION_AFFECTED_ROLES},
        }

    def action_authority(self) -> dict[str, Any]:
        return {
            "correction_event_id": self.event_id,
            "bindings": {role: self.affected[role].to_dict() for role in CORRECTION_ACTION_ROLES},
        }


@dataclass(frozen=True, slots=True)
class CandidateContext:
    """One exact predecessor artifact and its new-round disposition."""

    candidate_id: str
    artifact: ArtifactRevision
    disposition: str
    rationale: str


@dataclass(frozen=True, slots=True)
class FeedbackRoundArtifacts:
    """Artifacts created for an explicit feedback-triggered successor round."""

    round: RoundRecord
    feedback_input: ArtifactRevision
    carried_inputs: tuple[ArtifactRevision, ...]
    intent_model: ArtifactRevision
    working_brief: ArtifactRevision
    lineage: ArtifactRevision
    strategy: ArtifactRevision
    supersession: ArtifactRevision


@dataclass(frozen=True, slots=True)
class _PreparedSuccessor:
    prior_round: RoundRecord
    candidates: tuple[CandidateContext, ...]
    change_dimensions: tuple[str, ...]
    change_reason: str
    safe_checkpoint: str
    intent_input_ids: tuple[str, ...]
    context_member_input_ids: tuple[str, ...]
    selected_input_ids: tuple[str, ...]
    strategy_focus: tuple[str, ...]
    strategy_summary: str


class FeedbackRoundService:
    """Record feedback as either a successor round or an internal replan."""

    def __init__(self, store: RunStore) -> None:
        self._store = store
        self._intake = InputIntakeService(store)

    def start_successor(
        self,
        *,
        prior_round_id: str,
        successor_round_id: str,
        feedback_input_id: str,
        feedback_text: str,
        feedback_origin_locator: str,
        change_dimensions: Sequence[str],
        change_reason: str,
        safe_checkpoint: str,
        candidates: Sequence[CandidateContext],
        intent_id: str,
        intent_input_ids: Sequence[str],
        intent_analysis: Mapping[str, Any],
        context_bundle_id: str | None,
        context_member_input_ids: Sequence[str],
        brief_id: str,
        selected_input_ids: Sequence[str],
        input_roles: Mapping[str, str],
        material_conflicts: Sequence[Mapping[str, Any]],
        working_interpretation: str,
        technical_outcome: str,
        strategy_id: str,
        strategy_summary: str,
        strategy_focus: Sequence[str],
        overall_rejection: bool = False,
        assumptions: Sequence[str] = (),
        delivery_targets: Mapping[str, bool] | None = None,
    ) -> FeedbackRoundArtifacts:
        """Preflight a successor in isolation before changing the live store.

        Compiler validation happens against a filesystem copy containing the
        exact predecessor lineage. This keeps rejected feedback requests free
        of rounds, artifacts, and supersession overlays while retaining the
        existing compiler and storage validation paths.
        """

        request = {
            "prior_round_id": prior_round_id,
            "successor_round_id": successor_round_id,
            "feedback_input_id": feedback_input_id,
            "feedback_text": feedback_text,
            "feedback_origin_locator": feedback_origin_locator,
            "change_dimensions": change_dimensions,
            "change_reason": change_reason,
            "safe_checkpoint": safe_checkpoint,
            "candidates": candidates,
            "intent_id": intent_id,
            "intent_input_ids": intent_input_ids,
            "intent_analysis": intent_analysis,
            "context_bundle_id": context_bundle_id,
            "context_member_input_ids": context_member_input_ids,
            "brief_id": brief_id,
            "selected_input_ids": selected_input_ids,
            "input_roles": input_roles,
            "material_conflicts": material_conflicts,
            "working_interpretation": working_interpretation,
            "technical_outcome": technical_outcome,
            "strategy_id": strategy_id,
            "strategy_summary": strategy_summary,
            "strategy_focus": strategy_focus,
            "overall_rejection": overall_rejection,
            "assumptions": assumptions,
            "delivery_targets": delivery_targets,
        }
        with tempfile.TemporaryDirectory(prefix="feedback-preflight-") as temporary:
            staged_root = Path(temporary) / "run-store"
            shutil.copytree(self._store.root, staged_root)
            staged_service = FeedbackRoundService(RunStore(staged_root))
            staged_service._persist_successor(**request)

        return self._persist_successor(**request)

    def _persist_successor(
        self,
        *,
        prior_round_id: str,
        successor_round_id: str,
        feedback_input_id: str,
        feedback_text: str,
        feedback_origin_locator: str,
        change_dimensions: Sequence[str],
        change_reason: str,
        safe_checkpoint: str,
        candidates: Sequence[CandidateContext],
        intent_id: str,
        intent_input_ids: Sequence[str],
        intent_analysis: Mapping[str, Any],
        context_bundle_id: str | None,
        context_member_input_ids: Sequence[str],
        brief_id: str,
        selected_input_ids: Sequence[str],
        input_roles: Mapping[str, str],
        material_conflicts: Sequence[Mapping[str, Any]],
        working_interpretation: str,
        technical_outcome: str,
        strategy_id: str,
        strategy_summary: str,
        strategy_focus: Sequence[str],
        overall_rejection: bool = False,
        assumptions: Sequence[str] = (),
        delivery_targets: Mapping[str, bool] | None = None,
    ) -> FeedbackRoundArtifacts:
        """Create a successor only for an explicit target-changing feedback event.

        The method intentionally receives structured intent and strategy choices
        from an agent adapter. It validates their lineage and persists them; it
        does not infer an interpretation from the feedback text.
        """

        prepared = self._prepare_successor(
            prior_round_id=prior_round_id,
            successor_round_id=successor_round_id,
            feedback_input_id=feedback_input_id,
            change_dimensions=change_dimensions,
            change_reason=change_reason,
            safe_checkpoint=safe_checkpoint,
            candidates=candidates,
            intent_id=intent_id,
            intent_input_ids=intent_input_ids,
            context_bundle_id=context_bundle_id,
            context_member_input_ids=context_member_input_ids,
            brief_id=brief_id,
            selected_input_ids=selected_input_ids,
            strategy_id=strategy_id,
            strategy_summary=strategy_summary,
            strategy_focus=strategy_focus,
            overall_rejection=overall_rejection,
        )
        feedback_content = _nonempty_string(feedback_text, "feedback_text")
        feedback_locator = _nonempty_string(feedback_origin_locator, "feedback_origin_locator")
        interpretation = _nonempty_string(working_interpretation, "working_interpretation")
        outcome = _nonempty_string(technical_outcome, "technical_outcome")
        if not isinstance(intent_analysis, Mapping):
            raise InvalidFeedbackError("intent_analysis must be a mapping")
        if not isinstance(input_roles, Mapping):
            raise InvalidFeedbackError("input_roles must be a mapping")
        if isinstance(material_conflicts, (str, bytes)) or not isinstance(material_conflicts, Sequence):
            raise InvalidFeedbackError("material_conflicts must be a sequence")
        if not isinstance(overall_rejection, bool):
            raise InvalidFeedbackError("overall_rejection must be a bool")

        round_record = self._store.create_round(
            successor_round_id,
            parent_round_id=None if overall_rejection else prepared.prior_round.id,
        )
        feedback_input = self._intake.ingest_text(
            round_id=round_record.id,
            input_id=feedback_input_id,
            kind="feedback",
            content=feedback_content,
            origin_type="user",
            origin_locator=feedback_locator,
            role="signal",
        )
        carried_inputs = self._copy_carried_inputs(round_record.id, prepared.candidates)
        if context_bundle_id is not None:
            self._intake.create_context_bundle(
                round_id=round_record.id,
                input_id=context_bundle_id,
                member_input_ids=prepared.context_member_input_ids,
                origin_type="generated",
                origin_locator=f"feedback-lineage:{prepared.prior_round.id}",
                role="baseline",
                grouping="agent_composed",
            )

        context_bundle_ids: tuple[str, ...] = () if context_bundle_id is None else (context_bundle_id,)
        intent_model = IntentModelCompiler(self._store).compile(
            round_id=round_record.id,
            intent_id=intent_id,
            context_bundle_ids=context_bundle_ids,
            input_ids=prepared.intent_input_ids,
            analysis=intent_analysis,
        )
        working_brief = WorkingBriefCompiler(self._store).compile(
            round_id=round_record.id,
            brief_id=brief_id,
            intent_model=intent_model,
            triggers=[
                {
                    "kind": "feedback",
                    "text": feedback_content,
                    "input_ids": [feedback_input_id],
                }
            ],
            context_bundle_ids=context_bundle_ids,
            selected_input_ids=prepared.selected_input_ids,
            input_roles=input_roles,
            material_conflicts=material_conflicts,
            working_interpretation=interpretation,
            technical_outcome=outcome,
            assumptions=assumptions,
            prior_material_disposition={
                candidate.artifact.id: candidate.disposition for candidate in prepared.candidates
            },
            delivery_targets=delivery_targets,
        )
        lineage = self._append_feedback_lineage(
            round_id=round_record.id,
            prior_round_id=prepared.prior_round.id,
            feedback_input=feedback_input,
            candidates=prepared.candidates,
            change_dimensions=prepared.change_dimensions,
            change_reason=prepared.change_reason,
            safe_checkpoint=prepared.safe_checkpoint,
            overall_rejection=overall_rejection,
        )
        strategy = self._append_strategy(
            round_id=round_record.id,
            strategy_id=strategy_id,
            intent_model=intent_model,
            working_brief=working_brief,
            lineage=lineage,
            change_dimensions=prepared.change_dimensions,
            summary=prepared.strategy_summary,
            focus=prepared.strategy_focus,
        )
        supersession = self._append_supersession(
            prior_round_id=prepared.prior_round.id,
            successor_round_id=round_record.id,
            feedback_input=feedback_input,
            safe_checkpoint=prepared.safe_checkpoint,
            reason=prepared.change_reason,
        )
        return FeedbackRoundArtifacts(
            round=round_record,
            feedback_input=feedback_input,
            carried_inputs=carried_inputs,
            intent_model=intent_model,
            working_brief=working_brief,
            lineage=lineage,
            strategy=strategy,
            supersession=supersession,
        )

    def record_same_round_replan(
        self,
        *,
        round_id: str,
        replan_id: str,
        feedback_input_id: str,
        feedback_text: str,
        feedback_origin_locator: str,
        reason: str,
        affected_work_items: Sequence[ArtifactRevision] = (),
    ) -> ArtifactRevision:
        """Record a bounded internal adjustment without creating a successor."""

        try:
            snapshot = self._store.load_round(round_id)
            validate_identifier(replan_id, "replan_id")
            if replan_id == feedback_input_id:
                raise InvalidFeedbackError("replan_id and feedback_input_id must differ")
            _ensure_artifact_id_compatibility(snapshot.artifacts, replan_id, SAME_ROUND_REPLAN_KIND)
            validate_identifier(feedback_input_id, "feedback_input_id")
            _ensure_feedback_id_is_available(snapshot.artifacts, feedback_input_id)
            normalized_reason = _nonempty_string(reason, "reason")
            feedback_content = _nonempty_string(feedback_text, "feedback_text")
            feedback_locator = _nonempty_string(feedback_origin_locator, "feedback_origin_locator")
            works = _resolve_affected_work_items(snapshot.artifacts, affected_work_items, round_id)
        except (InvalidIdentifierError, TypeError, ValueError) as error:
            raise InvalidFeedbackError(str(error)) from error

        feedback_input = self._intake.ingest_text(
            round_id=round_id,
            input_id=feedback_input_id,
            kind="feedback",
            content=feedback_content,
            origin_type="user",
            origin_locator=feedback_locator,
            role="signal",
        )
        payload = {
            "id": replan_id,
            "round_id": round_id,
            "classification": "same_round_replan",
            "feedback_input_id": feedback_input.id,
            "reason": normalized_reason,
            "affected_work_refs": [ArtifactRef(work.round_id, work.id, work.revision).to_dict() for work in works],
        }
        validate_same_round_replan_payload(payload)
        return self._store.append_artifact(
            round_id,
            replan_id,
            SAME_ROUND_REPLAN_KIND,
            payload,
            parent_refs=(
                ArtifactRef(feedback_input.round_id, feedback_input.id, feedback_input.revision),
                *(ArtifactRef(work.round_id, work.id, work.revision) for work in works),
            ),
        )

    def _prepare_successor(
        self,
        *,
        prior_round_id: str,
        successor_round_id: str,
        feedback_input_id: str,
        change_dimensions: Sequence[str],
        change_reason: str,
        safe_checkpoint: str,
        candidates: Sequence[CandidateContext],
        intent_id: str,
        intent_input_ids: Sequence[str],
        context_bundle_id: str | None,
        context_member_input_ids: Sequence[str],
        brief_id: str,
        selected_input_ids: Sequence[str],
        strategy_id: str,
        strategy_summary: str,
        strategy_focus: Sequence[str],
        overall_rejection: bool,
    ) -> _PreparedSuccessor:
        try:
            prior_snapshot = self._store.load_round(prior_round_id)
            validate_identifier(successor_round_id, "successor_round_id")
            if successor_round_id == prior_round_id:
                raise InvalidFeedbackError("successor_round_id must differ from prior_round_id")
            try:
                self._store.load_round(successor_round_id)
            except RoundNotFoundError:
                pass
            else:
                raise InvalidFeedbackError(f"successor round already exists: {successor_round_id}")
            validate_identifier(feedback_input_id, "feedback_input_id")
            validate_identifier(intent_id, "intent_id")
            validate_identifier(brief_id, "brief_id")
            validate_identifier(strategy_id, "strategy_id")
            if context_bundle_id is not None:
                validate_identifier(context_bundle_id, "context_bundle_id")
            ids = [feedback_input_id, intent_id, brief_id, strategy_id]
            if context_bundle_id is not None:
                ids.append(context_bundle_id)
            if len(set(ids)) != len(ids):
                raise InvalidFeedbackError("successor feedback, model, brief, bundle, and strategy ids must differ")
            if not isinstance(overall_rejection, bool):
                raise InvalidFeedbackError("overall_rejection must be a bool")
            normalized_candidates = _normalize_candidates(prior_snapshot.artifacts, candidates)
            source_ids = [candidate.artifact.id for candidate in normalized_candidates]
            if len(set(source_ids)) != len(source_ids):
                raise InvalidFeedbackError(
                    "candidate source artifact ids must be distinct for the Working Brief disposition map"
                )
            dimensions = _enum_sequence(
                change_dimensions,
                "change_dimensions",
                TARGET_CHANGE_DIMENSIONS,
            )
            reason = _nonempty_string(change_reason, "change_reason")
            checkpoint = _nonempty_string(safe_checkpoint, "safe_checkpoint")
            model_inputs = _identifier_sequence(intent_input_ids, "intent_input_ids")
            selected_inputs = _identifier_sequence(selected_input_ids, "selected_input_ids")
            members = _identifier_sequence(
                context_member_input_ids,
                "context_member_input_ids",
                allow_empty=context_bundle_id is None,
            )
            carried_input_ids = {
                candidate.artifact.id
                for candidate in normalized_candidates
                if candidate.artifact.kind == INPUT_LEDGER_ARTIFACT_KIND
                and candidate.artifact.payload.get("kind") != "context_bundle"
                and candidate.disposition in CARRIED_INPUT_DISPOSITIONS
            }
            if feedback_input_id in carried_input_ids:
                raise InvalidFeedbackError("feedback_input_id cannot collide with a carried predecessor input id")
            if set(ids) & carried_input_ids:
                raise InvalidFeedbackError(
                    "successor model, brief, bundle, and strategy ids cannot collide with carried inputs"
                )
            available_inputs = {feedback_input_id, *carried_input_ids}
            if not set(model_inputs) <= available_inputs:
                raise InvalidFeedbackError(
                    "intent_input_ids must use feedback or explicitly carried predecessor inputs"
                )
            if feedback_input_id not in model_inputs:
                raise InvalidFeedbackError("feedback_input_id must be included in intent_input_ids")
            if not set(selected_inputs) <= set(model_inputs):
                raise InvalidFeedbackError("selected_input_ids must be a subset of the successor Intent Model inputs")
            if feedback_input_id not in selected_inputs:
                raise InvalidFeedbackError("feedback_input_id must be selected by the successor Working Brief")
            if context_bundle_id is None and members:
                raise InvalidFeedbackError("context_member_input_ids require a context_bundle_id")
            if context_bundle_id is not None:
                if not members:
                    raise InvalidFeedbackError("context_bundle_id requires at least one member input")
                if not set(members) <= available_inputs:
                    raise InvalidFeedbackError(
                        "context bundle members must use feedback or explicitly carried predecessor inputs"
                    )
            focus = _string_sequence(strategy_focus, "strategy_focus")
            summary = _nonempty_string(strategy_summary, "strategy_summary")
        except (InvalidIdentifierError, TypeError, ValueError) as error:
            raise InvalidFeedbackError(str(error)) from error
        return _PreparedSuccessor(
            prior_round=prior_snapshot.record,
            candidates=normalized_candidates,
            change_dimensions=dimensions,
            change_reason=reason,
            safe_checkpoint=checkpoint,
            intent_input_ids=model_inputs,
            context_member_input_ids=members,
            selected_input_ids=selected_inputs,
            strategy_focus=focus,
            strategy_summary=summary,
        )

    def _copy_carried_inputs(
        self,
        successor_round_id: str,
        candidates: Sequence[CandidateContext],
    ) -> tuple[ArtifactRevision, ...]:
        copied: list[ArtifactRevision] = []
        for candidate in candidates:
            source = candidate.artifact
            if (
                source.kind != INPUT_LEDGER_ARTIFACT_KIND
                or source.payload.get("kind") == "context_bundle"
                or candidate.disposition not in CARRIED_INPUT_DISPOSITIONS
            ):
                continue
            payload = thaw_json(source.payload)
            if not isinstance(payload, dict):
                raise InvalidFeedbackError("predecessor Input Ledger payload is malformed")
            payload["used_by_rounds"] = [successor_round_id]
            copied.append(
                self._store.append_artifact(
                    successor_round_id,
                    source.id,
                    INPUT_LEDGER_ARTIFACT_KIND,
                    payload,
                    parent_refs=(ArtifactRef(source.round_id, source.id, source.revision),),
                )
            )
        return tuple(copied)

    def _append_feedback_lineage(
        self,
        *,
        round_id: str,
        prior_round_id: str,
        feedback_input: ArtifactRevision,
        candidates: Sequence[CandidateContext],
        change_dimensions: Sequence[str],
        change_reason: str,
        safe_checkpoint: str,
        overall_rejection: bool,
    ) -> ArtifactRevision:
        lineage_id = f"feedback-lineage-{round_id}"
        payload = {
            "id": lineage_id,
            "round_id": round_id,
            "prior_round_id": prior_round_id,
            "lineage_kind": "new_root" if overall_rejection else "successor",
            "feedback_input_ref": ArtifactRef(
                feedback_input.round_id,
                feedback_input.id,
                feedback_input.revision,
            ).to_dict(),
            "change_dimensions": list(change_dimensions),
            "change_reason": change_reason,
            "safe_checkpoint": safe_checkpoint,
            "candidate_context": [
                {
                    "id": candidate.candidate_id,
                    "source_ref": ArtifactRef(
                        candidate.artifact.round_id,
                        candidate.artifact.id,
                        candidate.artifact.revision,
                    ).to_dict(),
                    "source_kind": candidate.artifact.kind,
                    "disposition": candidate.disposition,
                    "rationale": candidate.rationale,
                }
                for candidate in candidates
            ],
        }
        validate_feedback_lineage_payload(payload)
        parent_refs = (
            ArtifactRef(feedback_input.round_id, feedback_input.id, feedback_input.revision),
            *(ArtifactRef(item.artifact.round_id, item.artifact.id, item.artifact.revision) for item in candidates),
        )
        return self._store.append_artifact(
            round_id,
            lineage_id,
            FEEDBACK_LINEAGE_KIND,
            payload,
            parent_refs=parent_refs,
        )

    def _append_strategy(
        self,
        *,
        round_id: str,
        strategy_id: str,
        intent_model: ArtifactRevision,
        working_brief: ArtifactRevision,
        lineage: ArtifactRevision,
        change_dimensions: Sequence[str],
        summary: str,
        focus: Sequence[str],
    ) -> ArtifactRevision:
        payload = {
            "id": strategy_id,
            "round_id": round_id,
            "intent_model_id": intent_model.id,
            "working_brief_id": working_brief.id,
            "feedback_lineage_id": lineage.id,
            "change_dimensions": list(change_dimensions),
            "summary": summary,
            "focus": list(focus),
            "autonomy": {
                "ask_user": "only_non_recoverable_decisions",
                "routine_unknowns": "record_assumptions_and_validate",
            },
        }
        validate_research_strategy_payload(payload)
        return self._store.append_artifact(
            round_id,
            strategy_id,
            RESEARCH_STRATEGY_KIND,
            payload,
            parent_refs=(
                ArtifactRef(intent_model.round_id, intent_model.id, intent_model.revision),
                ArtifactRef(working_brief.round_id, working_brief.id, working_brief.revision),
                ArtifactRef(lineage.round_id, lineage.id, lineage.revision),
            ),
        )

    def _append_supersession(
        self,
        *,
        prior_round_id: str,
        successor_round_id: str,
        feedback_input: ArtifactRevision,
        safe_checkpoint: str,
        reason: str,
    ) -> ArtifactRevision:
        snapshot = self._store.load_round(prior_round_id)
        active_work = _latest_active_work(snapshot.artifacts)
        supersession_id = f"round-supersession-{successor_round_id}"
        _ensure_artifact_id_compatibility(
            snapshot.artifacts,
            supersession_id,
            ROUND_SUPERSESSION_KIND,
        )
        payload = {
            "id": supersession_id,
            "round_id": prior_round_id,
            "status": "superseded",
            "successor_round_id": successor_round_id,
            "feedback_input_ref": ArtifactRef(
                feedback_input.round_id,
                feedback_input.id,
                feedback_input.revision,
            ).to_dict(),
            "safe_checkpoint": safe_checkpoint,
            "reason": reason,
            "active_work": [
                {
                    "work_item_ref": ArtifactRef(work.round_id, work.id, work.revision).to_dict(),
                    "status_at_checkpoint": work.payload["status"],
                    "disposition": "superseded",
                }
                for work in active_work
            ],
        }
        validate_round_supersession_payload(payload)
        return self._store.append_artifact(
            prior_round_id,
            supersession_id,
            ROUND_SUPERSESSION_KIND,
            payload,
            parent_refs=(
                ArtifactRef(feedback_input.round_id, feedback_input.id, feedback_input.revision),
                *(ArtifactRef(work.round_id, work.id, work.revision) for work in active_work),
            ),
        )


def validate_feedback_lineage_payload(payload: Mapping[str, Any]) -> None:
    """Validate an inspectable cross-round candidate-context record."""

    data = _mapping(payload, "feedback lineage payload")
    _require_exact_keys(
        data,
        {
            "id",
            "round_id",
            "prior_round_id",
            "lineage_kind",
            "feedback_input_ref",
            "change_dimensions",
            "change_reason",
            "safe_checkpoint",
            "candidate_context",
        },
        "feedback lineage payload",
    )
    _identifier(data["id"], "feedback lineage id")
    _identifier(data["round_id"], "feedback lineage round_id")
    _identifier(data["prior_round_id"], "feedback lineage prior_round_id")
    lineage_kind = _nonempty_string(data["lineage_kind"], "feedback lineage lineage_kind")
    if lineage_kind not in {"successor", "new_root"}:
        raise InvalidFeedbackError("feedback lineage lineage_kind is unsupported")
    _validate_ref(data["feedback_input_ref"], "feedback lineage feedback_input_ref")
    _enum_sequence(data["change_dimensions"], "feedback lineage change_dimensions", TARGET_CHANGE_DIMENSIONS)
    _nonempty_string(data["change_reason"], "feedback lineage change_reason")
    _nonempty_string(data["safe_checkpoint"], "feedback lineage safe_checkpoint")
    candidates = _mapping_sequence(data["candidate_context"], "feedback lineage candidate_context", allow_empty=True)
    candidate_ids: set[str] = set()
    source_refs: set[ArtifactRef] = set()
    for index, candidate in enumerate(candidates):
        label = f"feedback lineage candidate_context[{index}]"
        _require_exact_keys(
            candidate,
            {"id", "source_ref", "source_kind", "disposition", "rationale"},
            label,
        )
        candidate_id = _identifier(candidate["id"], f"{label}.id")
        if candidate_id in candidate_ids:
            raise InvalidFeedbackError(f"duplicate feedback lineage candidate id: {candidate_id}")
        candidate_ids.add(candidate_id)
        source_ref = _validate_ref(candidate["source_ref"], f"{label}.source_ref")
        if source_ref in source_refs:
            raise InvalidFeedbackError(f"duplicate feedback lineage source ref: {source_ref}")
        source_refs.add(source_ref)
        _identifier(candidate["source_kind"], f"{label}.source_kind")
        disposition = _nonempty_string(candidate["disposition"], f"{label}.disposition")
        if disposition not in CANDIDATE_DISPOSITIONS:
            raise InvalidFeedbackError(f"{label}.disposition is unsupported: {disposition}")
        _nonempty_string(candidate["rationale"], f"{label}.rationale")


def validate_research_strategy_payload(payload: Mapping[str, Any]) -> None:
    """Validate the narrow strategy boundary created with a successor round."""

    data = _mapping(payload, "research strategy payload")
    _require_exact_keys(
        data,
        {
            "id",
            "round_id",
            "intent_model_id",
            "working_brief_id",
            "feedback_lineage_id",
            "change_dimensions",
            "summary",
            "focus",
            "autonomy",
        },
        "research strategy payload",
    )
    for key in (
        "id",
        "round_id",
        "intent_model_id",
        "working_brief_id",
        "feedback_lineage_id",
    ):
        _identifier(data[key], f"research strategy {key}")
    _enum_sequence(data["change_dimensions"], "research strategy change_dimensions", TARGET_CHANGE_DIMENSIONS)
    _nonempty_string(data["summary"], "research strategy summary")
    _string_sequence(data["focus"], "research strategy focus")
    autonomy = _mapping(data["autonomy"], "research strategy autonomy")
    _require_exact_keys(
        autonomy,
        {"ask_user", "routine_unknowns"},
        "research strategy autonomy",
    )
    if autonomy["ask_user"] != "only_non_recoverable_decisions":
        raise InvalidFeedbackError("research strategy autonomy.ask_user is not the fixed policy")
    if autonomy["routine_unknowns"] != "record_assumptions_and_validate":
        raise InvalidFeedbackError("research strategy autonomy.routine_unknowns is not the fixed policy")


def validate_round_supersession_payload(payload: Mapping[str, Any]) -> None:
    """Validate a non-destructive predecessor supersession overlay."""

    data = _mapping(payload, "round supersession payload")
    _require_exact_keys(
        data,
        {
            "id",
            "round_id",
            "status",
            "successor_round_id",
            "feedback_input_ref",
            "safe_checkpoint",
            "reason",
            "active_work",
        },
        "round supersession payload",
    )
    _identifier(data["id"], "round supersession id")
    _identifier(data["round_id"], "round supersession round_id")
    _identifier(data["successor_round_id"], "round supersession successor_round_id")
    if data["status"] != "superseded":
        raise InvalidFeedbackError("round supersession status must be superseded")
    _validate_ref(data["feedback_input_ref"], "round supersession feedback_input_ref")
    _nonempty_string(data["safe_checkpoint"], "round supersession safe_checkpoint")
    _nonempty_string(data["reason"], "round supersession reason")
    active_work = _mapping_sequence(data["active_work"], "round supersession active_work", allow_empty=True)
    seen: set[ArtifactRef] = set()
    for index, work in enumerate(active_work):
        label = f"round supersession active_work[{index}]"
        _require_exact_keys(
            work,
            {"work_item_ref", "status_at_checkpoint", "disposition"},
            label,
        )
        reference = _validate_ref(work["work_item_ref"], f"{label}.work_item_ref")
        if reference in seen:
            raise InvalidFeedbackError(f"duplicate active Work Item in supersession: {reference}")
        seen.add(reference)
        status = _nonempty_string(work["status_at_checkpoint"], f"{label}.status_at_checkpoint")
        if status not in ACTIVE_WORK_STATUSES:
            raise InvalidFeedbackError(f"{label}.status_at_checkpoint is not active")
        if work["disposition"] != "superseded":
            raise InvalidFeedbackError(f"{label}.disposition must be superseded")


def validate_same_round_replan_payload(payload: Mapping[str, Any]) -> None:
    """Validate an internal replan that must not masquerade as a successor."""

    data = _mapping(payload, "same-round replan payload")
    _require_exact_keys(
        data,
        {"id", "round_id", "classification", "feedback_input_id", "reason", "affected_work_refs"},
        "same-round replan payload",
    )
    _identifier(data["id"], "same-round replan id")
    _identifier(data["round_id"], "same-round replan round_id")
    _identifier(data["feedback_input_id"], "same-round replan feedback_input_id")
    if data["classification"] != "same_round_replan":
        raise InvalidFeedbackError("same-round replan classification must be same_round_replan")
    _nonempty_string(data["reason"], "same-round replan reason")
    refs = data["affected_work_refs"]
    if isinstance(refs, (str, bytes)) or not isinstance(refs, Sequence):
        raise InvalidFeedbackError("same-round replan affected_work_refs must be a sequence")
    seen: set[ArtifactRef] = set()
    for index, reference in enumerate(refs):
        parsed = _validate_ref(reference, f"same-round replan affected_work_refs[{index}]")
        if parsed in seen:
            raise InvalidFeedbackError(f"duplicate affected Work Item: {parsed}")
        seen.add(parsed)


def _normalize_candidates(
    prior_artifacts: Sequence[ArtifactRevision],
    candidates: Sequence[CandidateContext],
) -> tuple[CandidateContext, ...]:
    if isinstance(candidates, (str, bytes)) or not isinstance(candidates, Sequence):
        raise InvalidFeedbackError("candidates must be a sequence of CandidateContext values")
    stored_by_ref = {
        ArtifactRef(artifact.round_id, artifact.id, artifact.revision): artifact for artifact in prior_artifacts
    }
    normalized: list[CandidateContext] = []
    candidate_ids: set[str] = set()
    source_refs: set[ArtifactRef] = set()
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, CandidateContext):
            raise InvalidFeedbackError(f"candidates[{index}] must be a CandidateContext")
        candidate_id = _identifier(candidate.candidate_id, f"candidates[{index}].candidate_id")
        if candidate_id in candidate_ids:
            raise InvalidFeedbackError(f"duplicate candidate_id: {candidate_id}")
        candidate_ids.add(candidate_id)
        if not isinstance(candidate.artifact, ArtifactRevision):
            raise InvalidFeedbackError(f"candidates[{index}].artifact must be an ArtifactRevision")
        reference = ArtifactRef(
            candidate.artifact.round_id,
            candidate.artifact.id,
            candidate.artifact.revision,
        )
        stored = stored_by_ref.get(reference)
        if stored is None or stored != candidate.artifact:
            raise InvalidFeedbackError(
                f"candidates[{index}].artifact must be an exact artifact from the predecessor round"
            )
        if reference in source_refs:
            raise InvalidFeedbackError(f"duplicate candidate source ref: {reference}")
        source_refs.add(reference)
        disposition = _nonempty_string(candidate.disposition, f"candidates[{index}].disposition")
        if disposition not in CANDIDATE_DISPOSITIONS:
            raise InvalidFeedbackError(f"unsupported candidate disposition: {disposition}")
        rationale = _nonempty_string(candidate.rationale, f"candidates[{index}].rationale")
        normalized.append(
            CandidateContext(
                candidate_id=candidate_id,
                artifact=stored,
                disposition=disposition,
                rationale=rationale,
            )
        )

    required = {
        ArtifactRef(artifact.round_id, artifact.id, artifact.revision)
        for artifact in _latest_artifacts(prior_artifacts)
        if artifact.kind in REQUIRED_CANDIDATE_KINDS
    }
    missing = sorted(
        required - source_refs,
        key=lambda reference: (reference.artifact_id, reference.revision),
    )
    if missing:
        rendered = ", ".join(
            f"{reference.round_id}/{reference.artifact_id}@{reference.revision}" for reference in missing
        )
        raise InvalidFeedbackError(
            "candidates must explicitly disposition every latest prior input, finding, and decision: " + rendered
        )
    return tuple(normalized)


def _latest_artifacts(artifacts: Sequence[ArtifactRevision]) -> tuple[ArtifactRevision, ...]:
    latest: dict[tuple[str, str], ArtifactRevision] = {}
    for artifact in artifacts:
        key = (artifact.id, artifact.kind)
        previous = latest.get(key)
        if previous is None or artifact.revision > previous.revision:
            latest[key] = artifact
    return tuple(sorted(latest.values(), key=lambda artifact: (artifact.kind, artifact.id)))


def _resolve_affected_work_items(
    artifacts: Sequence[ArtifactRevision],
    values: Sequence[ArtifactRevision],
    round_id: str,
) -> tuple[ArtifactRevision, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise InvalidFeedbackError("affected_work_items must be a sequence")
    stored_by_ref = {ArtifactRef(artifact.round_id, artifact.id, artifact.revision): artifact for artifact in artifacts}
    resolved: list[ArtifactRevision] = []
    seen: set[ArtifactRef] = set()
    for index, value in enumerate(values):
        if not isinstance(value, ArtifactRevision):
            raise InvalidFeedbackError(f"affected_work_items[{index}] must be an ArtifactRevision")
        reference = ArtifactRef(value.round_id, value.id, value.revision)
        stored = stored_by_ref.get(reference)
        if stored is None or stored != value or stored.kind != WORK_ITEM_KIND:
            raise InvalidFeedbackError(f"affected_work_items[{index}] must be an exact current-round Work Item")
        if stored.round_id != round_id:
            raise InvalidFeedbackError("affected Work Item belongs to a different round")
        if reference in seen:
            raise InvalidFeedbackError(f"duplicate affected Work Item: {reference}")
        seen.add(reference)
        resolved.append(stored)
    return tuple(resolved)


def _latest_active_work(artifacts: Sequence[ArtifactRevision]) -> tuple[ArtifactRevision, ...]:
    latest_work = {
        artifact.id: artifact for artifact in _latest_artifacts(artifacts) if artifact.kind == WORK_ITEM_KIND
    }
    return tuple(
        latest_work[work_id]
        for work_id in sorted(latest_work)
        if latest_work[work_id].payload.get("status") in ACTIVE_WORK_STATUSES
    )


def _ensure_artifact_id_compatibility(artifacts: Sequence[ArtifactRevision], artifact_id: str, kind: str) -> None:
    foreign_kinds = {artifact.kind for artifact in artifacts if artifact.id == artifact_id and artifact.kind != kind}
    if foreign_kinds:
        raise InvalidFeedbackError(f"artifact id {artifact_id!r} is already used by kinds: {sorted(foreign_kinds)}")


def _ensure_feedback_id_is_available(artifacts: Sequence[ArtifactRevision], feedback_input_id: str) -> None:
    foreign_kinds = {
        artifact.kind
        for artifact in artifacts
        if artifact.id == feedback_input_id and artifact.kind != INPUT_LEDGER_ARTIFACT_KIND
    }
    if foreign_kinds:
        raise InvalidFeedbackError(
            f"feedback_input_id {feedback_input_id!r} is already used by kinds: {sorted(foreign_kinds)}"
        )
    input_kinds = {
        artifact.payload.get("kind")
        for artifact in artifacts
        if artifact.id == feedback_input_id and artifact.kind == INPUT_LEDGER_ARTIFACT_KIND
    }
    if input_kinds and input_kinds != {"feedback"}:
        raise InvalidFeedbackError(
            f"feedback_input_id {feedback_input_id!r} already represents non-feedback input material"
        )


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidFeedbackError(f"{label} must be a mapping")
    return value


def _mapping_sequence(value: Any, label: str, *, allow_empty: bool = False) -> list[Mapping[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise InvalidFeedbackError(f"{label} must be a sequence")
    normalized: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise InvalidFeedbackError(f"{label}[{index}] must be a mapping")
        normalized.append(item)
    if not normalized and not allow_empty:
        raise InvalidFeedbackError(f"{label} must not be empty")
    return normalized


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise InvalidFeedbackError(f"{label} must be a string")
    try:
        return validate_identifier(value, label)
    except InvalidIdentifierError as error:
        raise InvalidFeedbackError(str(error)) from error


def _identifier_sequence(value: Any, label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise InvalidFeedbackError(f"{label} must be a sequence")
    normalized = tuple(_identifier(item, f"{label}[{index}]") for index, item in enumerate(value))
    if not normalized and not allow_empty:
        raise InvalidFeedbackError(f"{label} must not be empty")
    if len(set(normalized)) != len(normalized):
        raise InvalidFeedbackError(f"{label} must not contain duplicates")
    return normalized


def _string_sequence(value: Any, label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise InvalidFeedbackError(f"{label} must be a sequence")
    normalized = tuple(_nonempty_string(item, f"{label}[{index}]") for index, item in enumerate(value))
    if not normalized and not allow_empty:
        raise InvalidFeedbackError(f"{label} must not be empty")
    if len(set(normalized)) != len(normalized):
        raise InvalidFeedbackError(f"{label} must not contain duplicates")
    return normalized


def _enum_sequence(value: Any, label: str, values: frozenset[str]) -> tuple[str, ...]:
    normalized = _string_sequence(value, label)
    unsupported = sorted(set(normalized) - values)
    if unsupported:
        raise InvalidFeedbackError(f"{label} contains unsupported values: {unsupported}")
    return normalized


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidFeedbackError(f"{label} must be a nonempty string")
    return value.strip()


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise InvalidFeedbackError(f"{label} keys must be exactly {sorted(expected)}, got {sorted(actual)}")


def _validate_ref(value: Any, label: str) -> ArtifactRef:
    if not isinstance(value, Mapping):
        raise InvalidFeedbackError(f"{label} must be an artifact reference mapping")
    try:
        return ArtifactRef.from_dict(dict(value))
    except (InvalidIdentifierError, TypeError, ValueError, RuntimeStoreError) as error:
        raise InvalidFeedbackError(f"{label} is invalid: {error}") from error
