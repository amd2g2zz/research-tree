"""Tests for the safe host subagent file protocol."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import host_adapter
from research_service import ResearchService


FRAME = {
    "focus": "runtime capabilities", "information_gap": "which primitives are available",
    "discriminator": "official documentation", "expected_update": "define a boundary",
    "evidence_requirement": "official source",
}


class HostAdapterTests(unittest.TestCase):
    @staticmethod
    def ready_intent_contract() -> dict:
        return {
            "status": "ready",
            "summary": "The bounded host-adapter test requires an evidence-backed research deliverable.",
            "deliverables": [{
                "id": "test-fixture", "kind": "test_fixture", "requires_research": False,
                "description": "Authorize the bounded host-adapter fixture to create its explicit research frame.",
            }],
            "research_questions": [], "design_requirements": [], "writing_requirements": [],
            "acceptance_criteria": [], "assumptions": [], "other_constraints": [],
            "user_materials": [], "clarifying_questions": [], "research_frames": [],
        }

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rt-host-"))
        self.env = mock.patch.dict(os.environ, {"RESEARCH_WORKSPACE": str(self.tmp)})
        self.env.start()
        service = ResearchService()
        service.initialize("Investigate an agent", [], "2026-07-29T00:00:00+00:00")
        service.analyze_intent(self.ready_intent_contract())
        self.frame_id = service.bootstrap([FRAME])["frame_ids"][0]

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_dispatch_writes_a_host_scoped_batch(self):
        result = host_adapter.dispatch("codex")
        self.assertEqual(result["task_count"], 0)
        path = self.tmp / result["path"]
        self.assertTrue(path.is_file())
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["batch"]["tasks"], [])
        self.assertEqual(payload["batch"]["coordinator_tasks"][0]["kind"], "formulate")

    def test_submit_only_accepts_structured_service_commands(self):
        result = host_adapter.submit("claude-code", [{
            "command_id": "host-formulate-001", "operation": "formulate", "frame_id": self.frame_id,
            "plan": [{"query": "agent runtime"}],
        }])
        self.assertEqual(result["accepted"], 1)
        self.assertEqual(ResearchService().status()["frame_states"], {"acquiring": 1})

    def test_cli_accepts_one_worker_command_object(self):
        command = self.tmp / "one-command.json"
        command.write_text(json.dumps({
            "command_id": "host-formulate-object-001", "operation": "formulate", "frame_id": self.frame_id,
            "plan": [{"query": "agent runtime"}],
        }), encoding="utf-8")
        with mock.patch("sys.stdout") as output:
            self.assertEqual(host_adapter.main([
                "submit", "--host", "codex", "--commands", "@one-command.json",
            ]), 0)
        written = "".join(call.args[0] for call in output.write.call_args_list)
        self.assertIn("\"accepted\": 1", written)
        self.assertEqual(ResearchService().status()["frame_states"], {"acquiring": 1})

    def test_command_reader_rejects_non_object_batch_members(self):
        with self.assertRaisesRegex(ValueError, "object or a list of objects"):
            host_adapter._read_commands('[{"command_id": "valid"}, 3]')

    def test_worker_evidence_cannot_bypass_saved_source_collection(self):
        host_adapter.submit("codex", [{
            "command_id": "host-formulate-001", "operation": "formulate", "frame_id": self.frame_id,
            "plan": [{"query": "agent runtime"}],
        }])
        with self.assertRaisesRegex(ValueError, "only after saved-source collection"):
            host_adapter.submit("codex", [{
                "command_id": "host-evidence-001", "operation": "evidence", "frame_id": self.frame_id,
                "reviewer_role": "source_triager", "evidence": [],
            }])
        with self.assertRaisesRegex(ValueError, "requires an expanded frame"):
            host_adapter.submit("codex", [{
                "command_id": "host-finish-001", "operation": "finish", "frame_id": self.frame_id,
                "state": "insufficient_evidence", "summary": "premature", "confidence": 0.0,
            }])
        self.assertEqual(ResearchService().status()["frame_states"], {"acquiring": 1})

    def test_source_acquisition_is_separate_from_graph_submission(self):
        packet = {"path": "research_drift/pages/anysearch-a.md", "evidence": {"provider": "anysearch"}}
        state_path = self.tmp / "research_drift" / "research_state.json"
        before = state_path.read_bytes()
        with mock.patch("source_acquirer.acquire_anysearch", return_value=packet) as acquire:
            result = host_adapter.acquire_source("codex", "https://example.com/source", "Source")
        self.assertEqual(result, {"host": "codex", "result": packet})
        acquire.assert_called_once_with("https://example.com/source", "Source")
        self.assertEqual(state_path.read_bytes(), before)

    def test_rejects_command_file_outside_workspace(self):
        with self.assertRaisesRegex(ValueError, "inside the research workspace"):
            host_adapter._read_json("@../outside.json", list)

    def test_writer_editor_and_qa_routes_are_separate_from_graph_commands(self):
        with mock.patch("project.submit_chapter", return_value={"path": "research/chapters/chapter-f_1.md"}) as chapter:
            result = host_adapter.submit_chapter("codex", "frozen-unit", "chapter-f_1", "[citation: c_1]")
        self.assertEqual(result["host"], "codex")
        chapter.assert_called_once_with("frozen-unit", "chapter-f_1", "[citation: c_1]")
        with mock.patch("project.compile_report", return_value={"report_path": "report.md"}) as report:
            result = host_adapter.compile_report("claude-code", "frozen-unit", "# Report")
        self.assertEqual(result["host"], "claude-code")
        report.assert_called_once_with("frozen-unit", "# Report")
        packet = {"status": "retrieved", "evidence_packets": []}
        with mock.patch("qa.ask", return_value=packet) as ask:
            result = host_adapter.answer("codex", "frozen-unit", "What changed?", 3)
        self.assertEqual(result["result"], packet)
        ask.assert_called_once_with("frozen-unit", "What changed?", 3)

    def test_rejects_text_file_outside_workspace(self):
        with self.assertRaisesRegex(ValueError, "inside the research workspace"):
            host_adapter._read_text("@../outside.md")


if __name__ == "__main__":
    unittest.main(verbosity=2)
