"""Tests for frozen corpus, Q&A, and project hand-offs."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import corpus  # noqa: E402
import engine  # noqa: E402
import project  # noqa: E402
import providers  # noqa: E402
import qa  # noqa: E402


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rt-project-v2-"))
        self.env = mock.patch.dict(os.environ, {"RESEARCH_WORKSPACE": str(self.tmp)})
        self.env.start()

    def tearDown(self):
        self.env.stop(); shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def ready_intent_contract() -> dict:
        return {
            "status": "ready",
            "summary": "The bounded corpus test requires an evidence-backed research deliverable.",
            "deliverables": [{
                "id": "test-fixture", "kind": "test_fixture", "requires_research": False,
                "description": "Authorize the bounded corpus fixture to create its explicit research frame.",
            }],
            "research_questions": [], "design_requirements": [], "writing_requirements": [],
            "acceptance_criteria": [], "assumptions": [], "other_constraints": [],
            "user_materials": [], "clarifying_questions": [], "research_frames": [],
        }

    def review_evidence(self, state: engine.ResearchState, frame_id: str, proposals: list[dict]) -> dict:
        discovery = self.tmp / "research_drift" / "discovery" / f"{frame_id}.json"
        manifest = self.tmp / "research_drift" / "sources" / f"{frame_id}.json"
        discovery.parent.mkdir(parents=True, exist_ok=True)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        discovery.write_text("{}", encoding="utf-8")
        records = [{"status": "captured", "evidence": dict(proposal),
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
            "topic_key": f"corpus-source-{index}",
            "topic": f"Corpus source {index}",
            "context_signature": "bounded frozen corpus test context",
            "dedup_rationale": "This saved page is retained as its own auditable topic source.",
            "sources": [{
                "local_path": record["evidence"]["local_path"],
                "content_sha256": record["content_sha256"],
                "relation": "representative",
                "primary": True,
                "quality_components": {
                    key: 0.8 for key in (
                        "authority", "directness", "traceability", "temporal_fit",
                        "capture_completeness", "independence",
                    )
                },
                "assessment_confidence": 0.9,
                "rationale": "The captured source is complete and directly relevant to the bounded topic.",
            }],
            "representative_local_paths": [record["evidence"]["local_path"]],
            "confidence_components": {
                key: 0.8 for key in (
                    "source_quality", "corroboration", "independence", "temporal_coherence", "scope_match",
                )
            },
            "confidence_rationale": "The saved source provides scoped, auditable support.",
            "unresolved": [],
        } for index, record in enumerate(records)], state.data["frames"][frame_id]["collection"]["source_manifest_sha256"])
        result = state.add_evidence(frame_id, proposals, "source_triager")
        state.add_evidence(frame_id, [], "source_adversary")
        return result

    def test_provider_policy_has_no_semantic_route(self):
        project.init("Investigate DeepMind")
        result = providers.eligible()
        self.assertTrue(result["selected"])
        self.assertNotIn("intent", result)
        self.assertIn("arxiv", [item["provider"] for item in result["selected"]])
        self.assertEqual(result["max_parallel"], 3)
        self.assertFalse(json.loads((self.tmp / "research_project.json").read_text())["delivery"]["pdf"]["enabled"])

    def test_enabled_provider_without_an_adapter_is_explicitly_skipped(self):
        config = providers.init()
        config["providers"]["ddg"]["enabled"] = True
        (self.tmp / providers.CONFIG_NAME).write_text(json.dumps(config), encoding="utf-8")
        result = providers.eligible()
        self.assertNotIn("ddg", [item["provider"] for item in result["selected"]])
        ddg = next(item for item in result["skipped"] if item["provider"] == "ddg")
        self.assertIn("adapter_unavailable", ddg["reasons"])

    def test_frozen_snapshot_is_required_for_qa(self):
        project.init("Investigate DeepMind")
        state = engine.ResearchState.create("Investigate DeepMind", [], "2026-07-29T00:00:00+00:00")
        state.analyze_intent(self.ready_intent_contract())
        state.save()
        frame_id, _ = state.add_frame({"focus": "history", "information_gap": "facts", "discriminator": "primary source",
                                       "expected_update": "timeline", "evidence_requirement": "dated source"})
        state.formulate(frame_id, [{"query": "DeepMind"}])
        page = self.tmp / "research_drift" / "pages" / "source.md"; page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("DeepMind published research in 2024.", encoding="utf-8")
        (page.parent / "unaccepted.md").write_text("This page must never enter the frozen corpus.", encoding="utf-8")
        self.review_evidence(state, frame_id, [{"local_path": "research_drift/pages/source.md", "published_at": "2024-01-01"}])
        evidence_id = state.data["frames"][frame_id]["evidence_ids"][0]
        state.extract(frame_id, [{"claim": "Research was published in 2024", "context_signature": "publication date",
                                  "evidence_time": "2024-01-01",
                                  "source_spans": [{"evidence_id": evidence_id, "locator": "p:1"}]}], [])
        state.finish(frame_id, "resolved", "timeline established", 0.8)
        state.save()
        with self.assertRaises(FileNotFoundError):
            qa.ask("missing", "When was research published?", 3)
        manifest = project.freeze("qa-unit")
        snapshot_root = self.tmp / "research_snapshots" / manifest["snapshot_id"]
        self.assertTrue((snapshot_root / "pages" / "source.md").is_file())
        self.assertFalse((snapshot_root / "pages" / "unaccepted.md").exists())
        frozen_chunks = (snapshot_root / "corpus" / "chunks.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("must never enter", frozen_chunks)
        page.write_text("The mutable workspace page has changed.", encoding="utf-8")
        self.assertTrue(project.audit_evidence(manifest["snapshot_id"])["ok"])
        self.assertFalse(project.audit_evidence()["ok"])
        answer = qa.ask(manifest["snapshot_id"], "When was research published?", 3)
        self.assertEqual(answer["status"], "retrieved")
        self.assertTrue(answer["evidence_packets"])
        self.assertTrue(answer["evidence_packets"][0]["source_path"].startswith("research_snapshots/qa-unit/pages/"))
        self.assertTrue(corpus.search_files(self.tmp / "research_corpus" / "chunks.jsonl", self.tmp / "research_corpus" / "inverted_index.json", "DeepMind", 1))

    def test_qa_rejects_a_tampered_frozen_corpus(self):
        project.init("Investigate DeepMind")
        state = engine.ResearchState.create("Investigate DeepMind", [], "2026-07-29T00:00:00+00:00")
        state.analyze_intent(self.ready_intent_contract())
        state.save()
        frame_id, _ = state.add_frame({"focus": "history", "information_gap": "facts", "discriminator": "primary source",
                                       "expected_update": "timeline", "evidence_requirement": "dated source"})
        state.formulate(frame_id, [{"query": "DeepMind"}])
        page = self.tmp / "research_drift" / "pages" / "source.md"; page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("DeepMind published research in 2024.", encoding="utf-8")
        evidence_id = self.review_evidence(state, frame_id, [{
            "local_path": "research_drift/pages/source.md", "published_at": "2024-01-01"}])["evidence_ids"][0]
        state.extract(frame_id, [{"claim": "Research was published in 2024", "context_signature": "publication date",
                                  "evidence_time": "2024-01-01",
                                  "source_spans": [{"evidence_id": evidence_id, "locator": "p:1"}]}], [])
        state.finish(frame_id, "resolved", "timeline established", 0.8)
        state.save()
        project.freeze("tamper-unit")
        snapshot_root = self.tmp / "research_snapshots" / "tamper-unit"
        state_path = snapshot_root / "research_state.json"
        original_state = state_path.read_text(encoding="utf-8")
        altered_state = json.loads(original_state)
        altered_state["reference_time"] = "2030-01-01T00:00:00+00:00"
        state_path.write_text(json.dumps(altered_state), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "integrity check failed"):
            qa.ask("tamper-unit", "DeepMind", 1)
        state_path.write_text(original_state, encoding="utf-8")
        frozen_page = snapshot_root / "pages" / "source.md"
        frozen_page.write_text("tampered evidence", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "integrity check failed"):
            qa.ask("tamper-unit", "DeepMind", 1)
        frozen_page.write_text(page.read_text(encoding="utf-8"), encoding="utf-8")
        chunks = self.tmp / "research_snapshots" / "tamper-unit" / "corpus" / "chunks.jsonl"
        chunks.write_text('{"text":"tampered"}\n', encoding="utf-8")
        self.assertFalse(project.audit_evidence("tamper-unit")["ok"])
        with self.assertRaisesRegex(ValueError, "integrity check failed"):
            qa.ask("tamper-unit", "DeepMind", 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
