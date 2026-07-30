"""Tests for bounded chapter submission and report compilation."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


HERE = Path(__file__).parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import engine  # noqa: E402
import project  # noqa: E402
from research_orchestrator import ResearchOrchestrator  # noqa: E402


FRAME = {
    "focus": "delivery evidence",
    "information_gap": "which frozen source supports the report",
    "discriminator": "saved primary source",
    "expected_update": "a cited chapter",
    "evidence_requirement": "locally persisted source",
}


class FrozenDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rt-delivery-"))
        self.environment = mock.patch.dict(os.environ, {"RESEARCH_WORKSPACE": str(self.tmp)})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def ready_intent_contract() -> dict:
        return {
            "status": "ready",
            "summary": "The bounded delivery test requires an evidence-backed research deliverable.",
            "deliverables": [{
                "id": "test-fixture", "kind": "test_fixture", "requires_research": False,
                "description": "Authorize the bounded delivery fixture to create its explicit research frames.",
            }],
            "research_questions": [], "design_requirements": [], "writing_requirements": [],
            "acceptance_criteria": [], "assumptions": [], "other_constraints": [],
            "user_materials": [], "clarifying_questions": [], "research_frames": [],
        }

    @staticmethod
    def delivery_checks(chapter: dict) -> str:
        return "\n".join(
            f"<!-- research-tree:check {item['id']} -->"
            for item in chapter.get("delivery_checklist", [])
        )

    def review_evidence(self, state: engine.ResearchState, frame_id: str, proposals: list[dict]) -> dict:
        discovery = self.tmp / "research_drift" / "discovery" / f"{frame_id}.json"
        manifest = self.tmp / "research_drift" / "sources" / f"{frame_id}.json"
        discovery.parent.mkdir(parents=True, exist_ok=True)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        discovery.write_text("{}", encoding="utf-8")
        records = [{"status": "captured", "evidence": {"local_path": proposal["local_path"]},
                    "content_sha256": hashlib.sha256((self.tmp / proposal["local_path"]).read_bytes()).hexdigest()}
                   for proposal in proposals]
        summary = {"candidate_count": len(records), "capture_limit": max(1, len(records)),
                   "captured_count": len(records), "failed_count": 0, "deferred_count": 0}
        manifest.write_text(json.dumps({"schema": 1, "frame_id": frame_id, "request_sha256": "a" * 64,
                                        "records": records, "summary": summary}), encoding="utf-8")
        state.collection_ready(frame_id, {
            "discovery_path": str(discovery.relative_to(self.tmp)).replace("\\", "/"),
            "source_manifest_path": str(manifest.relative_to(self.tmp)).replace("\\", "/"),
            "request_sha256": "a" * 64,
            "summary": summary,
            "review_roles": ["source_triager", "source_adversary"],
        })
        state.aggregate_sources(frame_id, [{
            "topic_key": f"delivery-source-{index}",
            "topic": f"Delivery source {index}",
            "context_signature": "bounded frozen delivery contract",
            "dedup_rationale": "This saved page is the sole source for its delivery topic.",
            "sources": [{
                "local_path": proposal["local_path"],
                "content_sha256": records[index]["content_sha256"],
                "relation": "representative",
                "primary": True,
                "quality_components": {
                    key: proposal.get("quality_score", 0.8)
                    for key in ("authority", "directness", "traceability", "temporal_fit", "capture_completeness", "independence")
                },
                "assessment_confidence": 0.9,
                "rationale": proposal.get("quality_rationale", "Direct, complete primary source."),
            }],
            "representative_local_paths": [proposal["local_path"]],
            "confidence_components": {
                key: proposal.get("cluster_confidence_score", 0.8)
                for key in ("source_quality", "corroboration", "independence", "temporal_coherence", "scope_match")
            },
            "confidence_rationale": proposal.get(
                "cluster_confidence_rationale", "The scoped source directly supports this bounded topic."
            ),
            "unresolved": proposal.get("unresolved", []),
        } for index, proposal in enumerate(proposals)], state.data["frames"][frame_id]["collection"]["source_manifest_sha256"])
        result = state.add_evidence(frame_id, proposals, "source_triager")
        state.add_evidence(frame_id, [], "source_adversary")
        return result

    def _frozen_plan(
        self,
        count: int = 2,
        *,
        quality_score: float = 0.8,
        cluster_confidence_score: float = 0.8,
        materials: list[dict] | None = None,
        intent_contract: dict | None = None,
    ) -> tuple[str, dict]:
        project.init("Investigate bounded frozen delivery")
        state = engine.ResearchState.create(
            "Investigate bounded frozen delivery", [], "2026-07-29T00:00:00+00:00", materials
        )
        state.analyze_intent(intent_contract or self.ready_intent_contract())
        state.save()
        declared_frame_ids = list(state.data["frames"])
        for index in range(count):
            if index < len(declared_frame_ids):
                frame_id = declared_frame_ids[index]
            else:
                proposal = dict(FRAME)
                proposal["focus"] = f"delivery evidence {index}"
                frame_id, _ = state.add_frame(proposal)
            state.formulate(frame_id, [{"query": f"frozen delivery evidence {index}"}])
            page = self.tmp / "research_drift" / "pages" / f"source-{index}.md"
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text(
                f"Primary source {index} establishes a bounded frozen delivery contract.\n\n"
                f"The chapter must cite source {index} only.",
                encoding="utf-8",
            )
            evidence_id = self.review_evidence(state, frame_id, [{
                "local_path": f"research_drift/pages/source-{index}.md",
                "published_at": "2026-07-01",
                "quality_score": quality_score,
                "cluster_confidence_score": cluster_confidence_score,
                "selection_override_rationale": "Keep this scored source so the delivery contract can expose its limitation.",
            }])["evidence_ids"][0]
            state.extract(frame_id, [{
                "claim": f"Source {index} supports bounded delivery",
                "context_signature": "frozen delivery contract",
                "evidence_time": "2026-07-01",
                "source_spans": [{"evidence_id": evidence_id, "locator": "p:1"}],
            }], [])
            state.finish(frame_id, "resolved", f"source {index} verified", 0.8)
        state.save()
        snapshot = project.freeze("delivery-unit")["snapshot_id"]
        return snapshot, project.chapter_plan(snapshot)

    def _decision_frozen_plan(self) -> tuple[str, dict, dict]:
        project.init("Decide whether to adopt a bounded workflow change")
        state = engine.ResearchState.create(
            "Decide whether to adopt a bounded workflow change", [], "2026-07-29T00:00:00+00:00"
        )
        contract = {
            "status": "ready", "summary": "Decide whether a bounded workflow change is ready for adoption.",
            "deliverables": [{
                "id": "decision-report", "kind": "research_report", "description": "A decision-ready report.",
                "requires_research": True, "research_frame_refs": ["adoption-evidence"],
            }],
            "research_questions": ["What does the saved evidence support?"],
            "decision_questions": [{
                "id": "adoption", "question": "Should the workflow change be approved now?",
                "why_it_matters": "It controls the implementation commitment.", "impact": "high",
                "deliverable_ids": ["decision-report"],
            }],
            "design_requirements": [], "writing_requirements": [], "acceptance_criteria": [],
            "assumptions": [], "other_constraints": [], "user_materials": [],
            "clarifying_questions": [], "research_frames": [{**FRAME, "contract_ref": "adoption-evidence"}],
        }
        state.analyze_intent(contract)
        frame_id = next(iter(state.data["frames"]))
        state.formulate(frame_id, [{"query": "bounded workflow evidence"}])
        page = self.tmp / "research_drift" / "pages" / "decision-report-source.md"
        page.write_text("The captured evidence supports only a measured preflight.", encoding="utf-8")
        evidence_id = self.review_evidence(state, frame_id, [{
            "local_path": "research_drift/pages/decision-report-source.md", "published_at": "2026-07-01",
        }])["evidence_ids"][0]
        extracted = state.extract(frame_id, [{
            "claim": "The captured evidence supports a measured preflight, not adoption.",
            "context_signature": "bounded workflow evidence", "evidence_time": "2026-07-01",
            "source_spans": [{"evidence_id": evidence_id, "locator": "p:1"}],
        }], [], [{
            "evidence_id": evidence_id, "disposition": "cited",
            "rationale": "It directly supports the constrained conclusion.",
        }])
        state.finish(frame_id, "resolved", "bounded evidence reviewed", 0.7)
        state.synthesize_decision({
            "overall_status": "conditional", "recommendation": "preflight_only",
            "summary": "Run a preflight before deciding on adoption.",
            "question_assessments": [{
                "decision_question_id": "adoption", "status": "conditional",
                "conclusion": "The evidence supports only a measured preflight.",
                "supporting_cognition_ids": extracted["cognition_ids"], "refuting_cognition_ids": [],
                "gap_ids": [], "user_questions": [],
                "conditions_to_change": ["Measure the actual workflow against its baseline."],
                "action": "Run the preflight, then reassess adoption.",
            }], "parameter_provenance": [],
        })
        state.save()
        snapshot = project.freeze("decision-delivery")["snapshot_id"]
        return snapshot, project.chapter_plan(snapshot), state.data["decision_synthesis"]

    def test_submit_rebuilds_plan_and_limits_citations_to_own_frozen_evidence(self):
        snapshot, plan = self._frozen_plan()
        first, second = plan["chapters"]
        own_chunk = first["citation_chunk_ids"][0]
        foreign_chunk = second["citation_chunk_ids"][0]

        # A worker-owned task file is mutable and therefore cannot grant a
        # chapter permission. Submission recomputes this data from the snapshot.
        tasks_path = self.tmp / "research" / "chapters" / "tasks.json"
        tasks_path.write_text(json.dumps({"snapshot_id": "forged", "chapters": []}), encoding="utf-8")
        result = project.submit_chapter(snapshot, first["chapter_id"], f"# Evidence\n[citation: {own_chunk}]")
        self.assertEqual(result["citation_chunk_ids"], [own_chunk])
        self.assertTrue((self.tmp / result["path"]).is_file())

        with self.assertRaisesRegex(ValueError, "outside its frozen evidence"):
            project.submit_chapter(snapshot, first["chapter_id"], f"[citation: {foreign_chunk}]")
        with self.assertRaisesRegex(ValueError, "not planned"):
            project.submit_chapter(snapshot, "../../report", f"[citation: {own_chunk}]")
        with self.assertRaisesRegex(ValueError, "control character"):
            project.submit_chapter(snapshot, first["chapter_id"], f"[citation: {own_chunk}]\x00")

    def test_compile_requires_every_chapter_and_revalidates_submissions(self):
        snapshot, plan = self._frozen_plan()
        first, second = plan["chapters"]
        first_chunk = first["citation_chunk_ids"][0]
        second_chunk = second["citation_chunk_ids"][0]
        project.submit_chapter(snapshot, first["chapter_id"], f"# First\n[citation: {first_chunk}]")

        with self.assertRaisesRegex(ValueError, "missing submitted chapters"):
            project.compile_report(snapshot, f"# Report\n[citation: {first_chunk}]")

        project.submit_chapter(snapshot, second["chapter_id"], f"# Second\n[citation: {second_chunk}]")
        with self.assertRaisesRegex(ValueError, "outside the frozen chapter evidence"):
            project.compile_report(snapshot, "# Report\n[citation: c_0000000000000000]")

        result = project.compile_report(snapshot, f"# Report\n[citation: {first_chunk}]\n[citation: {second_chunk}]")
        self.assertEqual(result["chapter_ids"], [first["chapter_id"], second["chapter_id"]])
        report = self.tmp / "report.md"
        manifest = self.tmp / "research" / "editor" / "report_manifest.json"
        self.assertTrue(report.is_file())
        self.assertTrue(manifest.is_file())
        self.assertEqual(set(json.loads(manifest.read_text(encoding="utf-8"))["chapter_hashes"]), set(result["chapter_ids"]))
        self.assertTrue(project.report_ready(snapshot))
        report.write_text("tampered", encoding="utf-8")
        self.assertFalse(project.report_ready(snapshot))

    def test_decision_report_requires_hash_bound_synthesis_and_independent_review(self):
        snapshot, plan, decision_record = self._decision_frozen_plan()
        chapter = plan["chapters"][0]
        chunk = chapter["citation_chunk_ids"][0]
        project.submit_chapter(snapshot, chapter["chapter_id"], f"# Evidence\n[citation: {chunk}]")
        synthesis = decision_record["synthesis"]
        assessment = synthesis["question_assessments"][0]
        report = f"""# Adoption Decision

<!-- research-tree:decision-synthesis {decision_record['sha256']} -->

## Decision Assessment

<!-- research-tree:decision-question adoption -->

Only a measured preflight is justified by the frozen evidence. [citation: {chunk}]

## What Would Change The Decision

Measure the actual workflow against its baseline.

## Parameter Provenance

No numerical operating parameter has been approved in this decision.
"""
        with self.assertRaisesRegex(ValueError, "approved independent report review"):
            project.compile_report(snapshot, report)
        project.stage_report(snapshot, report)
        with self.assertRaisesRegex(ValueError, "cover every decision question"):
            project.submit_report_review(snapshot, report, {
                "status": "approved", "summary": "Incomplete review.", "question_reviews": [],
                "parameter_reviews": [], "critical_gap_handling": "Not checked.",
            })
        review = {
            "status": "approved", "summary": "The report preserves the conditional decision.",
            "question_reviews": [{
                "decision_question_id": "adoption", "status": "conditional",
                "cognition_ids": assessment["supporting_cognition_ids"],
                "inference": "The cited evidence is bounded to a preflight.",
                "action": "Run the preflight before adoption.",
                "conditions_to_change": assessment["conditions_to_change"],
            }], "parameter_reviews": [],
            "critical_gap_handling": "The baseline measurement remains explicit and blocks adoption.",
        }
        project.submit_report_review(snapshot, report, review)
        result = project.compile_report(snapshot, report)
        self.assertTrue(project.report_ready(snapshot))
        report_manifest = json.loads((self.tmp / "research" / "editor" / "report_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(report_manifest["schema"], 5)
        self.assertEqual(report_manifest["decision_synthesis_sha256"], decision_record["sha256"])
        self.assertEqual(result["snapshot_id"], snapshot)

    def test_frozen_eight_chapter_plan_creates_eight_independent_writers(self):
        snapshot, chapter_plan = self._frozen_plan(count=8)

        planned = ResearchOrchestrator().plan(snapshot=snapshot)
        writer_tasks = planned["tasks"]

        self.assertEqual(len(chapter_plan["chapters"]), 8)
        self.assertEqual(len(writer_tasks), 8)
        self.assertEqual(planned["max_parallel"], 8)
        self.assertEqual({task["role"] for task in writer_tasks}, {"writer"})
        self.assertEqual({task["kind"] for task in writer_tasks}, {"write-chapter"})
        self.assertEqual(
            {task["task_id"] for task in writer_tasks},
            {f"writer:{chapter['chapter_id']}" for chapter in chapter_plan["chapters"]},
        )
        self.assertEqual(
            {task["chapter"]["chapter_id"] for task in writer_tasks},
            {chapter["chapter_id"] for chapter in chapter_plan["chapters"]},
        )
        self.assertEqual(
            {task["output_path"] for task in writer_tasks},
            {f"research/chapters/{chapter['chapter_id']}.md" for chapter in chapter_plan["chapters"]},
        )

    def test_submission_rejects_tampered_snapshot_and_oversized_content(self):
        snapshot, plan = self._frozen_plan(count=1)
        chapter = plan["chapters"][0]
        chunk = chapter["citation_chunk_ids"][0]
        with mock.patch.object(project, "MAX_CHAPTER_BYTES", 16):
            with self.assertRaisesRegex(ValueError, "exceeds"):
                project.submit_chapter(snapshot, chapter["chapter_id"], f"[citation: {chunk}]")

        frozen_chunks = self.tmp / "research_snapshots" / snapshot / "corpus" / "chunks.jsonl"
        frozen_chunks.write_text('{"id":"c_bad","source_path":"bad"}\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "integrity check failed"):
            project.submit_chapter(snapshot, chapter["chapter_id"], f"[citation: {chunk}]")

    def test_frozen_scores_flow_to_writer_and_editor_contracts(self):
        snapshot, plan = self._frozen_plan(count=1, quality_score=0.25, cluster_confidence_score=0.35)
        self.assertEqual(plan["schema"], 4)
        chapter = plan["chapters"][0]
        assessment = chapter["evidence_assessment"]
        self.assertEqual(assessment["status"], "available")
        self.assertEqual(assessment["thresholds"], {
            "low_source_quality": 0.5,
            "low_cluster_confidence": 0.5,
        })
        self.assertEqual(assessment["coverage"]["chapter_citable_source_count"], 1)
        self.assertRegex(assessment["aggregation_artifact"]["source_manifest_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(assessment["clusters"][0]["confidence_score"], 0.35)
        source = assessment["clusters"][0]["sources"][0]
        self.assertEqual(source["quality_score"], 0.25)
        self.assertEqual(source["availability"], "citable_in_this_chapter")
        self.assertTrue(source["citation_chunk_ids"])
        self.assertEqual({item["kind"] for item in assessment["required_disclosures"]}, {
            "low_source_quality", "low_cluster_confidence",
        })
        self.assertIn("Match claim strength", " ".join(assessment["writing_guidance"]))

        snapshot_root = self.tmp / "research_snapshots" / snapshot
        snapshot_manifest = json.loads((snapshot_root / "manifest.json").read_text(encoding="utf-8"))
        frozen_aggregation = snapshot_root / snapshot_manifest["frozen_aggregation_paths"][chapter["frame_id"]]
        self.assertTrue(frozen_aggregation.is_file())
        self.assertEqual(
            hashlib.sha256(frozen_aggregation.read_bytes()).hexdigest(),
            snapshot_manifest["aggregation_sha256"][chapter["frame_id"]],
        )

        packet = project.editor_packet(snapshot)
        editor_chapter = packet["chapters"][0]
        self.assertEqual(packet["schema"], 4)
        self.assertEqual(editor_chapter["evidence_assessment_sha256"], chapter["evidence_assessment_sha256"])
        self.assertEqual(
            editor_chapter["quality_review"]["required_disclosures"], assessment["required_disclosures"]
        )
        self.assertIn("low-score", editor_chapter["quality_review"]["instruction"])

        chunk = chapter["citation_chunk_ids"][0]
        submitted = project.submit_chapter(snapshot, chapter["chapter_id"], f"# Finding\n[citation: {chunk}]")
        self.assertEqual(len(submitted["quality_disclosure_requirement_ids"]), 2)
        chapter_manifest = json.loads(
            (self.tmp / "research" / "editor" / "chapter-manifests" / f"{chapter['chapter_id']}.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(chapter_manifest["schema"], 4)
        self.assertEqual(chapter_manifest["evidence_assessment_sha256"], chapter["evidence_assessment_sha256"])
        self.assertEqual(
            {item["kind"] for item in chapter_manifest["quality_disclosure_requirements"]},
            {"low_source_quality", "low_cluster_confidence"},
        )
        project.compile_report(snapshot, f"# Report\n[citation: {chunk}]")
        report_manifest = json.loads(
            (self.tmp / "research" / "editor" / "report_manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report_manifest["schema"], 4)
        self.assertEqual(
            report_manifest["chapter_evidence_assessment_sha256"][chapter["chapter_id"]],
            chapter["evidence_assessment_sha256"],
        )

        frozen_aggregation.write_text("tampered", encoding="utf-8")
        audit = project.verify_snapshot(snapshot)
        self.assertFalse(audit["ok"])
        self.assertIn({"issue": "aggregation_hash_changed", "frame_id": chapter["frame_id"]}, audit["issues"])

    def test_intent_material_and_experiment_deliverables_are_frozen_and_planned(self):
        material = self.tmp / "inputs" / "study-brief.md"
        material.parent.mkdir(parents=True, exist_ok=True)
        material.write_text(
            "# Study brief\n\nThe intervention needs a control group and a pre-registered primary outcome.",
            encoding="utf-8",
        )
        intent_contract = {
            "status": "ready",
            "summary": "Analyze the supplied study brief and design a feasible controlled experiment.",
            "deliverables": [
                {
                    "id": "research-report",
                    "kind": "research_report",
                    "description": "Evidence chapters supporting the experiment design.",
                    "requires_research": True,
                    "requires_material_analysis": False,
                    "requires_design": False,
                    "research_frame_refs": ["study-evidence"],
                },
                {
                    "id": "brief-analysis",
                    "kind": "material_analysis",
                    "description": "Analyze the supplied study brief.",
                    "requires_research": False,
                    "requires_material_analysis": True,
                    "requires_design": False,
                },
                {
                    "id": "controlled-experiment",
                    "kind": "experiment_plan",
                    "description": "Produce a complete controlled experiment plan.",
                    "requires_research": True,
                    "requires_material_analysis": True,
                    "requires_design": True,
                    "research_frame_refs": ["study-evidence"],
                },
            ],
            "research_questions": ["What frozen evidence informs the study design?"],
            "design_requirements": ["Specify control, intervention, primary outcome, and stopping rule."],
            "writing_requirements": ["Separate observed material facts from proposed design choices."],
            "acceptance_criteria": ["The plan is feasible and has an explicit primary outcome."],
            "assumptions": ["Participants can be randomized."],
            "other_constraints": ["Do not claim results before the experiment runs."],
            "user_materials": [{
                "material_id": "study-brief",
                "status": "provided",
                "required": True,
                "description": "The user's study brief.",
                "intended_use": "Constrain the experiment design.",
            }],
            "clarifying_questions": [],
            "research_frames": [{**FRAME, "contract_ref": "study-evidence"}],
        }
        snapshot, plan = self._frozen_plan(
            count=1,
            materials=[{
                "material_id": "study-brief",
                "path": "inputs/study-brief.md",
                "description": "The user's study brief.",
                "media_type": "text/markdown",
            }],
            intent_contract=intent_contract,
        )
        self.assertEqual(plan["schema"], 4)
        frame_chapter = next(item for item in plan["chapters"] if item["chapter_kind"] == "research_frame")
        deliverables = {
            item["deliverable"]["id"]: item
            for item in plan["chapters"] if item["chapter_kind"] == "intent_deliverable"
        }
        self.assertEqual(set(deliverables), {"brief-analysis", "controlled-experiment"})
        brief = deliverables["brief-analysis"]
        experiment = deliverables["controlled-experiment"]

        snapshot_root = self.tmp / "research_snapshots" / snapshot
        snapshot_manifest = json.loads((snapshot_root / "manifest.json").read_text(encoding="utf-8"))
        frozen_material = snapshot_manifest["frozen_materials"]["study-brief"]
        frozen_material_path = snapshot_root / frozen_material["path"]
        self.assertTrue(frozen_material_path.is_file())
        self.assertEqual(frozen_material["sha256"], hashlib.sha256(frozen_material_path.read_bytes()).hexdigest())
        self.assertTrue(frozen_material["path"].startswith("pages/materials/"))

        frozen_chunks = [
            json.loads(line)
            for line in (snapshot_root / "corpus" / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        material_source = str(frozen_material_path.relative_to(self.tmp)).replace("\\", "/")
        material_chunks = [item["id"] for item in frozen_chunks if item["source_path"] == material_source]
        self.assertTrue(material_chunks)
        self.assertEqual(brief["citation_chunk_ids"], material_chunks)
        self.assertNotIn(frame_chapter["citation_chunk_ids"][0], brief["citation_chunk_ids"])
        self.assertIn(material_chunks[0], experiment["citation_chunk_ids"])
        self.assertIn(frame_chapter["citation_chunk_ids"][0], experiment["citation_chunk_ids"])
        self.assertEqual(experiment["research_evidence_inputs"][0]["chapter_id"], frame_chapter["chapter_id"])
        self.assertIn(brief["chapter_id"], experiment["dependency_chapter_ids"])
        self.assertEqual(experiment["material_inputs"][0]["availability"], "citable_text_material")
        self.assertEqual(
            experiment["delivery_requirements"]["design_requirements"], intent_contract["design_requirements"]
        )
        self.assertEqual(
            experiment["delivery_requirements"]["acceptance_criteria"], intent_contract["acceptance_criteria"]
        )
        self.assertIn("user_material_unscored", {
            item["kind"] for item in experiment["evidence_assessment"]["required_disclosures"]
        })

        frozen_batch = ResearchOrchestrator().plan(snapshot=snapshot)
        self.assertNotIn(experiment["chapter_id"], {
            task["chapter"]["chapter_id"] for task in frozen_batch["tasks"]
        })
        self.assertEqual(frozen_batch["deferred_chapters"], [{
            "chapter_id": experiment["chapter_id"],
            "dependency_chapter_ids": experiment["dependency_chapter_ids"],
            "unmet_dependency_chapter_ids": experiment["dependency_chapter_ids"],
        }])

        with self.assertRaisesRegex(ValueError, "outside its frozen evidence"):
            project.submit_chapter(
                snapshot, brief["chapter_id"], f"[citation: {frame_chapter['citation_chunk_ids'][0]}]"
            )
        project.submit_chapter(snapshot, frame_chapter["chapter_id"], f"[citation: {frame_chapter['citation_chunk_ids'][0]}]")
        with self.assertRaisesRegex(ValueError, "omits required delivery checks"):
            project.submit_chapter(snapshot, brief["chapter_id"], f"[citation: {material_chunks[0]}]")
        with self.assertRaisesRegex(ValueError, "dependencies are not ready"):
            project.submit_chapter(
                snapshot,
                experiment["chapter_id"],
                f"[citation: {material_chunks[0]}]\n[citation: {frame_chapter['citation_chunk_ids'][0]}]",
            )
        submitted_brief = project.submit_chapter(
            snapshot, brief["chapter_id"],
            f"[citation: {material_chunks[0]}]\n{self.delivery_checks(brief)}",
        )
        submitted_experiment = project.submit_chapter(
            snapshot,
            experiment["chapter_id"],
            f"[citation: {material_chunks[0]}]\n[citation: {frame_chapter['citation_chunk_ids'][0]}]\n{self.delivery_checks(experiment)}",
        )
        self.assertTrue(submitted_brief["quality_disclosure_requirement_ids"])
        self.assertIn("chapter_contract_sha256", submitted_experiment)

        packet = project.editor_packet(snapshot)
        experiment_packet = next(item for item in packet["chapters"] if item["task"]["chapter_id"] == experiment["chapter_id"])
        self.assertEqual(experiment_packet["delivery_review"]["chapter_kind"], "intent_deliverable")
        self.assertEqual(
            experiment_packet["delivery_review"]["delivery_requirements"]["writing_requirements"],
            intent_contract["writing_requirements"],
        )
        self.assertEqual(experiment_packet["chapter_contract_sha256"], experiment["chapter_contract_sha256"])
        self.assertEqual(packet["report_presentation"]["profile"], "experiment_plan")

        with self.assertRaisesRegex(ValueError, "readable evidence labels"):
            project.compile_report(
                snapshot,
                f"# Delivery\n[citation: {material_chunks[0]}]\n[citation: {frame_chapter['citation_chunk_ids'][0]}]",
            )
        report = f"""# Delivery

- Snapshot: `{snapshot}`
- As of: `2026-01-01T00:00:00+00:00`
- Evidence window: `2023-01-01 through 2026-01-01`

## Decision Summary

Run the proposed controlled experiment before changing the workflow. [E1]
<!-- research-tree:evidence {material_chunks[0]} -->

## Evidence Judgment

| Label | Use |
|---|---|
| [E1] | Frozen study brief and bounded evidence |

<!-- research-tree:evidence {frame_chapter['citation_chunk_ids'][0]} -->

## Experiment Design

| Element | Protocol |
|---|---|
| Treatment and control | Compare the proposed intervention with the baseline. |

## Metrics and Adjudication

| Metric | Rule |
|---|---|
| Primary outcome | Use the pre-specified outcome and record invalid runs. |

## Analysis and Adoption

Use the planned paired analysis and pre-specified adoption rule.

## Execution Plan

| Phase | Output |
|---|---|
| Preflight | Locked inputs and run order |

## Risks and Stopping

Stop and report a partial result if a hard constraint is violated.

## Limitations

This is a proposed protocol, not an observed treatment effect.

## Sources and Traceability

| Label | Frozen location |
|---|---|
| [E1] | `research_snapshots/{snapshot}/pages/` |
"""
        project.compile_report(snapshot, report)
        frozen_material_path.write_bytes(b"x" * frozen_material["byte_count"])
        audit = project.verify_snapshot(snapshot)
        self.assertFalse(audit["ok"])
        self.assertIn({"issue": "material_hash_changed", "material_id": "study-brief"}, audit["issues"])

    def test_delivery_plan_keeps_legacy_snapshot_without_aggregation_usable(self):
        snapshot, _ = self._frozen_plan(count=1)
        original = self.tmp / "research_snapshots" / snapshot
        legacy_snapshot = "delivery-legacy"
        legacy = self.tmp / "research_snapshots" / legacy_snapshot
        shutil.copytree(original, legacy)
        state_path = legacy / "research_state.json"
        data = json.loads(state_path.read_text(encoding="utf-8"))
        data["snapshot_id"] = legacy_snapshot
        for frame in data["frames"].values():
            frame.pop("aggregation", None)
        state_path.write_text(json.dumps(data), encoding="utf-8")
        manifest_path = legacy / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["snapshot_id"] = legacy_snapshot
        manifest["state_sha256"] = hashlib.sha256(state_path.read_bytes()).hexdigest()
        manifest.pop("frozen_aggregation_paths", None)
        manifest.pop("aggregation_sha256", None)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        plan = project.chapter_plan(legacy_snapshot)
        assessment = plan["chapters"][0]["evidence_assessment"]
        self.assertEqual(assessment["status"], "unavailable")
        self.assertTrue(assessment["unscored_evidence_ids"])

    def test_cli_submit_reads_only_workspace_content_file(self):
        snapshot, plan = self._frozen_plan(count=1)
        chapter = plan["chapters"][0]
        chunk = chapter["citation_chunk_ids"][0]
        draft = self.tmp / "draft.md"
        draft.write_text(f"# Draft\n[citation: {chunk}]", encoding="utf-8")
        with mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(project.main([
                "submit-chapter", "--snapshot", snapshot, "--chapter", chapter["chapter_id"],
                "--content", "@draft.md",
            ]), 0)
        self.assertIn(chapter["chapter_id"], output.getvalue())
        with self.assertRaisesRegex(ValueError, "inside the research workspace"):
            project._read_content_argument("@../outside.md")


if __name__ == "__main__":
    unittest.main(verbosity=2)
