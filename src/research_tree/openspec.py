"""Explicit OpenSpec projection for implementation-ready research packages."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import tempfile
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .delivery import TECHNICAL_RESEARCH_PACKAGE_KIND, validate_technical_package_payload
from .domain import (
    ArtifactRef,
    ArtifactRevision,
    InvalidIdentifierError,
    RuntimeStoreError,
    thaw_json,
    validate_identifier,
)
from .readiness import (
    READINESS_RECORD_KIND,
    readiness_for_delivery,
    validate_readiness_record_payload,
)
from .storage import RunStore


class OpenSpecExportError(RuntimeStoreError):
    """Base error for an explicit OpenSpec conversion."""


class InvalidOpenSpecExportError(OpenSpecExportError):
    """Raised before an invalid package can emit OpenSpec files."""


@dataclass(frozen=True, slots=True)
class OpenSpecExport:
    """The files emitted by one caller-requested OpenSpec conversion."""

    change_name: str
    change_directory: Path
    technical_package_ref: ArtifactRef
    draft: bool
    files: Mapping[str, Path]


class OpenSpecExporter:
    """Project a persisted Technical Research Package into an OpenSpec change.

    The exporter has no default output location and is deliberately separate
    from ``DeliveryCompiler``. Calling it is the explicit opt-in that permits
    creation of files under the supplied OpenSpec root.
    """

    def __init__(self, store: RunStore) -> None:
        self._store = store

    def export(
        self,
        *,
        round_id: str,
        technical_package: ArtifactRevision,
        openspec_root: str | Path,
        change_name: str,
        draft: bool = False,
    ) -> OpenSpecExport:
        """Emit a non-overwriting OpenSpec change from one exact package.

        Normal mode requires the package's implementation-facing closure and
        readiness gates to pass. ``draft=True`` is an explicit caller choice
        that preserves visible blockers instead of inventing missing design.
        """

        try:
            snapshot = self._store.load_round(round_id)
            package = _resolve_exact_package(snapshot.artifacts, technical_package)
            if package.round_id != round_id:
                raise InvalidOpenSpecExportError(
                    "technical_package must belong to the requested export round"
                )
            validate_technical_package_payload(package.payload)
            if not isinstance(draft, bool):
                raise InvalidOpenSpecExportError("draft must be a boolean")
            selected_change_name = validate_identifier(change_name, "change_name")
            root = _openspec_root(openspec_root)
            document = _mapping(thaw_json(package.payload["document"]), "technical package document")
            _validate_traceability_against_parents(document, package, round_id)
            _validate_export_document_semantics(document)
            normal_blockers = _normal_export_blockers(document)
            if normal_blockers and not draft:
                raise InvalidOpenSpecExportError(
                    "OpenSpec export requires an implementation-ready package: "
                    + "; ".join(normal_blockers)
                )
            if not draft:
                verified_readiness = _resolve_verified_readiness(
                    snapshot.artifacts, package, round_id
                )
                normal_blockers += _verified_readiness_blockers(verified_readiness)
            draft_blockers = _draft_blockers(document, normal_blockers)
            if normal_blockers and not draft:
                raise InvalidOpenSpecExportError(
                    "OpenSpec export requires an implementation-ready package: "
                    + "; ".join(normal_blockers)
                )
            files = _render_files(
                change_name=selected_change_name,
                technical_package=package,
                document=document,
                draft=draft,
                blockers=draft_blockers if draft else (),
            )
        except InvalidOpenSpecExportError:
            raise
        except (InvalidIdentifierError, RuntimeStoreError, TypeError, ValueError) as error:
            raise InvalidOpenSpecExportError(str(error)) from error

        change_directory = root / "changes" / selected_change_name
        _write_change(change_directory, files)
        written = MappingProxyType(
            {relative: change_directory / Path(relative) for relative in files}
        )
        return OpenSpecExport(
            change_name=selected_change_name,
            change_directory=change_directory,
            technical_package_ref=ArtifactRef(round_id, package.id, package.revision),
            draft=draft,
            files=written,
        )


def _resolve_exact_package(
    artifacts: Sequence[ArtifactRevision], technical_package: ArtifactRevision
) -> ArtifactRevision:
    if not isinstance(technical_package, ArtifactRevision):
        raise InvalidOpenSpecExportError("technical_package must be an ArtifactRevision")
    for stored in artifacts:
        if stored.id == technical_package.id and stored.revision == technical_package.revision:
            if stored != technical_package:
                raise InvalidOpenSpecExportError(
                    "technical_package does not match its persisted revision"
                )
            if stored.kind != TECHNICAL_RESEARCH_PACKAGE_KIND:
                raise InvalidOpenSpecExportError(
                    "technical_package must be a technical-research-package artifact"
                )
            return stored
    raise InvalidOpenSpecExportError("technical_package has not been persisted in this RunStore")


def _openspec_root(value: str | Path) -> Path:
    if not isinstance(value, (str, Path)):
        raise InvalidOpenSpecExportError("openspec_root must be a path")
    root = Path(value).expanduser().resolve(strict=False)
    if root.exists() and not root.is_dir():
        raise InvalidOpenSpecExportError("openspec_root must be a directory when it exists")
    return root


def _validate_traceability_against_parents(
    document: Mapping[str, Any], package: ArtifactRevision, round_id: str
) -> None:
    traceability = _mapping(document["traceability"], "technical package traceability")
    reference_values: list[Mapping[str, Any]] = [
        _mapping(traceability["working_brief"], "traceability working_brief"),
        _mapping(traceability["intent_model"], "traceability intent_model"),
        _mapping(traceability["blueprint_target"], "traceability blueprint_target"),
    ]
    for field in ("input_refs", "decision_refs", "finding_refs"):
        reference_values.extend(_mapping_sequence(traceability[field], f"traceability {field}"))
    parent_refs = set(package.parent_refs)
    for value in reference_values:
        ref = _artifact_ref(value, "technical package traceability reference")
        if ref.round_id != round_id:
            raise InvalidOpenSpecExportError(
                "technical package traceability reference belongs to a different round"
            )
        if ref not in parent_refs:
            raise InvalidOpenSpecExportError(
                "technical package traceability reference is absent from package parents: "
                + _ref_label(value)
            )


def _validate_export_document_semantics(document: Mapping[str, Any]) -> None:
    """Ensure package sections still describe the same implementation plan.

    ``validate_technical_package_payload`` validates each section's shape. An
    exporter also needs the cross-section checks below because a generic
    ``RunStore`` writer can otherwise persist individually valid but mutually
    contradictory sections.
    """

    closure_by_slot: dict[str, Mapping[str, Any]] = {}
    for item in _mapping_sequence(document["blueprint_closure"], "blueprint_closure"):
        slot_id = _text(item["decision_slot_id"])
        if slot_id in closure_by_slot:
            raise InvalidOpenSpecExportError(
                f"blueprint_closure repeats decision slot: {slot_id}"
            )
        closure_by_slot[slot_id] = item

    records_by_slot: dict[str, Mapping[str, Any]] = {}
    records_by_id: dict[str, Mapping[str, Any]] = {}
    for record in _mapping_sequence(document["decision_records"], "decision_records"):
        slot_id = _text(record["decision_slot_id"])
        decision_id = _text(record["decision_id"])
        if slot_id in records_by_slot:
            raise InvalidOpenSpecExportError(
                f"decision_records repeats decision slot: {slot_id}"
            )
        if decision_id in records_by_id:
            raise InvalidOpenSpecExportError(
                f"decision_records repeats decision id: {decision_id}"
            )
        if slot_id not in closure_by_slot:
            raise InvalidOpenSpecExportError(
                f"decision record refers to an unknown blueprint closure slot: {slot_id}"
            )
        closure = closure_by_slot[slot_id]
        if _text(record["status"]) != _text(closure["status"]):
            raise InvalidOpenSpecExportError(
                f"decision record status does not match blueprint closure for {slot_id}"
            )
        if record["selected_option"] != closure["selected_option"]:
            raise InvalidOpenSpecExportError(
                f"decision record selected option does not match blueprint closure for {slot_id}"
            )
        records_by_slot[slot_id] = record
        records_by_id[decision_id] = record

    for slot_id, closure in closure_by_slot.items():
        status = _text(closure["status"])
        if status != "missing" and slot_id not in records_by_slot:
            raise InvalidOpenSpecExportError(
                f"blueprint closure {slot_id} is {status} without a Decision Ledger record"
            )

    for item in _mapping_sequence(document["implementation_plan"], "implementation_plan"):
        decision_id = _text(item["decision_id"])
        slot_id = _text(item["decision_slot_id"])
        record = records_by_id.get(decision_id)
        if record is None or _text(record["decision_slot_id"]) != slot_id:
            raise InvalidOpenSpecExportError(
                "implementation plan task does not match a Decision Ledger record: "
                f"{decision_id}/{slot_id}"
            )
        task_ids = {
            _text(task["id"])
            for task in _mapping_sequence(record["change_tasks"], "decision change_tasks")
        }
        task_id = _text(item["change_task_id"])
        if task_id not in task_ids:
            raise InvalidOpenSpecExportError(
                f"implementation plan task is absent from Decision Ledger: {task_id}"
            )


def _normal_export_blockers(document: Mapping[str, Any]) -> tuple[str, ...]:
    blockers: list[str] = []
    closure = _mapping_sequence(document["blueprint_closure"], "blueprint_closure")
    if not closure:
        blockers.append("blueprint_closure is empty")
    for item in closure:
        slot_id = _text(item["decision_slot_id"])
        status = _text(item["status"])
        if status in {"missing", "blocked"}:
            blockers.append(f"blueprint closure {slot_id} is {status}")

    plan = _mapping_sequence(document["implementation_plan"], "implementation_plan")
    if not plan:
        blockers.append("implementation_plan is empty")

    readiness = _mapping(document["readiness_record"], "readiness_record")
    gates = _mapping(readiness["gates"], "readiness gates")
    accepted = {
        "intent_alignment": {"pass"},
        "decision_closure": {"pass"},
        "traceability": {"pass"},
        "repository_fit": {"pass", "not_applicable"},
        "implementation_readiness": {"pass"},
        "operational_quality": {"pass", "deferred"},
    }
    for gate, states in accepted.items():
        state = _text(gates[gate])
        if state not in states:
            blockers.append(f"{gate}: {state}")
    return tuple(blockers)


def _resolve_verified_readiness(
    artifacts: Sequence[ArtifactRevision],
    package: ArtifactRevision,
    round_id: str,
) -> ArtifactRevision:
    expected_ref = ArtifactRef(round_id, package.id, package.revision)
    matches: list[ArtifactRevision] = []
    for artifact in artifacts:
        if artifact.kind != READINESS_RECORD_KIND:
            continue
        try:
            validate_readiness_record_payload(artifact.payload)
            package_ref = _artifact_ref(
                artifact.payload["technical_package_ref"],
                "readiness technical_package_ref",
            )
        except (OpenSpecExportError, RuntimeStoreError, TypeError, ValueError) as error:
            raise InvalidOpenSpecExportError(
                f"readiness record {artifact.id}@{artifact.revision} is invalid: {error}"
            ) from error
        if package_ref != expected_ref:
            continue
        if expected_ref not in artifact.parent_refs:
            raise InvalidOpenSpecExportError(
                "readiness record does not retain the exact technical package parent"
            )
        matches.append(artifact)
    if not matches:
        raise InvalidOpenSpecExportError(
            "normal OpenSpec export requires a persisted readiness record for the exact technical package revision"
        )
    return matches[-1]


def _verified_readiness_blockers(record: ArtifactRevision) -> tuple[str, ...]:
    projection = _mapping(readiness_for_delivery(record), "readiness delivery projection")
    gates = _mapping(projection["gates"], "readiness delivery gates")
    accepted = {
        "intent_alignment": {"pass"},
        "decision_closure": {"pass"},
        "traceability": {"pass"},
        "repository_fit": {"pass", "not_applicable"},
        "implementation_readiness": {"pass"},
        "operational_quality": {"pass", "deferred"},
    }
    return tuple(
        f"verified readiness {gate}: {_text(gates[gate])}"
        for gate, states in accepted.items()
        if _text(gates[gate]) not in states
    )


def _draft_blockers(
    document: Mapping[str, Any], normal_blockers: Sequence[str]
) -> tuple[str, ...]:
    blockers = list(normal_blockers)
    closure = _mapping_sequence(document["blueprint_closure"], "blueprint_closure")
    for item in closure:
        status = _text(item["status"])
        if status != "selected":
            entry = (
                f"blueprint closure {_text(item['decision_slot_id'])}: {status}; "
                f"next action: {_text(item['next_action'])}"
            )
            if entry not in blockers:
                blockers.append(entry)
    readiness = _mapping(document["readiness_record"], "readiness_record")
    gates = _mapping(readiness["gates"], "readiness gates")
    for gate in sorted(gates):
        state = _text(gates[gate])
        if state not in {"pass", "not_applicable"}:
            entry = f"{gate}: {state}"
            if entry not in blockers:
                blockers.append(entry)
    return tuple(blockers)


def _render_files(
    *,
    change_name: str,
    technical_package: ArtifactRevision,
    document: Mapping[str, Any],
    draft: bool,
    blockers: Sequence[str],
) -> dict[str, str]:
    files = {
        "proposal.md": _render_proposal(change_name, technical_package, document, draft, blockers),
        "design.md": _render_design(change_name, technical_package, document, draft, blockers),
        "tasks.md": _render_tasks(change_name, technical_package, document, draft, blockers),
    }
    for record in sorted(
        _mapping_sequence(document["decision_records"], "decision_records"),
        key=lambda item: _text(item["decision_slot_id"]),
    ):
        if _text(record["status"]) not in {"selected", "conditional"}:
            continue
        slot_id = _text(record["decision_slot_id"])
        files[f"specs/{slot_id}/spec.md"] = _render_delta_spec(
            slot_id, record, technical_package, draft, blockers
        )
    files["research-tree-export.json"] = _render_manifest(
        change_name, technical_package, document, draft, sorted(files)
    )
    return files


def _render_proposal(
    change_name: str,
    technical_package: ArtifactRevision,
    document: Mapping[str, Any],
    draft: bool,
    blockers: Sequence[str],
) -> str:
    scope = _mapping(document["round_and_scope"], "round_and_scope")
    lines = [f"# Proposal: {change_name}", ""]
    _append_draft_warning(lines, draft, blockers)
    lines.extend(["## Why", "", _text(scope["working_interpretation"]), ""])
    lines.extend(["## What Changes", ""])
    records = _mapping_sequence(document["decision_records"], "decision_records")
    selected = [
        record
        for record in records
        if _text(record["status"]) in {"selected", "conditional"}
    ]
    if not selected:
        lines.append("- No selected or conditional technical decision is present.")
    for record in selected:
        lines.append(
            f"- `{_text(record['decision_slot_id'])}`: "
            f"{_text(record['selected_option'])}; {_text(record['design_consequence'])}"
        )
    lines.extend(["", "## Scope and Non-Goals", ""])
    lines.append(f"- Technical outcome: {_text(scope['technical_outcome'])}")
    for non_goal in _value_sequence(scope["non_goals"], "non_goals"):
        lines.append(f"- Non-goal: {_text(non_goal)}")
    lines.extend(["", "## Repository Delta", ""])
    _append_repository_delta(lines, document)
    lines.extend(["", "## Source Traceability", ""])
    _append_source_traceability(lines, technical_package, document)
    return "\n".join(lines) + "\n"


def _render_delta_spec(
    slot_id: str,
    record: Mapping[str, Any],
    technical_package: ArtifactRevision,
    draft: bool,
    blockers: Sequence[str],
) -> str:
    validation = _mapping(record["validation"], "decision validation")
    lines = [f"# Delta for {slot_id}", ""]
    _append_draft_warning(lines, draft, blockers)
    lines.extend(["## ADDED Requirements", ""])
    selected_option = _text(record["selected_option"])
    lines.extend(
        [
            f"### Requirement: {slot_id} uses {selected_option}",
            "",
            (
                "The implementation MUST apply the selected option "
                f"`{selected_option}` for decision slot `{slot_id}`. "
                f"Recorded design consequence: {_text(record['design_consequence'])}"
            ),
            "",
            f"#### Scenario: {_text(validation['kind'])} validates {slot_id}",
            f"- **GIVEN** the recorded repository/greenfield boundary for `{slot_id}`",
            f"- **WHEN** the implementation runs its recorded validation",
            f"- **THEN** {_text(validation['oracle'])}",
            "",
            "## Source Traceability",
            "",
            f"- Technical Research Package: {_package_label(technical_package)}",
            f"- Decision Ledger: `{_text(record['decision_id'])}@{record['revision']}`",
            f"- Decision slot: `{slot_id}`",
            f"- Evidence anchors: {_anchors(record['anchors'])}",
            f"- Repository touchpoints: {_touchpoints(record['repository_touchpoints'])}",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_design(
    change_name: str,
    technical_package: ArtifactRevision,
    document: Mapping[str, Any],
    draft: bool,
    blockers: Sequence[str],
) -> str:
    scope = _mapping(document["round_and_scope"], "round_and_scope")
    lines = [f"# Design: {change_name}", ""]
    _append_draft_warning(lines, draft, blockers)
    lines.extend(["## Context", "", _text(scope["working_interpretation"]), ""])
    lines.extend(["## Goals / Non-Goals", "", "**Goals:**", ""])
    lines.append(f"- {_text(scope['technical_outcome'])}")
    lines.extend(["", "**Non-Goals:**", ""])
    non_goals = _value_sequence(scope["non_goals"], "non_goals")
    if non_goals:
        lines.extend(f"- {_text(item)}" for item in non_goals)
    else:
        lines.append("- No non-goal was recorded in the source package.")
    lines.extend(["", "## Decisions and Alternatives", ""])
    records = sorted(
        _mapping_sequence(document["decision_records"], "decision_records"),
        key=lambda item: _text(item["decision_slot_id"]),
    )
    if not records:
        lines.append("- No Decision Ledger record was supplied.")
    for record in records:
        slot_id = _text(record["decision_slot_id"])
        lines.extend(
            [
                f"### {slot_id}",
                "",
                f"- Status: {_text(record['status'])}",
                f"- Selected option: {_text(record['selected_option']) if record['selected_option'] is not None else 'none'}",
                f"- Design consequence: {_text(record['design_consequence'])}",
                f"- Alternatives: {_alternatives(record['alternatives'])}",
                f"- Evidence anchors: {_anchors(record['anchors'])}",
                f"- Repository touchpoints: {_touchpoints(record['repository_touchpoints'])}",
                f"- Validation: {_validation_label(record['validation'])}",
                f"- Fallback: {_text(record['fallback'])}",
                f"- Reversal condition: {_text(record['reversal_condition'])}",
                "",
            ]
        )
    lines.extend(["## Risks / Trade-offs", ""])
    risks = _mapping_sequence(document["risks_and_validation"], "risks_and_validation")
    if not risks:
        lines.append("- No additional structured risk was recorded.")
    for risk in risks:
        lines.extend(
            [
                f"- {_text(risk['statement'])}",
                f"  - Validation: {_text(risk['validation'])}",
                f"  - Response: {_text(risk['response'])}",
            ]
        )
    lines.extend(["", "## Migration and Operational Handoff", ""])
    migration_records = [record for record in records if _text(record["kind"]) == "migration"]
    if not migration_records:
        lines.append("- No migration decision was recorded in the source package.")
    for record in migration_records:
        lines.append(
            f"- `{_text(record['decision_slot_id'])}`: {_text(record['design_consequence'])}"
        )
    handoff = _mapping(document["operational_handoff"], "operational_handoff")
    observability = _mapping(handoff["observability"], "operational handoff observability")
    rollout = _mapping(handoff["rollout"], "operational handoff rollout")
    lines.extend(
        [
            f"- Observability: {_text(observability['status'])}; {_text(observability['next_action'])}",
            f"- Rollout: {_text(rollout['status'])}; {_text(rollout['next_action'])}",
        ]
    )
    lines.extend(["", "## Repository Delta", ""])
    _append_repository_delta(lines, document)
    lines.extend(["", "## Source Traceability", ""])
    _append_source_traceability(lines, technical_package, document)
    return "\n".join(lines) + "\n"


def _render_tasks(
    change_name: str,
    technical_package: ArtifactRevision,
    document: Mapping[str, Any],
    draft: bool,
    blockers: Sequence[str],
) -> str:
    lines = [f"# Tasks: {change_name}", ""]
    _append_draft_warning(lines, draft, blockers)
    lines.extend(["## Implementation", ""])
    plan = sorted(
        _mapping_sequence(document["implementation_plan"], "implementation_plan"),
        key=lambda item: int(item["order"]),
    )
    if not plan:
        lines.append("- No ordered implementation task is present in the source package.")
    for item in plan:
        lines.extend(
            [
                f"- [ ] {item['order']}. {_text(item['description'])}",
                f"  - Decision: `{_text(item['decision_id'])}` / `{_text(item['decision_slot_id'])}` / `{_text(item['change_task_id'])}`",
                f"  - Depends on: {_joined_identifiers(item['depends_on'])}",
                f"  - Repository touchpoints: {_touchpoints(item['repository_touchpoints'])}",
                f"  - Validation: {_validation_label(item['validation'])}",
                f"  - Rollback: {_text(item['rollback'])}",
            ]
        )
    lines.extend(["", "## Source Traceability", ""])
    _append_source_traceability(lines, technical_package, document)
    return "\n".join(lines) + "\n"


def _render_manifest(
    change_name: str,
    technical_package: ArtifactRevision,
    document: Mapping[str, Any],
    draft: bool,
    emitted_files: Sequence[str],
) -> str:
    payload = {
        "schema_version": 1,
        "source": "research-tree",
        "change_name": change_name,
        "draft": draft,
        "technical_package_ref": ArtifactRef(
            technical_package.round_id, technical_package.id, technical_package.revision
        ).to_dict(),
        "traceability": document["traceability"],
        "repository_baseline": document["technical_baseline"],
        "blueprint_closure": document["blueprint_closure"],
        "readiness_record": document["readiness_record"],
        "emitted_files": list(emitted_files) + ["research-tree-export.json"],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _append_draft_warning(lines: list[str], draft: bool, blockers: Sequence[str]) -> None:
    if not draft:
        return
    lines.extend(
        [
            "> **DRAFT - not implementation-ready. Resolve the recorded blockers before applying.**",
            "",
            "## Draft Blockers",
            "",
        ]
    )
    if blockers:
        lines.extend(f"- {_text(blocker)}" for blocker in blockers)
    else:
        lines.append("- Draft mode was explicitly selected; no additional blocker was derived.")
    lines.append("")


def _append_repository_delta(lines: list[str], document: Mapping[str, Any]) -> None:
    baseline = _mapping(document["technical_baseline"], "technical_baseline")
    state = _text(baseline["state"])
    if state == "greenfield":
        lines.append("- No repository baseline was selected; this is a greenfield delta.")
        return
    repositories = _mapping_sequence(baseline["repositories"], "technical_baseline.repositories")
    for repository in repositories:
        revision = _mapping(repository["revision"], "repository revision")
        lines.append(
            f"- Repository input `{_text(repository['input_id'])}`: "
            f"branch={_nullable(revision.get('branch'))}; "
            f"commit={_nullable(revision.get('commit'))}; "
            f"fingerprint={_nullable(revision.get('sha256'))}"
        )
        lines.append(f"  - Observed anchors: {_touchpoints(repository['anchors'])}")
        facts = _value_sequence(repository["facts"], "repository facts")
        if facts:
            lines.append("  - Observed facts:")
            for fact in facts:
                if isinstance(fact, Mapping) and isinstance(fact.get("anchor"), Mapping):
                    anchor = _mapping(fact["anchor"], "repository fact anchor")
                    if "path" in anchor and "symbol" in anchor:
                        lines.append(
                            f"    - `{_text(fact.get('category'))}` {_touchpoint(anchor)}: "
                            f"{_text(fact.get('observation'))}"
                        )
                        continue
                lines.append(f"    - {_json_text(fact)}")
    impacted = _all_touchpoints(document)
    lines.append(f"- Impacted change surface: {_touchpoints(impacted)}")


def _append_source_traceability(
    lines: list[str], technical_package: ArtifactRevision, document: Mapping[str, Any]
) -> None:
    traceability = _mapping(document["traceability"], "traceability")
    lines.append(f"- Technical Research Package: {_package_label(technical_package)}")
    for field, label in (
        ("working_brief", "Working Brief"),
        ("intent_model", "Intent Model"),
        ("blueprint_target", "Blueprint Target"),
    ):
        lines.append(f"- {label}: {_ref_label(traceability[field])}")
    for field, label in (
        ("input_refs", "Inputs"),
        ("decision_refs", "Decision Ledger"),
        ("finding_refs", "Finding Packs"),
    ):
        refs = _mapping_sequence(traceability[field], f"traceability {field}")
        lines.append(f"- {label}: {_refs_label(refs)}")


def _all_touchpoints(document: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    points: list[Mapping[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()
    for record in _mapping_sequence(document["decision_records"], "decision_records"):
        for point in _mapping_sequence(record["repository_touchpoints"], "decision touchpoints"):
            key = (_text(point["path"]), None if point["symbol"] is None else _text(point["symbol"]))
            if key not in seen:
                seen.add(key)
                points.append(point)
    for item in _mapping_sequence(document["implementation_plan"], "implementation_plan"):
        for point in _mapping_sequence(item["repository_touchpoints"], "plan touchpoints"):
            key = (_text(point["path"]), None if point["symbol"] is None else _text(point["symbol"]))
            if key not in seen:
                seen.add(key)
                points.append(point)
    return points


def _write_change(change_directory: Path, files: Mapping[str, str]) -> None:
    if change_directory.exists():
        raise InvalidOpenSpecExportError(
            f"OpenSpec change directory already exists: {change_directory}"
        )
    changes_directory = change_directory.parent
    temporary: Path | None = None
    try:
        changes_directory.mkdir(parents=True, exist_ok=True)
        if change_directory.exists():
            raise InvalidOpenSpecExportError(
                f"OpenSpec change directory already exists: {change_directory}"
            )
        temporary = Path(
            tempfile.mkdtemp(prefix=f".{change_directory.name}-", dir=changes_directory)
        )
        for relative, content in files.items():
            destination = temporary / Path(relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8", newline="\n")
        os.replace(temporary, change_directory)
        temporary = None
    except InvalidOpenSpecExportError:
        raise
    except OSError as error:
        raise InvalidOpenSpecExportError(f"cannot emit OpenSpec change: {error}") from error
    finally:
        if temporary is not None and temporary.exists():
            shutil.rmtree(temporary)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidOpenSpecExportError(f"{label} must be a mapping")
    return value


def _mapping_sequence(value: Any, label: str) -> list[Mapping[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise InvalidOpenSpecExportError(f"{label} must be a sequence of mappings")
    result: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise InvalidOpenSpecExportError(f"{label}[{index}] must be a mapping")
        result.append(item)
    return result


def _value_sequence(value: Any, label: str) -> list[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise InvalidOpenSpecExportError(f"{label} must be a sequence")
    return list(value)


def _artifact_ref(value: Mapping[str, Any], label: str) -> ArtifactRef:
    try:
        return ArtifactRef.from_dict(dict(value))
    except (RuntimeStoreError, TypeError, ValueError) as error:
        raise InvalidOpenSpecExportError(f"{label} is invalid: {error}") from error


def _text(value: Any) -> str:
    if value is None:
        return "none"
    return str(value).strip().replace("\r", " ").replace("\n", " ")


def _nullable(value: Any) -> str:
    return "unknown" if value is None else _text(value)


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _touchpoint(point: Mapping[str, Any]) -> str:
    path = _text(point["path"])
    return path if point.get("symbol") is None else f"{path}:{_text(point['symbol'])}"


def _touchpoints(value: Any) -> str:
    return ", ".join(_touchpoint(point) for point in _mapping_sequence(value, "touchpoints")) or "none"


def _anchors(value: Any) -> str:
    anchors = _mapping_sequence(value, "anchors")
    rendered = [f"{_text(anchor['kind'])}:{_text(anchor['ref'])}" for anchor in anchors]
    return ", ".join(rendered) or "none"


def _alternatives(value: Any) -> str:
    alternatives = _mapping_sequence(value, "alternatives")
    rendered = [
        f"{_text(item['option'])} ({_text(item['disposition'])}): {_text(item['reason'])}"
        for item in alternatives
    ]
    return "; ".join(rendered) or "none"


def _validation_label(value: Any) -> str:
    validation = _mapping(value, "validation")
    return f"{_text(validation['kind'])}: {_text(validation['oracle'])}"


def _joined_identifiers(value: Any) -> str:
    values = _value_sequence(value, "depends_on")
    return ", ".join(_text(item) for item in values) or "none"


def _package_label(package: ArtifactRevision) -> str:
    return f"{package.round_id}/{package.id}@{package.revision}"


def _ref_label(value: Any) -> str:
    reference = _mapping(value, "artifact reference")
    return f"{_text(reference['round_id'])}/{_text(reference['artifact_id'])}@{reference['revision']}"


def _refs_label(values: Sequence[Mapping[str, Any]]) -> str:
    return ", ".join(_ref_label(value) for value in values) or "none"
