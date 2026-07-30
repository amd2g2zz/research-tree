"""Project-space hand-offs for the frozen-snapshot research workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import unicodedata
from pathlib import Path

import corpus
import engine
import providers
from research_repository import atomic_write_json, atomic_write_text, default_repository


_CORPUS_FILES = ("chunks.jsonl", "inverted_index.json", "manifest.json")
MAX_CHAPTER_BYTES = 512 * 1024
MAX_REPORT_BYTES = 2 * 1024 * 1024
_CHUNK_ID = re.compile(r"(?<![A-Za-z0-9_])c_[A-Za-z0-9_-]+(?![A-Za-z0-9_])")
_DELIVERY_CHECK = re.compile(r"<!--\s*research-tree:check\s+([A-Za-z0-9._-]{1,128})\s*-->")
_VISIBLE_MACHINE_CITATION = re.compile(r"\[citation:\s*c_[A-Za-z0-9_-]+\]", re.IGNORECASE)
_DECISION_SYNTHESIS_BINDING = re.compile(r"<!--\s*research-tree:decision-synthesis\s+([0-9a-f]{64})\s*-->")
_DECISION_QUESTION_BINDING = re.compile(r"<!--\s*research-tree:decision-question\s+([A-Za-z0-9._-]{1,128})\s*-->")
_PARAMETER_BINDING = re.compile(r"<!--\s*research-tree:parameter\s+([A-Za-z0-9._-]{1,128})\s*-->")
_LOW_SOURCE_QUALITY = 0.5
_LOW_CLUSTER_CONFIDENCE = 0.5
_MATERIAL_SUFFIX = re.compile(r"\.[A-Za-z0-9]{1,16}\Z")

_EXPERIMENT_REPORT_SECTIONS = {
    "decision summary": ("decision summary", "executive summary", "决策摘要", "执行摘要"),
    "evidence judgment": ("evidence judgment", "evidence base", "evidence ledger", "证据判断", "证据基础", "证据台账"),
    "experiment design": ("experiment design", "experiment protocol", "实验设计", "实验方案", "实验协议"),
    "metrics and adjudication": ("metrics and adjudication", "metrics and failure taxonomy", "指标与判定", "指标与失败分类"),
    "analysis and adoption": ("analysis and adoption", "analysis and decision", "分析与采纳", "分析与决策"),
    "execution plan": ("execution plan", "operating plan", "runbook", "执行计划", "运行计划", "排期与预算"),
    "risks and stopping": ("risks and stopping", "risks and non-adoption", "风险与停止", "风险与不采纳"),
    "limitations": ("limitations", "局限"),
    "sources and traceability": ("sources and traceability", "evidence ledger", "来源与证据", "证据台账", "证据追溯"),
}

_DECISION_REPORT_SECTIONS = {
    "decision assessment": ("decision assessment", "decision summary", "executive decision"),
    "what changes the decision": ("what would change", "conditions that change", "decision conditions"),
    "parameter provenance": ("parameter provenance", "parameter basis", "assumptions and parameters"),
}


def workspace() -> Path:
    return Path(os.environ.get("RESEARCH_WORKSPACE", os.getcwd()))


def _snapshot_path(snapshot: str) -> Path:
    snapshot = engine.safe_snapshot_id(snapshot)
    path = workspace() / "research_snapshots" / snapshot
    if not (path / "research_state.json").is_file():
        raise FileNotFoundError(f"unknown frozen snapshot: {snapshot}")
    return path


def _snapshot_evidence_path(snapshot_root: Path, relative: str) -> Path:
    pages_root = (snapshot_root / "pages").resolve()
    candidate = (snapshot_root / relative).resolve()
    try:
        candidate.relative_to(pages_root)
    except ValueError as exc:
        raise ValueError("frozen evidence path escapes the snapshot page store") from exc
    return candidate


def _snapshot_aggregation_path(snapshot_root: Path, relative: str) -> Path:
    aggregation_root = (snapshot_root / "aggregation").resolve()
    candidate = (snapshot_root / relative).resolve()
    try:
        candidate.relative_to(aggregation_root)
    except ValueError as exc:
        raise ValueError("frozen aggregation path escapes the snapshot aggregation store") from exc
    return candidate


def _snapshot_material_path(snapshot_root: Path, relative: str) -> Path:
    materials_root = (snapshot_root / "pages" / "materials").resolve()
    candidate = (snapshot_root / relative).resolve()
    try:
        candidate.relative_to(materials_root)
    except ValueError as exc:
        raise ValueError("frozen material path escapes the snapshot material store") from exc
    return candidate


def _mutable_aggregation_path(relative: str) -> Path:
    aggregation_root = (workspace() / "research_drift" / "aggregation").resolve()
    candidate = (workspace() / relative).resolve()
    try:
        candidate.relative_to(aggregation_root)
    except ValueError as exc:
        raise ValueError("source aggregation path must be inside research_drift/aggregation") from exc
    return candidate


def _mutable_material_path(relative: str) -> Path:
    root = workspace().resolve()
    candidate = (workspace() / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("registered material path must stay inside the research workspace") from exc
    if not candidate.is_file():
        raise FileNotFoundError("registered material is missing from the research workspace")
    return candidate


def _canonical_json_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _score(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValueError(f"{label} must be a score between 0 and 1")
    return float(value)


def _short_text(value: object, label: str, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{label} must be a non-empty string of at most {maximum} characters")
    return value.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot_integrity_issues(snapshot_root: Path, manifest: dict) -> list[dict]:
    issues = []
    state = snapshot_root / "research_state.json"
    if manifest.get("state_sha256") != _sha256(state):
        issues.append({"issue": "state_hash_changed"})
    corpus_hashes = manifest.get("corpus_sha256")
    if not isinstance(corpus_hashes, dict):
        return issues + [{"issue": "missing_corpus_hashes"}]
    for filename in _CORPUS_FILES:
        expected = corpus_hashes.get(filename)
        path = snapshot_root / "corpus" / filename
        if not isinstance(expected, str):
            issues.append({"issue": "missing_corpus_hash", "file": filename})
        elif not path.is_file():
            issues.append({"issue": "missing_corpus_file", "file": filename})
        elif _sha256(path) != expected:
            issues.append({"issue": "corpus_hash_changed", "file": filename})
    aggregation_paths = manifest.get("frozen_aggregation_paths")
    aggregation_hashes = manifest.get("aggregation_sha256")
    if aggregation_paths is not None or aggregation_hashes is not None:
        if not isinstance(aggregation_paths, dict) or not isinstance(aggregation_hashes, dict):
            issues.append({"issue": "invalid_aggregation_manifest"})
        else:
            if set(aggregation_paths) != set(aggregation_hashes):
                issues.append({"issue": "aggregation_manifest_keys_changed"})
            for frame_id, relative in aggregation_paths.items():
                expected = aggregation_hashes.get(frame_id)
                if not isinstance(frame_id, str) or not isinstance(relative, str):
                    issues.append({"issue": "invalid_aggregation_manifest_entry", "frame_id": frame_id})
                    continue
                try:
                    path = _snapshot_aggregation_path(snapshot_root, relative)
                except ValueError:
                    issues.append({"issue": "invalid_frozen_aggregation_path", "frame_id": frame_id})
                    continue
                if not isinstance(expected, str):
                    issues.append({"issue": "missing_aggregation_hash", "frame_id": frame_id})
                elif not path.is_file():
                    issues.append({"issue": "missing_frozen_aggregation", "frame_id": frame_id})
                elif _sha256(path) != expected:
                    issues.append({"issue": "aggregation_hash_changed", "frame_id": frame_id})
    frozen_materials = manifest.get("frozen_materials")
    if frozen_materials is not None:
        if not isinstance(frozen_materials, dict):
            issues.append({"issue": "invalid_material_manifest"})
        else:
            for material_id, record in frozen_materials.items():
                if not isinstance(material_id, str) or not isinstance(record, dict):
                    issues.append({"issue": "invalid_material_manifest_entry", "material_id": material_id})
                    continue
                relative = record.get("path")
                expected = record.get("sha256")
                byte_count = record.get("byte_count")
                if not isinstance(relative, str) or not isinstance(expected, str) or not isinstance(byte_count, int):
                    issues.append({"issue": "invalid_material_manifest_entry", "material_id": material_id})
                    continue
                try:
                    path = _snapshot_material_path(snapshot_root, relative)
                except ValueError:
                    issues.append({"issue": "invalid_frozen_material_path", "material_id": material_id})
                    continue
                if not path.is_file():
                    issues.append({"issue": "missing_frozen_material", "material_id": material_id})
                elif path.stat().st_size != byte_count:
                    issues.append({"issue": "material_byte_count_changed", "material_id": material_id})
                elif _sha256(path) != expected:
                    issues.append({"issue": "material_hash_changed", "material_id": material_id})
    return issues


def _verified_snapshot(snapshot: str) -> tuple[str, Path, dict, dict]:
    """Load only a cryptographically verified frozen snapshot.

    Delivery files live outside the snapshot, so every submission starts from
    this check instead of trusting mutable chapter task files.
    """
    snapshot = engine.safe_snapshot_id(snapshot)
    verified = verify_snapshot(snapshot)
    if not verified["ok"]:
        raise ValueError(f"frozen snapshot integrity check failed: {verified['issues']}")
    root = Path(verified["path"]).resolve()
    data = json.loads((root / "research_state.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if data.get("snapshot_id") != snapshot or manifest.get("snapshot_id") != snapshot:
        raise ValueError("frozen snapshot identifiers do not match the requested snapshot")
    return snapshot, root, data, manifest


def _workspace_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(workspace().resolve())).replace("\\", "/")
    except ValueError as exc:
        raise ValueError("delivery path must remain inside the research workspace") from exc


def _fixed_delivery_path(*parts: str) -> Path:
    root = workspace().resolve()
    path = root.joinpath(*parts).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("delivery path escapes the research workspace") from exc
    return path


def _read_frozen_chunks(snapshot_root: Path) -> dict[str, dict]:
    chunks_path = snapshot_root / "corpus" / "chunks.jsonl"
    chunks: dict[str, dict] = {}
    for line_number, line in enumerate(chunks_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid frozen corpus chunk at line {line_number}") from exc
        chunk_id = item.get("id")
        source_path = item.get("source_path")
        if not isinstance(chunk_id, str) or not isinstance(source_path, str):
            raise ValueError(f"invalid frozen corpus chunk at line {line_number}")
        if chunk_id in chunks:
            raise ValueError(f"duplicate frozen corpus chunk id: {chunk_id}")
        chunks[chunk_id] = item
    return chunks


def _frozen_material_records(snapshot_root: Path, data: dict, manifest: dict, chunks: dict[str, dict]) -> dict[str, dict]:
    """Return frozen material metadata plus its citable corpus chunks."""
    frozen = manifest.get("frozen_materials")
    if frozen is None:
        return {}
    if not isinstance(frozen, dict):
        raise ValueError("frozen snapshot has an invalid material manifest")
    registered = data.get("materials", {})
    if not isinstance(registered, dict):
        raise ValueError("frozen snapshot has invalid registered materials")
    records = {}
    for material_id in sorted(frozen):
        entry = frozen[material_id]
        if not isinstance(material_id, str) or not isinstance(entry, dict):
            raise ValueError("frozen snapshot has an invalid material entry")
        relative = entry.get("path")
        content_hash = entry.get("sha256")
        byte_count = entry.get("byte_count")
        if (
            not isinstance(relative, str)
            or not isinstance(content_hash, str)
            or not re.fullmatch(r"[0-9a-f]{64}", content_hash)
            or isinstance(byte_count, bool)
            or not isinstance(byte_count, int)
            or byte_count < 0
        ):
            raise ValueError(f"frozen material metadata is invalid: {material_id}")
        registered_entry = registered.get(material_id)
        if isinstance(registered_entry, dict) and registered_entry.get("sha256") != content_hash:
            raise ValueError(f"frozen material does not match the frozen state: {material_id}")
        path = _snapshot_material_path(snapshot_root, relative)
        source_path = _workspace_relative(path)
        records[material_id] = {
            "material_id": material_id,
            "path": _workspace_relative(path),
            "sha256": content_hash,
            "byte_count": byte_count,
            "media_type": entry.get("media_type", "unknown"),
            "description": entry.get("description", material_id),
            "citation_chunk_ids": sorted(
                chunk_id for chunk_id, chunk in chunks.items() if chunk.get("source_path") == source_path
            ),
        }
    return records


def _contract_text_list(contract: dict, key: str) -> list[str]:
    value = contract.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"frozen intent contract has invalid {key}")
    return list(value)


def _frozen_delivery_contract(data: dict) -> tuple[dict, dict] | None:
    """Get a ready intent contract without making legacy snapshots unusable."""
    record = data.get("intent_contract")
    if record is None:
        return None
    if not isinstance(record, dict):
        raise ValueError("frozen intent contract is invalid")
    if record.get("status") != "ready":
        # A pre-contract snapshot, or an old interrupted run, still keeps its
        # original frame-based delivery behavior.
        return None
    contract = record.get("contract")
    if not isinstance(contract, dict):
        raise ValueError("ready frozen intent contract is missing its contract")
    deliverables = contract.get("deliverables")
    if not isinstance(deliverables, list) or not all(isinstance(item, dict) for item in deliverables):
        raise ValueError("ready frozen intent contract has invalid deliverables")
    return record, contract


def _frozen_decision_synthesis(data: dict) -> dict | None:
    """Return the hash-bound decision contract required by a new run's report."""

    contract_pair = _frozen_delivery_contract(data)
    if contract_pair is None:
        return None
    _, contract = contract_pair
    questions = contract.get("decision_questions", [])
    if not isinstance(questions, list):
        raise ValueError("frozen intent contract has invalid decision_questions")
    if not questions:
        return None
    state = engine.ResearchState(data)
    audit = state.decision_synthesis_audit()
    if not audit["ok"]:
        raise ValueError(f"frozen decision synthesis is invalid: {audit['issues']}")
    record = data.get("decision_synthesis")
    if not isinstance(record, dict) or not isinstance(record.get("synthesis"), dict):
        raise ValueError("frozen decision synthesis is missing")
    return {
        "sha256": record["sha256"],
        "basis_sha256": record.get("basis_sha256"),
        "questions": questions,
        "synthesis": record["synthesis"],
    }


def _delivery_requirements(contract_record: dict | None, contract: dict | None) -> dict:
    if contract_record is None or contract is None:
        return {
            "status": "legacy",
            "intent_summary": None,
            "design_requirements": [],
            "writing_requirements": [],
            "acceptance_criteria": [],
            "assumptions": [],
            "other_constraints": [],
        }
    summary = _short_text(contract.get("summary"), "frozen intent contract summary", 4096)
    return {
        "status": "ready",
        "intent_contract_version": contract_record.get("version"),
        "intent_summary": summary,
        "design_requirements": _contract_text_list(contract, "design_requirements"),
        "writing_requirements": _contract_text_list(contract, "writing_requirements"),
        "acceptance_criteria": _contract_text_list(contract, "acceptance_criteria"),
        "assumptions": _contract_text_list(contract, "assumptions"),
        "other_constraints": _contract_text_list(contract, "other_constraints"),
    }


def _contract_material_inputs(contract: dict | None, frozen_materials: dict[str, dict]) -> list[dict]:
    if contract is None:
        return []
    usages = contract.get("user_materials", [])
    if not isinstance(usages, list) or not all(isinstance(item, dict) for item in usages):
        raise ValueError("frozen intent contract has invalid user_materials")
    inputs = []
    for usage in usages:
        material_id = usage.get("material_id")
        status = usage.get("status")
        if not isinstance(material_id, str) or status not in {"provided", "missing", "optional"}:
            raise ValueError("frozen intent contract has invalid material use")
        frozen = frozen_materials.get(material_id)
        entry = {
            "material_id": material_id,
            "status": status,
            "required": bool(usage.get("required", status == "missing")),
            "description": usage.get("description", material_id),
            "intended_use": usage.get("intended_use", "inform the requested deliverables"),
        }
        if frozen is not None:
            entry.update(frozen)
            entry["availability"] = (
                "citable_text_material" if frozen["citation_chunk_ids"] else "frozen_material_without_text_chunks"
            )
        elif status == "provided":
            entry["availability"] = "registered_but_not_frozen"
        elif status == "missing":
            entry["availability"] = "missing"
        else:
            entry["availability"] = "not_provided"
        inputs.append(entry)
    return inputs


def _deliverable_chapter_id(deliverable_id: str) -> str:
    digest = hashlib.sha256(deliverable_id.encode("utf-8")).hexdigest()[:16]
    return f"chapter-d_{digest}"


def _research_input(chapter: dict) -> dict:
    return {
        "chapter_id": chapter["chapter_id"],
        "frame_id": chapter["frame_id"],
        "focus": chapter["focus"],
        "claim_ids": list(chapter["claim_ids"]),
        "source_span_ids": list(chapter["source_span_ids"]),
        "citation_chunk_ids": list(chapter["citation_chunk_ids"]),
        "return": chapter["return"],
        "contract_ref": chapter.get("contract_ref"),
        "deliverable_ids": list(chapter.get("deliverable_ids", [])),
        "evidence_assessment_sha256": chapter["evidence_assessment_sha256"],
    }


def _deduplicated_disclosures(items: list[dict]) -> list[dict]:
    selected = {}
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            selected.setdefault(item["id"], item)
    return [selected[key] for key in sorted(selected)]


def _deliverable_evidence_assessment(
    deliverable: dict, research_chapters: list[dict], material_inputs: list[dict]
) -> dict:
    research_assessments = []
    disclosures = []
    for chapter in research_chapters:
        assessment = chapter.get("evidence_assessment", {})
        if not isinstance(assessment, dict):
            continue
        research_assessments.append({
            "chapter_id": chapter["chapter_id"],
            "evidence_assessment_sha256": chapter["evidence_assessment_sha256"],
            "assessment": assessment,
        })
        requirements = assessment.get("required_disclosures", [])
        if isinstance(requirements, list):
            disclosures.extend(item for item in requirements if isinstance(item, dict))
    material_assessments = []
    for material in material_inputs:
        packet = {
            "material_id": material["material_id"],
            "availability": material["availability"],
            "citation_chunk_ids": list(material.get("citation_chunk_ids", [])),
        }
        material_assessments.append(packet)
        if material["availability"] == "citable_text_material":
            disclosures.append({
                "id": _assessment_disclosure_id("user_material_unscored", "material", material["material_id"]),
                "kind": "user_material_unscored",
                "material_id": material["material_id"],
                "citation_chunk_ids": list(material["citation_chunk_ids"]),
                "requirement": "Treat this user-provided material as a frozen input, not independently quality-scored evidence; distinguish what it states from externally corroborated findings.",
            })
        elif material["availability"] in {"missing", "registered_but_not_frozen"} and material["required"]:
            disclosures.append({
                "id": _assessment_disclosure_id("required_material_unavailable", "material", material["material_id"]),
                "kind": "required_material_unavailable",
                "material_id": material["material_id"],
                "citation_chunk_ids": [],
                "requirement": "This required material is unavailable in the frozen snapshot. State the limitation and do not invent material-derived observations.",
            })
    return {
        "status": "composite",
        "deliverable_id": deliverable["id"],
        "research_assessments": research_assessments,
        "material_assessments": material_assessments,
        "required_disclosures": _deduplicated_disclosures(disclosures),
        "writing_guidance": [
            "Use frozen research chunks and frozen user material only within this chapter's citation permissions.",
            "Carry forward every cited research assessment's claim-strength and limitation guidance into the design or material analysis.",
            "Separate material-derived inputs, externally corroborated findings, assumptions, and proposed experimental or design choices.",
        ],
    }


def _deliverable_checklist(
    deliverable: dict, research_inputs: list[dict], material_inputs: list[dict], delivery_requirements: dict
) -> tuple[list[dict], list[dict]]:
    """Build machine-checkable delivery obligations from the frozen contract.

    A marker proves that the writer deliberately addressed an obligation; source
    chunk checks prove that required material and research inputs were not
    silently omitted. The editor still evaluates the prose, but cannot compile
    a chapter that never declared coverage of its contracted requirements.
    """

    checks = []
    input_uses = []

    def add(check_id: str, kind: str, requirement: str) -> None:
        checks.append({"id": check_id, "kind": kind, "requirement": requirement})

    if deliverable.get("requires_design"):
        design_requirements = delivery_requirements.get("design_requirements", [])
        acceptance_criteria = delivery_requirements.get("acceptance_criteria", [])
        if not design_requirements:
            add("design-scope", "design_scope", "State the objective, proposed design, feasibility boundary, and validation approach.")
        for index, requirement in enumerate(design_requirements, start=1):
            add(f"design-{index}", "design_requirement", requirement)
        if not acceptance_criteria:
            add("acceptance-scope", "acceptance_scope", "State how the proposed design will be judged complete and feasible.")
        for index, criterion in enumerate(acceptance_criteria, start=1):
            add(f"acceptance-{index}", "acceptance_criterion", criterion)

    if deliverable.get("requires_material_analysis"):
        for material in material_inputs:
            if not material.get("required"):
                continue
            material_id = material["material_id"]
            check_id = f"material-{material_id}"
            add(check_id, "required_material", f"Address the supplied material '{material_id}' and distinguish its observations from proposed choices.")
            input_uses.append({
                "check_id": check_id,
                "kind": "material",
                "input_id": material_id,
                "citation_chunk_ids": list(material.get("citation_chunk_ids", [])),
                "availability": material.get("availability"),
            })

    if deliverable.get("requires_research"):
        for research in research_inputs:
            chapter_id = research["chapter_id"]
            check_id = f"research-{chapter_id}"
            add(check_id, "required_research", f"Use or explicitly bound the frozen research input '{chapter_id}'.")
            input_uses.append({
                "check_id": check_id,
                "kind": "research",
                "input_id": chapter_id,
                "citation_chunk_ids": list(research.get("citation_chunk_ids", [])),
                "availability": "citable" if research.get("citation_chunk_ids") else "no_citable_chunks",
            })

    if not checks:
        add("deliverable-scope", "deliverable_scope", "Address the named deliverable and its stated scope.")
    return checks, input_uses


def _selected_research_chapters(deliverable: dict, frame_chapters: list[dict]) -> list[dict]:
    """Select only the frozen frames explicitly bound to this deliverable."""

    refs = deliverable.get("research_frame_refs")
    deliverable_id = deliverable.get("id")
    if refs is None:
        # Snapshots from the initial intent-contract release did not carry a
        # binding. Retain their all-frame delivery behavior for readability.
        return list(frame_chapters)
    if not isinstance(refs, list) or not all(isinstance(item, str) for item in refs):
        raise ValueError("frozen intent deliverable has invalid research_frame_refs")
    return [
        chapter for chapter in frame_chapters
        if chapter.get("contract_ref") in refs or deliverable_id in chapter.get("deliverable_ids", [])
    ]


def _normalized_aggregation_clusters(frame_id: str, clusters: object) -> list[dict]:
    """Validate the durable parts of an aggregation artifact for delivery.

    Delivery never re-scores sources. It only carries forward the aggregator's
    auditable decisions, after checking that one frozen artifact has a coherent
    topic/source assignment.
    """
    if not isinstance(clusters, list):
        raise ValueError("frozen source aggregation must contain a clusters list")
    normalized = []
    cluster_ids = set()
    for raw_cluster in clusters:
        if not isinstance(raw_cluster, dict):
            raise ValueError("frozen source aggregation cluster must be an object")
        cluster_id = _short_text(raw_cluster.get("cluster_id"), "frozen aggregation cluster_id", 256)
        if cluster_id in cluster_ids:
            raise ValueError(f"frozen source aggregation repeats cluster: {cluster_id}")
        cluster_ids.add(cluster_id)
        topic = _short_text(raw_cluster.get("topic"), "frozen aggregation topic")
        dedup_rationale = _short_text(raw_cluster.get("dedup_rationale"), "frozen aggregation dedup_rationale")
        confidence_score = _score(raw_cluster.get("confidence_score"), "frozen aggregation confidence_score")
        confidence_rationale = _short_text(
            raw_cluster.get("confidence_rationale"), "frozen aggregation confidence_rationale"
        )
        raw_confidence_components = raw_cluster.get("confidence_components", {})
        if not isinstance(raw_confidence_components, dict):
            raise ValueError("frozen aggregation confidence_components must be an object")
        confidence_components = {
            _short_text(key, "frozen aggregation confidence component", 128): _score(
                value, "frozen aggregation confidence component score"
            )
            for key, value in raw_confidence_components.items()
        }
        raw_sources = raw_cluster.get("sources")
        if not isinstance(raw_sources, list) or not raw_sources:
            raise ValueError("frozen aggregation cluster requires scored sources")
        sources = []
        cluster_paths = set()
        for raw_source in raw_sources:
            if not isinstance(raw_source, dict):
                raise ValueError("frozen aggregation source must be an object")
            local_path = _short_text(raw_source.get("local_path"), "frozen aggregation source local_path", 4096)
            if local_path in cluster_paths:
                raise ValueError("frozen aggregation repeats a source in one topic")
            cluster_paths.add(local_path)
            raw_quality_components = raw_source.get("quality_components", {})
            if not isinstance(raw_quality_components, dict):
                raise ValueError("frozen aggregation quality_components must be an object")
            quality_components = {
                _short_text(key, "frozen aggregation quality component", 128): _score(
                    value, "frozen aggregation quality component score"
                )
                for key, value in raw_quality_components.items()
            }
            relation = raw_source.get("relation", "representative")
            if not isinstance(relation, str) or not relation.strip() or len(relation) > 128:
                raise ValueError("frozen aggregation source relation must be a short non-empty string")
            primary = raw_source.get("primary", True)
            if not isinstance(primary, bool):
                raise ValueError("frozen aggregation source primary must be a boolean")
            sources.append({
                "local_path": local_path,
                "content_sha256": raw_source.get("content_sha256"),
                "relation": relation,
                "primary": primary,
                "quality_components": quality_components,
                "quality_score": _score(raw_source.get("quality_score"), "frozen aggregation quality_score"),
                "quality_rationale": _short_text(
                    raw_source.get("quality_rationale", raw_source.get("rationale")),
                    "frozen aggregation quality_rationale"
                ),
                "assessment_confidence": _score(
                    raw_source.get("assessment_confidence", 1.0), "frozen aggregation assessment_confidence"
                ),
            })
        representatives = raw_cluster.get("representative_local_paths")
        if not isinstance(representatives, list) or not representatives:
            raise ValueError("frozen aggregation cluster requires representatives")
        if len(set(representatives)) != len(representatives) or any(
            not isinstance(path, str) or path not in cluster_paths for path in representatives
        ):
            raise ValueError("frozen aggregation representatives must be unique cluster sources")
        unresolved = raw_cluster.get("unresolved", [])
        if not isinstance(unresolved, list):
            raise ValueError("frozen aggregation unresolved must be a list")
        normalized.append({
            "cluster_id": cluster_id,
            "topic": topic,
            "dedup_rationale": dedup_rationale,
            "confidence_score": confidence_score,
            "confidence_rationale": confidence_rationale,
            "confidence_components": confidence_components,
            "representative_local_paths": list(representatives),
            "unresolved": [_short_text(item, "frozen aggregation unresolved") for item in unresolved],
            "sources": sorted(sources, key=lambda item: item["local_path"]),
        })
    return sorted(normalized, key=lambda item: item["cluster_id"])


def _read_frozen_aggregation(snapshot_root: Path, manifest: dict, frame_id: str, frame: dict) -> dict | None:
    aggregation = frame.get("aggregation")
    if not isinstance(aggregation, dict) or aggregation.get("status") != "complete":
        return None
    paths = manifest.get("frozen_aggregation_paths")
    hashes = manifest.get("aggregation_sha256")
    if paths is None and hashes is None:
        # A new domain version may retain the complete aggregation inline in
        # snapshot state. That state is protected by state_sha256. Old
        # snapshots simply have no scoring information and remain usable.
        state_clusters = aggregation.get("clusters")
        if isinstance(state_clusters, list):
            return {
                "path": "research_state.json",
                "sha256": manifest.get("state_sha256"),
                "storage": "frozen_state",
                "source_manifest_sha256": aggregation.get("source_manifest_sha256"),
                "clusters": _normalized_aggregation_clusters(frame_id, state_clusters),
            }
        return None
    if not isinstance(paths, dict) or not isinstance(hashes, dict):
        raise ValueError("frozen snapshot has an invalid aggregation manifest")
    relative = paths.get(frame_id)
    expected_hash = hashes.get(frame_id)
    if not isinstance(relative, str) or not isinstance(expected_hash, str):
        raise ValueError(f"frozen snapshot has no aggregation artifact for frame: {frame_id}")
    path = _snapshot_aggregation_path(snapshot_root, relative)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"frozen aggregation artifact is unreadable for frame: {frame_id}") from exc
    if not isinstance(payload, dict) or payload.get("frame_id") != frame_id:
        raise ValueError(f"frozen aggregation artifact does not match frame: {frame_id}")
    return {
        "path": _workspace_relative(path),
        "sha256": expected_hash,
        "storage": "frozen_artifact",
        "source_manifest_sha256": payload.get("source_manifest_sha256"),
        "clusters": _normalized_aggregation_clusters(frame_id, payload.get("clusters")),
    }


def _assessment_disclosure_id(kind: str, cluster_id: str, local_path: str | None = None) -> str:
    seed = f"{kind}\0{cluster_id}\0{local_path or ''}"
    return f"{kind}_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}"


def _chapter_evidence_assessment(
    snapshot_root: Path,
    data: dict,
    manifest: dict,
    frame: dict,
    chapter_evidence_ids: set[str],
    chunks: dict[str, dict],
) -> dict:
    """Bind source-quality and topic-confidence metrics to one chapter.

    All sources in an aggregation remain visible. A source that is not citable
    in this chapter is marked as such instead of being silently removed from
    the writer and editor contracts.
    """
    aggregation = _read_frozen_aggregation(snapshot_root, manifest, frame["id"], frame)
    frame_evidence_ids = [
        evidence_id for evidence_id in frame.get("evidence_ids", [])
        if isinstance(evidence_id, str) and isinstance(data.get("evidence", {}).get(evidence_id), dict)
    ]
    if aggregation is None:
        return {
            "status": "unavailable",
            "reason": "This frozen snapshot has no auditable source aggregation for the frame.",
            "unscored_evidence_ids": sorted(chapter_evidence_ids),
            "required_disclosures": [],
            "writing_guidance": [
                "Do not imply that source quality or topic confidence was scored for this chapter.",
                "Use only the listed frozen citations and state uncertainty where the evidence is incomplete or conflicting.",
            ],
        }

    frozen_paths = manifest.get("frozen_evidence_paths", {})
    evidence_by_path: dict[str, list[str]] = {}
    chunk_ids_by_evidence: dict[str, list[str]] = {}
    for evidence_id in frame_evidence_ids:
        evidence = data["evidence"][evidence_id]
        local_path = evidence.get("local_path")
        if not isinstance(local_path, str):
            continue
        evidence_by_path.setdefault(local_path, []).append(evidence_id)
        relative = frozen_paths.get(evidence_id) if isinstance(frozen_paths, dict) else None
        if not isinstance(relative, str):
            continue
        page_path = _snapshot_evidence_path(snapshot_root, relative)
        source_path = _workspace_relative(page_path)
        chunk_ids_by_evidence[evidence_id] = sorted(
            chunk_id for chunk_id, chunk in chunks.items() if chunk.get("source_path") == source_path
        )

    clusters = []
    disclosures = []
    chapter_source_paths = set()
    frozen_not_authorized_paths = set()
    assessed_source_paths = set()
    for cluster in aggregation["clusters"]:
        sources = []
        cluster_relevant = False
        for source in cluster["sources"]:
            local_path = source["local_path"]
            assessed_source_paths.add(local_path)
            evidence_ids = sorted(evidence_by_path.get(local_path, []))
            chapter_ids = sorted(set(evidence_ids) & chapter_evidence_ids)
            citation_chunk_ids = sorted({
                chunk_id for evidence_id in chapter_ids for chunk_id in chunk_ids_by_evidence.get(evidence_id, [])
            })
            if chapter_ids:
                availability = "citable_in_this_chapter"
                cluster_relevant = True
                chapter_source_paths.add(local_path)
            elif evidence_ids:
                availability = "frozen_but_not_authorized_for_this_chapter"
                frozen_not_authorized_paths.add(local_path)
            else:
                availability = "not_frozen_for_delivery"
            representative = local_path in cluster["representative_local_paths"]
            source_packet = {
                "local_path": local_path,
                "content_sha256": source["content_sha256"],
                "relation": source["relation"],
                "primary": source["primary"],
                "quality_components": source["quality_components"],
                "quality_score": source["quality_score"],
                "quality_rationale": source["quality_rationale"],
                "assessment_confidence": source["assessment_confidence"],
                "representative": representative,
                "frozen_evidence_ids": evidence_ids,
                "chapter_evidence_ids": chapter_ids,
                "citation_chunk_ids": citation_chunk_ids,
                "availability": availability,
            }
            sources.append(source_packet)
            if chapter_ids and source["primary"] and source["quality_score"] < _LOW_SOURCE_QUALITY:
                disclosures.append({
                    "id": _assessment_disclosure_id("low_source_quality", cluster["cluster_id"], local_path),
                    "kind": "low_source_quality",
                    "cluster_id": cluster["cluster_id"],
                    "local_path": local_path,
                    "quality_score": source["quality_score"],
                    "citation_chunk_ids": citation_chunk_ids,
                    "requirement": "If this source supports a claim, use qualified language and disclose its source-quality limitation.",
                })
        cluster_packet = {
            "cluster_id": cluster["cluster_id"],
            "topic": cluster["topic"],
            "dedup_rationale": cluster["dedup_rationale"],
            "confidence_score": cluster["confidence_score"],
            "confidence_rationale": cluster["confidence_rationale"],
            "confidence_components": cluster["confidence_components"],
            "unresolved": cluster["unresolved"],
            "chapter_relevant": cluster_relevant,
            "sources": sources,
        }
        clusters.append(cluster_packet)
        if cluster_relevant and cluster["confidence_score"] < _LOW_CLUSTER_CONFIDENCE:
            cited_chunks = sorted({
                chunk_id for source in sources for chunk_id in source["citation_chunk_ids"]
            })
            disclosures.append({
                "id": _assessment_disclosure_id("low_cluster_confidence", cluster["cluster_id"]),
                "kind": "low_cluster_confidence",
                "cluster_id": cluster["cluster_id"],
                "confidence_score": cluster["confidence_score"],
                "citation_chunk_ids": cited_chunks,
                "requirement": "Treat this topic as tentative, disclose the cluster-level uncertainty, and do not use it as the sole basis for a decisive conclusion.",
            })
    unassessed_evidence_ids = []
    for evidence_id in sorted(chapter_evidence_ids):
        evidence = data.get("evidence", {}).get(evidence_id, {})
        local_path = evidence.get("local_path") if isinstance(evidence, dict) else None
        if not isinstance(local_path, str) or local_path in assessed_source_paths:
            continue
        unassessed_evidence_ids.append(evidence_id)
        disclosures.append({
            "id": _assessment_disclosure_id("unassessed_chapter_evidence", "unassigned", local_path),
            "kind": "unassessed_chapter_evidence",
            "local_path": local_path,
            "evidence_id": evidence_id,
            "citation_chunk_ids": chunk_ids_by_evidence.get(evidence_id, []),
            "requirement": "This cited source has no matching frozen topic/quality assessment. Do not present it as scored support; state the assessment gap and use qualified language.",
        })
    return {
        "status": "available",
        "aggregation_artifact": {
            "path": aggregation["path"],
            "sha256": aggregation["sha256"],
            "storage": aggregation["storage"],
            "source_manifest_sha256": aggregation["source_manifest_sha256"],
        },
        "thresholds": {
            "low_source_quality": _LOW_SOURCE_QUALITY,
            "low_cluster_confidence": _LOW_CLUSTER_CONFIDENCE,
        },
        "coverage": {
            "cluster_count": len(clusters),
            "cluster_source_count": sum(len(cluster["sources"]) for cluster in clusters),
            "chapter_citable_source_count": len(chapter_source_paths),
            "frozen_but_not_authorized_source_count": len(frozen_not_authorized_paths),
            "unassessed_chapter_evidence_count": len(unassessed_evidence_ids),
        },
        "clusters": clusters,
        "unassessed_chapter_evidence_ids": unassessed_evidence_ids,
        "required_disclosures": sorted(disclosures, key=lambda item: item["id"]),
        "writing_guidance": [
            "Scores are evidence-management signals, not proof. Every factual claim still requires an allowed frozen citation.",
            "Match claim strength to the relevant source-quality and cluster-confidence scores; do not upgrade tentative evidence into a decisive conclusion.",
            "When a listed low-score source or low-confidence cluster materially supports the chapter, include the corresponding limitation instead of silently omitting it.",
            "A source marked not citable in this chapter remains visible for audit but cannot be cited as chapter evidence.",
        ],
    }


def _chapter_assessment_hash(chapter: dict) -> str:
    return _canonical_json_hash(chapter.get("evidence_assessment", {}))


def _chapter_contract_hash(chapter: dict) -> str:
    """Bind every writer-visible planning constraint, not just citations."""
    payload = {key: value for key, value in chapter.items() if key != "chapter_contract_sha256"}
    return _canonical_json_hash(payload)


def _chapter_disclosure_requirements(chapter: dict, cited: set[str]) -> list[dict]:
    assessment = chapter.get("evidence_assessment")
    if not isinstance(assessment, dict):
        return []
    requirements = assessment.get("required_disclosures", [])
    if not isinstance(requirements, list):
        return []
    selected = []
    for requirement in requirements:
        if not isinstance(requirement, dict):
            continue
        chunks = requirement.get("citation_chunk_ids", [])
        if isinstance(chunks, list) and cited.intersection(chunk for chunk in chunks if isinstance(chunk, str)):
            selected.append(requirement)
    return sorted(selected, key=lambda item: str(item.get("id", "")))


def _planned_chapters(snapshot_root: Path, data: dict, manifest: dict) -> list[dict]:
    chunks = _read_frozen_chunks(snapshot_root)
    frozen_paths = manifest.get("frozen_evidence_paths")
    if not isinstance(frozen_paths, dict):
        raise ValueError("frozen snapshot is missing evidence path mappings")
    contract_pair = _frozen_delivery_contract(data)
    contract_record, contract = contract_pair if contract_pair is not None else (None, None)
    delivery_requirements = _delivery_requirements(contract_record, contract)
    frozen_materials = _frozen_material_records(snapshot_root, data, manifest, chunks)
    material_inputs = _contract_material_inputs(contract, frozen_materials)
    deliverables = contract.get("deliverables", []) if contract is not None else []
    dependency_target_ids = {
        dependency_id
        for deliverable in deliverables
        if isinstance(deliverable, dict)
        for dependency_id in deliverable.get("depends_on_deliverable_ids", [])
        if isinstance(dependency_id, str)
    }
    chapters = []
    for frame_id in sorted(data.get("frames", {})):
        frame = data["frames"][frame_id]
        if frame.get("state") not in {"resolved", "contradicted", "insufficient_evidence"}:
            continue
        claims = []
        spans = []
        evidence_ids = set()
        for cognition_id in frame.get("cognition_ids", []):
            cognition = data.get("cognitions", {}).get(cognition_id)
            if not isinstance(cognition, dict):
                raise ValueError(f"frozen snapshot has missing cognition: {cognition_id}")
            claims.append(cognition)
            for span in cognition.get("source_spans", []):
                if not isinstance(span, dict) or not isinstance(span.get("evidence_id"), str):
                    raise ValueError(f"frozen snapshot has invalid source span in cognition: {cognition_id}")
                spans.append(dict(span))
                evidence_ids.add(span["evidence_id"])
        allowed_sources = set()
        for evidence_id in evidence_ids:
            relative = frozen_paths.get(evidence_id)
            if not isinstance(relative, str):
                raise ValueError(f"frozen snapshot has no page mapping for evidence: {evidence_id}")
            page_path = _snapshot_evidence_path(snapshot_root, relative)
            allowed_sources.add(_workspace_relative(page_path))
        allowed_chunk_ids = sorted(
            chunk_id for chunk_id, chunk in chunks.items()
            if chunk["source_path"] in allowed_sources
        )
        chapter_id = f"chapter-{frame_id}"
        chapter = {
            "chapter_id": chapter_id,
            "chapter_kind": "research_frame",
            "frame_id": frame_id,
            "contract_ref": frame.get("contract_ref"),
            "deliverable_ids": list(frame.get("deliverable_ids", [])),
            "focus": frame["focus"],
            "information_gap": frame["information_gap"],
            "evidence_requirement": frame["evidence_requirement"],
            "claim_ids": [item["id"] for item in claims],
            "source_span_ids": spans,
            "citation_chunk_ids": allowed_chunk_ids,
            "return": frame["return"],
            "delivery_requirements": delivery_requirements,
            "writer_guidance": [
                "Write the bounded research chapter from its cited frozen evidence only.",
                "Honor delivery_requirements.writing_requirements and acceptance_criteria when shaping this chapter for downstream deliverables.",
            ],
            "evidence_assessment": _chapter_evidence_assessment(
                snapshot_root, data, manifest, frame, evidence_ids, chunks
            ),
        }
        chapter["evidence_assessment_sha256"] = _chapter_assessment_hash(chapter)
        chapter["chapter_contract_sha256"] = _chapter_contract_hash(chapter)
        chapters.append(chapter)

    frame_chapters = list(chapters)
    for deliverable in deliverables:
        if not isinstance(deliverable, dict):
            raise ValueError("frozen intent contract has an invalid deliverable")
        requires_material_analysis = bool(deliverable.get("requires_material_analysis"))
        requires_design = bool(deliverable.get("requires_design"))
        if not (requires_material_analysis or requires_design or deliverable.get("id") in dependency_target_ids):
            continue
        deliverable_id = deliverable.get("id")
        description = deliverable.get("description")
        kind = deliverable.get("kind")
        if not isinstance(deliverable_id, str) or not isinstance(description, str) or not isinstance(kind, str):
            raise ValueError("frozen intent contract has invalid deliverable metadata")
        selected_materials = list(material_inputs) if requires_material_analysis else []
        selected_research = (
            _selected_research_chapters(deliverable, frame_chapters)
            if bool(deliverable.get("requires_research")) else []
        )
        research_inputs = [_research_input(chapter) for chapter in selected_research]
        material_chunk_ids = {
            chunk_id for material in selected_materials
            for chunk_id in material.get("citation_chunk_ids", [])
            if isinstance(chunk_id, str)
        }
        research_chunk_ids = {
            chunk_id for chapter in selected_research for chunk_id in chapter["citation_chunk_ids"]
        }
        chapter_id = _deliverable_chapter_id(deliverable_id)
        if any(item["chapter_id"] == chapter_id for item in chapters):
            raise ValueError(f"frozen intent deliverable maps to a duplicate chapter: {deliverable_id}")
        chapter = {
            "chapter_id": chapter_id,
            "chapter_kind": "intent_deliverable",
            "deliverable": {
                "id": deliverable_id,
                "kind": kind,
                "description": description,
                "required": bool(deliverable.get("required", True)),
                "requires_research": bool(deliverable.get("requires_research")),
                "requires_material_analysis": requires_material_analysis,
                "requires_design": requires_design,
                "depends_on_deliverable_ids": list(deliverable.get("depends_on_deliverable_ids", [])),
            },
            "focus": description,
            "information_gap": f"Fulfil the intent deliverable: {deliverable_id}",
            "evidence_requirement": "Use only the listed frozen research and material corpus chunks; identify absent required inputs as limitations.",
            "claim_ids": [claim_id for item in research_inputs for claim_id in item["claim_ids"]],
            "source_span_ids": [span for item in research_inputs for span in item["source_span_ids"]],
            "citation_chunk_ids": sorted(material_chunk_ids | research_chunk_ids),
            "return": None,
            "research_evidence_inputs": research_inputs,
            "material_inputs": selected_materials,
            "dependency_chapter_ids": sorted({
                *[item["chapter_id"] for item in research_inputs],
                *[
                    _deliverable_chapter_id(dependency_id)
                    for dependency_id in deliverable.get("depends_on_deliverable_ids", [])
                    if isinstance(dependency_id, str)
                ],
            }),
            "delivery_requirements": delivery_requirements,
            "writer_guidance": [
                "Produce the requested material analysis or design deliverable, not a generic research summary.",
                "Use research_evidence_inputs as frozen evidence inputs and material_inputs as the bounded user-provided context.",
                "Address every design_requirement and acceptance_criterion explicitly; distinguish evidence, material observations, assumptions, and proposed design choices.",
                "When an input is missing, non-textual, or not independently scored, state that limitation rather than inventing support.",
                "Do not begin this chapter until every dependency_chapter_id is a ready frozen chapter; use those dependencies as bounded inputs, not uncited background.",
                "For every delivery_checklist id, include <!-- research-tree:check <id> --> next to the prose that addresses it. A required citable input must also be cited; an unavailable required input still needs its check marker and an explicit limitation.",
            ],
            "evidence_assessment": _deliverable_evidence_assessment(
                deliverable, selected_research, selected_materials
            ),
        }
        checklist, input_uses = _deliverable_checklist(
            chapter["deliverable"], research_inputs, selected_materials, delivery_requirements
        )
        chapter["delivery_checklist"] = checklist
        chapter["input_use_requirements"] = input_uses
        chapter["evidence_assessment_sha256"] = _chapter_assessment_hash(chapter)
        chapter["chapter_contract_sha256"] = _chapter_contract_hash(chapter)
        chapters.append(chapter)
    return chapters


def _chapter_by_id(chapters: list[dict], chapter_id: str) -> dict:
    if not isinstance(chapter_id, str):
        raise ValueError("chapter id must be a string")
    chapter = next((item for item in chapters if item["chapter_id"] == chapter_id), None)
    if chapter is None:
        raise ValueError("chapter id is not planned by this frozen snapshot")
    return chapter


def _delivery_content(content: str, maximum_bytes: int, label: str) -> str:
    if not isinstance(content, str) or not content.strip():
        raise ValueError(f"{label} content must be a non-empty string")
    if any(unicodedata.category(character) == "Cc" and character not in "\t\n\r" for character in content):
        raise ValueError(f"{label} content contains a disallowed control character")
    try:
        encoded = content.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{label} content is not valid UTF-8 text") from exc
    if len(encoded) > maximum_bytes:
        raise ValueError(f"{label} content exceeds {maximum_bytes} bytes")
    return content


def _citation_chunk_ids(content: str) -> set[str]:
    return set(_CHUNK_ID.findall(content))


def _has_report_metadata(content: str, labels: tuple[str, ...]) -> bool:
    normalized_lines = [line.replace("**", "").casefold() for line in content.splitlines()]
    return any(label.casefold() in line for line in normalized_lines for label in labels)


def _report_presentation_requirements(chapters: list[dict]) -> dict:
    """Return the user-facing report profile implied by frozen deliverables."""

    requires_experiment_profile = any(
        chapter.get("chapter_kind") == "intent_deliverable"
        and isinstance(chapter.get("deliverable"), dict)
        and (
            chapter["deliverable"].get("kind") == "experiment_plan"
            or bool(chapter.get("delivery_requirements", {}).get("design_requirements"))
        )
        for chapter in chapters
    )
    if not requires_experiment_profile:
        return {"profile": "standard", "required_sections": [], "required_metadata": []}
    return {
        "profile": "experiment_plan",
        "required_metadata": ["snapshot", "as_of", "evidence_window"],
        "required_sections": list(_EXPERIMENT_REPORT_SECTIONS),
        "citation_style": {
            "visible": "Use readable evidence labels such as [E1] in prose and the evidence ledger.",
            "machine": "Keep required frozen chunk ids in HTML comments or a technical trace appendix, never as [citation: c_...] in reader-facing prose.",
        },
    }


def _validate_report_presentation(chapters: list[dict], content: str) -> dict:
    """Reject a generic summary when a frozen deliverable requires a protocol."""

    requirements = _report_presentation_requirements(chapters)
    if requirements["profile"] != "experiment_plan":
        return requirements
    if _VISIBLE_MACHINE_CITATION.search(content):
        raise ValueError("experiment-plan report must use readable evidence labels instead of [citation: c_...] prose")
    metadata = {
        "snapshot": ("snapshot:", "snapshot：", "快照:", "快照：", "快照 id:", "快照 ID："),
        "as_of": ("as of:", "as of：", "截至:", "截至：", "参考时间:", "参考时间："),
        "evidence_window": ("evidence window:", "evidence window：", "证据时间窗:", "证据时间窗：", "证据窗口:", "证据窗口："),
    }
    missing_metadata = [key for key, labels in metadata.items() if not _has_report_metadata(content, labels)]
    if missing_metadata:
        raise ValueError(f"experiment-plan report omits required metadata: {', '.join(missing_metadata)}")
    headings = [match.group(1).strip().casefold() for match in re.finditer(r"(?m)^#{2,6}\s+(.+?)\s*$", content)]
    missing_sections = [
        name for name, labels in _EXPERIMENT_REPORT_SECTIONS.items()
        if not any(label.casefold() in heading for heading in headings for label in labels)
    ]
    if missing_sections:
        raise ValueError(f"experiment-plan report omits required sections: {', '.join(missing_sections)}")
    if not re.search(r"(?<![A-Za-z0-9])\[E[1-9][0-9]*\]", content):
        raise ValueError("experiment-plan report must include readable evidence labels such as [E1]")
    return requirements


def _report_presentation_requirements(chapters: list[dict], data: dict | None = None) -> dict:
    """Return the reader-facing report contract implied by frozen state."""

    requires_experiment_profile = any(
        chapter.get("chapter_kind") == "intent_deliverable"
        and isinstance(chapter.get("deliverable"), dict)
        and (
            chapter["deliverable"].get("kind") == "experiment_plan"
            or bool(chapter.get("delivery_requirements", {}).get("design_requirements"))
        )
        for chapter in chapters
    )
    requirements = {
        "profile": "experiment_plan" if requires_experiment_profile else "standard",
        "experiment_profile": requires_experiment_profile,
        "required_metadata": ["snapshot", "as_of", "evidence_window"] if requires_experiment_profile else [],
        "required_sections": list(_EXPERIMENT_REPORT_SECTIONS) if requires_experiment_profile else [],
    }
    if requires_experiment_profile:
        requirements["citation_style"] = {
            "visible": "Use readable evidence labels such as [E1] in prose and the evidence ledger.",
            "machine": "Keep required frozen chunk ids in HTML comments or a technical trace appendix, never as [citation: c_...] in reader-facing prose.",
        }
    decision = _frozen_decision_synthesis(data) if data is not None else None
    if decision is not None:
        requirements.update({
            "profile": "decision_experiment_plan" if requires_experiment_profile else "decision_report",
            "decision_synthesis": {
                "sha256": decision["sha256"],
                "basis_sha256": decision["basis_sha256"],
                "question_ids": [item["id"] for item in decision["questions"]],
                "parameter_ids": [item["id"] for item in decision["synthesis"].get("parameter_provenance", [])],
                "required_sections": list(_DECISION_REPORT_SECTIONS),
            },
        })
    return requirements


def _validate_report_presentation(chapters: list[dict], content: str, data: dict | None = None) -> dict:
    """Reject a generic summary when frozen deliverables require a decision answer."""

    requirements = _report_presentation_requirements(chapters, data)
    if requirements["experiment_profile"]:
        if _VISIBLE_MACHINE_CITATION.search(content):
            raise ValueError("experiment-plan report must use readable evidence labels instead of [citation: c_...] prose")
        metadata = {
            "snapshot": ("snapshot:",),
            "as_of": ("as of:",),
            "evidence_window": ("evidence window:",),
        }
        missing_metadata = [key for key, labels in metadata.items() if not _has_report_metadata(content, labels)]
        if missing_metadata:
            raise ValueError(f"experiment-plan report omits required metadata: {', '.join(missing_metadata)}")
        headings = [match.group(1).strip().casefold() for match in re.finditer(r"(?m)^#{2,6}\s+(.+?)\s*$", content)]
        missing_sections = [
            name for name, labels in _EXPERIMENT_REPORT_SECTIONS.items()
            if not any(label.casefold() in heading for heading in headings for label in labels)
        ]
        if missing_sections:
            raise ValueError(f"experiment-plan report omits required sections: {', '.join(missing_sections)}")
        if not re.search(r"(?<![A-Za-z0-9])\[E[1-9][0-9]*\]", content):
            raise ValueError("experiment-plan report must include readable evidence labels such as [E1]")
    decision = requirements.get("decision_synthesis")
    if decision is None:
        return requirements
    bindings = set(_DECISION_SYNTHESIS_BINDING.findall(content))
    if bindings != {decision["sha256"]}:
        raise ValueError("decision report must bind the frozen decision synthesis hash")
    headings = [match.group(1).strip().casefold() for match in re.finditer(r"(?m)^#{2,6}\s+(.+?)\s*$", content)]
    missing_sections = [
        name for name, labels in _DECISION_REPORT_SECTIONS.items()
        if not any(label.casefold() in heading for heading in headings for label in labels)
    ]
    if missing_sections:
        raise ValueError(f"decision report omits required sections: {', '.join(missing_sections)}")
    question_ids = set(_DECISION_QUESTION_BINDING.findall(content))
    expected_questions = set(decision["question_ids"])
    if question_ids != expected_questions:
        raise ValueError("decision report must bind every frozen decision question exactly once")
    parameter_ids = set(_PARAMETER_BINDING.findall(content))
    expected_parameters = set(decision["parameter_ids"])
    if parameter_ids != expected_parameters:
        raise ValueError("decision report must bind every frozen parameter provenance entry exactly once")
    return requirements


def _validate_delivery_obligations(chapter: dict, content: str, cited: set[str]) -> dict:
    """Verify the explicit coverage and required-input use of a deliverable."""

    checks = chapter.get("delivery_checklist", [])
    uses = chapter.get("input_use_requirements", [])
    if not checks and not uses:
        return {"required": False, "verified_check_ids": [], "input_use": []}
    if not isinstance(checks, list) or not isinstance(uses, list):
        raise ValueError("chapter delivery requirements are invalid")
    check_ids = []
    for item in checks:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("chapter delivery checklist is invalid")
        check_ids.append(item["id"])
    if len(set(check_ids)) != len(check_ids):
        raise ValueError("chapter delivery checklist repeats an id")
    declared = set(_DELIVERY_CHECK.findall(content))
    missing_checks = sorted(set(check_ids) - declared)
    if missing_checks:
        raise ValueError(f"chapter omits required delivery checks: {', '.join(missing_checks)}")

    input_use = []
    for item in uses:
        if not isinstance(item, dict):
            raise ValueError("chapter input-use requirements are invalid")
        check_id = item.get("check_id")
        chunks = item.get("citation_chunk_ids", [])
        if not isinstance(check_id, str) or not isinstance(chunks, list) or not all(isinstance(value, str) for value in chunks):
            raise ValueError("chapter input-use requirement is invalid")
        cited_input_chunks = sorted(cited.intersection(chunks))
        if chunks and not cited_input_chunks:
            raise ValueError(f"chapter does not cite required {item.get('kind', 'input')}: {item.get('input_id')}")
        input_use.append({
            "check_id": check_id,
            "kind": item.get("kind"),
            "input_id": item.get("input_id"),
            "availability": item.get("availability"),
            "cited_chunk_ids": cited_input_chunks,
        })
    return {
        "required": True,
        "verified_check_ids": sorted(set(check_ids)),
        "input_use": input_use,
    }


def _validate_chapter_content(chapter: dict, content: str) -> set[str]:
    content = _delivery_content(content, MAX_CHAPTER_BYTES, "chapter")
    cited = _citation_chunk_ids(content)
    allowed = set(chapter["citation_chunk_ids"])
    unsupported = cited - allowed
    if unsupported:
        raise ValueError(f"chapter cites chunks outside its frozen evidence: {', '.join(sorted(unsupported))}")
    if allowed and not cited:
        raise ValueError("chapter content must cite at least one allowed frozen chunk id")
    _validate_delivery_obligations(chapter, content, cited)
    return cited


def init(intent: str) -> dict:
    for relative in ("research_drift/pages", "research_corpus", "research_snapshots",
                     "research/chapters", "research/editor", "deliverables"):
        (workspace() / relative).mkdir(parents=True, exist_ok=True)
    project = {
        "schema": 2, "intent": intent,
        "delivery": {"default_format": "markdown", "default_path": "report.md",
                     "pdf": {"enabled": False, "trigger": "explicit_user_request",
                             "path": "deliverables/report.pdf"}},
        "layout": {"state": "research_drift/research_state.json", "pages": "research_drift/pages",
                   "snapshots": "research_snapshots", "corpus": "research_corpus"},
    }
    atomic_write_json(_fixed_delivery_path("research_project.json"), project)
    providers.init()
    return project


def audit_evidence(snapshot: str | None = None) -> dict:
    if snapshot:
        snapshot_root = _snapshot_path(snapshot)
        data = json.loads((snapshot_root / "research_state.json").read_text(encoding="utf-8"))
        manifest = json.loads((snapshot_root / "manifest.json").read_text(encoding="utf-8"))
        frozen_paths = manifest.get("frozen_evidence_paths", {})
    else:
        data = engine.ResearchState.load().data
        snapshot_root = None
        frozen_paths = {}
    issues = _snapshot_integrity_issues(snapshot_root, manifest) if snapshot else []
    for evidence_id, evidence in data.get("evidence", {}).items():
        if snapshot:
            relative = frozen_paths.get(evidence_id)
            if not relative:
                issues.append({"evidence_id": evidence_id, "issue": "missing_frozen_page"})
                continue
            try:
                path = _snapshot_evidence_path(snapshot_root, relative)
            except ValueError:
                issues.append({"evidence_id": evidence_id, "issue": "invalid_frozen_page_path"})
                continue
        else:
            try:
                path = engine.saved_page_path(evidence["local_path"])
            except ValueError:
                issues.append({"evidence_id": evidence_id, "issue": "invalid_page_path"})
                continue
        if not path.is_file():
            issues.append({"evidence_id": evidence_id, "issue": "missing_page"})
        elif hashlib.sha256(path.read_bytes()).hexdigest() != evidence["content_hash"]:
            issues.append({"evidence_id": evidence_id, "issue": "content_hash_changed"})
    return {"snapshot": snapshot, "ok": not issues, "issues": issues,
            "evidence_count": len(data.get("evidence", {}))}


def verify_snapshot(snapshot: str) -> dict:
    root = _snapshot_path(snapshot)
    audit = audit_evidence(snapshot)
    return {"snapshot_id": snapshot, "path": root, "ok": audit["ok"], "issues": audit["issues"]}


def _copy_evidence_pages(snapshot_root: Path, evidence: dict[str, dict]) -> dict[str, str]:
    copied = {}
    for evidence_id, item in evidence.items():
        source = engine.saved_page_path(item["local_path"])
        destination = snapshot_root / "pages" / source.relative_to(engine.pages_dir().resolve())
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied[evidence_id] = str(destination.relative_to(snapshot_root)).replace("\\", "/")
    return copied


def _copy_registered_materials(snapshot_root: Path, materials: dict[str, dict]) -> dict[str, dict]:
    """Copy user-owned inputs into the frozen page store.

    Textual material keeps its original safe suffix under ``pages/materials`` so
    the existing corpus builder indexes it alongside frozen web evidence. Other
    file types remain hash-bound source artifacts but are intentionally skipped
    by the text-only corpus builder.
    """
    if not isinstance(materials, dict):
        raise ValueError("registered materials must be an object")
    copied = {}
    for material_id in sorted(materials):
        record = materials[material_id]
        if not isinstance(material_id, str) or not isinstance(record, dict):
            raise ValueError("registered material entry is invalid")
        local_path = record.get("local_path")
        expected_hash = record.get("sha256")
        expected_size = record.get("byte_count")
        if (
            not isinstance(local_path, str)
            or not isinstance(expected_hash, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)
            or isinstance(expected_size, bool)
            or not isinstance(expected_size, int)
            or expected_size < 0
        ):
            raise ValueError(f"registered material metadata is invalid: {material_id}")
        source = _mutable_material_path(local_path)
        if source.stat().st_size != expected_size or _sha256(source) != expected_hash:
            raise ValueError(f"registered material no longer matches its state hash: {material_id}")
        suffix = source.suffix.lower()
        if not _MATERIAL_SUFFIX.fullmatch(suffix):
            suffix = ".bin"
        filename = hashlib.sha256(f"{material_id}\0{expected_hash}".encode("utf-8")).hexdigest()[:24] + suffix
        destination = snapshot_root / "pages" / "materials" / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied[material_id] = {
            "path": str(destination.relative_to(snapshot_root)).replace("\\", "/"),
            "sha256": expected_hash,
            "byte_count": expected_size,
            "media_type": record.get("media_type", "unknown"),
            "description": record.get("description", material_id),
            "source_local_path": local_path,
        }
    return copied


def _copy_aggregation_artifacts(snapshot_root: Path, frames: dict[str, dict]) -> tuple[dict[str, str], dict[str, str]]:
    copied = {}
    hashes = {}
    for frame_id in sorted(frames):
        frame = frames[frame_id]
        aggregation = frame.get("aggregation") if isinstance(frame, dict) else None
        if not isinstance(aggregation, dict) or aggregation.get("status") != "complete":
            continue
        relative = aggregation.get("path")
        if not isinstance(relative, str):
            raise ValueError(f"completed source aggregation has no artifact path: {frame_id}")
        source = _mutable_aggregation_path(relative)
        expected_hash = aggregation.get("sha256")
        if isinstance(expected_hash, str) and _sha256(source) != expected_hash:
            raise ValueError(f"source aggregation artifact no longer matches its state hash: {frame_id}")
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"source aggregation artifact is unreadable for frame: {frame_id}") from exc
        if not isinstance(payload, dict) or payload.get("frame_id") != frame_id:
            raise ValueError(f"source aggregation artifact does not match frame: {frame_id}")
        _normalized_aggregation_clusters(frame_id, payload.get("clusters"))
        filename = hashlib.sha256(frame_id.encode("utf-8")).hexdigest()[:24] + ".json"
        destination = snapshot_root / "aggregation" / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied[frame_id] = str(destination.relative_to(snapshot_root)).replace("\\", "/")
        hashes[frame_id] = _sha256(destination)
    return copied, hashes


def freeze(snapshot: str | None) -> dict:
    # State, accepted pages, copied pages, and corpus hashes must describe one
    # instant. Hold the same cross-process state lock used by service commands
    # until the manifest is complete rather than allowing an evidence update to
    # race the copy phase.
    with default_repository().locked():
        state = engine.ResearchState.load()
        manifest = state.freeze(snapshot)
        state.save()
        audit = audit_evidence()
        if not audit["ok"]:
            raise ValueError("cannot publish snapshot with invalid evidence")
        snapshot_root = _snapshot_path(manifest["snapshot_id"])
        frozen_paths = _copy_evidence_pages(snapshot_root, state.data["evidence"])
        frozen_materials = _copy_registered_materials(snapshot_root, state.data.get("materials", {}))
        frozen_aggregation_paths, aggregation_hashes = _copy_aggregation_artifacts(
            snapshot_root, state.data.get("frames", {})
        )
        corpus.build(snapshot_root / "pages")
        destination = snapshot_root / "corpus"
        shutil.copytree(workspace() / "research_corpus", destination)
        manifest["corpus_path"] = str(destination.relative_to(workspace())).replace("\\", "/")
        manifest["frozen_evidence_paths"] = frozen_paths
        manifest["corpus_sha256"] = {filename: _sha256(destination / filename) for filename in _CORPUS_FILES}
        if frozen_materials:
            manifest["frozen_materials"] = frozen_materials
        if frozen_aggregation_paths:
            manifest["frozen_aggregation_paths"] = frozen_aggregation_paths
            manifest["aggregation_sha256"] = aggregation_hashes
        atomic_write_json(snapshot_root / "manifest.json", manifest)
        frozen_audit = audit_evidence(manifest["snapshot_id"])
        if not frozen_audit["ok"]:
            raise ValueError("frozen snapshot evidence integrity check failed")
        return manifest


def chapter_plan(snapshot: str) -> dict:
    snapshot, root, data, manifest = _verified_snapshot(snapshot)
    contract_pair = _frozen_delivery_contract(data)
    contract_record, contract = contract_pair if contract_pair is not None else (None, None)
    payload = {"schema": 4, "snapshot_id": snapshot, "intent": data["intent_versions"][-1]["raw"],
               "delivery_requirements": _delivery_requirements(contract_record, contract),
               "chapters": _planned_chapters(root, data, manifest),
               "instruction": "One writer owns one fixed chapter file. Cite only a listed citation_chunk_id and its source span; do not use evidence outside this frozen snapshot. Apply the chapter evidence_assessment: match claim strength to its source-quality and topic-confidence signals, and disclose every applicable required_disclosure rather than silently dropping low-score evidence. Honor each chapter's delivery_requirements, material_inputs, research_evidence_inputs, and acceptance criteria; a material-analysis or design chapter must produce that requested deliverable rather than a generic research summary."}
    output = _fixed_delivery_path("research", "chapters", "tasks.json")
    atomic_write_json(output, payload)
    return payload


def _chapter_output_path(chapter: dict) -> Path:
    chapter_id = chapter["chapter_id"]
    if not re.fullmatch(r"chapter-(?:f|d)_[A-Za-z0-9_]+", chapter_id):
        raise ValueError("frozen snapshot has an invalid planned chapter id")
    return _fixed_delivery_path("research", "chapters", f"{chapter_id}.md")


def _chapter_manifest_path(chapter: dict) -> Path:
    chapter_id = chapter["chapter_id"]
    if not re.fullmatch(r"chapter-(?:f|d)_[A-Za-z0-9_]+", chapter_id):
        raise ValueError("frozen snapshot has an invalid planned chapter id")
    return _fixed_delivery_path("research", "editor", "chapter-manifests", f"{chapter_id}.json")


def _chapter_artifact_ready(snapshot: str, chapter: dict) -> bool:
    output = _chapter_output_path(chapter)
    metadata = _chapter_manifest_path(chapter)
    if not output.is_file() or not metadata.is_file():
        return False
    try:
        record = json.loads(metadata.read_text(encoding="utf-8"))
        content = output.read_text(encoding="utf-8")
        cited = _validate_chapter_content(chapter, content)
        delivery_verification = _validate_delivery_obligations(chapter, content, cited)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False
    except ValueError:
        return False
    if not (
        record.get("schema") in {1, 2, 3, 4}
        and record.get("snapshot_id") == snapshot
        and record.get("chapter_id") == chapter["chapter_id"]
        and record.get("content_sha256") == _sha256(output)
        and record.get("citation_chunk_ids") == sorted(cited)
    ):
        return False
    if record.get("schema") in {2, 3}:
        if delivery_verification["required"]:
            return False
        matches_assessment = (
            record.get("evidence_assessment_sha256") == _chapter_assessment_hash(chapter)
            and record.get("quality_disclosure_requirements") == _chapter_disclosure_requirements(chapter, cited)
        )
        if record.get("schema") == 3:
            return (not delivery_verification["required"] and matches_assessment
                    and record.get("chapter_contract_sha256") == _chapter_contract_hash(chapter))
        return matches_assessment
    if record.get("schema") == 4:
        return (
            record.get("evidence_assessment_sha256") == _chapter_assessment_hash(chapter)
            and record.get("chapter_contract_sha256") == _chapter_contract_hash(chapter)
            and record.get("quality_disclosure_requirements") == _chapter_disclosure_requirements(chapter, cited)
            and record.get("delivery_verification") == delivery_verification
        )
    return not delivery_verification["required"]


def chapter_ready(snapshot: str, chapter_id: str) -> bool:
    """Check whether one writer artifact belongs to this exact snapshot."""
    snapshot, root, data, manifest = _verified_snapshot(snapshot)
    chapter = _chapter_by_id(_planned_chapters(root, data, manifest), chapter_id)
    return _chapter_artifact_ready(snapshot, chapter)


def report_ready(snapshot: str) -> bool:
    """Return whether the fixed report and provenance manifest bind this snapshot."""
    try:
        snapshot, root, data, manifest = _verified_snapshot(snapshot)
        chapters = _planned_chapters(root, data, manifest)
        report_path = _fixed_delivery_path("report.md")
        metadata = _fixed_delivery_path("research", "editor", "report_manifest.json")
        if not report_path.is_file() or not metadata.is_file() or not chapters:
            return False
        record = json.loads(metadata.read_text(encoding="utf-8"))
        expected_hashes = {chapter["chapter_id"]: _sha256(_chapter_output_path(chapter)) for chapter in chapters}
        if not (
            record.get("schema") in {1, 2, 3, 4, 5}
            and record.get("snapshot_id") == snapshot
            and record.get("report_sha256") == _sha256(report_path)
            and record.get("chapter_hashes") == expected_hashes
            and all(_chapter_artifact_ready(snapshot, chapter) for chapter in chapters)
        ):
            return False
        if record.get("schema") in {2, 3}:
            expected_assessments = {
                chapter["chapter_id"]: _chapter_assessment_hash(chapter) for chapter in chapters
            }
            expected_disclosures = {
                chapter["chapter_id"]: _chapter_disclosure_requirements(
                    chapter, _citation_chunk_ids(_chapter_output_path(chapter).read_text(encoding="utf-8"))
                )
                for chapter in chapters
            }
            matches_assessment = (
                record.get("chapter_evidence_assessment_sha256") == expected_assessments
                and record.get("chapter_quality_disclosure_requirements") == expected_disclosures
            )
            if record.get("schema") == 3:
                expected_contracts = {
                    chapter["chapter_id"]: _chapter_contract_hash(chapter) for chapter in chapters
                }
                return matches_assessment and record.get("chapter_contract_sha256") == expected_contracts
            return matches_assessment
        if record.get("schema") in {4, 5}:
            expected_assessments = {
                chapter["chapter_id"]: _chapter_assessment_hash(chapter) for chapter in chapters
            }
            expected_disclosures = {
                chapter["chapter_id"]: _chapter_disclosure_requirements(
                    chapter, _citation_chunk_ids(_chapter_output_path(chapter).read_text(encoding="utf-8"))
                )
                for chapter in chapters
            }
            expected_contracts = {
                chapter["chapter_id"]: _chapter_contract_hash(chapter) for chapter in chapters
            }
            expected_delivery = {
                chapter["chapter_id"]: _validate_delivery_obligations(
                    chapter,
                    _chapter_output_path(chapter).read_text(encoding="utf-8"),
                    _citation_chunk_ids(_chapter_output_path(chapter).read_text(encoding="utf-8")),
                )
                for chapter in chapters
            }
            base_ready = (
                record.get("chapter_evidence_assessment_sha256") == expected_assessments
                and record.get("chapter_quality_disclosure_requirements") == expected_disclosures
                and record.get("chapter_contract_sha256") == expected_contracts
                and record.get("chapter_delivery_verification") == expected_delivery
            )
            if record.get("schema") == 4:
                return base_ready
            decision = _frozen_decision_synthesis(data)
            if decision is None:
                return False
            _verified_report_review(snapshot, data, report_path.read_text(encoding="utf-8"))
            return (
                base_ready
                and record.get("decision_synthesis_sha256") == decision["sha256"]
                and record.get("decision_synthesis_basis_sha256") == decision["basis_sha256"]
                and record.get("report_review_sha256") == _sha256(_report_review_path())
            )
        return True
    except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return False


def submit_chapter(snapshot: str, chapter_id: str, content: str) -> dict:
    """Persist one bounded chapter owned by one frozen-snapshot task.

    The caller supplies prose, not a destination path. The chapter ID is matched
    against a plan reconstructed from the verified snapshot before any file is
    opened, which prevents both task-file tampering and path traversal.
    """
    with default_repository().locked():
        return _submit_chapter_locked(snapshot, chapter_id, content)


def _submit_chapter_locked(snapshot: str, chapter_id: str, content: str) -> dict:
    snapshot, root, data, manifest = _verified_snapshot(snapshot)
    chapters = _planned_chapters(root, data, manifest)
    chapter = _chapter_by_id(chapters, chapter_id)
    chapters_by_id = {item["chapter_id"]: item for item in chapters}
    dependencies = chapter.get("dependency_chapter_ids", [])
    if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
        raise ValueError("chapter dependency plan is invalid")
    unknown_dependencies = sorted(set(dependencies) - set(chapters_by_id))
    if unknown_dependencies:
        raise ValueError(f"chapter has unknown planned dependencies: {', '.join(unknown_dependencies)}")
    unmet_dependencies = [
        dependency_id for dependency_id in dependencies
        if not _chapter_artifact_ready(snapshot, chapters_by_id[dependency_id])
    ]
    if unmet_dependencies:
        raise ValueError(
            "chapter dependencies are not ready: " + ", ".join(sorted(unmet_dependencies))
        )
    cited = _validate_chapter_content(chapter, content)
    delivery_verification = _validate_delivery_obligations(chapter, content, cited)
    output = _chapter_output_path(chapter)
    atomic_write_text(output, content)
    metadata = _chapter_manifest_path(chapter)
    disclosure_requirements = _chapter_disclosure_requirements(chapter, cited)
    chapter_manifest = {"schema": 4, "snapshot_id": snapshot, "chapter_id": chapter["chapter_id"],
                        "content_sha256": _sha256(output), "citation_chunk_ids": sorted(cited),
                        "evidence_assessment_sha256": _chapter_assessment_hash(chapter),
                        "chapter_contract_sha256": _chapter_contract_hash(chapter),
                        "quality_disclosure_requirements": disclosure_requirements,
                        "delivery_verification": delivery_verification,
                        "path": _workspace_relative(output)}
    atomic_write_json(metadata, chapter_manifest)
    return {
        "snapshot_id": snapshot,
        "chapter_id": chapter["chapter_id"],
        "path": _workspace_relative(output),
        "byte_count": len(content.encode("utf-8")),
        "citation_chunk_ids": sorted(cited),
        "chapter_contract_sha256": _chapter_contract_hash(chapter),
        "quality_disclosure_requirement_ids": [item["id"] for item in disclosure_requirements],
        "delivery_check_ids": delivery_verification["verified_check_ids"],
    }


def _report_draft_path() -> Path:
    return _fixed_delivery_path("research", "editor", "report_draft.md")


def _report_review_path() -> Path:
    return _fixed_delivery_path("research", "editor", "report_review.json")


def _validate_report_candidate(snapshot: str, content: str) -> dict:
    """Validate a draft against the same frozen chapter boundary as publication."""

    snapshot, root, data, manifest = _verified_snapshot(snapshot)
    chapters = _planned_chapters(root, data, manifest)
    if not chapters:
        raise ValueError("cannot prepare a report without planned frozen chapters")
    allowed_chunk_ids = set()
    missing = []
    for chapter in chapters:
        if not _chapter_artifact_ready(snapshot, chapter):
            missing.append(chapter["chapter_id"])
            continue
        chapter_content = _chapter_output_path(chapter).read_text(encoding="utf-8")
        _validate_chapter_content(chapter, chapter_content)
        allowed_chunk_ids.update(chapter["citation_chunk_ids"])
    if missing:
        raise ValueError(f"cannot prepare report; missing submitted chapters: {', '.join(missing)}")
    content = _delivery_content(content, MAX_REPORT_BYTES, "report")
    cited = _citation_chunk_ids(content)
    unsupported = cited - allowed_chunk_ids
    if unsupported:
        raise ValueError(f"report cites chunks outside the frozen chapter evidence: {', '.join(sorted(unsupported))}")
    if allowed_chunk_ids and not cited:
        raise ValueError("report content must cite at least one allowed frozen chunk id")
    presentation = _validate_report_presentation(chapters, content, data)
    return {
        "snapshot": snapshot, "root": root, "data": data, "manifest": manifest,
        "chapters": chapters, "content": content, "citation_chunk_ids": sorted(cited),
        "presentation": presentation,
    }


def stage_report(snapshot: str, content: str) -> dict:
    """Persist a decision-report draft for an independent frozen-snapshot review."""

    with default_repository().locked():
        candidate = _validate_report_candidate(snapshot, content)
        output = _report_draft_path()
        atomic_write_text(output, candidate["content"])
        draft_manifest = {
            "schema": 1, "snapshot_id": candidate["snapshot"],
            "draft_sha256": _sha256(output), "citation_chunk_ids": candidate["citation_chunk_ids"],
            "presentation_validation": candidate["presentation"],
        }
        manifest_path = _fixed_delivery_path("research", "editor", "report_draft_manifest.json")
        atomic_write_json(manifest_path, draft_manifest)
        return {
            "snapshot_id": candidate["snapshot"], "path": _workspace_relative(output),
            "manifest_path": _workspace_relative(manifest_path), "byte_count": len(candidate["content"].encode("utf-8")),
        }


def _normalise_report_review(assessment: dict, decision: dict) -> dict:
    if not isinstance(assessment, dict):
        raise ValueError("report review assessment must be an object")
    if assessment.get("status") != "approved":
        raise ValueError("report review must be approved before publication")
    synthesis = decision["synthesis"]
    assessments = {
        item["decision_question_id"]: item
        for item in synthesis.get("question_assessments", []) if isinstance(item, dict)
    }
    question_reviews = assessment.get("question_reviews")
    if not isinstance(question_reviews, list) or len(question_reviews) != len(assessments):
        raise ValueError("report review must cover every decision question exactly once")
    normalized_questions = []
    seen = set()
    for item in question_reviews:
        if not isinstance(item, dict):
            raise ValueError("report review question entries must be objects")
        question_id = item.get("decision_question_id")
        source = assessments.get(question_id)
        if source is None or question_id in seen:
            raise ValueError("report review references an unknown or repeated decision question")
        cognition_ids = item.get("cognition_ids", [])
        if not isinstance(cognition_ids, list) or not all(isinstance(value, str) for value in cognition_ids):
            raise ValueError("report review cognition_ids must be a list")
        expected_cognitions = set(source.get("supporting_cognition_ids", [])) | set(source.get("refuting_cognition_ids", []))
        if set(cognition_ids) != expected_cognitions:
            raise ValueError("report review cognition ids must match the decision assessment")
        conditions = item.get("conditions_to_change", [])
        if not isinstance(conditions, list):
            raise ValueError("report review conditions_to_change must be a list")
        if len(conditions) > 32:
            raise ValueError("report review conditions_to_change exceeds the bound")
        normalized_conditions = [
            _short_text(value, "report review conditions_to_change", 2048) for value in conditions
        ]
        if set(normalized_conditions) != set(source.get("conditions_to_change", [])):
            raise ValueError("report review conditions must match the decision assessment")
        if item.get("status") != source.get("status"):
            raise ValueError("report review status must match the decision assessment")
        normalized_questions.append({
            "decision_question_id": question_id,
            "status": source["status"],
            "cognition_ids": sorted(set(cognition_ids)),
            "inference": _short_text(item.get("inference"), "report review inference", 4096),
            "action": _short_text(item.get("action"), "report review action", 4096),
            "conditions_to_change": normalized_conditions,
        })
        seen.add(question_id)
    if seen != set(assessments):
        raise ValueError("report review omits a decision question")
    provenance = {item["id"]: item for item in synthesis.get("parameter_provenance", []) if isinstance(item, dict)}
    parameter_reviews = assessment.get("parameter_reviews", [])
    if not isinstance(parameter_reviews, list) or len(parameter_reviews) != len(provenance):
        raise ValueError("report review must cover every parameter provenance entry exactly once")
    normalized_parameters = []
    seen_parameters = set()
    for item in parameter_reviews:
        if not isinstance(item, dict):
            raise ValueError("report review parameter entries must be objects")
        parameter_id = item.get("parameter_id")
        source = provenance.get(parameter_id)
        if source is None or parameter_id in seen_parameters:
            raise ValueError("report review references an unknown or repeated parameter")
        if item.get("basis") != source.get("basis") or item.get("disclosed") is not True:
            raise ValueError("report review must confirm the frozen parameter basis and disclosure")
        normalized_parameters.append({
            "parameter_id": parameter_id, "basis": source["basis"], "disclosed": True,
            "note": _short_text(item.get("note"), "report review parameter note", 2048),
        })
        seen_parameters.add(parameter_id)
    return {
        "status": "approved",
        "summary": _short_text(assessment.get("summary"), "report review summary", 4096),
        "question_reviews": sorted(normalized_questions, key=lambda item: item["decision_question_id"]),
        "parameter_reviews": sorted(normalized_parameters, key=lambda item: item["parameter_id"]),
        "critical_gap_handling": _short_text(
            assessment.get("critical_gap_handling"), "report review critical_gap_handling", 4096
        ),
    }


def submit_report_review(snapshot: str, content: str, assessment: dict) -> dict:
    """Record an independent, hash-bound senior-user review of a report draft."""

    with default_repository().locked():
        candidate = _validate_report_candidate(snapshot, content)
        decision = _frozen_decision_synthesis(candidate["data"])
        if decision is None:
            raise ValueError("report review is required only for a decision-aware frozen snapshot")
        normalized = _normalise_report_review(assessment, decision)
        content_hash = hashlib.sha256(candidate["content"].encode("utf-8")).hexdigest()
        record = {
            "schema": 1, "snapshot_id": candidate["snapshot"], "status": "approved",
            "report_sha256": content_hash, "decision_synthesis_sha256": decision["sha256"],
            "assessment": normalized,
        }
        path = _report_review_path()
        atomic_write_json(path, record)
        return {"snapshot_id": candidate["snapshot"], "path": _workspace_relative(path),
                "report_sha256": content_hash, "decision_synthesis_sha256": decision["sha256"]}


def _verified_report_review(snapshot: str, data: dict, content: str) -> dict | None:
    decision = _frozen_decision_synthesis(data)
    if decision is None:
        return None
    path = _report_review_path()
    if not path.is_file():
        raise ValueError("decision report requires an approved independent report review")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("decision report review is unreadable") from exc
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if not isinstance(record, dict) or not (
        record.get("schema") == 1 and record.get("status") == "approved"
        and record.get("snapshot_id") == snapshot and record.get("report_sha256") == content_hash
        and record.get("decision_synthesis_sha256") == decision["sha256"]
    ):
        raise ValueError("decision report review does not bind this snapshot, draft, and decision synthesis")
    normalized = _normalise_report_review(record.get("assessment"), decision)
    if normalized != record.get("assessment"):
        raise ValueError("decision report review is not normalized")
    return record


def report_review_ready(snapshot: str) -> bool:
    """Return whether the staged draft has a matching approved independent review."""

    try:
        snapshot, _, data, _ = _verified_snapshot(snapshot)
        if _frozen_decision_synthesis(data) is None:
            return True
        draft = _report_draft_path()
        if not draft.is_file():
            return False
        _verified_report_review(snapshot, data, draft.read_text(encoding="utf-8"))
        return True
    except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return False


def compile_report(snapshot: str, content: str) -> dict:
    """Publish a Markdown report only after every planned chapter is present.

    Submitted chapter files are checked again because they are mutable delivery
    artifacts outside the frozen snapshot. The report and its provenance
    manifest use fixed, workspace-confined paths and atomic replacement.
    """
    with default_repository().locked():
        return _compile_report_locked(snapshot, content)


def _compile_report_locked(snapshot: str, content: str) -> dict:
    snapshot, root, data, manifest = _verified_snapshot(snapshot)
    chapters = _planned_chapters(root, data, manifest)
    if not chapters:
        raise ValueError("cannot compile a report without planned frozen chapters")
    missing = []
    chapter_hashes = {}
    chapter_assessment_hashes = {}
    chapter_contract_hashes = {}
    chapter_disclosure_requirements = {}
    chapter_delivery_verifications = {}
    allowed_chunk_ids = set()
    for chapter in chapters:
        output = _chapter_output_path(chapter)
        metadata = _chapter_manifest_path(chapter)
        if not _chapter_artifact_ready(snapshot, chapter):
            missing.append(chapter["chapter_id"])
            continue
        chapter_manifest = json.loads(metadata.read_text(encoding="utf-8"))
        if chapter_manifest.get("citation_chunk_ids") != sorted(_citation_chunk_ids(output.read_text(encoding="utf-8"))):
            missing.append(chapter["chapter_id"])
            continue
        chapter_content = output.read_text(encoding="utf-8")
        chapter_citations = _validate_chapter_content(chapter, chapter_content)
        delivery_verification = _validate_delivery_obligations(chapter, chapter_content, chapter_citations)
        chapter_hashes[chapter["chapter_id"]] = _sha256(output)
        chapter_assessment_hashes[chapter["chapter_id"]] = _chapter_assessment_hash(chapter)
        chapter_contract_hashes[chapter["chapter_id"]] = _chapter_contract_hash(chapter)
        chapter_disclosure_requirements[chapter["chapter_id"]] = _chapter_disclosure_requirements(
            chapter, chapter_citations
        )
        chapter_delivery_verifications[chapter["chapter_id"]] = delivery_verification
        allowed_chunk_ids.update(chapter["citation_chunk_ids"])
    if missing:
        raise ValueError(f"cannot compile report; missing submitted chapters: {', '.join(missing)}")
    content = _delivery_content(content, MAX_REPORT_BYTES, "report")
    cited = _citation_chunk_ids(content)
    unsupported = cited - allowed_chunk_ids
    if unsupported:
        raise ValueError(f"report cites chunks outside the frozen chapter evidence: {', '.join(sorted(unsupported))}")
    if allowed_chunk_ids and not cited:
        raise ValueError("report content must cite at least one allowed frozen chunk id")
    presentation = _validate_report_presentation(chapters, content, data)
    report_review = _verified_report_review(snapshot, data, content)
    report_path = _fixed_delivery_path("report.md")
    atomic_write_text(report_path, content)
    report_manifest = {
        "schema": 5 if report_review is not None else 4,
        "snapshot_id": snapshot,
        "report_path": _workspace_relative(report_path),
        "report_sha256": _sha256(report_path),
        "chapter_hashes": chapter_hashes,
        "chapter_evidence_assessment_sha256": chapter_assessment_hashes,
        "chapter_contract_sha256": chapter_contract_hashes,
        "chapter_quality_disclosure_requirements": chapter_disclosure_requirements,
        "chapter_delivery_verification": chapter_delivery_verifications,
        "citation_chunk_ids": sorted(cited),
        "presentation_validation": presentation,
    }
    if report_review is not None:
        decision = _frozen_decision_synthesis(data)
        report_manifest["decision_synthesis_sha256"] = decision["sha256"]
        report_manifest["decision_synthesis_basis_sha256"] = decision["basis_sha256"]
        report_manifest["report_review_sha256"] = _sha256(_report_review_path())
    manifest_path = _fixed_delivery_path("research", "editor", "report_manifest.json")
    atomic_write_json(manifest_path, report_manifest)
    return {
        "snapshot_id": snapshot,
        "report_path": _workspace_relative(report_path),
        "manifest_path": _workspace_relative(manifest_path),
        "chapter_ids": [chapter["chapter_id"] for chapter in chapters],
        "byte_count": len(content.encode("utf-8")),
    }


def editor_packet(snapshot: str) -> dict:
    snapshot, root, data, manifest = _verified_snapshot(snapshot)
    chapters = _planned_chapters(root, data, manifest)
    packet_chapters = []
    for task in chapters:
        chapter_path = _chapter_output_path(task)
        assessment = task.get("evidence_assessment", {})
        packet_chapters.append({
            "task": task,
            "path": _workspace_relative(chapter_path),
            "present": _chapter_artifact_ready(snapshot, task),
            "evidence_assessment_sha256": _chapter_assessment_hash(task),
            "chapter_contract_sha256": _chapter_contract_hash(task),
            "quality_review": {
                "assessment_status": assessment.get("status") if isinstance(assessment, dict) else "unavailable",
                "required_disclosures": assessment.get("required_disclosures", []) if isinstance(assessment, dict) else [],
                "instruction": "Check that each factual conclusion retains a frozen citation, reflects the applicable source-quality and cluster-confidence signals, and explicitly states every limitation triggered by its cited low-score evidence. Do not remove a low-score source or topic from the audit trail merely to make the prose stronger.",
            },
            "delivery_review": {
                "chapter_kind": task.get("chapter_kind", "research_frame"),
                "deliverable": task.get("deliverable"),
                "dependency_chapter_ids": task.get("dependency_chapter_ids", []),
                "delivery_requirements": task.get("delivery_requirements", {}),
                "delivery_checklist": task.get("delivery_checklist", []),
                "input_use_requirements": task.get("input_use_requirements", []),
                "material_inputs": task.get("material_inputs", []),
                "research_evidence_inputs": task.get("research_evidence_inputs", []),
                "instruction": "For an intent_deliverable chapter, verify every dependency_chapter_id was completed first and every delivery_checklist item against the prose and its required-input citation. Check markers are a necessary provenance signal, not semantic proof. Reject a generic summary, a plan that omits a required material or research input, or a design that does not actually address the stated design requirements and acceptance criteria; return repair tasks rather than silently compiling it.",
            },
        })
    presentation = _report_presentation_requirements(chapters, data)
    decision = _frozen_decision_synthesis(data)
    packet = {"schema": 4, "snapshot_id": snapshot, "snapshot_path": _workspace_relative(root),
              "chapters": packet_chapters,
              "report_presentation": presentation,
              "decision_synthesis": decision,
              "instruction": "Compile report.md only from submitted chapters and cited frozen evidence. Audit each chapter's quality_review and delivery_review before compilation: keep claims proportionate to source quality and topic confidence, require explicit limitations for applicable low-score evidence, and return unsupported, overconfident, or unmet design/material requirements as repair tasks rather than prose. Build a reader-facing report, not a chapter summary: preserve each applicable operating detail from an experiment or design chapter, use readable evidence labels with a source/evidence ledger, and keep machine chunk ids out of reader-facing prose. When decision_synthesis is present, lead with its current recommendation, map every decision question from evidence to inference to action, preserve user-input/gap/insufficient conditions, and mark each consequential parameter with its frozen provenance id. Follow report_presentation exactly when it declares a non-standard profile."}
    output = _fixed_delivery_path("research", "editor", "editor_packet.json")
    atomic_write_json(output, packet)
    return packet


def _read_content_argument(value: str) -> str:
    if value.startswith("@@"):
        return value[1:]
    if not value.startswith("@"):
        return value
    candidate = (workspace() / value[1:]).resolve()
    try:
        candidate.relative_to(workspace().resolve())
    except ValueError as exc:
        raise ValueError("content file must be inside the research workspace") from exc
    if not candidate.is_file():
        raise FileNotFoundError(f"content file not found: {candidate}")
    return candidate.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="project", description="research project lifecycle")
    sub = parser.add_subparsers(dest="command", required=True)
    init_cmd = sub.add_parser("init"); init_cmd.add_argument("--intent", required=True)
    audit_cmd = sub.add_parser("audit-evidence"); audit_cmd.add_argument("--snapshot")
    freeze_cmd = sub.add_parser("freeze"); freeze_cmd.add_argument("--snapshot")
    plan_cmd = sub.add_parser("chapter-plan"); plan_cmd.add_argument("--snapshot", required=True)
    editor_cmd = sub.add_parser("editor-packet"); editor_cmd.add_argument("--snapshot", required=True)
    chapter_cmd = sub.add_parser("submit-chapter")
    chapter_cmd.add_argument("--snapshot", required=True); chapter_cmd.add_argument("--chapter", required=True); chapter_cmd.add_argument("--content", required=True)
    draft_cmd = sub.add_parser("stage-report")
    draft_cmd.add_argument("--snapshot", required=True); draft_cmd.add_argument("--content", required=True)
    review_cmd = sub.add_parser("submit-report-review")
    review_cmd.add_argument("--snapshot", required=True); review_cmd.add_argument("--content", required=True); review_cmd.add_argument("--assessment", required=True)
    report_cmd = sub.add_parser("compile-report")
    report_cmd.add_argument("--snapshot", required=True); report_cmd.add_argument("--content", required=True)
    args = parser.parse_args(argv)
    if args.command == "init": result = init(args.intent)
    elif args.command == "audit-evidence": result = audit_evidence(args.snapshot)
    elif args.command == "freeze": result = freeze(args.snapshot)
    elif args.command == "chapter-plan": result = chapter_plan(args.snapshot)
    elif args.command == "editor-packet": result = editor_packet(args.snapshot)
    elif args.command == "submit-chapter": result = submit_chapter(args.snapshot, args.chapter, _read_content_argument(args.content))
    elif args.command == "stage-report": result = stage_report(args.snapshot, _read_content_argument(args.content))
    elif args.command == "submit-report-review":
        assessment = json.loads(_read_content_argument(args.assessment))
        if not isinstance(assessment, dict):
            raise ValueError("report review assessment must be a JSON object")
        result = submit_report_review(args.snapshot, _read_content_argument(args.content), assessment)
    else: result = compile_report(args.snapshot, _read_content_argument(args.content))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
