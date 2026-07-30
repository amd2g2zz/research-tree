"""Tests for repository-local Claude Code and Codex lifecycle hook templates."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks"
SCRIPTS = ROOT / "scripts"
for path in (HOOKS, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from research_hook import HookInputError, handle  # noqa: E402
from research_service import ResearchService  # noqa: E402


FRAME = {
    "focus": "hook planning",
    "information_gap": "which task is next",
    "discriminator": "live frame state",
    "expected_update": "produce a role-scoped task",
    "evidence_requirement": "not required for planning",
}


class ResearchHookTests(unittest.TestCase):
    @staticmethod
    def ready_intent_contract() -> dict:
        return {
            "status": "ready",
            "summary": "The bounded hook test requires an evidence-backed research deliverable.",
            "deliverables": [{
                "id": "test-fixture", "kind": "test_fixture", "requires_research": False,
                "description": "Authorize the bounded hook fixture to create its explicit research frame.",
            }],
            "research_questions": [], "design_requirements": [], "writing_requirements": [],
            "acceptance_criteria": [], "assumptions": [], "other_constraints": [],
            "user_materials": [], "clarifying_questions": [], "research_frames": [],
        }

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(prefix="rt-hook-", dir=ROOT)
        self.workspace = Path(self.tempdir.name).resolve()
        self.environment = mock.patch.dict(os.environ, {"RESEARCH_WORKSPACE": str(self.workspace)})
        self.environment.start()
        service = ResearchService()
        service.initialize("Test hook planning", [], "2026-07-29T00:00:00+00:00")
        service.analyze_intent(self.ready_intent_contract())
        service.bootstrap([FRAME])

    def tearDown(self):
        self.environment.stop()
        self.tempdir.cleanup()

    def payload(self, event: str = "SessionStart") -> dict:
        return {"cwd": str(self.workspace), "hook_event_name": event, "session_id": "not-recorded"}

    def test_record_writes_minimal_event_without_raw_session_data(self):
        result = handle(self.payload(), action="record", expected_event="SessionStart",
                        root=ROOT, process_cwd=self.workspace)
        self.assertEqual(result["status"], "recorded")
        events = list((self.workspace / "research_drift" / "hook_events").glob("*.json"))
        self.assertEqual(len(events), 1)
        record = json.loads(events[0].read_text(encoding="utf-8"))
        self.assertEqual(record["event"], "SessionStart")
        self.assertEqual(record["action"], "record")
        self.assertNotIn("session_id", record)
        self.assertNotIn("transcript_path", record)

    def test_plan_is_read_only_and_does_not_write_a_worker_batch(self):
        result = handle(self.payload("Stop"), action="plan", expected_event="Stop",
                        root=ROOT, process_cwd=self.workspace)
        self.assertEqual(result["status"], "recorded")
        self.assertEqual(result["plan"]["status"], "planned")
        self.assertEqual(result["plan"]["roles"], [])
        self.assertEqual(result["plan"]["coordinator_roles"], ["coordinator"])
        self.assertFalse((self.workspace / "research" / "orchestrator" / "worker_batch.json").exists())

    def test_rejects_relative_or_external_workspaces(self):
        with self.assertRaises(HookInputError):
            handle({"cwd": ".", "hook_event_name": "SessionStart"}, action="record",
                   expected_event="SessionStart", root=ROOT, process_cwd=self.workspace)
        outside = Path(tempfile.gettempdir()).resolve()
        with self.assertRaises(HookInputError):
            handle({"cwd": str(outside), "hook_event_name": "SessionStart"}, action="record",
                   expected_event="SessionStart", root=ROOT, process_cwd=self.workspace)

    def test_reentrant_stop_is_skipped_without_an_event_file(self):
        payload = self.payload("Stop")
        payload["stop_hook_active"] = True
        result = handle(payload, action="plan", expected_event="Stop", root=ROOT, process_cwd=self.workspace)
        self.assertEqual(result["status"], "skipped_reentrant_stop")
        self.assertFalse((self.workspace / "research_drift" / "hook_events").exists())

    def test_templates_are_valid_json_with_static_hook_commands(self):
        for name in ("claude-code.settings.template.json", "codex.hooks.template.json"):
            template = json.loads((HOOKS / name).read_text(encoding="utf-8"))
            text = json.dumps(template)
            self.assertIn("research_hook.py", text)
            self.assertNotIn("${", text)
            self.assertNotIn("$(", text)
        claude = json.loads((HOOKS / "claude-code.settings.template.json").read_text(encoding="utf-8"))
        self.assertIn("SessionStart", claude)
        self.assertNotIn("hooks", claude)
        codex = json.loads((HOOKS / "codex.hooks.template.json").read_text(encoding="utf-8"))
        self.assertIn("hooks", codex)


if __name__ == "__main__":
    unittest.main(verbosity=2)
