"""Tests for pre-research intent understanding and requirement clarification."""

from __future__ import annotations

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

from research_orchestrator import ResearchOrchestrator  # noqa: E402
from research_service import ResearchService  # noqa: E402


FRAME = {
    "focus": "experimental controls",
    "information_gap": "which controls and metrics make the experiment feasible",
    "discriminator": "independent methodological evidence",
    "expected_update": "select controls and outcome measures",
    "evidence_requirement": "dated methodological or primary sources",
}


class IntentContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rt-intent-contract-"))
        self.environment = mock.patch.dict(os.environ, {"RESEARCH_WORKSPACE": str(self.tmp)})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def research_contract(*, status: str = "ready", frames: list[dict] | None = None,
                          questions: list[dict] | None = None, materials: list[dict] | None = None) -> dict:
        return {
            "status": status,
            "summary": "Produce an auditable experimental plan grounded in the specified evidence and user material.",
            "deliverables": [
                {"id": "material-analysis", "kind": "material_analysis", "description": "Analyze the user material.",
                 "requires_research": False, "requires_material_analysis": True},
                {"id": "experiment-plan", "kind": "experiment_plan", "description": "Write a feasible experiment plan.",
                 "requires_research": True, "requires_material_analysis": True, "requires_design": True},
            ],
            "research_questions": ["Which controls and outcome metrics are suitable?"],
            "design_requirements": ["State the hypothesis, controls, metrics, procedures, risks, and reproducibility checks."],
            "writing_requirements": ["Separate observed material facts from proposed design choices."],
            "acceptance_criteria": ["The plan is feasible and each consequential factual claim is cited."],
            "assumptions": [],
            "other_constraints": [],
            "user_materials": materials or [],
            "clarifying_questions": questions or [],
            "research_frames": frames or [],
        }

    def test_pending_contract_plans_only_the_intent_analyst_and_skips_discovery(self):
        service = ResearchService()
        service.initialize("根据我提供的材料写一个实验方案", [], "2026-07-30T00:00:00+00:00")
        self.assertEqual(service.next()["action"], "analyze_intent")
        batch = ResearchOrchestrator(service).plan()
        self.assertEqual([task["role"] for task in batch["tasks"]], ["intent_analyst"])
        self.assertEqual(batch["tasks"][0]["reference_time"], "2026-07-30T00:00:00+00:00")
        self.assertIn("registered_materials", batch["tasks"][0]["instruction"])
        self.assertEqual(batch["coordinator_tasks"], [])
        self.assertEqual(ResearchOrchestrator(service).discover()["skipped"], "intent_contract_not_ready")

    def test_blocking_question_prevents_bootstrap_until_user_answers(self):
        service = ResearchService()
        service.initialize("Design an experiment from my material", [], "2026-07-30T00:00:00+00:00")
        contract = self.research_contract(
            status="needs_clarification",
            questions=[{
                "id": "material-file", "question": "Which material should define the experimental setting?",
                "why": "No material was provided.", "blocking": True,
            }],
        )
        service.analyze_intent(contract)
        self.assertEqual(service.next()["action"], "clarify_intent")
        with self.assertRaisesRegex(ValueError, "intent contract must be ready"):
            service.bootstrap([FRAME])
        result = service.answer_intent_questions({"material-file": "Use the uploaded protocol note."})
        self.assertEqual(result["status"], "pending")
        self.assertEqual(service.next()["action"], "analyze_intent")

    def test_material_and_experiment_contract_registers_requirements_and_research_frame(self):
        material = self.tmp / "protocol.md"
        material.write_text("# Protocol\n\nMeasure accuracy under two interventions.", encoding="utf-8")
        service = ResearchService()
        service.initialize(
            "根据我的 protocol 设计一个完整实验方案", [], "2026-07-30T00:00:00+00:00",
            [{"id": "protocol", "path": "protocol.md", "description": "User-supplied protocol note"}],
        )
        contract = self.research_contract(
            frames=[FRAME],
            materials=[{
                "material_id": "protocol", "status": "provided", "required": True,
                "description": "Protocol note", "intended_use": "Extract the experiment context and constraints.",
            }],
        )
        result = service.analyze_intent(contract)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(len(result["created_frame_ids"]), 1)
        state = service.read_state()
        stored = state.intent_contract()["contract"]
        self.assertEqual([item["kind"] for item in stored["deliverables"]], ["material_analysis", "experiment_plan"])
        self.assertEqual(stored["deliverables"][1]["depends_on_deliverable_ids"], ["material-analysis"])
        self.assertEqual(stored["user_materials"][0]["registered"]["local_path"], "protocol.md")
        self.assertTrue(state.material_audit()["ok"])
        self.assertEqual(service.next()["action"], "formulate")

    def test_ready_material_analysis_contract_rejects_missing_required_material(self):
        service = ResearchService()
        service.initialize("根据材料写实验方案", [], "2026-07-30T00:00:00+00:00")
        contract = self.research_contract(
            frames=[FRAME],
            materials=[{
                "material_id": "missing-protocol", "status": "missing", "required": True,
                "description": "Required protocol", "intended_use": "Set the experimental context.",
            }],
        )
        with self.assertRaisesRegex(ValueError, "missing required material"):
            service.analyze_intent(contract)

    def test_ready_research_deliverable_requires_a_declared_bound_frame(self):
        service = ResearchService()
        service.initialize("Design an experiment from my material", [], "2026-07-30T00:00:00+00:00")
        contract = self.research_contract(frames=[])
        with self.assertRaisesRegex(ValueError, "research deliverable requires one or more declared research frames"):
            service.analyze_intent(contract)

    def test_contract_binds_research_deliverable_to_declared_frame(self):
        material = self.tmp / "protocol.md"
        material.write_text("# Protocol\n", encoding="utf-8")
        service = ResearchService()
        service.initialize(
            "Design an experiment from my protocol", [], "2026-07-30T00:00:00+00:00",
            [{"id": "protocol", "path": "protocol.md", "description": "protocol"}],
        )
        frame = {**FRAME, "contract_ref": "method-evidence"}
        contract = self.research_contract(
            frames=[frame],
            materials=[{
                "material_id": "protocol", "status": "provided", "required": True,
                "description": "Protocol", "intended_use": "constrain design",
            }],
        )
        contract["deliverables"][1]["research_frame_refs"] = ["method-evidence"]
        service.analyze_intent(contract)
        state = service.read_state()
        stored = state.intent_contract()["contract"]
        self.assertEqual(stored["deliverables"][1]["research_frame_refs"], ["method-evidence"])
        frame_id = next(iter(state.data["frames"]))
        self.assertEqual(state.data["frames"][frame_id]["contract_ref"], "method-evidence")
        self.assertEqual(state.data["frames"][frame_id]["deliverable_ids"], ["experiment-plan"])
        self.assertFalse(state.delivery_research_audit()["ok"])

    def test_partial_intent_answers_stay_in_clarification(self):
        service = ResearchService()
        service.initialize("Design an experiment", [], "2026-07-30T00:00:00+00:00")
        contract = self.research_contract(
            status="needs_clarification",
            questions=[
                {"id": "material", "question": "Which material?", "why": "Need context.", "blocking": True},
                {"id": "outcome", "question": "What outcome?", "why": "Need success criterion.", "blocking": True},
            ],
        )
        service.analyze_intent(contract)
        partial = service.answer_intent_questions({"material": "Use protocol A."})
        self.assertEqual(partial["status"], "needs_clarification")
        self.assertEqual(partial["unanswered_question_ids"], ["outcome"])
        self.assertEqual(service.next()["action"], "clarify_intent")
        completed = service.answer_intent_questions({"outcome": "Primary accuracy."})
        self.assertEqual(completed["status"], "pending")

    def test_material_can_be_registered_after_clarification_before_reanalysis(self):
        service = ResearchService()
        service.initialize("Design an experiment from an upload", [], "2026-07-30T00:00:00+00:00")
        contract = self.research_contract(
            status="needs_clarification",
            questions=[{
                "id": "upload", "question": "Upload the protocol.", "why": "Need context.", "blocking": True,
            }],
            materials=[{
                "material_id": "protocol", "status": "missing", "required": True,
                "description": "Protocol", "intended_use": "constrain design",
            }],
        )
        service.analyze_intent(contract)
        (self.tmp / "uploaded.md").write_text("# Uploaded protocol\n", encoding="utf-8")
        registered = service.register_material({
            "id": "protocol", "path": "uploaded.md", "description": "Uploaded protocol",
        })
        self.assertFalse(registered["replaced"])
        self.assertEqual(registered["material"]["local_path"], "uploaded.md")
        service.answer_intent_questions({"upload": "Uploaded protocol.md."})
        replacement = self.tmp / "uploaded-v2.md"
        replacement.write_text("# Revised protocol\n", encoding="utf-8")
        replaced = service.register_material({
            "id": "protocol", "path": "uploaded-v2.md", "description": "Revised protocol",
        }, replace=True)
        self.assertTrue(replaced["replaced"])
        self.assertEqual(replaced["material"]["local_path"], "uploaded-v2.md")

    def test_ready_material_analysis_rejects_unextractable_required_material(self):
        binary = self.tmp / "protocol.pdf"
        binary.write_bytes(b"%PDF-1.7\nplaceholder")
        service = ResearchService()
        service.initialize(
            "Design an experiment from my PDF", [], "2026-07-30T00:00:00+00:00",
            [{"id": "protocol", "path": "protocol.pdf", "description": "PDF protocol"}],
        )
        contract = self.research_contract(
            frames=[FRAME],
            materials=[{
                "material_id": "protocol", "status": "provided", "required": True,
                "description": "PDF protocol", "intended_use": "constrain design",
            }],
        )
        with self.assertRaisesRegex(ValueError, "text-extractable material"):
            service.analyze_intent(contract)

    def test_deliverable_dependency_cycle_is_rejected_before_research(self):
        material = self.tmp / "protocol.md"
        material.write_text("# Protocol\n", encoding="utf-8")
        service = ResearchService()
        service.initialize(
            "Design an experiment from my protocol", [], "2026-07-30T00:00:00+00:00",
            [{"id": "protocol", "path": "protocol.md", "description": "protocol"}],
        )
        contract = self.research_contract(
            frames=[FRAME],
            materials=[{
                "material_id": "protocol", "status": "provided", "required": True,
                "description": "Protocol", "intended_use": "constrain design",
            }],
        )
        contract["deliverables"][0]["depends_on_deliverable_ids"] = ["experiment-plan"]
        contract["deliverables"][1]["depends_on_deliverable_ids"] = ["material-analysis"]
        with self.assertRaisesRegex(ValueError, "dependencies contain a cycle"):
            service.analyze_intent(contract)


if __name__ == "__main__":
    unittest.main(verbosity=2)
